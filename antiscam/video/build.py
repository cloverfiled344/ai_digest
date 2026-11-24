"""Ролик по посту antiscam: пост → сценарий (Claude) → озвучка → видео 1080×1920 + обложка + подписи для соцсетей.

  python antiscam/video/build.py <post.json> <out_dir>

post.json — запись из state["recent_posts"] (text — HTML поста в Telegram).
В out_dir появятся video.mp4, thumb.png, meta.json (сценарий и подписи для Instagram и Threads).
Озвучка: ElevenLabs, если заданы ELEVENLABS_API_KEY и ELEVENLABS_VOICE_ID, иначе бесплатный голос Piper.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "config.yaml")

SCENES = ("hook", "chat", "trap", "loss", "flags", "todo", "outro")
TRAPS = ("file", "link", "code", "call", "card")
LOSSES = ("sms", "account", "money", "contacts")

PROMPT = """Ты сценарист коротких вертикальных роликов (30–40 секунд) для канала о мошенничестве.
По посту ниже напиши сценарий 2D-анимации на русском. Ролик собирается из готовых сцен:
- hook — первая реплика: цепляющий вопрос или фраза, которую пишет/говорит мошенник. На экране телефон с уведомлением.
- chat — переписка или разговор с мошенником; messages — 1–3 сообщения, которые видит жертва: {{"from":"them"|"me","text":"..."}}, или файл {{"from":"them","file":"имя.apk"}}, или ссылка {{"from":"them","link":"hxxps://адрес[.]com"}}.
- trap — ловушка, trap: file (файл-программа), link (поддельная страница входа), code (выманивают код из SMS), call (звонок «из банка/полиции»), card (данные карты).
- loss — последствия, loss: sms (перехват SMS-кодов), account (украден аккаунт), money (списали деньги, amount — сумма строкой, если она есть в посте), contacts (рассылка друзьям).
- flags — признаки обмана, items: 2–4 пункта до 26 символов.
- todo — как защититься, items: 2–4 пункта до 26 символов, конкретные действия.
- outro — последняя реплика: короткий призыв подписаться, чтобы знать схемы.

Правила:
1. 6–8 реплик в порядке: hook, chat (можно 1–2), trap, loss (можно 1–2), flags, todo, outro. Сцены можно пропускать, если не подходят.
2. Всего 80–105 слов. Реплики короткие, разговорные, на «ты». Без кавычек и тире. Числа пиши словами, если они не суммы.
3. Только факты из поста. Никаких имён реальных людей, названий банков, компаний и брендов — пиши «банк», «магазин», «мессенджер».
4. label — подпись сцены заглавными, до 3 слов и 18 символов (например «ЭТО НЕ ВИДЕО»). У hook label не нужен.
5. title_lines — 2 строки для обложки и заголовка, каждая до 10 символов, заглавными (например ["ЭТО ТЫ", "НА ВИДЕО?"]).
6. contact — кто пишет в чате (обычное имя, например «Айбек», или роль: «Служба банка», «Курьер»). caller — кто звонит, если есть звонок.
7. ig_caption — подпись для Instagram: 2–3 коротких абзаца (что за схема, главный признак, что делать) + 5 хэштегов на русском. До 900 символов.
8. threads_text — короткая версия для Threads: 2–3 предложения, до 380 символов, без хэштегов и ссылок.
9. ky — одна фраза-предупреждение на кыргызском (до 80 символов) или пустая строка, если не уверен в переводе.

Верни только JSON:
{{"title_lines": ["...", "..."], "contact": "...", "caller": "...", "lines": [{{"scene": "hook", "text": "..."}}, ...], "ig_caption": "...", "threads_text": "...", "ky": "..."}}

Пост:
{post}"""


def log(*a):
    print(*a, flush=True)


def plain(html_text):
    t = re.sub(r"<br\s*/?>", "\n", html_text or "")
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def ask_claude(prompt):
    key = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("VIDEO_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-5-5"
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": prompt}]},
                      timeout=120)
    r.raise_for_status()
    txt = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise SystemExit("Claude не вернул JSON сценария")
    return json.loads(m.group(0))


def clean(s, n):
    s = re.sub(r"[«»\"“”„]", "", str(s or "")).replace("—", ",").replace("–", ",").strip()
    return s[:n]


def sanitize(sc, cfg):
    """Приводит сценарий к тому, что умеет шаблон: известные сцены, ограничения длины."""
    lines = []
    for ln in sc.get("lines", [])[:9]:
        scene = ln.get("scene") if ln.get("scene") in SCENES else None
        text = clean(ln.get("text"), 220)
        if not scene or not text:
            continue
        out = {"scene": scene, "text": text}
        if ln.get("label") and scene != "hook":
            out["label"] = clean(ln["label"], 18).upper()
        if scene == "chat":
            msgs = []
            for m in (ln.get("messages") or [])[:3]:
                mm = {"from": "me" if m.get("from") == "me" else "them"}
                if m.get("file"):
                    mm["file"] = clean(m["file"], 24)
                elif m.get("link"):
                    mm["link"] = clean(m["link"], 40)
                elif m.get("text"):
                    mm["text"] = clean(m["text"], 70)
                else:
                    continue
                msgs.append(mm)
            out["messages"] = msgs
        if scene == "trap":
            out["trap"] = ln.get("trap") if ln.get("trap") in TRAPS else "link"
        if scene == "loss":
            out["loss"] = ln.get("loss") if ln.get("loss") in LOSSES else "money"
            if ln.get("amount"):
                out["amount"] = clean(ln["amount"], 14)
        if scene in ("flags", "todo"):
            out["items"] = [clean(x, 30) for x in (ln.get("items") or [])[:4] if x]
            if not out["items"]:
                continue
        lines.append(out)
    if len(lines) < 4:
        raise SystemExit(f"Сценарий слишком короткий: {len(lines)} реплик")
    if lines[0]["scene"] != "hook":
        lines[0]["scene"] = "hook"
    for i, ln in enumerate(lines):
        ln["id"] = f"s{i}"
    v = cfg.get("video") or {}
    title = [clean(x, 12).upper() for x in (sc.get("title_lines") or [])][:2] or ["ОСТОРОЖНО", "ОБМАН"]
    return {"title_lines": title, "contact": clean(sc.get("contact") or "Знакомый", 18),
            "caller": clean(sc.get("caller") or "Служба банка", 22), "channel": v.get("channel", ""),
            "socials": v.get("socials") or [], "lines": lines}


def run(cmd, cwd):
    log("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def render(scenario, out_dir):
    pub = os.path.join(HERE, "public")
    for d in ("public/audio", "public/vo", "out"):
        os.makedirs(os.path.join(HERE, d), exist_ok=True)
    with open(os.path.join(pub, "scenario.json"), "w", encoding="utf-8") as f:
        json.dump(scenario, f, ensure_ascii=False, indent=1)
    py = sys.executable
    run([py, "make_script.py"], HERE)
    run([py, "engine/voice.py"], HERE)
    run([py, "make_script.py", "public/scenario.json", "script.json", "--slots"], HERE)
    run([py, "engine/audio.py"], HERE)
    chrome = ["--browser-executable", os.environ["CHROME"]] if os.environ.get("CHROME") else []
    run(["npx", "remotion", "render", "Video", "out/video.mp4", "--log=error", "--codec=h264", "--crf=20",
         "--audio-codec=aac", "--audio-bitrate=192k", f"--concurrency={os.cpu_count() or 2}", *chrome], HERE)
    run(["npx", "remotion", "still", "Thumb", "out/thumb.png", "--log=error", *chrome], HERE)
    os.makedirs(out_dir, exist_ok=True)
    for name in ("video.mp4", "thumb.png"):
        shutil.copy(os.path.join(HERE, "out", name), os.path.join(out_dir, name))


def socials_text(cfg):
    s = (cfg.get("video") or {}).get("socials") or []
    return "\n".join(s)


def main(post_path, out_dir):
    cfg = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    post = json.load(open(post_path, encoding="utf-8"))
    # готовый сценарий (тестовый запуск) или сценарий от Claude
    sc = post.get("scenario") or ask_claude(PROMPT.format(post=plain(post["text"])[:3500]))
    scenario = sanitize(sc, cfg)
    log(json.dumps(scenario, ensure_ascii=False, indent=1))
    render(scenario, out_dir)
    extra = socials_text(cfg)
    meta = {"post_id": post.get("id"), "title": post.get("title"), "scenario": scenario,
            "ig_caption": (str(sc.get("ig_caption") or "")[:1800] + ("\n\n" + extra if extra else "")).strip(),
            "threads_text": str(sc.get("threads_text") or "")[:420].strip(), "ky": str(sc.get("ky") or "")[:120],
            "voice": json.load(open(os.path.join(HERE, "script.json"), encoding="utf-8")).get("voice")}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"Готово: {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
