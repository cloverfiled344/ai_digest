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


def last_video(done):
    ts = [d.get("ts", "") for k, d in done.items() if k != "test" and d.get("ts")]
    return datetime.fromisoformat(max(ts)) if ts else None


def is_due(done, v):
    """Пора ли делать ролик: прошло video.every_days дней с прошлого."""
    last = last_video(done)
    every = timedelta(days=v.get("every_days", 5))
    if last and datetime.now(timezone.utc) - last < every - timedelta(hours=2):
        log(f"Прошлый ролик {last:%d.%m %H:%M} UTC — следующий через {every - (datetime.now(timezone.utc) - last)}")
        return False
    return True


PICK_PROMPT = """Ты продюсер канала о мошенничестве. Раз в {days} дней мы делаем один короткий анимированный ролик
для Instagram Reels и Threads по самому сильному посту. Выбери ОДИН пост из списка.

Лучший пост для ролика:
- схема понятна за 30 секунд и её легко показать: сообщение, звонок, ссылка, файл, код из SMS;
- касается многих людей (мессенджеры, банки, покупки, родственники), а не узкой группы;
- есть ясный урок: признак обмана и что делать;
- лучше новая или набирающая обороты схема, чем давно известная;
- приоритет историям из СНГ, особенно Кыргызстана, но сильная мировая схема тоже подходит.

Верни только JSON: {{"id": "id выбранного поста", "why": "одно предложение, почему он"}}

Посты:
{posts}"""


def plain(t):
    import html, re
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", t or ""))).strip()


def pick(posts, done, v):
    """Лучший пост за период без ролика — выбирает Claude; напоминания (TIP) не берём."""
    cats = set(v.get("categories", ["MANUAL", "CIS", "WORLD"]))
    last = last_video(done)
    since = max(last or datetime.min.replace(tzinfo=timezone.utc),
                datetime.now(timezone.utc) - timedelta(days=v.get("every_days", 5), hours=12)).isoformat()
    cands = [p for p in posts if p["id"] not in done and p.get("category") in cats and p.get("ts", "") >= since]
    log(f"Кандидатов за период: {len(cands)}")
    if len(cands) <= 1:
        return cands[0] if cands else None
    listing = "\n\n".join(f"id: {p['id']} [{p['category']}]\n{plain(p['text'])[:600]}" for p in cands[-45:])
    try:
        import re
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=120,
                          headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": os.environ.get("VIDEO_MODEL") or "claude-sonnet-5-5", "max_tokens": 400,
                                "messages": [{"role": "user", "content": PICK_PROMPT.format(days=v.get("every_days", 5), posts=listing)}]})
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", []))
        choice = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        best = next((p for p in cands if p["id"] == str(choice.get("id"))), None)
        if best:
            best["why"] = choice.get("why", "")
            log(f"Claude выбрал {best['id']}: {best['why']}")
            return best
    except Exception as ex:  # не смогли выбрать — берём по приоритету рубрик
        log(f"Выбор Claude не удался: {ex}")
    prio = {c: i for i, c in enumerate(v.get("categories", ["MANUAL", "CIS", "WORLD"]))}
    return sorted(cands, key=lambda p: (prio.get(p["category"], 9), -int(p["id"].replace("-", ""))))[0]


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
                              "caption": f"🎬 Ролик к посту: {post.get('title', '')[:200]}\n{('Почему этот: ' + post['why']) if post.get('why') else ''}"[:1000]},
           files={"video": ("video.mp4", vf, "video/mp4"), "cover": ("thumb.png", tf, "image/png")})
    tg("sendMessage", json={"chat_id": chat, "text": "📸 Подпись для Instagram:\n\n" + meta["ig_caption"][:3800]})
    tg("sendMessage", json={"chat_id": chat, "text": "🧵 Текст для Threads:\n\n" + meta["threads_text"]})


def main():
    v = CFG.get("video") or {}
    if not os.environ.get("ELEVENLABS_VOICE_ID", "").strip() and v.get("voice_id"):
        os.environ["ELEVENLABS_VOICE_ID"] = str(v["voice_id"])  # голос из config.yaml
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ADMIN_CHAT_ID", "TELEGRAM_BOT_TOKEN"):
        log(f"{name}: {'задан' if os.environ.get(name, '').strip() else 'НЕ ЗАДАН'}")
    state = load(STATE, {})
    posts = state.get("recent_posts", [])
    done = load(VIDEOS, {})
    want = os.environ.get("POST_ID", "").strip()
    if want == "test":  # проверка сборки без Claude: сценарий из public/scenario.example.json
        post = {"id": "test", "title": "Тестовый ролик «Это ты на видео?»", "category": "MANUAL",
                "scenario": json.load(open(os.path.join(HERE, "public", "scenario.example.json"), encoding="utf-8"))}
    elif want:
        post = next((p for p in posts if p["id"] == want), None)
    else:
        if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" and not is_due(done, v):
            return
        post = pick(posts, done, v)
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


def check():
    """Для workflow: run=true, если пора делать ролик (или запуск вручную с post_id)."""
    v = CFG.get("video") or {}
    run = bool(os.environ.get("POST_ID", "").strip()) or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" \
        or is_due(load(VIDEOS, {}), v)
    log(f"run={str(run).lower()}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"run={str(run).lower()}\n")


if __name__ == "__main__":
    check() if "--check" in sys.argv else main()
