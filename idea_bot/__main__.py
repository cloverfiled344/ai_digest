"""Точка входа.

    python -m idea_bot                 # собрать сигналы, разобрать через Claude, отправить в Telegram
    python -m idea_bot --dry-run       # то же, но вывести в консоль и ничего не сохранять
    python -m idea_bot --no-llm        # без Claude: просто лучшие сигналы по источникам
    python -m idea_bot --sync-feedback # только забрать пожелания, которые ты написал боту
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from . import config as cfg
from .formatter import format_digest, format_fallback
from .sources import collect_all, fetch_reddit_questions
from .state import State
from .telegram import Telegram, sync_feedback

log = logging.getLogger("idea_bot")


def main() -> int:
    ap = argparse.ArgumentParser(prog="idea_bot")
    ap.add_argument("--dry-run", action="store_true", help="вывести дайджест в консоль, не отправлять")
    ap.add_argument("--no-llm", action="store_true", help="не вызывать Claude")
    ap.add_argument("--sync-feedback", action="store_true", help="только забрать пожелания из чата")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    state = State.load()

    # чат: секрет TELEGRAM_CHAT_ID → запомненный чат → первый, кто напишет боту
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if token:
        bot_id = token.split(":", 1)[0]
        if state.tg_bot_id != bot_id:
            # сменили бота: позиция в чате у нового бота своя
            state.tg_bot_id, state.tg_offset = bot_id, 0
    tg = Telegram(token, os.getenv("TELEGRAM_CHAT_ID") or state.chat_id) if token else None
    if not tg and not args.dry_run:
        log.error("Нет токена бота: добавь секрет IDEA_BOT_TELEGRAM_TOKEN в Settings → Secrets and variables → Actions "
                  "(или запусти с --dry-run)")
        return 1

    # 1. пожелания из чата — до анализа, чтобы учесть их уже сегодня
    if tg and not args.dry_run:
        try:
            n = sync_feedback(tg, state)
            log.info("Новых пожеланий из чата: %d", n)
        except Exception as e:
            log.warning("Не удалось прочитать сообщения боту: %s", e)
        if not tg.chat_id:
            log.error("Не знаю, куда слать: напиши боту /start в Telegram и запусти ещё раз")
            state.save()
            return 1
    if args.sync_feedback:
        state.save()
        return 0

    # 2. сбор сигналов; вопросы с Reddit собираем параллельно
    with ThreadPoolExecutor(max_workers=1) as pool:
        qa_future = pool.submit(fetch_reddit_questions, skip=state.was_sent)
        items, status = collect_all()
        try:
            questions = qa_future.result()
            log.info("Вопросы Reddit → %d кандидатов, с ответами: %d",
                     len(questions), sum(1 for q in questions if q.answers))
        except Exception as e:
            log.warning("Вопросы Reddit → ошибка: %s", str(e)[:160])
            questions = None
    if cfg.REDDIT_QA_COUNT > 0:
        status["Вопросы Reddit"] = None if questions is None else len(questions)
    fresh = [it for it in items if not state.was_sent(it.url)]
    log.info("Всего сигналов: %d, новых: %d", len(items), len(fresh))
    if not fresh:
        log.error("Ни один источник не дал новых сигналов")
        return 1

    # равномерно режем по источникам, чтобы один GitHub не съел весь лимит
    fresh = _balance(fresh, cfg.MAX_ITEMS_TO_ANALYZE)

    # 3. анализ
    digest, reason = None, ""
    if args.no_llm:
        reason = "Режим без ИИ: лучшие сигналы по источникам."
    elif not os.getenv("ANTHROPIC_API_KEY"):
        reason = "Нет ANTHROPIC_API_KEY — присылаю сигналы без разбора."
    else:
        try:
            from .analyzer import analyze
            digest = analyze(fresh, state, questions)
        except Exception as e:
            log.exception("Claude не справился")
            reason = f"Claude недоступен ({type(e).__name__}), поэтому сегодня — сигналы без разбора."

    messages = format_digest(digest, status) if digest else format_fallback(fresh, status, reason)

    # 4. отправка
    if args.dry_run:
        for m in messages:
            print("─" * 60)
            print(re.sub(r"<[^>]+>", "", m))
        print("─" * 60)
        print(f"[dry-run] {len(messages)} сообщ., {sum(map(len, messages))} символов. Ничего не отправлено.")
        return 0

    tg.send_all(messages)
    log.info("Отправлено сообщений: %d", len(messages))

    # 5. память: что отправили — больше не предлагаем
    if digest:
        urls = [s.url for idea in digest["ideas"] for s in idea["sources"]]
        urls += [q["source"].url for q in digest.get("reddit_qa", [])]
        state.mark_sent(urls, [idea["title"] for idea in digest["ideas"]])
    state.save()
    return 0


def _balance(items, limit):
    by_source: dict[str, list] = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it)
    for group in by_source.values():
        group.sort(key=lambda x: x.score, reverse=True)
    out, i = [], 0
    while len(out) < limit and any(i < len(g) for g in by_source.values()):
        for g in by_source.values():
            if i < len(g) and len(out) < limit:
                out.append(g[i])
        i += 1
    return out


if __name__ == "__main__":
    sys.exit(main())
