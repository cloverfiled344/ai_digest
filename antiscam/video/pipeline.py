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
    # Telegram даёт боту удалить сообщение только в первые 48 часов, а ролик заменяет исходный пост —
    # поэтому выбираем из постов не старше video.max_age_hours (по умолчанию 44 ч)
    since = max(last or datetime.min.replace(tzinfo=timezone.utc),
                datetime.now(timezone.utc) - timedelta(hours=v.get("max_age_hours", 44))).isoformat()
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


def channel_caption(post, meta):
    """Подпись под роликом — весь пост в одном сообщении (сжатый до лимита Telegram 1024 символа).
    HTML: место и заголовок жирным, разделы как в обычном посте, хэштеги из исходного поста."""
    import html as H
    import re
    e = lambda x: H.escape(str(x or "").strip())  # noqa: E731
    src = post.get("text") or ""
    loc = re.search(r"📍\s*<b>(.*?)</b>", src)
    tags = " ".join(re.findall(r"(?<!\w)#[\wА-Яа-яЁё_]+", plain(src.split("Источник")[-1] if "Источник" in src else src)))
    tg = meta.get("tg") or {}
    title = e(tg.get("title") or post.get("title"))
    flags = [e(f) for f in (tg.get("flags") or [])[:3] if f]
    todo = [e(t) for t in (tg.get("todo") or [])[:2] if t]
    parts = [f"📍 <b>{loc.group(1)}</b>" if loc else "", f"🎬 <b>{title}</b>",
             f"<b>В чём подвох:</b> {e(tg.get('how'))}" if tg.get("how") else e(meta.get("threads_text")),
             ("<b>Признаки:</b>\n" + "\n".join(f"❌ {f}" for f in flags)) if flags else "",
             ("<b>Что делать:</b>\n" + "\n".join(f"✅ {t}" for t in todo)) if todo else "",
             (src_line.group(0) if (src_line := re.search(r"📰 Источник:[^\n]*", src)) else ""),
             "👇 Перешли родителям — пусть тоже знают", tags]
    parts = [p for p in parts if p]
    visible = lambda ps: len(re.sub(r"<[^>]+>", "", H.unescape("\n\n".join(ps))))  # noqa: E731
    while visible(parts) > 1000 and len(parts) > 3:  # не влезает — убираем разделы с конца (кроме хэштегов)
        parts.pop(-2)
    if "<a " in "".join(parts) and "</a>" not in "".join(parts):
        parts = [p for p in parts if "<a " not in p]
    return "\n\n".join(parts)


def send_for_review(chat, out_dir, post, meta):
    """Ролик админу с кнопками. Возвращает file_id видео в Telegram (по нему ролик потом уйдёт в канал)."""
    # чтобы нажатия кнопок точно доходили до бота (Telegram помнит allowed_updates прошлого getUpdates)
    tg("getUpdates", json={"timeout": 0, "limit": 1,
                           "allowed_updates": ["message", "channel_post", "my_chat_member", "callback_query"]})
    cap = channel_caption(post, meta)
    why = f"\n\n🤔 Почему этот пост: {post['why']}" if post.get("why") else ""
    head = "🎬 Ролик на проверку. После «Опубликовать» в канале выйдет одно сообщение — ролик с этим текстом, а исходный текстовый пост удалится:\n\n"
    keyboard = {"inline_keyboard": [[{"text": "✅ Опубликовать", "callback_data": f"vpub:{post['id']}"},
                                     {"text": "❌ Пропустить", "callback_data": f"vskip:{post['id']}"}]]}
    with open(os.path.join(out_dir, "video.mp4"), "rb") as vf, open(os.path.join(out_dir, "thumb.png"), "rb") as tf:
        data = tg("sendVideo", data={"chat_id": chat, "supports_streaming": "true", "width": 1080, "height": 1920,
                                     "caption": cap, "parse_mode": "HTML", "reply_markup": json.dumps(keyboard)},
                  files={"video": ("video.mp4", vf, "video/mp4"), "cover": ("thumb.png", tf, "image/png")})
    if not data.get("ok"):
        raise SystemExit("Не удалось отправить ролик на проверку")
    tg("sendMessage", json={"chat_id": chat, "text": head.strip() + why})
    tg("sendMessage", json={"chat_id": chat, "text": "📸 Подпись для Instagram:\n\n" + meta["ig_caption"][:3800]})
    tg("sendMessage", json={"chat_id": chat, "text": "🧵 Текст для Threads:\n\n" + meta["threads_text"]})
    return data["result"]["video"]["file_id"], cap


def main():
    v = CFG.get("video") or {}
    if not os.environ.get("ELEVENLABS_VOICE_ID", "").strip() and v.get("voice_id"):
        os.environ["ELEVENLABS_VOICE_ID"] = str(v["voice_id"])  # голос из config.yaml
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "TELEGRAM_BOT_TOKEN"):
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

    chat = (os.environ.get("ADMIN_CHAT_ID", "").strip() or str(v.get("admin_chat_id") or "")).strip()
    file_id = cap = None
    if chat and os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("DRY_RUN") != "1":
        file_id, cap = send_for_review(chat, OUT, post, meta)
    else:
        log("Админ не задан (video.admin_chat_id) или тестовый режим — ролик только в артефактах запуска")

    if os.environ.get("DRY_RUN") != "1" and post["id"] != "test":
        done[post["id"]] = {"day": datetime.now(TZ).strftime("%Y%m%d"), "title": post.get("title"),
                            "voice": meta["voice"], "ts": datetime.now(timezone.utc).isoformat(),
                            # pending — ждёт кнопки в личке; бот (antiscam --loop) опубликует в канал
                            "status": "pending" if file_id else "not_sent", "file_id": file_id,
                            "caption": cap, "replace": post.get("message_id")}
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
