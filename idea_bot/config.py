"""Настройки бота. Всё, что можно менять без программирования, — здесь."""

import os

# ── Кто ты. Claude подбирает идеи под этот профиль — перепиши под себя. ──────────
USER_PROFILE = """
Разработчик и предприниматель из Центральной Азии (Кыргызстан).
Интересуют идеи в ИИ, IT и автоматизации, которые можно запустить соло или маленькой
командой: SaaS, AI-агенты, Telegram-боты, автоматизации на n8n/Make, dev-инструменты,
сервисы для малого и среднего бизнеса. Важны реальный спрос, понятная монетизация и
быстрый MVP. Плюс, если идею можно адаптировать под рынок СНГ и Центральной Азии.
""".strip()

# ── Дайджест ──────────────────────────────────────────────────────────────────
IDEAS_PER_DIGEST = 6
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL") or "claude-sonnet-5-5"
MAX_ITEMS_TO_ANALYZE = 180  # сколько сигналов максимум отдаём Claude за раз

# ── Источники ─────────────────────────────────────────────────────────────────
HN_SHOW_MIN_POINTS = 40       # Show HN за 3 дня с таким рейтингом и выше
HN_STORY_MIN_POINTS = 150     # обычные посты HN за сутки

GITHUB_LOOKBACK_DAYS = 14     # репозитории, созданные за последние N дней
GITHUB_MIN_STARS = 150
GITHUB_QUERIES = [            # пустая строка = все новые репозитории подряд
    "",
    "topic:ai-agents",
    "topic:llm",
    "topic:automation",
    "topic:mcp",
]

HF_SPACES_LIMIT = 30
HF_MODELS_LIMIT = 15

REDDIT_SUBS = [
    "SaaS", "SideProject", "Entrepreneur", "startups", "indiehackers",
    "n8n", "automation", "AI_Agents", "LocalLLaMA",
]
REDDIT_PER_SUB = 6
REDDIT_MIN_SCORE = 20

NEWS_FEEDS = {
    "TechCrunch · AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "TechCrunch · Startups": "https://techcrunch.com/category/startups/feed/",
}
NEWS_MAX_AGE_HOURS = 48

PRODUCTHUNT_LIMIT = 30

# Слова, по которым отсекаем мусор ещё до Claude
BLOCKLIST = ["nsfw", "uncensored", "nude", "porn", "hentai", "onlyfans", "casino", "betting"]

# ── Память бота ───────────────────────────────────────────────────────────────
STATE_PATH = os.getenv("STATE_PATH") or "state/state.json"
REMEMBER_SENT_DAYS = 90       # не присылать одну и ту же ссылку повторно столько дней
MAX_FEEDBACK = 15             # сколько последних пожеланий из чата помнить
