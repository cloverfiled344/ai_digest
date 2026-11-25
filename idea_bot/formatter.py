"""Превращает дайджест в сообщения Telegram (HTML, ≤ 4096 символов каждое)."""

from __future__ import annotations

import re
from datetime import date
from html import escape
from urllib.parse import urlsplit

from . import config as cfg
from .sources import Item

TG_LIMIT = 4000  # с запасом от лимита Telegram в 4096

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]

STATUS = {"exploded": "🔥 Уже выстрелило", "rising": "🌱 Набирает обороты", "gap": "🪟 Окно возможностей"}
WHY_LABEL = {"exploded": "Почему залетело", "rising": "Почему может залететь", "gap": "Почему сработает здесь"}
IT_LEVEL = {"it": "🟦 <b>IT</b>", "near_it": "🟨 <b>ОКОЛО-IT</b>", "non_it": "⬜ НЕ IT"}
SEGMENT_TITLES = {code: title for code, title, _ in cfg.SEGMENTS}

SOURCE_LABELS = {
    "news.ycombinator.com": "HN", "github.com": "GitHub", "producthunt.com": "Product Hunt",
    "huggingface.co": "Hugging Face", "reddit.com": "Reddit", "techcrunch.com": "TechCrunch",
    "habr.com": "Хабр", "digitalbusiness.kz": "Digital Business", "kz.kursiv.media": "Курсив",
    "spot.uz": "Spot", "gazeta.uz": "Gazeta.uz", "kun.uz": "Kun.uz", "tazabek.kg": "Tazabek",
    "economist.kg": "Economist.kg", "kaktus.media": "Kaktus",
}


def _e(text: str) -> str:
    return escape(str(text or ""), quote=False)


def _today() -> str:
    d = date.today()
    return f"{d.day} {MONTHS[d.month - 1]}"


def _label(url: str) -> str:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return SOURCE_LABELS.get(host, host or "ссылка")


def _short_title(it: Item) -> str:
    """Подпись ссылки: имя репозитория/продукта, а не просто «GitHub»."""
    title = re.sub(r"^(Show|Launch|Ask) HN:\s*", "", it.title).strip()
    if "/" in title and " " not in title:          # owner/repo, org/model
        title = title.split("/", 1)[1]
    title = re.split(r"\s[–—-]\s|:\s", title, maxsplit=1)[0]
    return title if len(title) <= 28 else title[:27].rstrip() + "…"


def _links(sources: list[Item]) -> str:
    links, seen = [], set()
    for it in sources:
        pairs = [(it.url, f"{_short_title(it)} ({_label(it.url)})")]
        if it.discussion_url and it.discussion_url != it.url:
            pairs.append((it.discussion_url, "обсуждение на HN"))
        for url, label in pairs:
            if url and url not in seen:
                seen.add(url)
                links.append(f'<a href="{escape(url, quote=True)}">{_e(label)}</a>')
    return " · ".join(links[:4])


def _footer(status: dict[str, int | None]) -> str:
    parts = [f"{name} {'✗' if n is None else n}" for name, n in status.items()]
    return ("<i>Сигналов: " + " · ".join(parts) + "</i>\n"
            "<i>Напиши боту, что тебе интересно (например «больше про n8n, меньше dev tools») — "
            "учту в следующем дайджесте. /wishes — список пожеланий, /reset — сбросить.</i>")


def _pack(blocks: list[str]) -> list[str]:
    """Склеивает блоки в сообщения, не разрывая блок посередине."""
    messages, current = [], ""
    for block in blocks:
        if len(block) > TG_LIMIT:
            block = block[: TG_LIMIT - 1] + "…"
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > TG_LIMIT:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def format_digest(digest: dict, status: dict[str, int | None]) -> list[str]:
    blocks = [f"💡 <b>Идеи дня · {_today()}</b>"]
    counts = {k: sum(1 for i in digest["ideas"] if i.get("it_level") == k) for k in IT_LEVEL}
    blocks[0] += "\n" + " · ".join(f"{IT_LEVEL[k]} {n}" for k, n in counts.items() if n)
    if qa_n := len(digest.get("reddit_qa") or []):
        blocks[0] += f" · ❓ вопросов с Reddit: {qa_n}"
    if digest.get("trend_of_day"):
        blocks[0] += f"\n\n<b>Тренд дня.</b> {_e(digest['trend_of_day'])}"

    current_segment = None
    for n, idea in enumerate(digest["ideas"], 1):
        d = idea["difficulty"]
        kind = idea.get("status", "")
        lines = []
        if idea.get("segment") != current_segment:
            current_segment = idea.get("segment")
            lines += [f"<b>{_e(SEGMENT_TITLES.get(current_segment, ''))}</b>", ""]
        lines += [
            f"{IT_LEVEL.get(idea.get('it_level'), '💡')} │ <b>{n}. {_e(idea['title'])}</b>",
            f"{STATUS.get(kind, '💡')} · <i>{_e(idea['category'])}</i>",
            "",
            f"<b>Что это:</b> {_e(idea['what'])}",
            f"<b>{WHY_LABEL.get(kind, 'Почему это важно')}:</b> {_e(idea.get('why', ''))}",
            f"<b>Цифры:</b> {_e(idea['signal'])}",
            f"<b>Что построить:</b> {_e(idea['opportunity'])}",
            f"<b>Деньги:</b> {_e(idea['monetization'])}",
            f"<b>Сложность:</b> {'●' * d}{'○' * (5 - d)} · <b>MVP:</b> {_e(idea['mvp_time'])}",
        ]
        if links := _links(idea["sources"]):
            lines.append(f"🔗 {links}")
        blocks.append("\n".join(lines))

    blocks += _qa_blocks(digest.get("reddit_qa") or [], start=len(digest["ideas"]) + 1)
    blocks.append(_footer(status))
    return _pack(blocks)


def _qa_blocks(qa: list[dict], start: int) -> list[str]:
    """Рубрика «Вопросы и решения с Reddit»."""
    blocks = []
    for n, item in enumerate(qa, start):
        q = item["source"]
        lines = [f"<b>❓ ВОПРОСЫ И РЕШЕНИЯ · REDDIT</b>", ""] if n == start else []
        lines += [
            f"<b>{n}. {_e(item['question'])}</b>",
            f"<i>r/{_e(q.sub)} · {q.num_comments} комментариев</i>",
            "",
            f"<b>Ситуация:</b> {_e(item['context'])}",
            f"<b>Как решить:</b> {_e(item['answer'])}",
        ]
        if item.get("community", "").strip():
            lines.append(f"<b>Что советуют на Reddit:</b> {_e(item['community'])}")
        lines += [
            f"<b>💡 Идея</b> ({IT_LEVEL.get(item.get('it_level'), '💡')}): {_e(item['idea'])}",
            f'🔗 <a href="{escape(q.url, quote=True)}">вопрос на Reddit</a>',
        ]
        blocks.append("\n".join(lines))
    return blocks


def format_fallback(items: list[Item], status: dict[str, int | None], reason: str, per_source: int = 3) -> list[str]:
    """Дайджест без ИИ: лучшие сигналы каждого источника."""
    blocks = [f"📡 <b>Сигналы дня · {_today()}</b>\n<i>{_e(reason)}</i>"]
    by_source: dict[str, list[Item]] = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it)
    for source, group in by_source.items():
        group.sort(key=lambda x: x.score, reverse=True)
        lines = [f"<b>{_e(source)}</b>"]
        for it in group[:per_source]:
            lines.append(f'• <a href="{escape(it.url, quote=True)}">{_e(it.title)}</a> — {_e(it.metric)}')
        blocks.append("\n".join(lines))
    blocks.append(_footer(status))
    return _pack(blocks)
