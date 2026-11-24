"""QA helpers.
  python3 engine/check.py sheet <video.mp4> <out.png> [t1 t2 ...]   contact sheet (default: every cue)
  python3 engine/check.py hear  <video.mp4>                          transcribe final audio vs script"""
import difflib, json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(__file__))


def sheet(video, out, times):
    tl = json.load(open("public/timeline.json"))
    if not times:
        cues = sorted(set(round(v + 0.25, 2) for k, v in tl["cues"].items() if not k.startswith("L") and v < tl["total"]))
        times = cues + [round(tl["total"] - 0.6, 2)]
    for part in range(0, len(times), 24):
        chunk, d = times[part:part + 24], tempfile.mkdtemp()
        for i, t in enumerate(chunk):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", "-update", "1",
                            "-vf", f"scale=270:-1,drawtext=text='{t}':x=6:y=6:fontsize=20:fontcolor=white:box=1:boxcolor=black",
                            f"{d}/f{i:02d}.png"], check=True)
        cols = min(8, len(chunk))
        name = out if len(times) <= 24 else out.replace(".png", f"_{part // 24 + 1}.png")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"{d}/f%02d.png", "-frames:v", "1",
                        "-vf", f"tile={cols}x{(len(chunk) + cols - 1) // cols}", name], check=True)
        print("sheet:", name, "times:", chunk)


def hear(video):
    import voice
    tl = json.load(open("public/timeline.json"))
    wav = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    import soundfile as sf
    x, sr = sf.read(wav, dtype="float32")
    text, _ = voice.recognize(voice.make_asr(tl["lang"]), x, sr)
    want = " ".join(l["text"] for l in tl["lines"])
    a, b = [voice.norm(w) for w in want.split()], [voice.norm(w) for w in text.split()]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    print("heard:", text)
    print(f"match: {sm.ratio():.2f}")
    for op, i0, i1, j0, j1 in sm.get_opcodes():
        if op != "equal":
            print(f"  {op}: script '{' '.join(a[i0:i1])}' vs heard '{' '.join(b[j0:j1])}'")


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet(sys.argv[2], sys.argv[3], [float(x) for x in sys.argv[4:]])
    else:
        hear(sys.argv[2])
