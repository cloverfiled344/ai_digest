"""Sound: synthesized SFX + music + VO mix -> public/audio/mix.wav (-14 LUFS). Everything generated, no samples.
Usage: python3 engine/audio.py [script.json]   (after voice.py; run from the project folder)"""
import json, subprocess, sys
import numpy as np, soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100
rng = np.random.default_rng(7)


def T(d): return np.arange(int(d * SR)) / SR
def E(d, tau): return np.exp(-T(d) / tau)
def lp(x, f, o=2): return sosfilt(butter(o, f, "low", fs=SR, output="sos"), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, "high", fs=SR, output="sos"), x)
def bp(x, a, b, o=2): return sosfilt(butter(o, [a, b], "band", fs=SR, output="sos"), x)
def midi(n): return 440 * 2 ** ((n - 69) / 12)
def noise(d): return rng.standard_normal(int(d * SR))


def sweep(f0, f1, d):
    t = T(d)
    return 2 * np.pi * np.cumsum(f0 * (f1 / f0) ** (t / d)) / SR


def place(buf, x, t, g=1.0):
    i = int(t * SR)
    if 0 <= i < len(buf):
        j = min(len(buf), i + len(x))
        buf[i:j] += g * x[: j - i]


def fade(x, a=0.005, r=0.02):
    x = x.copy()
    na, nr = int(a * SR), int(r * SR)
    if na: x[:na] *= np.linspace(0, 1, na)
    if nr: x[-nr:] *= np.linspace(1, 0, nr)
    return x


def bell(f, d=2.0, amp=0.35):
    t, x = T(d), 0
    for r, a, tau in [(1, 1, .9), (2, .5, .6), (2.76, .35, .45), (5.4, .2, .25), (8.93, .08, .15)]:
        x = x + a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / tau)
    return fade(x * amp, 0.002, 0.1)


# ---------------- SFX library (name -> function(**args)) ----------------
def boom(d=1.4):
    return fade(np.tanh(1.6 * (np.sin(sweep(110, 32, d)) * E(d, .45) + lp(noise(d), 400) * E(d, .12) * .6
                               + np.sin(2 * np.pi * 45 * T(d)) * E(d, .6) * .5)) * .9)


def whoosh(d=0.6, lo=300, hi=6000, down=False):
    n, x, out = int(d * SR), noise(d), np.zeros(int(d * SR))
    for k in range(0, n, 512):
        p = k / n
        f = lo * (hi / lo) ** ((1 - p) if down else p)
        out[k:k + 512] = bp(x[k:k + 512], max(60, f * .6), min(SR / 2 - 100, f * 1.4), 1)
    return fade(lp(out, 9000) * np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5 * 1.4)


def pop(f0=700, f1=260, d=0.12):
    return fade(np.sin(sweep(f0, f1, d)) * E(d, .04) * .8, .001, .01)


def glitch(d=0.42):
    t = T(d)
    sq = np.sign(np.sin(2 * np.pi * 180 * t)) * .4 + np.sign(np.sin(2 * np.pi * 247 * t)) * .3
    return fade(lp(sq * (np.floor(t * 28) % 3 != 1), 3500) * E(d, .2) * .7)


def burst(d=0.9):
    sp = np.zeros(int(d * SR))
    for k in range(7):
        place(sp, np.sin(2 * np.pi * rng.uniform(1800, 4200) * T(.35)) * E(.35, .07) * .18, .03 + k * .045)
    return fade(np.tanh(hp(noise(d), 1500) * E(d, .035) * .9 + np.sin(sweep(160, 50, d)) * E(d, .12) + sp))


def powerdown(d=0.9):
    ph = sweep(520, 70, d)
    return fade(lp((np.sin(ph) + .4 * np.sin(2 * ph) + .2 * np.sin(3 * ph)) * np.linspace(1, .2, int(d * SR)), 2500) * .5)


def powerup(d=0.7):
    ph = sweep(140, 1100, d)
    sh = np.zeros(int(d * SR))
    for k, n in enumerate([84, 88, 91, 96, 100, 103]):
        place(sh, np.sin(2 * np.pi * midi(n) * T(.4)) * E(.4, .12) * .25, .25 + k * .06)
    return fade(lp((np.sin(ph) + .35 * np.sin(2 * ph)) * np.linspace(.3, 1, int(d * SR)), 4000) * .45 + sh)


def sparkle(n=8, spread=0.45):
    out = np.zeros(int((spread + .5) * SR))
    for _ in range(n):
        f = midi(rng.choice([88, 91, 93, 95, 98, 100]))
        place(out, np.sin(2 * np.pi * f * T(.45)) * E(.45, .1) * .22, rng.uniform(0, spread))
    return out


def click():
    return fade((np.sin(2 * np.pi * 1900 * T(.15)) * E(.15, .008) + np.sin(sweep(300, 120, .15)) * E(.15, .03) * .8) * .7, .0005, .01)


def ding(note=84):
    return bell(midi(note))


def rise(d=1.2):
    n = int(d * SR)
    return fade(bp(noise(d), 800, 6000) * np.linspace(0, 1, n) ** 2 * .35
                + np.sin(sweep(midi(60), midi(72), d)) * np.linspace(0, 1, n) ** 2 * .25)


def crack(d=0.7):
    x = hp(noise(d), 2500) * E(d, .05)
    for _ in range(9):
        place(x, hp(noise(.02), 4000) * .9, rng.uniform(0, .25))
    return fade(np.tanh(x + np.sin(sweep(220, 70, d)) * E(d, .1) * .8))


def fail():
    out = np.zeros(int(1.0 * SR))
    for k, n in enumerate([62, 58]):
        ph = 2 * np.pi * midi(n) * T(.45)
        place(out, fade(lp((np.sin(ph) + .3 * np.sin(2 * ph)) * E(.45, .18), 2000)), k * .22, .45)
    return out


def ice():
    out = np.zeros(int(1.2 * SR))
    for _ in range(12):
        f = midi(rng.choice([96, 98, 100, 103, 105]))
        place(out, np.sin(2 * np.pi * f * T(.6)) * E(.6, .15) * .15, rng.uniform(0, .6))
    return out + hp(noise(1.2), 6000) * np.sin(np.pi * np.linspace(0, 1, len(out))) * .08


def thud(d=0.5):
    return fade(np.sin(sweep(130, 45, d)) * E(d, .12) * .9)


def beep(f=1320, n=1, gap=0.28):
    out = np.zeros(int((n * gap + .1) * SR))
    for k in range(n):
        place(out, fade(np.sin(2 * np.pi * (f + 80 * k) * T(.09)) * .4, .002, .02), k * gap)
    return out


def chime():
    out = np.zeros(int(1.4 * SR))
    place(out, bell(midi(88), 1.2, .3), 0)
    place(out, bell(midi(91), 1.0, .25), .12)
    return out


def bubbles(n=10, every=0.3):
    out = np.zeros(int((n * every + .3) * SR))
    for k in range(n):
        d = .12
        place(out, fade(np.sin(sweep(rng.uniform(300, 500), rng.uniform(900, 1400), d)) * E(d, .05) * .5, .002, .02),
              k * every + rng.uniform(0, every * .5))
    return out


def heartbeat(n=2, bpm=70):
    out = np.zeros(int((n * 60 / bpm + .5) * SR))
    k = np.sin(sweep(90, 40, .3)) * E(.3, .08)
    for i in range(n):
        place(out, k, i * 60 / bpm, .9)
        place(out, k, i * 60 / bpm + .22, .6)
    return out


def tick(n=4, every=0.25):
    out = np.zeros(int((n * every + .1) * SR))
    for k in range(n):
        place(out, fade(hp(noise(.03), 3000) * E(.03, .006), .0005, .005), k * every, .8)
    return out


def swish(d=0.35):
    return whoosh(d, 1500, 600, False) * .8


SFX = {k: v for k, v in globals().items() if callable(v) and k in
       "boom whoosh pop glitch burst powerdown powerup sparkle click ding rise crack fail ice thud beep chime bubbles heartbeat tick swish".split()}

# ---------------- music ----------------
PROGS = {  # (bass midi, chord midi notes) per bar
    "mystery": [(45, [57, 60, 64]), (41, [57, 60, 65]), (48, [55, 60, 64]), (40, [56, 59, 64])],  # Am F C E
    "dark": [(38, [57, 62, 65]), (46, [58, 62, 65]), (41, [57, 60, 65]), (48, [55, 60, 64])],     # Dm Bb F C
    "hope": [(41, [57, 60, 65]), (43, [55, 59, 62]), (45, [57, 60, 64]), (48, [55, 60, 64])],     # F G Am C
    "bright": [(48, [55, 60, 64]), (43, [55, 59, 62]), (45, [57, 60, 64]), (41, [57, 60, 65])],   # C G Am F
}


def saw(f, d, det=0.0):
    t, x = T(d), 0
    for h in range(1, 14):
        x = x + np.sin(2 * np.pi * f * (1 + det) * h * t) / h
    return x


def music(total, sections, bpm=120):
    """sections: [{"t": start_sec, "prog": name, "energy": 1|2|3}] sorted by t."""
    N, beat = int(total * SR), 60 / bpm
    bar = 4 * beat
    pad, bass, arp, drum = (np.zeros(N) for _ in range(4))
    nbars = int(np.ceil(total / bar))
    counters = {}
    for b in range(nbars):
        t0 = b * bar
        si = max([i for i, s in enumerate(sections) if s["t"] <= t0 + 0.5] or [0])
        sec = sections[si]
        idx = counters.get(si, 0)
        counters[si] = idx + 1
        root, tones = PROGS[sec["prog"]][idx % 4]
        en = sec.get("energy", 1)
        d = bar + .6
        p = sum(saw(midi(n), d, .003) + saw(midi(n), d, -.004) for n in tones)
        envp = np.minimum(1, T(d) / .35) * np.minimum(1, np.maximum(0, (d - T(d)) / .6))
        place(pad, lp(p, [1200, 1900, 2800][en - 1]) * envp, t0, .05)
        for k in range(8):
            x = np.sin(2 * np.pi * midi(root) * T(beat / 2)) + .3 * np.sin(4 * np.pi * midi(root) * T(beat / 2))
            place(bass, fade(np.tanh(1.5 * x) * E(beat / 2, [.1, .14, .18][en - 1]), .002, .02), t0 + k * beat / 2, .33 if k % 2 == 0 else .22)
        seq = tones + [tones[1] + 12, tones[2] + 12, tones[1] + 12]
        step = beat / 2 if en == 1 else beat / 4
        for k in range(int(bar / step)):
            a = np.sin(2 * np.pi * midi(seq[k % len(seq)] + 12) * T(.35)) * E(.35, .09)
            place(arp, fade(a, .001, .02), t0 + k * step, [.06, .085, .095][en - 1])
        kick = np.sin(sweep(110, 42, .35)) * E(.35, .09)
        for k in range(4):
            tb = t0 + k * beat
            if en == 1:
                if k in (0, 2):
                    place(drum, kick, tb, .45)
                    place(drum, kick, tb + .22, .28)
            else:
                place(drum, kick, tb, .5)
                place(drum, hp(noise(.05), 7000) * E(.05, .012), tb + beat / 2, .12)
                if en == 3 and k in (1, 3):
                    place(drum, bp(noise(.18), 900, 5000) * E(.18, .05), tb, .25)
    m = pad + bass + arp + drum
    m[-int(1.2 * SR):] *= np.linspace(1, .15, int(1.2 * SR))
    return m


def main():
    sp = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "script.json"))
    tl = json.load(open("public/timeline.json"))
    cues, total = tl["cues"], tl["total"]
    N = int(total * SR)

    def at(ev):
        return (cues[ev["cue"]] if "cue" in ev else ev.get("t", 0)) + ev.get("offset", 0)

    sfx = np.zeros(N)
    for ev in sp.get("sfx", []):
        place(sfx, SFX[ev["sfx"]](**ev.get("args", {})), at(ev), ev.get("gain", .6))
    ms = sp.get("music", {})
    secs = [{"t": at(s) if ("cue" in s or "t" in s) else 0, **{k: v for k, v in s.items() if k in ("prog", "energy")}}
            for s in ms.get("sections", [{"t": 0, "prog": "mystery", "energy": 1}])]
    mus = music(total, sorted(secs, key=lambda s: s["t"]), ms.get("bpm", 120))

    vo = np.zeros(N)
    chain = ("aresample=44100,highpass=f=90,equalizer=f=250:t=q:w=1:g=-1.5,equalizer=f=4200:t=q:w=1.5:g=1.5,"
             "acompressor=threshold=-21dB:ratio=2.5:attack=6:release=90:makeup=2") if tl["lang"] == "en" else \
            ("aresample=44100,highpass=f=75,equalizer=f=220:t=q:w=1:g=-2,equalizer=f=3200:t=q:w=1.2:g=3,"
             "acompressor=threshold=-20dB:ratio=3:attack=4:release=80:makeup=2")
    for ln in tl["lines"]:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"public/vo/s{ln['i']}.wav", "-af", chain,
                        "-ac", "1", f"public/vo/p{ln['i']}.wav"], check=True)
        x, _ = sf.read(f"public/vo/p{ln['i']}.wav", dtype="float64")
        place(vo, x, ln["start"])
    vo /= np.max(np.abs(vo)) + 1e-9
    ir = lp(noise(.45), 5500) * np.exp(-T(.45) / .1)
    ir[: int(.012 * SR)] = 0
    wet = fftconvolve(vo, ir)[:N]
    vo = vo + ms.get("reverb", .16) * wet * np.sqrt(np.mean(vo ** 2) / (np.mean(wet ** 2) + 1e-12))
    vo /= np.max(np.abs(vo)) + 1e-9
    envv = np.convolve(np.abs(vo), np.ones(int(.05 * SR)) / int(.05 * SR), "same")
    duck = lp(1 - .45 * np.clip(envv / .08, 0, 1), 6, 1)
    mix = np.tanh((vo * .95 + mus * ms.get("level", .55) * duck + sfx * sp.get("sfx_level", .55)) * 1.05) * .9
    sf.write("public/audio/mix_raw.wav", np.stack([mix, mix], 1), SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "public/audio/mix_raw.wav", "-af",
                    "loudnorm=I=-14:TP=-1.0:LRA=9", "-ar", "48000", "public/audio/mix.wav"], check=True)
    print(f"mix ok: {total:.2f}s, {len(sp.get('sfx', []))} sfx, {len(secs)} music sections")


if __name__ == "__main__":
    main()
