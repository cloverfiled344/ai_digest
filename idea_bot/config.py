"""Настройки бота. Всё, что можно менять без программирования, — здесь."""

import os

# ── Кто ты. Claude подбирает идеи под этот профиль — перепиши под себя. ──────────
USER_PROFILE = """
Разработчик и предприниматель из Центральной Азии (Кыргызстан).
Главное — идеи в ИИ, IT и автоматизации, которые можно запустить соло или маленькой
командой: SaaS, AI-агенты, Telegram-боты и Mini Apps, автоматизации на n8n/Make, dev-инструменты,
сервисы для малого и среднего бизнеса. Также интересны около-IT идеи (агентства и услуги
вокруг AI/автоматизации, цифровые продукты, контент, аутстафф) и сильные не-IT бизнесы,
где онлайн — главный канал продаж. Рынок — весь мир, а не только СНГ: важно, что можно
продавать клиентам из США, Европы, Азии удалённо. Важны реальный спрос, понятная
монетизация, быстрый MVP и шанс получить первых платящих клиентов за 1–2 месяца.
""".strip()

# ── Дайджест ──────────────────────────────────────────────────────────────────
# Разделы дайджеста: (код, заголовок, сколько идей)
SEGMENTS = [
    ("world", "🌍 МИР", 4),
    ("cis", "🧭 СНГ", 1),
    ("central_asia", "🏔 ЦЕНТРАЛЬНАЯ АЗИЯ", 2),
]
IDEAS_PER_DIGEST = sum(n for _, _, n in SEGMENTS)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL") or "claude-sonnet-5-5"
MAX_ITEMS_TO_ANALYZE = 240  # сколько сигналов максимум отдаём Claude за раз

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
    "smallbusiness", "EntrepreneurRideAlong", "sweatystartup",  # около-IT и не-IT бизнесы
]
REDDIT_PER_SUB = 6
REDDIT_MIN_SCORE = 20

NEWS_FEEDS = {
    "TechCrunch · AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "TechCrunch · Startups": "https://techcrunch.com/category/startups/feed/",
}
NEWS_MAX_AGE_HOURS = 48

PRODUCTHUNT_LIMIT = 30

# Региональные медиа: (название, RSS, регион, брать только IT/бизнес-новости)
# Регион: "cis" — СНГ, "central_asia" — Центральная Азия.
REGIONAL_FEEDS = [
    ("vc.ru", "https://vc.ru/rss/all", "cis", True),
    ("Хабр · ИИ", "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/?fl=ru", "cis", False),
    ("Хабр · стартапы", "https://habr.com/ru/rss/hubs/startuprise/articles/?fl=ru", "cis", False),
    ("RB.ru", "https://rb.ru/feeds/all/", "cis", True),
    ("Digital Business (KZ)", "https://digitalbusiness.kz/feed/", "central_asia", False),
    ("Profit.kz", "https://profit.kz/rss/", "central_asia", False),
    ("Курсив (KZ)", "https://kz.kursiv.media/feed/", "central_asia", True),
    ("Spot (UZ)", "https://www.spot.uz/ru/rss/", "central_asia", True),
    ("Gazeta.uz", "https://www.gazeta.uz/ru/rss/", "central_asia", True),
    ("Kun.uz", "https://kun.uz/ru/news/rss", "central_asia", True),
    ("24.kg", "https://24.kg/rss/", "central_asia", True),
    ("Tazabek (KG)", "https://www.tazabek.kg/rss/", "central_asia", True),
    ("Economist.kg", "https://economist.kg/feed/", "central_asia", True),
    ("Kaktus.media", "https://kaktus.media/?rss", "central_asia", True),
]
REGIONAL_MAX_AGE_HOURS = 72   # в регионах IT-новостей меньше — смотрим за 3 дня
REGIONAL_PER_FEED = 15

# Слова, по которым отсекаем мусор ещё до Claude
BLOCKLIST = ["nsfw", "uncensored", "nude", "porn", "hentai", "onlyfans", "casino", "betting"]

# ── Память бота ───────────────────────────────────────────────────────────────
STATE_PATH = os.getenv("STATE_PATH") or "state/state.json"
REMEMBER_SENT_DAYS = 90       # не присылать одну и ту же ссылку повторно столько дней
MAX_FEEDBACK = 15             # сколько последних пожеланий из чата помнить
