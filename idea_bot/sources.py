"""Сборщики сигналов: что сейчас взлетает в ИИ, IT и автоматизации.

Каждый сборщик возвращает список Item и никогда не роняет бота: если источник
недоступен, он просто пропускается, а в подвале дайджеста будет отметка ✗.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from . import config as cfg

log = logging.getLogger(__name__)

TIMEOUT = 20
UA = "idea-bot/1.0 (personal trend digest; +https://github.com)"


@dataclass
class Item:
    source: str            # «Hacker News · Show HN»
    title: str
    url: str
    description: str = ""
    metric: str = ""       # человекочитаемая метрика тяги: «512 очков, 230 комментариев»
    score: float = 0.0     # для сортировки внутри источника
    discussion_url: str = ""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def _get_json(s: requests.Session, url: str, **kw):
    r = s.get(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean(text: str | None, limit: int = 300) -> str:
    if not text:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = _WS_RE.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _blocked(*texts: str) -> bool:
    joined = " ".join(t.lower() for t in texts if t)
    return any(word in joined for word in cfg.BLOCKLIST)


# ── Hacker News ───────────────────────────────────────────────────────────────

def fetch_hackernews(s: requests.Session) -> list[Item]:
    now = int(time.time())
    api = "https://hn.algolia.com/api/v1/search"
    items: list[Item] = []

    queries = [
        ("Hacker News · Show HN", "show_hn", 3 * 86400, cfg.HN_SHOW_MIN_POINTS),
        ("Hacker News · топ", "story", 86400, cfg.HN_STORY_MIN_POINTS),
    ]
    seen: set[str] = set()
    for source, tag, window, min_points in queries:
        data = _get_json(s, api, params={
            "tags": tag,
            "numericFilters": f"created_at_i>{now - window},points>={min_points}",
            "hitsPerPage": 40,
        })
        for h in data.get("hits", []):
            oid = h.get("objectID")
            title = h.get("title") or ""
            if not oid or oid in seen or not title:
                continue
            seen.add(oid)
            hn_url = f"https://news.ycombinator.com/item?id={oid}"
            points, comments = h.get("points") or 0, h.get("num_comments") or 0
            items.append(Item(
                source=source,
                title=title,
                url=h.get("url") or hn_url,
                description=clean(h.get("story_text")),
                metric=f"{points} очков, {comments} комментариев на HN",
                score=points,
                discussion_url=hn_url,
            ))
    return items


# ── GitHub ────────────────────────────────────────────────────────────────────

def fetch_github(s: requests.Session) -> list[Item]:
    since = (datetime.now(timezone.utc) - timedelta(days=cfg.GITHUB_LOOKBACK_DAYS)).date()
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    items: list[Item] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc)
    for q in cfg.GITHUB_QUERIES:
        query = f"{q} created:>{since.isoformat()} stars:>={cfg.GITHUB_MIN_STARS}".strip()
        data = _get_json(s, "https://api.github.com/search/repositories", headers=headers, params={
            "q": query, "sort": "stars", "order": "desc", "per_page": 25,
        })
        for r in data.get("items", []):
            name = r.get("full_name")
            if not name or name in seen or r.get("fork"):
                continue
            seen.add(name)
            desc = r.get("description") or ""
            if _blocked(name, desc):
                continue
            created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            age = max(1, (now - created).days)
            stars = r.get("stargazers_count") or 0
            topics = ", ".join((r.get("topics") or [])[:5])
            metric = f"★ {stars} за {age} дн."
            if r.get("language"):
                metric += f", {r['language']}"
            if topics:
                metric += f", темы: {topics}"
            items.append(Item(
                source="GitHub · новые репозитории",
                title=name,
                url=r["html_url"],
                description=clean(desc),
                metric=metric,
                score=stars / age,
            ))
    return items


# ── Hugging Face ──────────────────────────────────────────────────────────────

_HF_NOISE_TAGS = {"gradio", "docker", "static", "streamlit", "transformers", "safetensors"}


def fetch_huggingface(s: requests.Session) -> list[Item]:
    items: list[Item] = []
    spaces = _get_json(s, "https://huggingface.co/api/spaces",
                       params={"sort": "trendingScore", "limit": cfg.HF_SPACES_LIMIT})
    for sp in spaces:
        sid = sp.get("id", "")
        tags = [t for t in sp.get("tags", []) if not t.startswith(("region:", "license:"))
                and t not in _HF_NOISE_TAGS]
        if not sid or _blocked(sid, " ".join(tags)):
            continue
        items.append(Item(
            source="Hugging Face · трендовые приложения",
            title=sid,
            url=f"https://huggingface.co/spaces/{sid}",
            description=f"Теги: {', '.join(tags[:8])}" if tags else "",
            metric=f"❤ {sp.get('likes', 0)}, trending score {sp.get('trendingScore', 0)}",
            score=sp.get("trendingScore") or 0,
        ))

    models = _get_json(s, "https://huggingface.co/api/models",
                       params={"sort": "trendingScore", "limit": cfg.HF_MODELS_LIMIT})
    for m in models:
        mid = m.get("id", "")
        if not mid or _blocked(mid):
            continue
        task = m.get("pipeline_tag") or ""
        items.append(Item(
            source="Hugging Face · трендовые модели",
            title=mid,
            url=f"https://huggingface.co/{mid}",
            description=f"Задача: {task}" if task else "",
            metric=f"❤ {m.get('likes', 0)}, скачиваний {m.get('downloads', 0)}",
            score=m.get("trendingScore") or m.get("likes") or 0,
        ))
    return items


# ── Reddit ────────────────────────────────────────────────────────────────────

def _reddit_posts(s: requests.Session, sub: str) -> list[dict]:
    try:
        data = _get_json(s, f"https://www.reddit.com/r/{sub}/top.json",
                         params={"t": "day", "limit": cfg.REDDIT_PER_SUB * 2})
        return [c["data"] for c in data["data"]["children"]]
    except Exception:
        # С облачных IP Reddit часто отвечает 403 на JSON — пробуем RSS
        r = s.get(f"https://www.reddit.com/r/{sub}/top/.rss", params={"t": "day"}, timeout=TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        return [{"title": e.get("title", ""), "permalink": e.get("link", ""),
                 "selftext": e.get("summary", ""), "score": None} for e in feed.entries]


def fetch_reddit(s: requests.Session) -> list[Item]:
    items: list[Item] = []
    failures = 0
    for sub in cfg.REDDIT_SUBS:
        try:
            posts = _reddit_posts(s, sub)
        except Exception as e:
            failures += 1
            log.info("Reddit r/%s недоступен: %s", sub, e)
            if failures >= 3 and not items:
                raise RuntimeError("Reddit блокирует запросы с этого сервера") from e
            continue
        taken = 0
        for p in posts:
            if p.get("stickied") or p.get("over_18"):
                continue
            score = p.get("score")
            if score is not None and score < cfg.REDDIT_MIN_SCORE:
                continue
            title = p.get("title") or ""
            if not title or _blocked(title, p.get("selftext", "")):
                continue
            link = p.get("permalink") or ""
            if link.startswith("/"):
                link = "https://www.reddit.com" + link
            metric = (f"{score} апвоутов, {p.get('num_comments', 0)} комментариев"
                      if score is not None else "топ дня")
            items.append(Item(
                source=f"Reddit · r/{sub}",
                title=title,
                url=link,
                description=clean(p.get("selftext")),
                metric=metric,
                score=score or 0,
            ))
            taken += 1
            if taken >= cfg.REDDIT_PER_SUB:
                break
        time.sleep(1)  # Reddit не любит частые запросы
    return items


# ── Product Hunt ──────────────────────────────────────────────────────────────

_PH_QUERY = """
query($after: DateTime!, $first: Int!) {
  posts(first: $first, order: VOTES, postedAfter: $after) {
    edges { node {
      name tagline url votesCount commentsCount
      topics(first: 3) { edges { node { name } } }
    } }
  }
}
"""


def fetch_producthunt(s: requests.Session) -> list[Item]:
    token = os.getenv("PRODUCTHUNT_TOKEN")
    if token:
        try:
            return _producthunt_api(s, token)
        except Exception as e:
            log.warning("Product Hunt API не ответил (%s), беру RSS", e)
    return _producthunt_rss(s)


def _producthunt_api(s: requests.Session, token: str) -> list[Item]:
    after = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = s.post("https://api.producthunt.com/v2/api/graphql", timeout=TIMEOUT,
               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
               json={"query": _PH_QUERY, "variables": {"after": after, "first": cfg.PRODUCTHUNT_LIMIT}})
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0].get("message", "GraphQL error"))
    items = []
    for edge in payload["data"]["posts"]["edges"]:
        n = edge["node"]
        topics = ", ".join(t["node"]["name"] for t in n.get("topics", {}).get("edges", []))
        items.append(Item(
            source="Product Hunt · топ дня",
            title=n["name"],
            url=n["url"],
            description=clean(f"{n.get('tagline', '')}. Темы: {topics}" if topics else n.get("tagline")),
            metric=f"▲ {n.get('votesCount', 0)} голосов, {n.get('commentsCount', 0)} комментариев",
            score=n.get("votesCount") or 0,
        ))
    return items


def _producthunt_rss(s: requests.Session) -> list[Item]:
    r = s.get("https://www.producthunt.com/feed", timeout=TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for i, e in enumerate(feed.entries[: cfg.PRODUCTHUNT_LIMIT]):
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        tagline = clean(summary.split("Discussion")[0])
        if _blocked(e.get("title", ""), tagline):
            continue
        items.append(Item(
            source="Product Hunt · новинки",
            title=e.get("title", ""),
            url=e.get("link", ""),
            description=tagline,
            metric="свежий запуск",
            score=cfg.PRODUCTHUNT_LIMIT - i,
        ))
    return items


# ── Новости стартапов (раунды, запуски) ───────────────────────────────────────

def fetch_news(s: requests.Session) -> list[Item]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.NEWS_MAX_AGE_HOURS)
    items: list[Item] = []
    for name, url in cfg.NEWS_FEEDS.items():
        r = s.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        for e in feed.entries[:25]:
            published = e.get("published_parsed") or e.get("updated_parsed")
            if published and datetime(*published[:6], tzinfo=timezone.utc) < cutoff:
                continue
            items.append(Item(
                source=name,
                title=e.get("title", ""),
                url=e.get("link", ""),
                description=clean(e.get("summary")),
                metric="новость за последние 48 ч",
                score=0,
            ))
    return items


# ── Сбор всего вместе ─────────────────────────────────────────────────────────

SOURCES = {
    "Hacker News": fetch_hackernews,
    "GitHub": fetch_github,
    "Product Hunt": fetch_producthunt,
    "Hugging Face": fetch_huggingface,
    "Reddit": fetch_reddit,
    "TechCrunch": fetch_news,
}


def collect_all() -> tuple[list[Item], dict[str, int | None]]:
    """Запускает все источники параллельно. Возвращает (сигналы, {источник: кол-во или None при ошибке})."""
    status: dict[str, int | None] = {}
    results: list[Item] = []

    def run(name_fn):
        name, fn = name_fn
        try:
            got = fn(_session())
            log.info("%-13s → %d сигналов", name, len(got))
            return name, got
        except Exception as e:
            log.warning("%-13s → ошибка: %s", name, str(e)[:160])
            return name, None

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        for name, got in pool.map(run, SOURCES.items()):
            status[name] = None if got is None else len(got)
            results.extend(got or [])

    # убираем дубли по ссылке (один проект может быть и на HN, и на GitHub)
    unique: dict[str, Item] = {}
    for it in results:
        key = it.url.rstrip("/").lower()
        if it.title and key and key not in unique:
            unique[key] = it
    return list(unique.values()), status
