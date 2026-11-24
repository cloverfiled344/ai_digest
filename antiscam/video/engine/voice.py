"""Voiceover: script.json -> public/vo/s*.wav + public/timeline.json (word times, cues, total).
Usage: python3 engine/voice.py [script.json]   (run from the project folder)"""
import difflib, json, os, re, sys
import numpy as np, sherpa_onnx, soundfile as sf

M = os.environ.get("MODELS", "/home/claude/models")
KOK = f"{M}/kokoro-multi-lang-v1_0"
EN_VOICES = ("af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky "
             "am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa "
             "bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis").split()


class ElevenLabs:
    """Озвучка голосом из ElevenLabs (ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID). Настройки как у голоса
    «Silk Road»: Multilingual v2, speed 1.0, stability 0.5, similarity 0.75, style 0, speaker boost."""
    def __init__(self, key, voice_id):
        self.key, self.voice_id, self.prev = key, voice_id, ""

    def generate(self, text, speed=1.0, next_text=""):
        import requests
        body = {"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0,
                                   "use_speaker_boost": True, "speed": max(0.7, min(1.2, speed))},
                "previous_text": self.prev[-300:] or None, "next_text": next_text[:300] or None}
        for attempt in range(3):
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=pcm_24000",
                              headers={"xi-api-key": self.key, "content-type": "application/json"}, json=body, timeout=120)
            if r.status_code == 200:
                break
            if r.status_code in (401, 403, 404, 422):
                raise SystemExit(f"ElevenLabs: {r.status_code} {r.text[:300]}")
            import time; time.sleep(5 * (attempt + 1))
        r.raise_for_status()
        self.prev = (self.prev + " " + text).strip()
        return np.frombuffer(r.content, dtype="<i2").astype(np.float32) / 32768.0, 24000


class Clone:
    """Голос по образцу (voice/ref.flac) — Chatterbox Multilingual (MIT), работает на CPU.
    Образец английский, поэтому cfg_weight по умолчанию 0: меньше акцента при русской речи."""
    def __init__(self, ref):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        import torch
        torch.set_num_threads(os.cpu_count() or 2)
        self.m = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
        self.ex = float(os.environ.get("CLONE_EXAGGERATION", "0.5"))
        self.cfg = float(os.environ.get("CLONE_CFG", "0"))
        self.m.prepare_conditionals(ref, exaggeration=self.ex)

    def generate(self, text, speed=1.0, next_text=""):
        import torch
        torch.manual_seed(7)
        wav = self.m.generate(text, language_id="ru", exaggeration=self.ex, cfg_weight=self.cfg, temperature=0.7)
        x = wav.squeeze(0).cpu().numpy().astype(np.float32)
        rate = float(os.environ.get("CLONE_SPEED", "1.15")) * speed  # клон говорит медленно — ускоряем без смены тона
        if abs(rate - 1) > 0.01:
            import librosa
            x = librosa.effects.time_stretch(x, rate=rate).astype(np.float32)
        return x, self.m.sr


def make_tts(lang, voice):
    if voice == "clone":
        return Clone(os.environ.get("CLONE_REF", "voice/ref.flac")), None
    if voice == "elevenlabs":
        return ElevenLabs(os.environ["ELEVENLABS_API_KEY"], os.environ["ELEVENLABS_VOICE_ID"]), None
    if lang == "en":
        mc = sherpa_onnx.OfflineTtsModelConfig(kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=f"{KOK}/model.onnx", voices=f"{KOK}/voices.bin", tokens=f"{KOK}/tokens.txt",
            data_dir=f"{KOK}/espeak-ng-data", dict_dir=f"{KOK}/dict",
            lexicon=f"{KOK}/lexicon-us-en.txt,{KOK}/lexicon-zh.txt"), num_threads=2)
        return sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=mc, max_num_sentences=1, silence_scale=0.3)), EN_VOICES.index(voice)
    base = f"{M}/vits-piper-ru_RU-{voice}-medium"
    mc = sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(
        model=f"{base}/ru_RU-{voice}-medium.onnx", tokens=f"{base}/tokens.txt", data_dir=f"{base}/espeak-ng-data",
        noise_scale=0.6, noise_scale_w=0.8), num_threads=2)
    return sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=mc)), 0


def make_asr(lang):
    if lang == "en":
        d, sfx = f"{M}/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8", ".int8"
    else:
        d, sfx = f"{M}/sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19", ""
    enc = f"{d}/encoder.int8.onnx"
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=enc, decoder=f"{d}/decoder{sfx}.onnx", joiner=f"{d}/joiner{sfx}.onnx",
        tokens=f"{d}/tokens.txt", model_type="nemo_transducer", num_threads=2)


def synth(tts, sid, text, speed, next_text=""):
    if isinstance(tts, (ElevenLabs, Clone)):
        x, sr = tts.generate(text, speed, next_text)
    else:
        a = tts.generate(text, sid=sid, speed=speed)
        x, sr = np.array(a.samples, dtype=np.float32), a.sample_rate
    idx = np.where(np.abs(x) > 0.008)[0]
    if len(idx):
        p = int(0.04 * sr)
        x = x[max(0, idx[0] - p): idx[-1] + p]
    return x, sr


def to16k(x, sr):
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr == 16000:
        return x.astype(np.float32)
    n = int(len(x) * 16000 / sr)
    return np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x).astype(np.float32)


def recognize(rec, x, sr):
    s = rec.create_stream()
    s.accept_waveform(16000, to16k(x, sr))
    rec.decode_stream(s)
    words, new = [], True
    for tok, ts in zip(s.result.tokens, s.result.timestamps):
        if tok.strip() == "":
            new = True
            continue
        if tok[0] in " ▁":
            new = True
        tok = tok.strip(" ▁")
        if new or not words:
            words.append([tok, ts])
            new = False
        else:
            words[-1][0] += tok
    return s.result.text, [(w, t) for w, t in words if norm(w)]


def norm(w):
    return re.sub(r"[^a-zа-я0-9]", "", w.lower().replace("ё", "е"))


def align(disp, heard, dur):
    a, b = [norm(w) for w in disp], [norm(w) for w, _ in heard]
    times = [None] * len(disp)
    for blk in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = heard[blk.b + k][1]
    anchors = [(-1, 0.0)] + [(i, t) for i, t in enumerate(times) if t is not None] + [(len(disp), dur)]
    for (i0, t0), (i1, t1) in zip(anchors, anchors[1:]):
        if i1 - i0 > 1:  # spread unmatched words by character length
            lens = [len(disp[i]) + 1 for i in range(i0 + 1, i1)]
            acc = len(disp[i0]) + 1 if i0 >= 0 else 0
            tot = sum(lens) + acc
            for k, i in enumerate(range(i0 + 1, i1)):
                times[i] = t0 + (t1 - t0) * acc / max(1, tot)
                acc += lens[k]
    for i in range(1, len(times)):
        times[i] = max(times[i], times[i - 1] + 0.05)
    return times


def fix_captions(words, fixes):
    out, i = [], 0
    while i < len(words):
        for f in fixes:
            say = [norm(w) for w in f["say"].split()]
            if [norm(w["w"]) for w in words[i:i + len(say)]] == say:
                tail = re.sub(r"^.*?([.,!?…]*)$", r"\1", words[i + len(say) - 1]["w"])
                out.append({"w": f["show"] + tail, "t": words[i]["t"]})
                i += len(say)
                break
        else:
            out.append(words[i])
            i += 1
    return out


def resolve(cue, lines):
    ln = lines[cue["line"]]
    if "word" in cue:
        hits = [w["t"] for w in ln["words"] if norm(w["w"]).startswith(norm(cue["word"]))]
        if len(hits) < cue.get("n", 1):
            raise SystemExit(f"cue word '{cue['word']}' not found in line {cue['line']}: {ln['text']}")
        t = hits[cue.get("n", 1) - 1]
    else:
        t = ln["start"] + (ln["dur"] if cue.get("at") == "end" else 0)
    return round(t + cue.get("offset", 0), 3)


def main():
    sp = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "script.json"))
    lang = sp["lang"]
    voice = sp.get("voice", "am_michael" if lang == "en" else "dmitri")
    tts, sid = make_tts(lang, voice)
    rec = make_asr(lang)
    os.makedirs("public/vo", exist_ok=True)
    lines, t = [], sp.get("lead_in", 0.15)
    for i, ln in enumerate(sp["lines"]):
        nxt = sp["lines"][i + 1]["text"] if i + 1 < len(sp["lines"]) else ""
        x, sr = synth(tts, sid, ln["text"], ln.get("speed", sp.get("speed", 1.0)), nxt)
        sf.write(f"public/vo/s{i}.wav", x, sr)
        dur = len(x) / sr
        heard, hw = recognize(rec, x, sr)
        disp = [w for w in ln["text"].replace("...", "… ").replace(" — ", " ").split() if norm(w)]
        rel = align(disp, hw, dur)
        words = [{"w": w.replace("…", ""), "t": round(t + r, 3)} for w, r in zip(disp, rel)]
        words = fix_captions(words, sp.get("caption_fixes", []))
        score = difflib.SequenceMatcher(a=[norm(w["w"]) for w in words], b=[norm(w) for w, _ in hw]).ratio()
        lines.append({"i": i, "id": ln.get("id", f"l{i}"), "text": ln["text"], "start": round(t, 3),
                      "dur": round(dur, 3), "words": words, "heard": heard, "match": round(score, 2)})
        flag = "" if score > 0.85 else "   <-- CHECK pronunciation"
        print(f"[{i}] {t:6.2f}s +{dur:4.2f}s  match {score:.2f}  heard: {heard}{flag}")
        t += dur + ln.get("pause", sp.get("pause", 0.28))
    speech_end = lines[-1]["start"] + lines[-1]["dur"]
    cues = {"start": 0.0}
    for i, ln in enumerate(lines):
        cues[f"L{i}"] = ln["start"]
        cues[ln["id"]] = ln["start"]
    for k, c in sp.get("cues", {}).items():
        cues[k] = resolve(c, lines)
    cues["end"] = round(speech_end + 0.15, 3)
    total = round(cues["end"] + sp.get("end_card", 2.2), 2)
    json.dump({"fps": 30, "lang": lang, "total": total, "lines": lines, "cues": cues},
              open("public/timeline.json", "w"), ensure_ascii=False, indent=1)
    print(f"speech {speech_end:.2f}s, total {total:.2f}s")
    print("cues:", json.dumps(cues, ensure_ascii=False))


if __name__ == "__main__":
    main()
