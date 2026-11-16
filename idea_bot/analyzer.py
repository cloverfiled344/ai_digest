"""Claude отбирает лучшие идеи из потока сигналов и разбирает каждую."""

from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlsplit

import anthropic

from . import config as cfg
from .sources import Item
from .state import State

log = logging.getLogger(__name__)

# цены за 1M токенов (вход, выход) — только чтобы писать стоимость запуска в лог
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-fable-5-2": (8.0, 40.0),
}

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Короткое название идеи или продукта (до 60 символов)"},
        "status": {
            "type": "string",
            "enum": ["exploded", "rising"],
            "description": "exploded — уже выстрелило (явная массовая тяга); rising — ранние сигналы роста",
        },
        "category": {"type": "string", "description": "Например: AI-агенты, Автоматизация, Dev tools, No-code, SaaS"},
        "what": {"type": "string", "description": "Что это, 1–2 предложения"},
        "signal": {"type": "string", "description": "Почему это выстрелило/выстрелит — только факты и цифры из данных"},
        "opportunity": {"type": "string", "description": "Что конкретно построить читателю: для кого, какая боль, угол атаки, адаптация под СНГ/ЦА"},
        "monetization": {"type": "string", "description": "Как на этом зарабатывать, 1 предложение"},
        "difficulty": {"type": "integer", "description": "Сложность повторить: 1 (выходные на no-code) … 5 (нужна команда и R&D)"},
        "mvp_time": {"type": "string", "description": "Оценка срока до MVP, например «2 недели»"},
        "source_ids": {"type": "array", "items": {"type": "integer"}, "description": "Номера сигналов [N], на которых основана идея"},
    },
    "required": ["title", "status", "category", "what", "signal", "opportunity",
                 "monetization", "difficulty", "mvp_time", "source_ids"],
    "additionalProperties": False,
}

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_of_day": {"type": "string", "description": "Главный тренд дня по всем сигналам, 2–3 предложения"},
        "ideas": {"type": "array", "items": IDEA_SCHEMA},
    },
    "required": ["trend_of_day", "ideas"],
    "additionalProperties": False,
}

SYSTEM = f"""Ты — венчурный аналитик и опытный инди-хакер. Каждое утро ты просматриваешь поток сигналов \
(Hacker News, GitHub, Product Hunt, Hugging Face, Reddit, новости о стартапах) и находишь идеи в сфере ИИ, IT \
и автоматизации, которые уже выстрелили или вот-вот выстрелят. Твоя ценность — не пересказ новостей, а \
ответ на вопрос «что из этого я могу построить и продать».

Правила отбора:
- Выбери до {cfg.IDEAS_PER_DIGEST} лучших идей. Лучше меньше, но сильных.
- Держи баланс: часть идей со статусом exploded (явная тяга: тысячи звёзд за дни, топ HN, крупный раунд), \
часть rising (ранние сигналы, ниша только разгоняется).
- Идея — это конкретный продукт или ниша, а не общая новость. Если в новостях раунд инвестиций, идея — это \
продукт и ниша, которую раунд подтверждает.
- Можно объединить несколько сигналов про один тренд в одну идею и указать все их номера.
- Остерегайся накрутки: одинаковые репозитории от разных аккаунтов, звёзды без описания и смысла, \
«конфиги» и «чекеры» для обхода блокировок — это не идеи.
- Пропускай: NSFW и «uncensored»-модели, крипто-пампы, чисто научные статьи без продукта, политику, \
идеи, которым нужны миллионы на старте, и повторы уже присланных идей.

Правила текста:
- signal — только факты из данных: цифры, площадки, сроки. Не выдумывай выручку, пользователей или \
инвестиции, которых нет в сигналах.
- opportunity — конкретный угол атаки для соло-разработчика или маленькой команды: для кого, какую боль \
решает, чем отличиться от оригинала, можно ли адаптировать под СНГ и Центральную Азию. Не «сделайте аналог».
- Пиши по-русски, ёмко и без воды. Названия продуктов и термины оставляй как есть."""


def _format_items(items: list[Item]) -> str:
    lines = []
    for i, it in enumerate(items):
        host = urlsplit(it.url).netloc.removeprefix("www.")
        line = f"[{i}] {it.source} | {it.title} | {host} | {it.metric}"
        if it.description:
            line += f" | {it.description}"
        lines.append(line)
    return "\n".join(lines)


def _build_prompt(items: list[Item], state: State) -> str:
    parts = [f"Сегодня {date.today().isoformat()}.", f"Профиль читателя:\n{cfg.USER_PROFILE}"]
    if state.feedback:
        wishes = "\n".join(f"- {f['text']}" for f in state.feedback)
        parts.append(f"Пожелания читателя (он написал их боту, обязательно учитывай):\n{wishes}")
    if state.recent_ideas:
        recent = "\n".join(f"- {r['title']}" for r in state.recent_ideas[-30:])
        parts.append(f"Уже присланные идеи (не повторяй их и близкие к ним):\n{recent}")
    parts.append(f"Сигналы ({len(items)} шт.):\n{_format_items(items)}")
    return "\n\n".join(parts)


def analyze(items: list[Item], state: State) -> dict:
    """Возвращает {'trend_of_day': str, 'ideas': [...]}; у каждой идеи есть 'sources': [Item]."""
    client = anthropic.Anthropic()
    prompt = _build_prompt(items, state)

    response = client.messages.create(
        model=cfg.CLAUDE_MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": DIGEST_SCHEMA}},
    )

    usage = response.usage
    price_in, price_out = PRICES.get(cfg.CLAUDE_MODEL, (0, 0))
    cost = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
    log.info("Claude %s: %d токенов на вход, %d на выход, ≈ $%.3f",
             cfg.CLAUDE_MODEL, usage.input_tokens, usage.output_tokens, cost)

    if response.stop_reason not in ("end_turn", "stop_sequence"):
        raise RuntimeError(f"Claude не закончил ответ (stop_reason={response.stop_reason})")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    ideas = []
    for idea in data.get("ideas", [])[: cfg.IDEAS_PER_DIGEST]:
        ids = [i for i in idea.get("source_ids", []) if isinstance(i, int) and 0 <= i < len(items)]
        if not ids:
            continue  # идея без опоры на реальные сигналы — отбрасываем
        idea["sources"] = [items[i] for i in dict.fromkeys(ids)]
        idea["difficulty"] = min(5, max(1, int(idea.get("difficulty") or 3)))
        ideas.append(idea)

    if not ideas:
        raise RuntimeError("Claude не вернул ни одной идеи")
    return {"trend_of_day": data.get("trend_of_day", ""), "ideas": ideas}
