"""Выбирает свежие посты antiscam без ролика, собирает ролики и присылает их на проверку в личку.

  python antiscam/video/pipeline.py            — по расписанию: до video.per_day роликов в день, один за запуск
  POST_ID=20261124-091700 python …/pipeline.py — ролик для конкретного поста

Память — data/antiscam_videos.json: какие посты уже получили ролик.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CFG = yaml.safe_load(open(os.path.join(HERE, "..", "config.yaml"), encoding="utf-8"))
STATE = os.environ.get("STATE_PATH") or os.path.join(ROOT, "data", "antiscam_state.json")
VIDEOS = os.path.join(ROOT, "data", "antiscam_videos.json")
OUT = os.path.join(ROOT, "out_video")
TZ = timezone(timedelta(hours=CFG.get("utc_offset_hours", 6)))


def log(*a):
    print(*a, flush=True)


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def pick(posts, done, v):
    """Лучшие посты без ролика: готовые (MANUAL) → СНГ → мир; напоминания (TIP) пропускаем."""
    today = datetime.now(TZ).strftime("%Y%m%d")
    made_today = sum(1 for d in done.values() if d.get("day") == today)
    if made_today >= v.get("per_day", 2):
        log(f"Сегодня уже {made_today} ролика(ов) — лимит video.per_day")
        return None
    prio = {c: i for i, c in enumerate(v.get("categories", ["MANUAL", "CIS", "WORLD"]))}
    since = (datetime.now(timezone.utc) - timedelta(hours=v.get("max_age_hours", 30))).isoformat()
    cands = [p for p in posts if p["id"] not in done and p.get("category") in prio and p.get("ts", "") >= since]
    cands.sort(key=lambda p: (prio[p["category"]], -int(p["id"].replace("-", ""))))
    return cands[0] if cands else None


def tg(method, **kw):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=180, **kw)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("ok"):
        log(f"Telegram {method}: {r.status_code} {data.get('description')}")
    return data


def send_for_review(chat, out_dir, post, meta):
    with open(os.path.join(out_dir, "video.mp4"), "rb") as vf, open(os.path.join(out_dir, "thumb.png"), "rb") as tf:
        tg("sendVideo", data={"chat_id": chat, "supports_streaming": "true", "width": 1080, "height": 1920,
                              "caption": f"🎬 Ролик к посту: {post.get('title', '')[:200]}\nГолос: {meta['voice']}"},
           files={"video": ("video.mp4", vf, "video/mp4"), "cover": ("thumb.png", tf, "image/png")})
    tg("sendMessage", json={"chat_id": chat, "text": "📸 Подпись для Instagram:\n\n" + meta["ig_caption"][:3800]})
    tg("sendMessage", json={"chat_id": chat, "text": "🧵 Текст для Threads:\n\n" + meta["threads_text"]})


def main():
    v = CFG.get("video") or {}
    state = load(STATE, {})
    posts = state.get("recent_posts", [])
    done = load(VIDEOS, {})
    want = os.environ.get("POST_ID", "").strip()
    if want == "test":  # проверка сборки без Claude: сценарий из public/scenario.example.json
        post = {"id": "test", "title": "Тестовый ролик «Это ты на видео?»", "category": "MANUAL",
                "scenario": json.load(open(os.path.join(HERE, "public", "scenario.example.json"), encoding="utf-8"))}
    else:
        post = next((p for p in posts if p["id"] == want), None) if want else pick(posts, done, v)
    if not post:
        log("Нет поста для ролика" + (f" с id {want}" if want else ""))
        return
    log(f"Ролик для поста {post['id']} [{post['category']}]: {post.get('title')}")
    os.makedirs(OUT, exist_ok=True)
    post_path = os.path.join(OUT, "post.json")
    json.dump(post, open(post_path, "w", encoding="utf-8"), ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(HERE, "build.py"), post_path, OUT], check=True)
    meta = json.load(open(os.path.join(OUT, "meta.json"), encoding="utf-8"))

    chat = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if chat and os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("DRY_RUN") != "1":
        send_for_review(chat, OUT, post, meta)
    else:
        log("ANTISCAM_ADMIN_CHAT_ID не задан или тестовый режим — ролик только в артефактах запуска")

    if os.environ.get("DRY_RUN") != "1" and post["id"] != "test":
        done[post["id"]] = {"day": datetime.now(TZ).strftime("%Y%m%d"), "title": post.get("title"),
                            "voice": meta["voice"], "ts": datetime.now(timezone.utc).isoformat()}
        # храним 60 последних
        done = dict(sorted(done.items())[-60:])
        os.makedirs(os.path.dirname(VIDEOS), exist_ok=True)
        json.dump(done, open(VIDEOS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
