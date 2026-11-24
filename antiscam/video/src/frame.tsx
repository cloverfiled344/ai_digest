// Video shell: scene switching with transitions, word-synced captions, progress bar, vignette, fonts, audio.
import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import { Audio } from "@remotion/media";
import "@fontsource/rubik/700.css";
import "@fontsource/rubik/800.css";
import "@fontsource/rubik/900.css";
import { at, C, clamp, easeIn, easeInOut, easeOut, FONT, H, lerp, pop, W } from "./kit";
import { cue, FPS, TL } from "./tl";

export type Tr = "cut" | "flash" | "push" | "whip" | "iris" | "zoom";
export type Scene = { from: number; comp: React.FC<{ t: number }>; tr?: Tr };
const TRD: Record<Tr, number> = { cut: 0.28, flash: 0.22, push: 0.34, whip: 0.24, iris: 0.42, zoom: 0.36 };

export const useFonts = () => {
  const [h] = useState(() => delayRender("fonts"));
  useEffect(() => {
    Promise.all(["900 80px Rubik", "800 40px Rubik", "700 40px Rubik"].map((f) => document.fonts.load(f, "AgЖё")))
      .then(() => continueRender(h))
      .catch(() => continueRender(h));
  }, [h]);
};

type Page = { words: { w: string; t: number }[]; start: number; end: number };
const buildPages = (maxChars: number): Page[] => {
  const pages: Page[] = [];
  for (const ln of TL.lines) {
    let cur: { w: string; t: number }[] = [], chars = 0;
    const flush = () => {
      if (cur.length) pages.push({ words: cur, start: cur[0].t - 0.06, end: 0 });
      cur = [];
      chars = 0;
    };
    for (const w of ln.words) {
      if (cur.length >= 3 || (cur.length > 0 && chars + w.w.length > maxChars)) flush();
      cur.push(w);
      chars += w.w.length + 1;
      if (/[.,!?:;]$/.test(w.w)) flush();
    }
    flush();
  }
  if (pages.length) pages[0].start = 0;
  pages.forEach((p, i) => (p.end = i + 1 < pages.length ? pages[i + 1].start : cue("end")));
  return pages;
};

const OUTLINE = (() => {
  const s: string[] = [];
  for (let a = 0; a < 16; a++) s.push(`${(Math.cos((a / 16) * Math.PI * 2) * 7).toFixed(1)}px ${(Math.sin((a / 16) * Math.PI * 2) * 7).toFixed(1)}px 0 ${C.ink}`);
  return s.concat(`0 10px 0 ${C.ink}`).join(",");
})();

const Captions: React.FC<{ t: number; pages: Page[]; top: number; size: number }> = ({ t, pages, top, size }) => {
  const page = pages.find((p) => t >= p.start && t < p.end);
  if (!page) return null;
  const pp = page.start === 0 ? 1 : pop(t, page.start, 0.14);
  let active = -1;
  page.words.forEach((w, i) => t >= w.t - 0.03 && (active = i));
  return (
    <div style={{ position: "absolute", left: 90, width: 900, top, display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0px 30px", transform: `scale(${0.82 + 0.18 * pp})`, transformOrigin: "50% 40%" }}>
      {page.words.map((w, i) => (
        <span key={i} style={{ fontFamily: FONT, fontWeight: 900, fontSize: size, lineHeight: 1.12, textTransform: "uppercase", color: i === active ? C.yellow : C.white, textShadow: OUTLINE, display: "inline-block", transform: `scale(${i === active ? 1.08 : 1}) rotate(${i === active ? -1.5 : 0}deg)` }}>
          {w.w.replace(/[.,!?:;]+$/, "")}
        </span>
      ))}
    </div>
  );
};

const Vignette = () => (
  <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
    <defs><radialGradient id="vig" cx="50%" cy="45%" r="75%"><stop offset="60%" stopColor="#000" stopOpacity={0} /><stop offset="100%" stopColor="#000" stopOpacity={0.5} /></radialGradient></defs>
    <rect width={W} height={H} fill="url(#vig)" />
  </svg>
);

/**
 * scenes: contiguous list, each lasts until the next one's `from`. `tr` = transition INTO that scene.
 * hideCaptions: time ranges where a scene shows its own big text. captionTop: y of caption block (keep below main action).
 */
export const Shell: React.FC<{ scenes: Scene[]; hideCaptions?: [number, number][]; captionTop?: number; captionSize?: number; maxChars?: number; progress?: boolean; audio?: string }> = ({ scenes, hideCaptions = [], captionTop = 1290, captionSize = 76, maxChars = 17, progress = true, audio = "audio/mix.wav" }) => {
  useFonts();
  const t = useCurrentFrame() / FPS;
  const [pages] = useState(() => buildPages(maxChars));
  let i = 0;
  scenes.forEach((s, k) => t >= s.from && (i = k));
  const cur = scenes[i], tr: Tr = cur.tr ?? (i === 0 ? "cut" : "flash");
  const k = i === 0 ? 1 : clamp((t - cur.from) / TRD[tr]);
  const Prev = i > 0 ? scenes[i - 1].comp : null, Cur = cur.comp;
  let prevEl: React.ReactNode = null, curEl: React.ReactNode = <Cur t={t} />, flash = 0;
  if (k < 1 && Prev) {
    const e = easeInOut(k);
    if (tr === "push" || tr === "whip") {
      const ee = tr === "whip" ? easeIn(k) : e;
      prevEl = <g transform={`translate(${-W * ee} 0)`}><Prev t={t} /></g>;
      curEl = <g transform={`translate(${W * (1 - ee)} 0)`}><Cur t={t} /></g>;
      if (tr === "whip") flash = 0.25 * Math.sin(k * Math.PI);
    } else if (tr === "iris") {
      const r = lerp(0, 1500, easeIn(k));
      prevEl = <Prev t={t} />;
      curEl = (
        <g>
          <clipPath id={`iris${i}`}><circle cx={540} cy={860} r={r} /></clipPath>
          <g clipPath={`url(#iris${i})`}><Cur t={t} /></g>
          <circle cx={540} cy={860} r={r} fill="none" stroke={C.white} strokeWidth={18 * (1 - k)} />
        </g>
      );
    } else if (tr === "zoom") {
      prevEl = <g transform={at(540, 860, 1 + 1.6 * easeIn(k))} opacity={1 - e}><Prev t={t} /></g>;
      curEl = <g transform={at(540, 860, lerp(0.82, 1, easeOut(k)))} opacity={e}><Cur t={t} /></g>;
    } else {
      curEl = <g transform={at(540, 860, lerp(tr === "flash" ? 1.08 : 1.05, 1, easeOut(k)))}><Cur t={t} /></g>;
      if (tr === "flash") flash = (i === 1 ? 0.8 : 0.4) * (1 - k);
    }
  }
  const hidden = hideCaptions.some(([a, b]) => t >= a && t < b) || t >= cue("end");
  return (
    <AbsoluteFill style={{ backgroundColor: "#090B2B" }}>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        {prevEl}
        {curEl}
      </svg>
      <Vignette />
      {!hidden && <Captions t={t} pages={pages} top={captionTop} size={captionSize} />}
      {progress && <div style={{ position: "absolute", left: 0, top: 0, height: 10, width: `${(100 * t) / TL.total}%`, background: C.yellow, opacity: 0.9 }} />}
      <AbsoluteFill style={{ backgroundColor: C.white, opacity: flash }} />
      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
  );
};
