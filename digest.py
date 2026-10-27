#!/usr/bin/env python3
"""
AI-дайджест в Telegram.

1. Собирает свежие материалы по AI: блоги лабораторий, новости, Хабр, Hacker News,
   новые репозитории GitHub, статьи дня с Hugging Face, YouTube-каналы.
2. Claude отбирает только полезное (по твоему profile.md) и пишет короткие пояснения на русском.
3. Отправляет дайджест в Telegram.

Запуск:
    python digest.py              # обычный запуск (собрать → отобрать → отправить)
    python digest.py --dry-run    # показать дайджест в консоли, ничего не отправлять
    python digest.py --no-llm     # без Claude: просто топ по рейтингу (для проверки)

Переменные окружения:
    TELEGRAM_BOT_TOKEN  — токен от @BotFather (обязательно)
    TELEGRAM_CHAT_ID    — куда слать; если не задан, скрипт покажет id твоих чатов
    ANTHROPIC_API_KEY   — ключ Claude API (без него будет простой топ без отбора)
    CLAUDE_MODEL        — модель, по умолчанию claude-sonnet-5-5
    GITHUB_TOKEN        — необязательно; в GitHub Actions подставляется сам
    TZ_OFFSET_HOURS     — твой часовой пояс для даты в заголовке, по умолчанию 6 (Бишкек)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
SOURCES_PATH = ROOT / "sources.yaml"
PROFILE_PATH = ROOT / "profile.md"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 ai-digest-bot/1.0"
TIMEOUT = 25
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
TZ = dt.timezone(dt.timedelta(hours=float(os.getenv("TZ_OFFSET_HOURS", "6"))))
TG_LIMIT = 3900  # Telegram режет на 4096 символах, оставляем запас

SECTIONS = {
    "main": "🔥 <b>Главное</b>",
    "tools": "🛠 <b>Инструменты и код</b>",
    "video": "📺 <b>Видео</b>",
    "research": "📄 <b>Исследования</b>",
    "other": "📌 <b>Ещё полезное</b>",
}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


# ───────────────────────────── утилиты ─────────────────────────────

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def http_get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": UA, **kw.pop("headers", {})}
    r = requests.get(url, headers=headers, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def clean(text: str | None, limit: int = 280) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def norm_url(url: str) -> str:
    """Убирает utm-метки и якоря, чтобы одна ссылка не считалась разными."""
    try:
        p = urlsplit(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid"))]
        return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(q), ""))
    except Exception:
        return url.strip()


def item_key(url: str) -> str:
    return hashlib.sha1(norm_url(url).encode()).hexdigest()[:16]


def struct_to_dt(st) -> dt.datetime | None:
    if not st:
        return None
    try:
        return dt.datetime(*st[:6], tzinfo=dt.timezone.utc)
    except Exception:
        return None


def make_item(source, kind, title, url, summary="", published=None, score="", extra_links=None):
    return {
        "source": source, "kind": kind, "title": clean(title, 200), "url": url.strip(),
        "summary": clean(summary), "published": published.isoformat() if published else None,
        "score": score, "extra_links": extra_links or [],
    }


# ───────────────────────────── состояние ─────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text("utf-8"))
        except Exception as e:
            log(f"⚠️ state.json повреждён, начинаю с нуля: {e}")
    return {"seen": {}, "yt_ids": {}}


def save_state(state: dict, keep_days: int = 21) -> None:
    cutoff = (now_utc() - dt.timedelta(days=keep_days)).date().isoformat()
    state["seen"] = {k: d for k, d in state.get("seen", {}).items() if d >= cutoff}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")


# ───────────────────────────── источники ─────────────────────────────

def fetch_feed(name: str, url: str, since: dt.datetime, limit: int, kind: str = "news") -> list[dict]:
    r = http_get(url)
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"не похоже на RSS: {feed.bozo_exception}")
    out = []
    for e in feed.entries:
        link = e.get("link")
        if not link or "/shorts/" in link:
            continue
        published = struct_to_dt(e.get("published_parsed") or e.get("updated_parsed"))
        if published and published < since:
            continue
        out.append(make_item(name, kind, e.get("title", ""), link, e.get("summary", ""), published))
        if len(out) >= limit:
            break
    return out


def collect_rss(cfg: dict, since: dt.datetime, per_source: int) -> list[dict]:
    items = []
    for src in cfg.get("rss", []) or []:
        try:
            got = fetch_feed(src["name"], src["url"], since, src.get("limit", per_source), src.get("kind", "news"))
            log(f"  ✓ {src['name']}: {len(got)}")
            items += got
        except Exception as e:
            log(f"  ✗ {src['name']}: {e}")
    return items


YT_ID_PATTERNS = [
    r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
    r'"externalId":"(UC[\w-]{22})"',
    r'<meta itemprop="(?:identifier|channelId)" content="(UC[\w-]{22})"',
]


def resolve_youtube(handle: str, state: dict) -> str | None:
    if handle.startswith("UC") and len(handle) == 24:
        return handle
    cache = state.setdefault("yt_ids", {})
    if handle in cache:
        return cache[handle]
    page = http_get(f"https://www.youtube.com/{handle if handle.startswith('@') else '@' + handle}",
                    cookies={"CONSENT": "YES+1", "SOCS": "CAI"}).text
    for pat in YT_ID_PATTERNS:
        m = re.search(pat, page)
        if m:
            cache[handle] = m.group(1)
            return m.group(1)
    return None


def collect_youtube(cfg: dict, since: dt.datetime, state: dict) -> list[dict]:
    items = []
    for entry in cfg.get("youtube", []) or []:
        handle = entry if isinstance(entry, str) else entry.get("channel_id") or entry.get("handle")
        try:
            cid = resolve_youtube(handle, state)
            if not cid:
                raise ValueError("не нашёл channel_id — укажи его вручную (UC...)")
            got = fetch_feed(f"YouTube {handle}", f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                             since, 3, kind="video")
            log(f"  ✓ YouTube {handle}: {len(got)}")
            items += got
        except Exception as e:
            log(f"  ✗ YouTube {handle}: {e}")
    return items


def collect_hackernews(cfg: dict, since: dt.datetime) -> list[dict]:
    hn = cfg.get("hackernews")
    if not hn:
        return []
    ts = int(since.timestamp())
    r = http_get("https://hn.algolia.com/api/v1/search", params={
        "tags": "story",
        "numericFilters": f"created_at_i>{ts},points>={hn.get('min_points', 80)}",
        "hitsPerPage": 300,
    })
    kw = re.compile(r"\b(" + "|".join(hn.get("keywords", [])) + r")\b", re.I)
    out = []
    for h in r.json().get("hits", []):
        title = h.get("title") or ""
        if not kw.search(title):
            continue
        hn_url = f"https://news.ycombinator.com/item?id={h['objectID']}"
        url = h.get("url") or hn_url
        extra = [("HN", hn_url)] if h.get("url") else []
        published = dt.datetime.fromtimestamp(h.get("created_at_i", ts), dt.timezone.utc)
        out.append(make_item("Hacker News", "news", title, url, h.get("story_text", ""), published,
                             f"{h.get('points', 0)} pts, {h.get('num_comments', 0)} комм.", extra))
    out.sort(key=lambda i: -int(i["score"].split()[0]))
    out = out[: hn.get("limit", 25)]
    log(f"  ✓ Hacker News: {len(out)}")
    return out


def collect_github(cfg: dict) -> list[dict]:
    gh = cfg.get("github")
    if not gh:
        return []
    created = (now_utc() - dt.timedelta(days=gh.get("days", 7))).date().isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    repos: dict[str, dict] = {}
    for topic in gh.get("topics", []):
        try:
            r = http_get("https://api.github.com/search/repositories", headers=headers, params={
                "q": f"topic:{topic} created:>{created} stars:>={gh.get('min_stars', 50)}",
                "sort": "stars", "order": "desc", "per_page": 10,
            })
            for repo in r.json().get("items", []):
                repos[repo["full_name"]] = repo
        except Exception as e:
            log(f"  ✗ GitHub topic:{topic}: {e}")
    top = sorted(repos.values(), key=lambda x: -x["stargazers_count"])[: gh.get("limit", 8)]
    out = [make_item("GitHub (новые репо)", "code", r["full_name"], r["html_url"],
                     f"{r.get('description') or ''} [{r.get('language') or '—'}]",
                     dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
                     f"★{r['stargazers_count']}") for r in top]
    log(f"  ✓ GitHub: {len(out)}")
    return out


def collect_hf_papers(cfg: dict) -> list[dict]:
    hf = cfg.get("hf_papers")
    if not hf:
        return []
    day = (now_utc() - dt.timedelta(days=1)).date().isoformat()
    data = http_get("https://huggingface.co/api/daily_papers", params={"date": day}).json()
    papers = sorted(data, key=lambda x: -(x.get("paper", {}).get("upvotes") or 0))
    out = []
    for p in papers:
        paper = p.get("paper", {})
        up = paper.get("upvotes") or 0
        if up < hf.get("min_upvotes", 20) or not paper.get("id"):
            continue
        out.append(make_item("HF Daily Papers", "research", paper.get("title") or p.get("title", ""),
                             f"https://huggingface.co/papers/{paper['id']}",
                             paper.get("ai_summary") or p.get("summary", ""), None, f"▲{up}"))
        if len(out) >= hf.get("limit", 6):
            break
    log(f"  ✓ HF Daily Papers: {len(out)}")
    return out


def collect_all(cfg: dict, state: dict, hours: float) -> list[dict]:
    since = now_utc() - dt.timedelta(hours=hours)
    per_source = cfg.get("per_source_limit", 15)
    log(f"Собираю материалы за последние {hours:g} ч…")
    items: list[dict] = []
    items += collect_rss(cfg, since, per_source)
    items += collect_youtube(cfg, since, state)
    for fn, args in ((collect_hackernews, (cfg, since)), (collect_github, (cfg,)), (collect_hf_papers, (cfg,))):
        try:
            items += fn(*args)
        except Exception as e:
            log(f"  ✗ {fn.__name__}: {e}")

    seen = state.get("seen", {})
    unique: dict[str, dict] = {}
    for it in items:
        k = item_key(it["url"])
        if k in seen or k in unique:
            continue
        it["key"] = k
        unique[k] = it
    result = list(unique.values())[: cfg.get("max_candidates", 250)]
    log(f"Всего новых кандидатов: {len(result)} (было {len(items)} до удаления повторов)")
    return result


# ───────────────────────────── отбор через Claude ─────────────────────────────

DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "1–2 предложения: главное за день"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "номер кандидата из списка"},
                    "section": {"type": "string", "enum": list(SECTIONS)},
                    "title": {"type": "string", "description": "короткий заголовок на русском"},
                    "why": {"type": "string", "description": "1–2 предложения: что это и чем полезно"},
                    "related_ids": {"type": "array", "items": {"type": "integer"},
                                    "description": "номера других кандидатов про ту же новость"},
                },
                "required": ["id", "section", "title", "why", "related_ids"],
                "additionalProperties": False,
            },
        },
        "tip": {"type": "string", "description": "практическая фишка дня на основе одного из пунктов, или пустая строка"},
    },
    "required": ["headline", "items", "tip"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Ты — редактор личного AI-дайджеста для одного читателя. Тебе дают список свежих материалов \
(новости, блоги, видео, репозитории, статьи) за последние сутки. Твоя задача — выбрать только то, что реально \
полезно этому читателю, и коротко объяснить по-русски, что это и зачем ему это знать.

Профиль читателя:
<profile>
{profile}
</profile>

Правила:
- Выбери от 0 до {max_items} пунктов. Лучше меньше, но сильнее. Если день пустой — так и выбирай мало.
- Одна новость из нескольких источников — это ОДИН пункт: возьми лучший источник в id, остальные номера положи в related_ids.
- Раздел: main — самое важное за день (не больше 3), tools — инструменты, библиотеки, репозитории, фишки для кода, \
video — видео, research — исследования с практическим смыслом, other — остальное полезное.
- title — короткий понятный заголовок на русском (названия продуктов и моделей не переводи).
- why — 1–2 предложения: что это, чем полезно, что можно попробовать. Конкретно, без воды и восторгов.
- Пиши только то, что следует из данных кандидата. Не выдумывай цифры, даты и возможности.
- headline — 1–2 предложения о главном за день.
- tip — одна практическая фишка (как применить что-то из выбранного), 1–2 предложения; если нечего — пустая строка.
- Отвечай строго JSON по заданной схеме."""


def build_candidates_text(items: list[dict]) -> str:
    lines = []
    for i, it in enumerate(items):
        meta = " | ".join(x for x in (it["source"], it["kind"], it["score"]) if x)
        line = f"[{i}] ({meta}) {it['title']}"
        if it["summary"]:
            line += f" — {it['summary']}"
        lines.append(line)
    return "\n".join(lines)


def call_claude(system: str, user: str, use_schema: bool = True) -> str:
    body = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if use_schema:
        body["output_config"] = {"format": {"type": "json_schema", "schema": DIGEST_SCHEMA}}
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    for attempt in range(4):
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=180)
        if r.status_code in (429, 500, 502, 503, 529) and attempt < 3:
            wait = 15 * (attempt + 1)
            log(f"  Claude API {r.status_code}, повтор через {wait} с…")
            time.sleep(wait)
            continue
        if r.status_code == 400 and use_schema and "output_config" in r.text:
            log("  Модель не поддерживает structured outputs, пробую обычным JSON…")
            return call_claude(system, user, use_schema=False)
        if r.status_code >= 400:
            raise RuntimeError(f"Claude API {r.status_code}: {r.text[:500]}")
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    raise RuntimeError("Claude API не ответил после нескольких попыток")


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def curate(items: list[dict], max_items: int) -> dict:
    profile = PROFILE_PATH.read_text("utf-8") if PROFILE_PATH.exists() else "Интересуется AI и программированием."
    system = SYSTEM_PROMPT.format(profile=profile.strip(), max_items=max_items)
    user = "Кандидаты:\n\n" + build_candidates_text(items)
    log(f"Отбираю через {MODEL} из {len(items)} кандидатов…")
    result = parse_json(call_claude(system, user))

    picked, used = [], set()
    for it in result.get("items", []):
        idx = it.get("id")
        if not isinstance(idx, int) or not (0 <= idx < len(items)) or idx in used:
            continue
        used.add(idx)
        related = [r for r in it.get("related_ids", []) if isinstance(r, int) and 0 <= r < len(items) and r != idx]
        picked.append({
            "section": it.get("section") if it.get("section") in SECTIONS else "other",
            "title": it.get("title") or items[idx]["title"],
            "why": it.get("why", ""),
            "item": items[idx],
            "related": [items[r] for r in related],
        })
        if len(picked) >= max_items:
            break
    log(f"Отобрано: {len(picked)}")
    return {"headline": result.get("headline", ""), "picked": picked, "tip": result.get("tip", "")}


def fallback_digest(items: list[dict], max_items: int) -> dict:
    """Без Claude: берём лучшее по рейтингу и свежести, без пояснений."""
    def score(it):
        m = re.search(r"\d+", it["score"] or "")
        return int(m.group()) if m else 0
    kind_section = {"news": "main", "code": "tools", "video": "video", "research": "research"}
    ranked = sorted(items, key=lambda it: -score(it))[:max_items]
    picked = [{"section": kind_section.get(it["kind"], "other"), "title": it["title"],
               "why": it["summary"][:160], "item": it, "related": []} for it in ranked]
    return {"headline": "Режим без Claude: топ по рейтингу, без отбора.", "picked": picked, "tip": ""}


# ───────────────────────────── оформление и отправка ─────────────────────────────

def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def link(url: str, text: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(text)}</a>'


def short_source(it: dict) -> str:
    return it["source"].replace("YouTube ", "").replace("GitHub (новые репо)", "GitHub")


def render(digest: dict) -> list[str]:
    today = dt.datetime.now(TZ)
    blocks = [f"🤖 <b>AI-дайджест · {today.day} {MONTHS[today.month - 1]}</b>"]
    if digest.get("headline"):
        blocks[0] += f"\n<i>{esc(digest['headline'])}</i>"

    for sec, header in SECTIONS.items():
        entries = [p for p in digest["picked"] if p["section"] == sec]
        if not entries:
            continue
        blocks.append(header)
        for p in entries:
            it = p["item"]
            meta = short_source(it) + (f", {it['score']}" if it["score"] else "")
            text = f"• {link(it['url'], p['title'])}"
            if p["why"]:
                text += f" — {esc(p['why'])}"
            text += f" <i>({esc(meta)})</i>"
            extras = list(it.get("extra_links", [])) + [(short_source(r), r["url"]) for r in p["related"]]
            if extras:
                text += "\n   ещё: " + " · ".join(link(u, n) for n, u in extras[:4])
            blocks.append(text)

    if digest.get("tip"):
        blocks.append(f"💡 <b>Фишка дня:</b> {esc(digest['tip'])}")

    # склеиваем блоки в сообщения, не разрывая пункты
    messages, cur = [], ""
    for b in blocks:
        sep = "\n\n" if b.startswith(("🔥", "🛠", "📺", "📄", "📌", "💡")) else "\n"
        candidate = (cur + sep + b) if cur else b
        if len(candidate) > TG_LIMIT and cur:
            messages.append(cur)
            cur = b
        else:
            cur = candidate
    if cur:
        messages.append(cur)
    return messages


def tg_api(method: str, payload: dict | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    for attempt in range(4):
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload or {}, timeout=30)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False, "description": r.text[:200]}
        if r.status_code == 429 and attempt < 3:
            time.sleep(data.get("parameters", {}).get("retry_after", 5) + 1)
            continue
        return data
    return data


def send_telegram(messages: list[str]) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    for msg in messages:
        res = tg_api("sendMessage", {"chat_id": chat_id, "text": msg, "parse_mode": "HTML",
                                     "link_preview_options": {"is_disabled": True}})
        if not res.get("ok"):
            log(f"  Telegram не принял HTML ({res.get('description')}), шлю простым текстом…")
            plain = html.unescape(re.sub(r"<[^>]+>", "", msg))
            res = tg_api("sendMessage", {"chat_id": chat_id, "text": plain[:4096],
                                         "link_preview_options": {"is_disabled": True}})
            if not res.get("ok"):
                raise RuntimeError(f"Telegram: {res.get('description')}")
        time.sleep(1)
    log(f"Отправлено сообщений: {len(messages)}")


def show_chat_ids() -> None:
    """Помогает узнать TELEGRAM_CHAT_ID: показывает чаты, где боту писали."""
    res = tg_api("getUpdates")
    if not res.get("ok"):
        log(f"Не получилось обратиться к боту: {res.get('description')}. Проверь TELEGRAM_BOT_TOKEN.")
        return
    chats = {}
    for upd in res.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            chats[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
    if not chats:
        log("Боту ещё никто не писал. Открой бота в Telegram, нажми Start / напиши ему что угодно и запусти снова.")
    for cid, name in chats.items():
        log(f"  TELEGRAM_CHAT_ID = {cid}   ({name})")


# ───────────────────────────── main ─────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="AI-дайджест в Telegram")
    ap.add_argument("--dry-run", action="store_true", help="напечатать дайджест, ничего не отправлять и не сохранять")
    ap.add_argument("--no-llm", action="store_true", help="без Claude, просто топ по рейтингу")
    ap.add_argument("--hours", type=float, help="окно в часах (по умолчанию из sources.yaml)")
    args = ap.parse_args()

    if not args.dry_run:
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            log("Нет TELEGRAM_BOT_TOKEN. Создай бота у @BotFather и добавь токен в секреты.")
            return 1
        if not os.getenv("TELEGRAM_CHAT_ID"):
            log("Нет TELEGRAM_CHAT_ID. Вот чаты, где писали боту:")
            show_chat_ids()
            return 1

    cfg = yaml.safe_load(SOURCES_PATH.read_text("utf-8")) or {}
    state = load_state()
    max_items = int(cfg.get("max_items", 12))
    items = collect_all(cfg, state, args.hours or cfg.get("window_hours", 36))

    if not items:
        digest = {"headline": "", "picked": [], "tip": ""}
    elif args.no_llm or not os.getenv("ANTHROPIC_API_KEY"):
        if not args.no_llm:
            log("⚠️ Нет ANTHROPIC_API_KEY — отправляю простой топ без отбора.")
        digest = fallback_digest(items, max_items)
    else:
        digest = curate(items, max_items)

    if not digest["picked"]:
        if not cfg.get("send_empty", True):
            log("Ничего стоящего, сообщение не отправляю.")
            messages = []
        else:
            messages = ["🤖 <b>AI-дайджест</b>\nСегодня ничего действительно стоящего не нашлось. Отдыхаем 🙂"]
    else:
        messages = render(digest)

    if args.dry_run:
        print("\n\n────────── следующее сообщение ──────────\n\n".join(messages))
        return 0

    if messages:
        send_telegram(messages)
    today = now_utc().date().isoformat()
    for it in items:
        state.setdefault("seen", {})[it["key"]] = today
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
