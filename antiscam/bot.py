#!/usr/bin/env python3
"""Бот-разборщик новостей о мошенничестве для Telegram-канала.

Каждый запуск (по расписанию GitHub Actions, до 10 раз в день) бот:
  1) собирает свежие новости о мошенничестве из RSS (СНГ, США, мир);
  2) выбирает рубрику по плану дня (по умолчанию 5 × СНГ, 3 × мир, 2 × США);
  3) с помощью ИИ отбирает лучшую историю этой рубрики и пишет разбор,
     в начале — жирным, где это произошло;
  4) публикует пост в канал и запоминает его, чтобы не повторяться.

Запуск:
  python bot.py                 — опубликовать следующий пост дня
  python bot.py --find-chat     — показать chat_id чатов, где есть бот
  python bot.py --test-message  — отправить тестовое сообщение в канал

Переменные окружения:
  TELEGRAM_BOT_TOKEN  токен бота от @BotFather
  TELEGRAM_CHAT_ID    @username канала или числовой id (-100...)
  ANTHROPIC_API_KEY   ключ Claude API (или GEMINI_API_KEY — ключ Gemini API)
  CATEGORY            auto / CIS / USA / WORLD — принудительно выбрать рубрику (для тестов)
  DRY_RUN             1 — только показать пост в логах, ничего не отправлять
  BOT_CTA             строка-призыв в конце поста (например «🔍 Проверить ссылку: @mybot»)
  ADD_KYRGYZ          true — добавлять краткий пересказ на кыргызском
  STATE_PATH          где хранить память бота (по умолчанию state/posted.json рядом со скриптом)
"""

import base64
import calendar
import difflib
import html
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote_plus, urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
STATE_PATH = os.environ.get("STATE_PATH") or os.path.join(ROOT, "state", "posted.json")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Accept-Language": "ru,en;q=0.8",
})

CATEGORY_ORDER = ["CIS", "WORLD", "USA"]           # приоритет, если рубрика по плану пустая
CATEGORY_NAMES = {"CIS": "СНГ", "USA": "США", "WORLD": "мир", "TIP": "напоминание"}
PRIORITY_BOOST = {"KG": 3, "UZ": 1.5, "KZ": 1.5}
TELEGRAM_LIMIT = 4000  # у Telegram лимит 4096 символов, оставляем запас
FLAG_RE = re.compile(r"^[\U0001F1E6-\U0001F1FF]{2}$")
CONFIG = {}


# ───────────────────────── утилиты ─────────────────────────

def log(*args):
    print(*args, flush=True)


def env(name, default=""):
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def env_flag(name):
    return env(name).lower() in ("1", "true", "yes", "да")


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_utc():
    return datetime.now(timezone.utc)


def local_tz():
    return timezone(timedelta(hours=CONFIG.get("utc_offset_hours", 6)))


def local_now():
    return now_utc().astimezone(local_tz())


def clean_html(raw):
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title):
    t = title.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def similar(a, b):
    """Похожи ли два нормализованных заголовка (одна и та же история)."""
    if not a or not b:
        return False
    if difflib.SequenceMatcher(None, a, b).ratio() > 0.72:
        return True
    wa, wb = set(a.split()), set(b.split())
    if len(wa) < 4 or len(wb) < 4:
        return False
    return len(wa & wb) / len(wa | wb) > 0.6


def domain_of(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def esc(text):
    return html.escape(text or "", quote=False)


# ───────────────────────── «обезвреживание» ссылок ─────────────────────────

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")
_DOMAIN_RE = re.compile(
    r"(?i)\b(?:[a-z0-9-]+\.)+(?:com|net|org|info|site|online|top|xyz|shop|store|click|link|live|"
    r"app|io|me|cc|tk|pro|biz|ru|kz|uz|kg|su|icu|vip|club|space|website|tech|cfd|sbs)\b"
)


def defang(text, safe_domains=()):
    """Делает ссылки в тексте некликабельными: https://evil.site → hxxps://evil[.]site.

    Домены из safe_domains (СМИ, госорганы) не трогаем."""
    if not text:
        return text
    safe = {d.lower() for d in safe_domains}

    def is_safe(token):
        host = domain_of(token if "://" in token else "http://" + token).split("/")[0]
        return any(host == d or host.endswith("." + d) for d in safe)

    def fix_url(m):
        token = m.group(0)
        if is_safe(token):
            return token
        token = re.sub(r"(?i)^http", "hxxp", token)
        return token.replace(".", "[.]")

    text = _URL_RE.sub(fix_url, text)

    def fix_domain(m):
        token = m.group(0)
        if "[.]" in token or is_safe(token):
            return token
        return token.replace(".", "[.]")

    return _DOMAIN_RE.sub(fix_domain, text)


# ───────────────────────── состояние (что уже публиковали) ─────────────────────────

def load_state(path=None):
    try:
        with open(path or STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("posted", [])
    state.setdefault("evergreen_index", 0)
    return state


def save_state(state, path=None):
    path = path or STATE_PATH
    cutoff = (now_utc() - timedelta(days=30)).isoformat()
    state["posted"] = [p for p in state["posted"] if p.get("ts", "") >= cutoff][-3000:]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def mark_posted(state, items, category):
    """Первая запись — опубликованная история (считается в дневной лимит), остальные — её дубли."""
    ts, day = now_utc().isoformat(), local_now().date().isoformat()
    for i, it in enumerate(items):
        state["posted"].append({"url": it["link"], "title": it["title"], "ts": ts, "date": day,
                                "category": category, "counted": i == 0})


def today_stats(state):
    day = local_now().date().isoformat()
    return Counter(p.get("category") for p in state["posted"] if p.get("date") == day and p.get("counted"))


def already_posted(item, state):
    norm = normalize_title(item["title"])
    for p in state["posted"]:
        if p.get("url") == item["link"]:
            return True
        if similar(norm, normalize_title(p.get("title", ""))):
            return True
    return False


# ───────────────────────── план дня ─────────────────────────

def category_order(cfg, stats):
    """Какую рубрику публиковать сейчас (и запасные), исходя из плана и уже вышедших постов."""
    used = Counter({k: v for k, v in stats.items() if k in CATEGORY_NAMES and k != "TIP"})
    remaining = []
    for cat in cfg.get("plan", CATEGORY_ORDER):
        if used[cat] > 0:
            used[cat] -= 1
        else:
            remaining.append(cat)
    if not remaining:  # план выполнен, а лимит ещё нет — берём что найдётся
        return list(CATEGORY_ORDER)
    order = [remaining[0]]
    order += [c for c in CATEGORY_ORDER if c in remaining and c not in order]
    return order


# ───────────────────────── сбор новостей ─────────────────────────

def feed_url(src, cfg):
    kind = src.get("type", "rss")
    if kind == "google":
        q = f'{src["query"]} when:{cfg.get("google_when", "2d")}'
        params = src.get("google_params") or cfg.get("google_params", "hl=ru&gl=RU&ceid=RU:ru")
        return f"https://news.google.com/rss/search?q={quote_plus(q)}&{params}"
    if kind == "bing":
        params = src.get("bing_params", "setlang=ru")
        return f"https://www.bing.com/news/search?q={quote_plus(src['query'])}&format=rss&{params}"
    return src["url"]


def decode_bing_link(link):
    """Bing оборачивает ссылку: .../apiclick.aspx?...&url=<настоящий адрес>."""
    try:
        qs = parse_qs(urlparse(link).query)
        if "url" in qs:
            return qs["url"][0]
    except Exception:
        pass
    return link


def decode_google_link(link):
    """Пытается достать настоящий адрес из ссылки Google Новостей (работает для старого формата)."""
    try:
        if "news.google.com" not in link:
            return link
        token = urlparse(link).path.rstrip("/").split("/")[-1]
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        m = re.search(rb"https?://[\x21-\x7e]+", raw)
        if m:
            url = m.group(0).decode("ascii", "ignore")
            if "news.google.com" not in url and len(url) > 12:
                return url
    except Exception:
        pass
    return link


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def parse_feed(src, content):
    feed = feedparser.parse(content)
    kind = src.get("type", "rss")
    items = []
    for e in feed.entries:
        title = clean_html(e.get("title", ""))
        link = e.get("link", "")
        summary = clean_html(e.get("summary", "") or e.get("description", ""))
        source_name = src["name"]

        if kind == "google":
            src_info = e.get("source") or {}
            src_title = src_info.get("title") if hasattr(src_info, "get") else None
            if src_title and title.endswith(" - " + src_title):
                title = title[: -(len(src_title) + 3)]
            source_name = src_title or domain_of(src_info.get("href", "")) or "Google Новости"
            link = decode_google_link(link)
            summary = ""  # у Google в описании только повтор заголовка
        elif kind == "bing":
            link = decode_bing_link(link)
            source_name = e.get("news_source") or domain_of(link) or src["name"]
        else:
            feed_host, link_host = domain_of(src.get("url", "")), domain_of(link)
            if feed_host and link_host and not (link_host.endswith(feed_host) or feed_host.endswith(link_host)):
                source_name = link_host  # лента ссылается на чужой сайт — показываем его адрес

        if not title or not link:
            continue
        items.append({
            "title": title,
            "link": link,
            "summary": summary[:600],
            "published": entry_time(e),
            "source": source_name,
            "kind": kind,
            "src_category": src.get("category"),
        })
    return items


def fetch_source(src, cfg):
    url = feed_url(src, cfg)
    try:
        r = SESSION.get(url, timeout=20)
        r.raise_for_status()
        items = parse_feed(src, r.content)
        log(f"  ✓ {src['name']}: {len(items)} записей")
        return items
    except Exception as ex:
        log(f"  ✗ {src['name']}: {type(ex).__name__}: {str(ex)[:120]}")
        return []


def collect(cfg):
    log("Собираю новости:")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda s: fetch_source(s, cfg), cfg["sources"]))
    return [it for batch in results for it in batch]


def guess_category(item, cfg):
    """Предварительная рубрика по словам в тексте. None — непонятно, решит ИИ."""
    text = f" {item['title']} {item['summary']} ".lower()
    found = {cat for cat, words in (cfg.get("regions") or {}).items() if any(w.lower() in text for w in words)}
    if len(found) == 1:
        return found.pop()
    if item.get("src_category") in found or not found:
        return item.get("src_category")
    return None


def priority_country(item, cfg):
    text = f" {item['title']} {item['summary']} ".lower()
    for code, words in (cfg.get("priority") or {}).items():
        if any(w.lower() in text for w in words):
            return code
    return None


def select_candidates(items, state, cfg):
    """Фильтр по ключевым словам, свежести и повторам; склейка дублей. Возвращает все уникальные истории."""
    keywords = [k.lower() for k in cfg["keywords"]]
    cutoff = now_utc() - timedelta(hours=cfg.get("lookback_hours", 36))
    kind_rank = {"rss": 0, "bing": 1, "google": 2}  # при дублях оставляем прямую ссылку на СМИ

    fresh = []
    for it in items:
        text = f"{it['title']} {it['summary']}".lower()
        hits = sum(1 for k in keywords if k in text)
        if not hits:
            continue
        if it["published"] and it["published"] < cutoff:
            continue
        if already_posted(it, state):
            continue
        it["category"] = guess_category(it, cfg)
        it["country"] = priority_country(it, cfg)
        it["norm"] = normalize_title(it["title"])
        age_h = (now_utc() - it["published"]).total_seconds() / 3600 if it["published"] else 24
        it["score"] = hits + PRIORITY_BOOST.get(it["country"], 0) - age_h / 24
        fresh.append(it)

    fresh.sort(key=lambda x: (kind_rank.get(x["kind"], 3), -x["score"]))
    unique = []
    for it in fresh:
        dup = next((u for u in unique if similar(u["norm"], it["norm"])), None)
        if dup:
            dup.setdefault("dups", []).append(it)
            if dup["category"] is None:
                dup["category"] = it["category"]
        else:
            unique.append(it)

    unique.sort(key=lambda x: -x["score"])
    for i, it in enumerate(unique, 1):
        it["id"] = f"n{i}"
    counts = Counter(c["category"] or "?" for c in unique)
    log(f"Свежих историй: {len(unique)} " + ", ".join(f"{CATEGORY_NAMES.get(k, k)}: {v}" for k, v in counts.items()))
    return unique


def candidates_for(cands, category, limit=30):
    return [c for c in cands if c["category"] in (category, None)][:limit]


def fetch_article_text(url, limit=3500):
    """Достаёт основной текст статьи (для точного пересказа). Не страшно, если не вышло."""
    if "news.google.com" in url:
        return ""
    try:
        r = SESSION.get(url, timeout=15)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "figure"]):
            tag.decompose()
        container = soup.find("article") or soup.find("main") or soup
        paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
        text = "\n".join(p for p in paras if len(p) > 40)
        return text[:limit]
    except Exception as ex:
        log(f"  (не удалось прочитать статью {domain_of(url)}: {type(ex).__name__})")
        return ""


def attach_texts(cands):
    with ThreadPoolExecutor(max_workers=5) as pool:
        texts = list(pool.map(lambda c: fetch_article_text(c["link"]), cands))
    for c, t in zip(cands, texts):
        c["text"] = t


# ───────────────────────── ИИ ─────────────────────────

SYSTEM_PROMPT = """Ты редактор русскоязычного Telegram-канала, который учит читателей из СНГ (прежде всего Кыргызстана, Узбекистана и Казахстана) распознавать мошенников на реальных историях со всего мира.
Строгие правила:
1. Только факты из присланных материалов. Не придумывай цифры, даты, суммы и детали. Если текста мало — пиши коротко и только то, что следует из заголовка.
2. Пиши по-русски и своими словами. Если материал на английском — перескажи, а не переводи дословно. Не копируй фразы и не используй цитаты.
3. Никаких имён и фамилий, фото, телефонов, номеров карт и адресов подозреваемых и потерпевших. Можно: возраст, город, род занятий («25-летний житель Бишкека»).
4. Про конкретного человека, чья вина не установлена судом, пиши «подозреваемый» или «задержан по подозрению», а не «мошенник».
5. Если в материале есть адрес фишингового сайта, пиши его только в обезвреженном виде: hxxps://example[.]com. Названия СМИ в тексте не упоминай — ссылка на источник добавится отдельно.
6. Что важнее всего: новые или необычные схемы и официальные предупреждения → случаи с понятным уроком для читателя → статистика. Отсеивай всё, что не про мошенничество против людей и бизнеса, а также политику и рекламу.
7. Тон спокойный и понятный даже пожилому человеку: без паники, без канцелярита, короткие предложения.
Отвечай только JSON без пояснений."""


def call_anthropic(system, user, key):
    model = env("ANTHROPIC_MODEL", "claude-haiku-5-5")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 2500, "system": system,  # temperature у моделей 5.5 не поддерживается
              "messages": [{"role": "user", "content": user}]},
        timeout=90,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def call_gemini(system, user, key):
    model = env("GEMINI_MODEL", "gemini-flash-latest")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "content-type": "application/json"},
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}},
        timeout=90,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def llm_available():
    return bool(env("ANTHROPIC_API_KEY") or env("GEMINI_API_KEY"))


def parse_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("в ответе нет JSON")
    return json.loads(text[start:end + 1])


LLM_ERRORS = []  # ошибки ИИ за этот запуск: если ничего не опубликовано из-за них, запуск падает и GitHub пришлёт письмо


def ask_llm(user_prompt):
    """Возвращает dict из ответа ИИ или None. Одна повторная попытка при сбое."""
    for attempt in (1, 2):
        try:
            if env("ANTHROPIC_API_KEY"):
                raw = call_anthropic(SYSTEM_PROMPT, user_prompt, env("ANTHROPIC_API_KEY"))
            elif env("GEMINI_API_KEY"):
                raw = call_gemini(SYSTEM_PROMPT, user_prompt, env("GEMINI_API_KEY"))
            else:
                return None
            return parse_json(raw)
        except Exception as ex:
            detail = ""
            if isinstance(ex, requests.HTTPError) and ex.response is not None:
                detail = ex.response.text[:300]
            log(f"  ИИ: попытка {attempt} не удалась: {type(ex).__name__}: {ex} {detail}")
            if attempt == 2:
                LLM_ERRORS.append(f"{type(ex).__name__}: {detail or ex}"[:300])
            time.sleep(3)
    return None


def format_candidates(cands, with_text=False):
    lines = []
    for c in cands:
        date = c["published"].astimezone(local_tz()).strftime("%d.%m %H:%M") if c["published"] else "дата ?"
        lines.append(f"[{c['id']}] {date} | {c['source']} | {c['title']}")
        body = c.get("text") if with_text and c.get("text") else c.get("summary")
        if body:
            lines.append(f"    {body[:3500 if with_text else 300]}")
    return "\n".join(lines)


def kyrgyz_instruction():
    if env_flag("ADD_KYRGYZ"):
        return 'Заполни поле "ky": одно-два коротких предложения на кыргызском языке с главным советом из поста.'
    return 'Поле "ky" оставь пустой строкой.'


STORY_FIELDS = """"title": "заголовок своими словами до 90 символов",
"how_it_works": "2–3 предложения: как устроена схема и на что давят мошенники",
"red_flags": ["3–4 коротких признака, по которым можно распознать такую схему"],
"what_to_do": ["2–3 конкретных действия для читателя из СНГ: как защититься и что делать, если деньги уже переведены (звонок в банк по номеру на карте, блокировка карты, заявление в полицию/милицию — 102)"],
"ky": \"\""""


def llm_pick(cands, category, cfg):
    describe = cfg["categories"][category]["describe"]
    prompt = f"""Сейчас {local_now().strftime('%d.%m.%Y %H:%M')}. Ниже свежие новости.
Выбери до 2 лучших историй о мошенничестве, которые произошли {describe}. Важно, где пострадали люди или где действовали мошенники, а не где вышла новость.
Одна и та же история в разных СМИ — дубликат: выбирай одну, остальные укажи в duplicates.
Верни JSON: {{"ids": ["n3", "n1"], "duplicates": ["n7"]}} — ids в порядке качества. Если подходящих нет — {{"ids": [], "duplicates": []}}.

Новости:
{format_candidates(cands)}"""
    data = ask_llm(prompt)
    if data is None:
        return None, []
    by_id = {c["id"]: c for c in cands}
    chosen = [by_id[i] for i in data.get("ids", []) if i in by_id][:2]
    dups = [by_id[i] for i in data.get("duplicates", []) if i in by_id and by_id[i] not in chosen]
    log(f"  ИИ выбрал: {[c['id'] for c in chosen]}, дубликаты: {[c['id'] for c in dups]}")
    return chosen, dups


def llm_write_story(story, category):
    abroad = category != "CIS"
    prompt = f"""Сделай разбор истории [{story['id']}].
Верни JSON:
{{"location": "где это произошло, по-русски: страна и город или регион, например «Кыргызстан, Бишкек» или «США, Техас». Если город неизвестен — только страна",
"flag": "эмодзи-флаг этой страны",
"country_tag": "страна одним словом для хэштега, например Кыргызстан, США, Германия",
"what_happened": "2–3 предложения: что произошло",
{STORY_FIELDS},
"for_us": "{'1–2 предложения: может ли такая схема встретиться в СНГ и как она могла бы выглядеть у нас' if abroad else ''}"}}
{kyrgyz_instruction()}

Материал:
{format_candidates([story], with_text=True)}"""
    return ask_llm(prompt)


# ───────────────────────── оформление поста ─────────────────────────

def source_link(item):
    return f'<a href="{html.escape(item["link"], quote=True)}">{esc(item["source"])}</a>'


def hashtag(word):
    word = re.sub(r"[^\w]", "", (word or "").replace(" ", "_"))
    return f"#{word}" if word else ""


def footer(cfg, category, country_tag=""):
    parts = []
    cta = env("BOT_CTA")
    if cta:
        parts.append(cta)
    tags = [cfg.get("hashtags", "")]
    if category in cfg.get("categories", {}):
        tags.append(cfg["categories"][category]["hashtag"])
    tag = hashtag(country_tag)
    if tag and tag not in tags:
        tags.append(tag)
    parts.append(" ".join(t for t in tags if t))
    return "\n\n".join(parts)


def build_story(cfg, data, category, item=None):
    safe = cfg.get("safe_domains", [])
    d = lambda s: esc(defang(s or "", safe))  # noqa: E731
    flag = data.get("flag", "").strip()
    flag = "💡" if category == "TIP" else flag if FLAG_RE.match(flag) else "🌍"
    location = data.get("location") or ("Напоминание" if not item else CATEGORY_NAMES.get(category, ""))

    parts = [f"📍 <b>{flag} {d(location)}</b>", f"⚠️ <b>{d(data.get('title'))}</b>"]
    if data.get("what_happened"):
        parts.append(f"<b>Что случилось</b>\n{d(data['what_happened'])}")
    if data.get("intro"):
        parts.append(d(data["intro"]))
    if data.get("how_it_works"):
        parts.append(f"<b>Как работает схема</b>\n{d(data['how_it_works'])}")
    flags = [f for f in data.get("red_flags", []) if f]
    if flags:
        parts.append("<b>🚩 Признаки обмана</b>\n" + "\n".join(f"• {d(f)}" for f in flags[:5]))
    todo = [t for t in data.get("what_to_do", []) if t]
    if todo:
        parts.append("<b>✅ Как защититься</b>\n" + "\n".join(f"• {d(t)}" for t in todo[:4]))
    if category != "CIS" and data.get("for_us"):
        parts.append(f"<b>🌍 Может ли это случиться у нас?</b>\n{d(data['for_us'])}")
    if data.get("ky"):
        parts.append(f"🇰🇬 <i>{d(data['ky'])}</i>")
    if item:
        parts.append(f"📰 Источник: {source_link(item)}")
    parts.append(footer(cfg, category, data.get("country_tag", "")))

    text = "\n\n".join(parts)
    if visible_len(text) > TELEGRAM_LIMIT:  # на всякий случай укорачиваем
        text = text[:TELEGRAM_LIMIT - 50].rsplit("\n", 1)[0] + "\n…"
    return text


def build_headline(cfg, item, category):
    """Запасной вариант без ИИ: заголовок и ссылка."""
    return "\n\n".join([
        f"📍 <b>{CATEGORY_NAMES.get(category, '').upper()}</b>",
        f"⚠️ <b>{esc(item['title'])}</b>",
        f"📰 Источник: {source_link(item)}",
        footer(cfg, category),
    ])


def visible_len(text):
    return len(re.sub(r"<[^>]+>", "", html.unescape(text)))


# ───────────────────────── один выпуск ─────────────────────────

def expand_dups(items):
    out = []
    for it in items:
        out.append(it)
        out.extend(it.get("dups", []))
    return out


def make_story(cfg, cands, category):
    """Возвращает (text, preview_url, used_items) или None."""
    if not llm_available():
        item = cands[0]
        return build_headline(cfg, item, category), None, expand_dups([item])

    chosen, dups = llm_pick(cands, category, cfg)
    if not chosen:
        return None
    attach_texts(chosen)
    story = next((c for c in chosen if len(c.get("text", "")) > 500), chosen[0])
    data = llm_write_story(story, category)
    if not data or not data.get("title"):
        return None
    preview = story["link"] if "news.google.com" not in story["link"] else None
    extra = [c for c in chosen if c is not story and similar(c["norm"], story["norm"])]
    return build_story(cfg, data, category, item=story), preview, expand_dups([story] + extra + dups)


def make_evergreen(cfg, state):
    schemes = cfg.get("evergreen") or []
    if not schemes or not llm_available():
        return None
    idx = state.get("evergreen_index", 0) % len(schemes)
    scheme = schemes[idx]
    log(f"Подходящих историй не нашлось — напоминание о схеме: {scheme}")
    prompt = f"""Свежих новостей нет. Напиши напоминание о распространённой в СНГ схеме: «{scheme}».
Не приводи цифр, статистики и конкретных случаев — только общеизвестную механику и советы.
Верни JSON:
{{"location": "Напоминание", "flag": "", "country_tag": "",
"intro": "2 предложения: почему стоит об этом помнить",
{STORY_FIELDS}}}
{kyrgyz_instruction()}"""
    data = ask_llm(prompt)
    if not data or not data.get("title"):
        return None
    data["location"] = "Напоминание о схеме"
    state["evergreen_index"] = idx + 1
    item = {"link": f"evergreen:{scheme}", "title": scheme}
    return build_story(cfg, data, "TIP"), None, [item]


def run_once(cfg, state):
    """Публикует следующий пост дня. Возвращает (text, preview, used, category) или None."""
    stats = today_stats(state)
    total = sum(stats.values())
    limit = cfg.get("daily_limit", 10)
    log(f"Сегодня уже опубликовано: {total} из {limit} "
        f"({', '.join(f'{CATEGORY_NAMES.get(k, k)}: {v}' for k, v in stats.items()) or 'пока ничего'})")
    if total >= limit:
        log("Дневной лимит выполнен.")
        return None

    forced = env("CATEGORY", "auto").upper()
    order = [forced] if forced in cfg["categories"] else category_order(cfg, stats)
    log(f"Рубрика по плану: {CATEGORY_NAMES[order[0]]}" + (f", запасные: {[CATEGORY_NAMES[c] for c in order[1:]]}" if len(order) > 1 else ""))

    cands = select_candidates(collect(cfg), state, cfg)
    for category in order:
        subset = candidates_for(cands, category)
        if not subset:
            log(f"  {CATEGORY_NAMES[category]}: свежих историй нет")
            continue
        log(f"Ищу историю для рубрики «{CATEGORY_NAMES[category]}» среди {len(subset)} новостей")
        result = make_story(cfg, subset, category)
        if result:
            return (*result, category)
        log(f"  {CATEGORY_NAMES[category]}: подходящей истории не нашлось")

    if stats.get("TIP", 0) < cfg.get("evergreen_max_per_day", 1):
        result = make_evergreen(cfg, state)
        if result:
            return (*result, "TIP")
    return None


# ───────────────────────── Telegram ─────────────────────────

def tg_call(method, payload=None, token=None):
    token = token or env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{method}"
    for _ in range(3):
        try:
            r = requests.post(url, json=payload or {}, timeout=30)
        except requests.RequestException as ex:
            # текст ошибки requests содержит адрес с токеном — в лог его не пускаем
            raise SystemExit(f"Telegram недоступен ({type(ex).__name__}), метод {method}") from None
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False}
        if r.status_code == 429:
            wait = data.get("parameters", {}).get("retry_after", 5)
            log(f"Telegram просит подождать {wait} с")
            time.sleep(wait)
            continue
        return r.status_code, data
    return r.status_code, data


def send_post(text, preview_url=None, silent=False):
    chat_id = env("TELEGRAM_CHAT_ID")
    preview = {"url": preview_url, "prefer_small_media": True} if preview_url else {"is_disabled": True}
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "link_preview_options": preview, "disable_notification": silent}
    status, data = tg_call("sendMessage", payload)
    if data.get("ok"):
        log(f"✅ Опубликовано (message_id={data['result']['message_id']}{', без звука' if silent else ''})")
        return True
    desc = data.get("description", "")
    log(f"Telegram ответил ошибкой {status}: {desc}")
    if "parse" in desc.lower() or "entit" in desc.lower():
        log("Пробую отправить без форматирования…")
        plain = html.unescape(re.sub(r"<[^>]+>", "", text))
        status, data = tg_call("sendMessage", {"chat_id": chat_id, "text": plain, "disable_notification": silent,
                                               "link_preview_options": {"is_disabled": True}})
        if data.get("ok"):
            log("✅ Опубликовано без форматирования")
            return True
    raise SystemExit(f"Не удалось отправить пост: {data.get('description')}")


def find_chat():
    status, data = tg_call("getUpdates", {"allowed_updates": ["message", "channel_post", "my_chat_member"]})
    if not data.get("ok"):
        raise SystemExit(f"Ошибка: {data.get('description')} — проверьте TELEGRAM_BOT_TOKEN")
    chats = {}
    for upd in data.get("result", []):
        for key in ("message", "channel_post", "my_chat_member", "edited_message", "edited_channel_post"):
            chat = (upd.get(key) or {}).get("chat")
            if chat:
                chats[chat["id"]] = chat
    if not chats:
        log("Чатов не найдено. Добавьте бота в канал админом, опубликуйте там любое сообщение и запустите снова.")
        return
    log("Найденные чаты (скопируйте нужный id в секрет TELEGRAM_CHAT_ID):")
    for cid, chat in chats.items():
        name = chat.get("title") or chat.get("username") or chat.get("first_name")
        log(f"  {cid}  |  {chat.get('type')}  |  {name}")


def test_message():
    send_post(f"✅ <b>Бот подключён</b>\nТестовое сообщение, {local_now().strftime('%d.%m.%Y %H:%M')}. Его можно удалить.")


# ───────────────────────── main ─────────────────────────

def is_silent(category):
    """Без звука: рубрики из silent_categories и любые посты в тихие часы (GitHub может запустить с опозданием)."""
    if category in CONFIG.get("silent_categories", []):
        return True
    quiet = CONFIG.get("quiet_hours") or {}
    start, end = quiet.get("from"), quiet.get("to")
    if start is None or end is None:
        return False
    hour = local_now().hour
    return hour >= start or hour < end if start > end else start <= hour < end


def main(argv):
    global CONFIG
    CONFIG = load_config()
    if "--find-chat" in argv:
        return find_chat()
    if "--test-message" in argv:
        return test_message()

    dry = env_flag("DRY_RUN") or not (env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))
    log(f"Запуск {local_now():%d.%m.%Y %H:%M}{' (тестовый режим — без отправки)' if dry else ''}")
    log(f"ИИ: {'Claude' if env('ANTHROPIC_API_KEY') else 'Gemini' if env('GEMINI_API_KEY') else 'нет ключа'}")

    state = load_state()
    result = run_once(CONFIG, state)
    if not result:
        if LLM_ERRORS:
            raise SystemExit("ИИ не ответил, пост не опубликован. Последняя ошибка: " + LLM_ERRORS[-1])
        log("Публиковать нечего — пропускаю этот запуск.")
        return

    text, preview, used, category = result
    log("\n──────── пост ────────\n" + text + "\n──────────────────────")
    if dry:
        log("Тестовый режим: пост не отправлен, список опубликованного не изменён.")
        return
    send_post(text, preview, silent=is_silent(category))
    mark_posted(state, used, category)
    save_state(state)


if __name__ == "__main__":
    main(sys.argv[1:])
