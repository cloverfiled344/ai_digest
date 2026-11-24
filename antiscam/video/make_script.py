"""scenario.json -> script.json для движка озвучки (voice.py / audio.py): реплики, музыка, звуки по сценам."""
import json, os, sys

src = sys.argv[1] if len(sys.argv) > 1 else "public/scenario.json"
dst = sys.argv[2] if len(sys.argv) > 2 else "script.json"
sc = json.load(open(src, encoding="utf-8"))
lines, sfx = [], [{"sfx": "boom", "t": 0, "gain": 0.8}]
music = [{"t": 0, "prog": "mystery", "energy": 1}]
seen = set()
for i, ln in enumerate(sc["lines"]):
    lid = ln.get("id") or f"s{i}"
    text = ln["text"].replace("«", "").replace("»", "").replace('"', "").replace("—", ",")
    lines.append({"id": lid, "text": text, **({"pause": ln["pause"]} if "pause" in ln else {})})
    kind = ln["scene"]
    if i:
        sfx.append({"sfx": "whoosh", "cue": lid, "offset": -0.3, "gain": 0.45, "args": {"d": 0.5, "lo": 300, "hi": 7000}})
    if kind == "hook":
        sfx += [{"sfx": "beep", "cue": lid, "offset": 0.35, "gain": 0.45, "args": {"f": 880, "n": 2, "gap": 0.12}}]
    if kind == "trap":
        sfx += [{"sfx": "glitch", "cue": lid, "offset": 0.8, "gain": 0.45}]
        if "dark" not in seen:
            music.append({"cue": lid, "prog": "dark", "energy": 2}); seen.add("dark")
    if kind == "loss":
        sfx += [{"sfx": "fail", "cue": lid, "offset": 0.9, "gain": 0.55}]
    if kind == "todo" and "hope" not in seen:
            music.append({"cue": lid, "prog": "hope", "energy": 2}); seen.add("hope")
    if kind == "outro" and "bright" not in seen:
        music.append({"cue": lid, "prog": "bright", "energy": 1}); seen.add("bright")
sfx.append({"sfx": "chime", "cue": "end", "gain": 0.5})

# после озвучки (есть public/timeline.json) — звуки на появление сообщений и пунктов списков,
# в те же моменты, что и в scam.tsx: slot(i, k, n) = lerp(L+0.25, LE-0.5, k/(n-1))
if "--slots" in sys.argv:
    tl = json.load(open("public/timeline.json", encoding="utf-8"))
    for i, ln in enumerate(sc["lines"]):
        items = (ln.get("messages") or []) if ln["scene"] == "chat" else (ln.get("items") or [])[:4] if ln["scene"] in ("flags", "todo") else []
        L0 = tl["lines"][i]["start"]; L1 = L0 + tl["lines"][i]["dur"]; n = len(items)
        for k in range(n):
            t = L0 + 0.25 + ((L1 - 0.5) - (L0 + 0.25)) * (0 if n <= 1 else k / (n - 1))
            name = {"chat": "pop", "flags": "click", "todo": "ding"}[ln["scene"]]
            sfx.append({"sfx": name, "t": round(t, 3), "gain": 0.45 if name != "ding" else 0.35,
                        **({"args": {"f0": 700 + 50 * k}} if name == "pop" else {"args": {"note": 76 + 2 * k}} if name == "ding" else {})})
eleven = bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID"))
script = {"lang": "ru", "voice": "elevenlabs" if eleven else sc.get("voice", "dmitri"),
          "speed": 1.0 if eleven else sc.get("speed", 1.05), "pause": 0.3, "end_card": 2.5,
          "lines": lines, "caption_fixes": sc.get("caption_fixes", []), "cues": {},
          "music": {"bpm": 112, "sections": music, "level": 0.45}, "sfx": [s for s in sfx if s.get("gain", 1) > 0]}
json.dump(script, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"script.json: {len(lines)} реплик")
