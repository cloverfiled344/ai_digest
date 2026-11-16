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

SEGMENT_CODES = [code for code, _, _ in cfg.SEGMENTS]
_SEGMENT_NAMES = {"world": "Мир", "cis": "СНГ", "central_asia": "Центральная Азия"}
_SEGMENT_PLAN = ", ".join(f"{_SEGMENT_NAMES.get(code, code)} — {n}" for code, _, n in cfg.SEGMENTS)

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "segment": {
            "type": "string",
            "enum": SEGMENT_CODES,
            "description": "Раздел: world — мир, cis — СНГ, central_asia — Центральная Азия",
        },
        "title": {"type": "string", "description": "Короткое название идеи или продукта (до 60 символов)"},
        "status": {
            "type": "string",
            "enum": ["exploded", "rising", "gap"],
            "description": "exploded — уже выстрелило; rising — ранние сигналы роста; "
                           "gap — в мире работает, а в этом регионе ниша, судя по данным, пустая",
        },
        "category": {"type": "string", "description": "Например: AI-агенты, Автоматизация, Финтех, E-commerce, SaaS"},
        "what": {"type": "string", "description": "Что это, 1–2 коротких предложения"},
        "why": {
            "type": "string",
            "description": "Почему залетело или залетит: какую боль закрывает, почему именно сейчас "
                           "(технология подешевела, сменилось поведение, регуляция), как распространялось. Максимум 2 предложения",
        },
        "signal": {"type": "string", "description": "2–3 самых сильных факта из сигналов: звёзды, очки, раунды, сроки. Ничего не выдумывать"},
        "opportunity": {"type": "string", "description": "Что конкретно построить читателю: для кого, угол атаки, чем отличиться. Максимум 2 предложения"},
        "monetization": {"type": "string", "description": "Как на этом зарабатывать, 1 предложение"},
        "difficulty": {"type": "integer", "description": "Сложность повторить: 1 (выходные на no-code) … 5 (нужна команда и R&D)"},
        "mvp_time": {"type": "string", "description": "Оценка срока до MVP, например «2 недели»"},
        "source_ids": {"type": "array", "items": {"type": "integer"}, "description": "Номера сигналов [N], на которых основана идея"},
    },
    "required": ["segment", "title", "status", "category", "what", "why", "signal", "opportunity",
                 "monetization", "difficulty", "mvp_time", "source_ids"],
    "additionalProperties": False,
}

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_of_day": {"type": "string", "description": "Главный тренд дня по всем сигналам, 2 предложения"},
        "ideas": {"type": "array", "items": IDEA_SCHEMA},
    },
    "required": ["trend_of_day", "ideas"],
    "additionalProperties": False,
}

SYSTEM = f"""Ты — венчурный аналитик и опытный инди-хакер, который хорошо знает и мировой рынок, и рынки СНГ \
и Центральной Азии. Каждое утро ты просматриваешь поток сигналов и находишь идеи в сфере ИИ, IT и \
автоматизации, которые уже выстрелили или вот-вот выстрелят. Твоя ценность — не пересказ новостей, а \
ответ на вопросы «почему это залетело» и «что из этого я могу построить и продать».

Сигналы помечены регионом: [Мир] — Hacker News, GitHub, Product Hunt, Hugging Face, Reddit, TechCrunch; \
[СНГ] — русскоязычные медиа (vc.ru, Хабр, RB.ru); [ЦА] — медиа Казахстана, Узбекистана и Кыргызстана.

Разделы дайджеста ({_SEGMENT_PLAN} идей):
- world (Мир): что выстрелило или разгоняется в мире. Опирайся на сигналы [Мир]. В opportunity объясни, \
как перенести идею в СНГ или Центральную Азию.
- cis (СНГ): что растёт на рынке России и СНГ. Опирайся прежде всего на сигналы [СНГ].
- central_asia (Центральная Азия): что растёт в Казахстане, Узбекистане, Кыргызстане, Таджикистане. \
Опирайся прежде всего на сигналы [ЦА].
- Если региональных сигналов мало, в cis или central_asia можно поставить идею со статусом gap: мировой \
тренд, у которого в данных нет местного аналога. Тогда прямо напиши, что отсутствие конкурентов — \
гипотеза, которую надо проверить, и укажи номера и мирового сигнала, и местного, если он есть.
- Если в разделе нечего показать, лучше меньше идей, чем слабые. Идеи в разных разделах не повторяются.

Правила отбора:
- Идея — это конкретный продукт или ниша, а не общая новость. Если в новостях раунд инвестиций или \
запуск, идея — это продукт и ниша, которую он подтверждает.
- Можно объединить несколько сигналов про один тренд в одну идею и указать все их номера.
- Остерегайся накрутки: одинаковые репозитории от разных аккаунтов, звёзды без описания и смысла, \
«конфиги» и «чекеры» для обхода блокировок — это не идеи.
- Пропускай: NSFW и «uncensored»-модели, крипто-пампы, чисто научные статьи без продукта, политику, \
госпропаганду, идеи, которым нужны миллионы на старте, и повторы уже присланных идей.

Правила текста:
- why — причины, а не цифры: какую боль закрывает, почему именно сейчас, за счёт чего распространилось. \
Для регионов учитывай местную специфику (языки, местные платёжные системы и маркетплейсы, Telegram как \
главный канал, роль госуслуг), но не выдумывай фактов о рынке.
- signal — только факты из данных: цифры, площадки, сроки. Не выдумывай выручку, пользователей или \
инвестиции, которых нет в сигналах.
- opportunity — конкретный угол атаки для соло-разработчика или маленькой команды: для кого, какую боль \
решает, чем отличиться от оригинала. Не «сделайте аналог».
- Краткость: what, why, opportunity — максимум 2 коротких предложения каждое; signal — 2–3 самых сильных факта, без пересказа новостей; monetization — одно предложение. Вся идея — не длиннее ~800 символов. Номера сигналов в квадратных скобках в текст не вставляй.
- Пиши по-русски, ёмко и без воды. Названия продуктов и термины оставляй как есть."""

_REGION_TAG = {"world": "Мир", "cis": "СНГ", "central_asia": "ЦА"}


def _format_items(items: list[Item]) -> str:
    lines = []
    for i, it in enumerate(items):
        host = urlsplit(it.url).netloc.removeprefix("www.")
        line = f"[{i}] [{_REGION_TAG.get(it.region, 'Мир')}] {it.source} | {it.title} | {host} | {it.metric}"
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
        max_tokens=12000,
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

    limits = {code: n for code, _, n in cfg.SEGMENTS}
    taken = dict.fromkeys(limits, 0)
    ideas = []
    for idea in data.get("ideas", []):
        seg = idea.get("segment")
        if seg not in limits or taken[seg] >= limits[seg]:
            continue
        ids = [i for i in idea.get("source_ids", []) if isinstance(i, int) and 0 <= i < len(items)]
        if not ids:
            continue  # идея без опоры на реальные сигналы — отбрасываем
        idea["sources"] = [items[i] for i in dict.fromkeys(ids)]
        idea["difficulty"] = min(5, max(1, int(idea.get("difficulty") or 3)))
        ideas.append(idea)
        taken[seg] += 1
    order = list(limits)
    ideas.sort(key=lambda x: order.index(x["segment"]))  # Мир → СНГ → ЦА

    if not ideas:
        raise RuntimeError("Claude не вернул ни одной идеи")
    return {"trend_of_day": data.get("trend_of_day", ""), "ideas": ideas}
