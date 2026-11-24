// Flat 2D science-explainer kit. Everything is a pure function of time `t` (seconds). SVG, 1080x1920.
import React from "react";

export const W = 1080;
export const H = 1920;
export const FONT = "Rubik, sans-serif";
export const C = { ink: "#15102F", white: "#FFFFFF", yellow: "#FFD23F", red: "#FF3D5A", green: "#2DBE6C", blue: "#3D7BF2" };
export type Pal = { main: string; dark: string; light: string };
export const P: Record<string, Pal> = {
  cell: { main: "#FFB089", dark: "#E57A5C", light: "#FFD9BF" },
  cancer: { main: "#F2386B", dark: "#A3164A", light: "#FF8AA8" },
  hunter: { main: "#36C3F2", dark: "#1C7FC4", light: "#A5ECFF" },
  sleepy: { main: "#7F8CB0", dark: "#535E86", light: "#B3BED8" },
  gold: { main: "#FFC83D", dark: "#DB8E00", light: "#FFE9A0" },
  person: { main: "#3346A8", dark: "#22307A", light: "#5C72D6" },
  virus: { main: "#8BD346", dark: "#4E9A1E", light: "#CBF29A" },
  germ: { main: "#5BD68A", dark: "#2E9E5B", light: "#B5F5CF" },
  purple: { main: "#A77BF3", dark: "#7146C2", light: "#D9C6FF" },
  ice: { main: "#9FD6FF", dark: "#5A97D1", light: "#EAF7FF" },
  blood: { main: "#E8344E", dark: "#A6162F", light: "#FF8C9C" },
  ghost: { main: "#7A3A9E", dark: "#5A2580", light: "#A866C9" },
};

// ---------- math ----------
export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
export const easeOut = (p: number) => 1 - Math.pow(1 - p, 3);
export const easeIn = (p: number) => p * p * p;
export const easeInOut = (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
export const backOut = (p: number) => 1 + 2.9 * Math.pow(p - 1, 3) + 1.9 * Math.pow(p - 1, 2);
/** 0..1 progress of t between a and b, eased */
export const prog = (t: number, a: number, b: number, e: (x: number) => number = (x) => x) => e(clamp((t - a) / (b - a)));
/** springy entrance 0..1 (overshoots) starting at t0 */
export const pop = (t: number, t0: number, d = 0.35) => prog(t, t0, t0 + d, backOut);
/** 0→1→0 bump of length d starting at t0 (for squash, flashes, punches) */
export const bump = (t: number, t0: number, d = 0.3) => Math.sin(clamp((t - t0) / d) * Math.PI);
export const rand = (i: number) => {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
/** transform string: scale s around point (x,y) */
export const at = (x: number, y: number, s: number, rot = 0) => `translate(${x} ${y}) rotate(${rot}) scale(${s}) translate(${-x} ${-y})`;
const hex = (h: string) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
export const mix = (a: string, b: string, p: number) =>
  "#" + hex(a).map((v, k) => Math.round(lerp(v, hex(b)[k], clamp(p))).toString(16).padStart(2, "0")).join("");
export const mixPal = (a: Pal, b: Pal, p: number): Pal => ({ main: mix(a.main, b.main, p), dark: mix(a.dark, b.dark, p), light: mix(a.light, b.light, p) });
/** decaying screen-shake offset after each event time */
export const shake = (t: number, events: number[], amp = 16, dur = 0.45): [number, number] => {
  let x = 0, y = 0;
  for (const e of events) {
    const p = (t - e) / dur;
    if (p < 0 || p > 1) continue;
    const a = amp * Math.pow(1 - p, 2);
    x += Math.sin(t * 91 + e) * a;
    y += Math.cos(t * 77 + e * 3) * a;
  }
  return [x, y];
};
/** idle float offset so nothing is ever perfectly still */
export const float = (t: number, seed = 0, amp = 8): [number, number] => [Math.sin(t * 1.3 + seed * 2.1) * amp, Math.cos(t * 1.1 + seed * 1.7) * amp];

// ---------- camera ----------
/** Wrap a scene's content: slow push-in across [from,to], optional punch-ins and shakes. Never leaves a frame static. */
export const Cam: React.FC<{ t: number; from: number; to: number; zoom?: [number, number]; focus?: [number, number]; punches?: number[]; shakes?: number[]; drift?: number; children: React.ReactNode }> = ({ t, from, to, zoom = [1, 1.07], focus = [540, 860], punches = [], shakes = [], drift = 10, children }) => {
  let s = lerp(zoom[0], zoom[1], prog(t, from, to, easeInOut));
  for (const p of punches) s *= 1 + 0.07 * bump(t, p, 0.35);
  const [sx, sy] = shake(t, shakes, 16, 0.4);
  const dx = Math.sin(t * 0.5) * drift + sx;
  const dy = Math.cos(t * 0.4) * drift * 0.6 + sy;
  return <g transform={`translate(${dx} ${dy}) ${at(focus[0], focus[1], s)}`}>{children}</g>;
};

// ---------- shapes ----------
export function blobPath(cx: number, cy: number, r: number, t: number, o: { wob?: number; seed?: number; spikes?: number; spikeAmp?: number; n?: number; sx?: number; sy?: number } = {}) {
  const { wob = 0.035, seed = 0, spikes = 0, spikeAmp = 0, n = 56, sx = 1, sy = 1 } = o;
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const th = (i / n) * Math.PI * 2;
    let k = 1 + wob * (Math.sin(3 * th + t * 1.7 + seed) * 0.5 + Math.sin(5 * th - t * 1.2 + seed * 1.7) * 0.3 + Math.sin(2 * th + t * 0.9 + seed * 2.3) * 0.2);
    if (spikes) k += spikeAmp * Math.pow(Math.max(0, Math.cos(spikes * th + seed + Math.sin(t * 0.8 + seed) * 0.25)), 10);
    pts.push([cx + Math.cos(th) * r * k * sx, cy + Math.sin(th) * r * k * sy]);
  }
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    d += `C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)},${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)},${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d + "Z";
}

export type Mood = "happy" | "angry" | "sly" | "sleepy" | "determined" | "scared" | "neutral" | "sad" | "shock";

export const Face: React.FC<{ id: string; x: number; y: number; r: number; t: number; mood: Mood; look?: [number, number]; seed?: number; lid?: number; lidColor: string }> = ({ id, x, y, r, t, mood, look = [0, 0], seed = 0, lid = 0, lidColor }) => {
  const ex = r * 0.29, ey = -r * 0.05, erx = r * 0.15, ery = r * 0.19, sw = r * 0.06;
  const ph = (t + seed * 1.37) % 3.4;
  const blink = ph < 0.16 ? Math.sin((ph / 0.16) * Math.PI) : 0;
  let base = lid;
  if (mood === "sly") base = Math.max(base, 0.42);
  if (mood === "sleepy") base = Math.max(base, 0.72);
  if (mood === "angry") base = Math.max(base, 0.18);
  if (mood === "sad") base = Math.max(base, 0.25);
  const lidAmt = clamp(Math.max(base, mood === "shock" ? 0 : blink));
  const pupil = mood === "scared" || mood === "shock" ? r * 0.055 : mood === "angry" ? r * 0.075 : r * 0.088;
  const bw = { stroke: C.ink, strokeWidth: sw, strokeLinecap: "round" as const };
  const ms = { ...bw, fill: "none" };
  const eyes = [-1, 1].map((s) => {
    const cx = x + s * ex, cy = y + ey, cid = `${id}e${s}`;
    const brows: Partial<Record<Mood, [number, number, number, number]>> = {
      angry: [1.15, 1.5, -0.7, 0.95], determined: [1.1, 1.45, -0.8, 1.12], scared: [1.1, 1.3, -0.6, 1.7],
      sad: [1.1, 1.25, -0.7, 1.6], shock: [1.0, 1.75, -0.8, 1.75], sly: [1.1, s > 0 ? 1.55 : 1.25, -0.7, s > 0 ? 1.3 : 1.15],
    };
    const b = brows[mood];
    return (
      <g key={s}>
        <clipPath id={cid}><ellipse cx={cx} cy={cy} rx={erx} ry={ery} /></clipPath>
        <ellipse cx={cx} cy={cy} rx={erx} ry={ery * (mood === "shock" ? 1.12 : 1)} fill={C.white} />
        <g clipPath={`url(#${cid})`}>
          <circle cx={cx + look[0] * erx * 0.42} cy={cy + look[1] * ery * 0.4} r={pupil} fill={C.ink} />
          <circle cx={cx + look[0] * erx * 0.42 - pupil * 0.35} cy={cy + look[1] * ery * 0.4 - pupil * 0.4} r={pupil * 0.32} fill={C.white} />
          <rect x={cx - erx - 2} y={cy - ery - 2} width={erx * 2 + 4} height={(ery * 2 + 4) * lidAmt} fill={lidColor} />
        </g>
        {b && <line x1={cx + s * erx * b[0]} y1={cy - ery * b[1]} x2={cx + s * erx * b[2]} y2={cy - ery * b[3]} {...bw} />}
      </g>
    );
  });
  const my = y + r * 0.3;
  const mouths: Record<Mood, React.ReactNode> = {
    happy: <path d={`M${x - r * 0.13},${my - r * 0.03} Q${x},${my + r * 0.1} ${x + r * 0.13},${my - r * 0.03}`} {...ms} />,
    angry: <path d={`M${x - r * 0.14},${my + r * 0.06} Q${x},${my - r * 0.06} ${x + r * 0.14},${my + r * 0.06}`} {...ms} />,
    sad: <path d={`M${x - r * 0.11},${my + r * 0.05} Q${x},${my - r * 0.03} ${x + r * 0.11},${my + r * 0.05}`} {...ms} />,
    sly: <path d={`M${x - r * 0.12},${my} Q${x + r * 0.04},${my + r * 0.08} ${x + r * 0.17},${my - r * 0.07}`} {...ms} />,
    determined: <path d={`M${x - r * 0.1},${my + r * 0.02} L${x + r * 0.1},${my + r * 0.01}`} {...ms} />,
    sleepy: <ellipse cx={x} cy={my + r * 0.02} rx={r * 0.05} ry={r * 0.04} fill={C.ink} />,
    scared: <ellipse cx={x} cy={my + r * 0.02} rx={r * 0.065} ry={r * 0.085} fill={C.ink} />,
    shock: <ellipse cx={x} cy={my + r * 0.04} rx={r * 0.08} ry={r * 0.11} fill={C.ink} />,
    neutral: <path d={`M${x - r * 0.08},${my} Q${x},${my + r * 0.04} ${x + r * 0.08},${my}`} {...ms} />,
  };
  return <g>{eyes}{mouths[mood]}</g>;
};

type CellProps = { id: string; x: number; y: number; r: number; t: number; pal: Pal; mood?: Mood; seed?: number; spikes?: number; spikeAmp?: number; look?: [number, number]; lid?: number; knobs?: number; face?: boolean; opacity?: number; sx?: number; sy?: number; wob?: number; glow?: number; squash?: number };

/** Round blobby character. knobs = receptor bumps (immune cell), spikes = angry tumour look. squash 0..1 = impact squash. */
export const Cell: React.FC<CellProps> = ({ id, x, y, r, t, pal, mood = "happy", seed = 0, spikes = 0, spikeAmp = 0, look, lid = 0, knobs = 0, face = true, opacity = 1, sx = 1, sy = 1, wob = 0.035, glow = 0, squash = 0 }) => {
  if (r <= 0.5) return null;
  sx *= 1 + 0.12 * squash;
  sy *= 1 - 0.12 * squash;
  const o = { seed, spikes, spikeAmp, sx, sy, wob, n: spikes ? 84 : 56 };
  const d = blobPath(x, y, r, t, o);
  return (
    <g opacity={opacity}>
      {glow > 0 && (
        <>
          <defs><radialGradient id={`gl-${id}`}><stop offset="0%" stopColor={pal.light} stopOpacity={0.9} /><stop offset="100%" stopColor={pal.light} stopOpacity={0} /></radialGradient></defs>
          <circle cx={x} cy={y} r={r * 1.7} fill={`url(#gl-${id})`} opacity={glow} />
        </>
      )}
      <path d={blobPath(x, y + r * 0.1, r, t, o)} fill="rgba(5,0,25,0.28)" />
      {Array.from({ length: knobs }).map((_, k) => {
        const a = (k / knobs) * Math.PI * 2 + seed + Math.sin(t * 0.6 + k) * 0.05;
        return <circle key={k} cx={x + Math.cos(a) * r * 0.98 * sx} cy={y + Math.sin(a) * r * 0.98 * sy} r={r * 0.13} fill={pal.light} />;
      })}
      <clipPath id={`${id}c`}><path d={d} /></clipPath>
      <path d={d} fill={pal.dark} />
      <path d={blobPath(x - r * 0.07, y - r * 0.09, r * 0.92, t, o)} fill={pal.main} clipPath={`url(#${id}c)`} />
      <ellipse cx={x - r * 0.42} cy={y - r * 0.44} rx={r * 0.17} ry={r * 0.08} transform={`rotate(-38 ${x - r * 0.42} ${y - r * 0.44})`} fill={pal.light} opacity={0.95} />
      <circle cx={x - r * 0.62} cy={y - r * 0.16} r={r * 0.045} fill={pal.light} opacity={0.9} />
      {face && <Face id={`${id}f`} x={x} y={y + r * 0.04} r={r * Math.min(sx, 1.1)} t={t} mood={mood} seed={seed} look={look} lid={lid} lidColor={pal.main} />}
    </g>
  );
};

/** Virus: body + protein spikes with ball tips (spikes slowly rotate) */
export const Virus: React.FC<CellProps & { n?: number }> = (p) => {
  const { x, y, r, t, pal, seed = 0, n = 12, opacity = 1 } = p;
  const rot = t * 12 + seed * 40;
  return (
    <g opacity={opacity}>
      <g transform={`rotate(${rot} ${x} ${y})`}>
        {Array.from({ length: n }).map((_, k) => {
          const a = (k / n) * Math.PI * 2, x1 = x + Math.cos(a) * r * 0.9, y1 = y + Math.sin(a) * r * 0.9, x2 = x + Math.cos(a) * r * 1.32, y2 = y + Math.sin(a) * r * 1.32;
          return (
            <g key={k}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={pal.dark} strokeWidth={r * 0.1} strokeLinecap="round" />
              <circle cx={x2} cy={y2} r={r * 0.13} fill={pal.light} stroke={pal.dark} strokeWidth={r * 0.04} />
            </g>
          );
        })}
      </g>
      <Cell {...p} knobs={0} opacity={1} />
    </g>
  );
};

/** Rod-shaped bacterium with wiggling flagellum */
export const Bacterium: React.FC<{ x: number; y: number; len: number; h?: number; rot: number; pal: Pal; t: number; seed: number; s?: number }> = ({ x, y, len, h = 50, rot, pal, t, seed, s = 1 }) => {
  const tail = Array.from({ length: 10 }).map((_, i) => `${-len / 2 - i * 9},${Math.sin(t * 12 + i * 0.9 + seed) * 7}`).join(" L");
  const blink = (t + seed) % 3 < 0.12 ? 0.15 : 1;
  return (
    <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`}>
      <path d={`M${tail}`} stroke={pal.dark} strokeWidth={5} fill="none" strokeLinecap="round" />
      <rect x={-len / 2} y={-h / 2 + 5} width={len} height={h} rx={h / 2} fill="rgba(5,0,25,0.25)" />
      <rect x={-len / 2} y={-h / 2} width={len} height={h} rx={h / 2} fill={pal.dark} />
      <rect x={-len / 2 + 3} y={-h / 2 + 2} width={len - 8} height={h - 8} rx={(h - 8) / 2} fill={pal.main} />
      <ellipse cx={len * 0.18} cy={-3} rx={6} ry={8 * blink} fill={C.ink} />
      <ellipse cx={len * 0.34} cy={-3} rx={6} ry={8 * blink} fill={C.ink} />
      <path d={`M${len * 0.2},${h * 0.18} Q${len * 0.26},${h * 0.32} ${len * 0.33},${h * 0.18}`} stroke={C.ink} strokeWidth={4} fill="none" strokeLinecap="round" />
    </g>
  );
};

/** Red blood cell (biconcave disc) */
export const RBC: React.FC<{ x: number; y: number; r: number; rot: number; opacity?: number }> = ({ x, y, r, rot, opacity = 1 }) => (
  <g transform={`translate(${x} ${y}) rotate(${rot})`} opacity={opacity}>
    <ellipse rx={r} ry={r * 0.62} fill={P.blood.dark} />
    <ellipse rx={r * 0.92} ry={r * 0.55} cy={-2} fill={P.blood.main} />
    <ellipse rx={r * 0.48} ry={r * 0.26} fill={P.blood.dark} opacity={0.6} />
    <ellipse cx={-r * 0.45} cy={-r * 0.25} rx={r * 0.18} ry={r * 0.07} fill={P.blood.light} opacity={0.8} />
  </g>
);

/** Y-shaped antibody / drug molecule */
export const Antibody: React.FC<{ x: number; y: number; s: number; rot: number; opacity?: number; pal?: Pal }> = ({ x, y, s, rot, opacity = 1, pal = P.gold }) => {
  const arm = (a: number) => (
    <g transform={`rotate(${a})`}>
      <rect x={-15} y={-84} width={30} height={92} rx={15} fill={pal.dark} />
      <rect x={-15} y={-84} width={23} height={86} rx={11.5} fill={pal.main} />
      <rect x={-11} y={-78} width={8} height={30} rx={4} fill={pal.light} />
    </g>
  );
  return (
    <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`} opacity={opacity}>
      <rect x={-15} y={-4} width={30} height={78} rx={15} fill={pal.dark} />
      <rect x={-15} y={-4} width={23} height={74} rx={11.5} fill={pal.main} />
      {arm(-36)}
      {arm(36)}
      <circle r={18} fill={pal.main} />
    </g>
  );
};

/** Two-tone capsule pill */
export const Capsule: React.FC<{ x: number; y: number; s: number; rot: number; a?: string; b?: string }> = ({ x, y, s, rot, a = "#FF5A6E", b = "#FFFFFF" }) => (
  <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`}>
    <rect x={-110} y={-40} width={220} height={88} rx={44} fill="rgba(5,0,25,0.3)" />
    <path d="M0,-44 L-66,-44 A44,44 0 0 0 -66,44 L0,44 Z" fill={a} />
    <path d="M0,-44 L66,-44 A44,44 0 0 1 66,44 L0,44 Z" fill={b} />
    <rect x={-92} y={-30} width={70} height={14} rx={7} fill="#FFFFFF" opacity={0.45} />
  </g>
);

/** Animated DNA double helix, vertical, centred at x; breakAt (0..1 along) shows a red broken rung */
export const DNA: React.FC<{ x: number; y0: number; y1: number; t: number; amp?: number; breakAt?: number; a?: string; b?: string }> = ({ x, y0, y1, t, amp = 90, breakAt, a = "#3DD6F5", b = "#FF8AA8" }) => {
  const n = 22;
  const rungs = [], s1: string[] = [], s2: string[] = [];
  for (let i = 0; i <= n; i++) {
    const p = i / n, y = lerp(y0, y1, p), ph = p * Math.PI * 4 + t * 2;
    const xa = x + Math.sin(ph) * amp, xb = x - Math.sin(ph) * amp;
    s1.push(`${xa},${y}`);
    s2.push(`${xb},${y}`);
    const broken = breakAt !== undefined && Math.abs(p - breakAt) < 0.03;
    rungs.push(<line key={i} x1={xa} y1={y} x2={broken ? lerp(xa, xb, 0.35) : xb} y2={y} stroke={broken ? C.red : "#FFFFFF"} strokeWidth={broken ? 14 : 10} strokeLinecap="round" opacity={broken ? 1 : 0.55} />);
    if (broken) rungs.push(<g key={`b${i}`}><circle cx={(xa + xb) / 2} cy={y} r={34 + 6 * Math.sin(t * 10)} fill={C.red} opacity={0.35} /><line x1={lerp(xa, xb, 0.6)} y1={y} x2={xb} y2={y} stroke={C.red} strokeWidth={14} strokeLinecap="round" /></g>);
  }
  return (
    <g>
      {rungs}
      <polyline points={s1.join(" ")} fill="none" stroke={a} strokeWidth={18} strokeLinecap="round" />
      <polyline points={s2.join(" ")} fill="none" stroke={b} strokeWidth={18} strokeLinecap="round" />
    </g>
  );
};

export const PERSON_PATH = "M-48,78 L48,78 L52,128 L150,128 C205,128 232,152 236,196 L266,610 C270,652 238,676 204,666 L168,340 L162,980 L-162,980 L-168,340 L-204,666 C-238,676 -270,652 -266,610 L-236,196 C-232,152 -205,128 -150,128 L-52,128 Z";
/** Flat human silhouette; origin = head centre; ~1080 tall at s=1 */
export const Person: React.FC<{ id?: string; x: number; y: number; s: number; fill?: string; glow?: string; glowAmt?: number; children?: React.ReactNode }> = ({ id = "pp", x, y, s, fill = P.person.main, glow = "#7FA2FF", glowAmt = 0.6, children }) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <defs>
      <linearGradient id={`${id}g`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={fill} /><stop offset="85%" stopColor={fill} stopOpacity={0.9} /><stop offset="100%" stopColor={fill} stopOpacity={0} /></linearGradient>
    </defs>
    <circle r={100} fill={glow} opacity={glowAmt * 0.25} />
    <path d={PERSON_PATH} fill={glow} opacity={glowAmt * 0.18} transform="scale(1.04)" />
    <circle r={95} fill={`url(#${id}g)`} />
    <path d={PERSON_PATH} fill={`url(#${id}g)`} />
    <ellipse cx={-34} cy={-40} rx={26} ry={12} transform="rotate(-35 -34 -40)" fill={P.person.light} opacity={0.6} />
    {children}
  </g>
);

/** Gold medal with ribbon; crack 0..1 draws cracks; spin = cos value for coin flip */
export const Medal: React.FC<{ x: number; y: number; s: number; label?: string; crack?: number; spin?: number }> = ({ x, y, s, label = "2018", crack = 0, spin = 1 }) => {
  const laurel = (side: number) => Array.from({ length: 9 }).map((_, i) => {
    const a = (90 + side * (40 + i * 15)) * (Math.PI / 180), lx = Math.cos(a) * 150, ly = Math.sin(a) * 150;
    return <ellipse key={i} cx={lx} cy={ly} rx={13} ry={30} fill={P.gold.dark} transform={`rotate(${(a * 180) / Math.PI + (side > 0 ? 90 : -90) + side * 30} ${lx} ${ly})`} />;
  });
  const cracks = ["M0,0 L-30,-40 L-20,-90 L-70,-140 L-60,-190", "M0,0 L50,-20 L90,-70 L150,-80 L185,-60", "M0,0 L20,60 L-10,110 L30,160 L10,195", "M0,0 L-60,20 L-110,70 L-170,60"];
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <path d="M-70,-330 L-20,-170 L20,-170 L-30,-330 Z" fill="#D9334F" />
      <path d="M70,-330 L20,-170 L-20,-170 L30,-330 Z" fill="#B0233D" />
      <g transform={`scale(${Math.max(0.06, Math.abs(spin))} 1)`}>
        <circle r={200} fill={P.gold.dark} />
        <circle r={190} cy={-6} fill={P.gold.main} />
        <circle r={160} fill="none" stroke={P.gold.dark} strokeWidth={6} />
        {laurel(1)}
        {laurel(-1)}
        <ellipse cx={-90} cy={-110} rx={40} ry={16} transform="rotate(-40 -90 -110)" fill={P.gold.light} opacity={0.8} />
        <text y={30} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={96} fill={C.ink} opacity={0.85}>{label}</text>
        {crack > 0 && cracks.map((d, i) => <path key={i} d={d} stroke={C.ink} strokeWidth={14} fill="none" strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray={`${crack} 1`} />)}
      </g>
    </g>
  );
};

/** Thermometer; level 0..1, hot 0..1 blends blue→orange */
export const Thermo: React.FC<{ x: number; y: number; level: number; hot: number; s?: number; opacity?: number }> = ({ x, y, level, hot, s = 1, opacity = 1 }) => {
  const col = mix("#4FB3FF", "#FF6A3D", hot), h = 220;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
      <rect x={-26} y={-h} width={52} height={h + 10} rx={26} fill={C.white} />
      <circle cy={30} r={46} fill={C.white} />
      <rect x={-13} y={-h + 14 + (h - 14) * (1 - level)} width={26} height={(h - 14) * level + 10} rx={13} fill={col} />
      <circle cy={30} r={33} fill={col} />
    </g>
  );
};

export type BadgeKind = "check" | "cross" | "question" | "warn" | "brake" | "heart" | "plus" | "bolt";
/** Round icon badge with speech tail; use for reactions above characters */
export const Badge: React.FC<{ x: number; y: number; s: number; kind: BadgeKind; tail?: boolean; crossed?: number }> = ({ x, y, s, kind, tail = true, crossed = 0 }) => {
  if (s <= 0.01) return null;
  const bg: Record<BadgeKind, string> = { check: C.green, cross: C.red, question: C.white, warn: "#FFB020", brake: C.red, heart: "#FF4F7B", plus: C.green, bolt: C.yellow };
  const icon: Record<BadgeKind, React.ReactNode> = {
    check: <path d="M-28,2 L-8,24 L30,-22" stroke={C.white} strokeWidth={16} fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    cross: <path d="M-22,-22 L22,22 M22,-22 L-22,22" stroke={C.white} strokeWidth={15} strokeLinecap="round" />,
    question: <text y={30} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={86} fill={C.ink}>?</text>,
    warn: <text y={30} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={86} fill={C.ink}>!</text>,
    brake: <text y={30} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={86} fill={C.white}>!</text>,
    heart: <path d="M0,26 C-40,-2 -38,-34 -16,-34 C-6,-34 0,-26 0,-20 C0,-26 6,-34 16,-34 C38,-34 40,-2 0,26 Z" fill={C.white} />,
    plus: <path d="M0,-26 L0,26 M-26,0 L26,0" stroke={C.white} strokeWidth={15} strokeLinecap="round" />,
    bolt: <path d="M8,-36 L-20,6 L0,6 L-8,36 L22,-8 L2,-8 Z" fill={C.ink} />,
  };
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle cy={8} r={62} fill="rgba(5,0,25,0.35)" />
      {kind === "brake" ? (
        <>
          <circle r={58} fill={bg.brake} />
          <path d="M-78,-44 A92,92 0 0 0 -78,44" stroke={C.red} strokeWidth={13} strokeLinecap="round" fill="none" />
          <path d="M78,-44 A92,92 0 0 1 78,44" stroke={C.red} strokeWidth={13} strokeLinecap="round" fill="none" />
        </>
      ) : (
        <>
          <circle r={62} fill={bg[kind]} />
          {tail && <path d="M-22,48 L-8,82 L12,50 Z" fill={bg[kind]} />}
        </>
      )}
      {icon[kind]}
      {crossed > 0 && <line x1={-80} y1={-80} x2={-80 + 160 * crossed} y2={-80 + 160 * crossed} stroke={C.white} strokeWidth={18} strokeLinecap="round" />}
    </g>
  );
};

/** Floating "z z z" for sleeping characters */
export const Zzz: React.FC<{ t: number; t0: number; x: number; y: number }> = ({ t, t0, x, y }) => (
  <g>
    {[0, 1, 2].map((k) => {
      if (t < t0 + k * 0.2) return null;
      const ph = ((t - t0) * 0.9 + k / 3) % 1;
      return <text key={k} x={x + 60 + ph * 70 + k * 6} y={y - 40 - ph * 150} fontFamily={FONT} fontWeight={900} fontSize={44 + k * 10} fill={C.white} opacity={Math.sin(ph * Math.PI)}>z</text>;
    })}
  </g>
);

/** ID card (e.g. MHC-I "passport") */
export const IdCard: React.FC<{ x: number; y: number; s: number; rot?: number; title?: string; photo?: string }> = ({ x, y, s, rot = -10, title = "ID", photo = P.cancer.light }) =>
  s <= 0.02 ? null : (
    <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`}>
      <rect x={-92} y={-52} width={184} height={124} rx={16} fill="rgba(5,0,25,0.3)" />
      <rect x={-92} y={-58} width={184} height={124} rx={16} fill={C.white} />
      <path d="M-92,-30 L-92,-44 A14,14 0 0 1 -78,-58 L78,-58 A14,14 0 0 1 92,-44 L92,-30 Z" fill={C.blue} />
      <text y={-36} textAnchor="middle" fontFamily={FONT} fontWeight={800} fontSize={20} fill={C.white}>{title}</text>
      <rect x={-74} y={-14} width={56} height={64} rx={10} fill={photo} />
      {[-8, 12, 32].map((yy, i) => <rect key={i} x={-6} y={yy} width={[78, 62, 70][i]} height={10} rx={5} fill="#C9CEDF" />)}
    </g>
  );

export const Snow: React.FC<{ t: number; n?: number; alpha?: number }> = ({ t, n = 26, alpha = 1 }) => (
  <g opacity={alpha}>
    {Array.from({ length: n }).map((_, i) => {
      const x = (rand(i * 1.7) * W + Math.sin(t * 0.8 + i) * 40) % W, y = ((rand(i * 3.1) * H + t * (60 + rand(i) * 80)) % (H + 100)) - 50;
      return (
        <g key={i} transform={`translate(${x} ${y}) rotate(${t * 40 + i * 20}) scale(${0.6 + rand(i * 5) * 0.9})`} opacity={0.75}>
          {[0, 60, 120].map((a) => <rect key={a} x={-2.5} y={-16} width={5} height={32} rx={2.5} fill={C.white} transform={`rotate(${a})`} />)}
        </g>
      );
    })}
  </g>
);

/** Ice crystals around a circle (frozen look) */
export const Frost: React.FC<{ x: number; y: number; r: number; alpha: number; seed?: number }> = ({ x, y, r, alpha, seed = 0 }) =>
  alpha <= 0 ? null : (
    <g opacity={alpha}>
      {Array.from({ length: 10 }).map((_, i) => {
        const a = (i / 10) * Math.PI * 2 + seed, cx = x + Math.cos(a) * r * 0.92, cy = y + Math.sin(a) * r * 0.92, s = 10 + rand(i + seed) * 12;
        return <path key={i} d={`M${cx},${cy - s} L${cx + s * 0.55},${cy} L${cx},${cy + s} L${cx - s * 0.55},${cy} Z`} fill={P.ice.light} transform={`rotate(${(a * 180) / Math.PI} ${cx} ${cy})`} />;
      })}
    </g>
  );

/** Explosion: flash + ring + flying particles, 0.75s from t0 */
export const Burst: React.FC<{ x: number; y: number; t: number; t0: number; color: string; size?: number; seed?: number; n?: number }> = ({ x, y, t, t0, color, size = 1, seed = 0, n = 16 }) => {
  const p = (t - t0) / 0.75;
  if (p < 0 || p > 1) return null;
  const e = easeOut(p);
  return (
    <g>
      <circle cx={x} cy={y} r={lerp(30, 250 * size, e)} fill="none" stroke={C.white} strokeWidth={Math.max(0, 22 * (1 - p))} opacity={1 - p} />
      {p < 0.35 && <circle cx={x} cy={y} r={110 * size * (1 - p / 0.35)} fill={C.white} opacity={0.85 * (1 - p / 0.35)} />}
      {Array.from({ length: n }).map((_, i) => {
        const a = (i / n) * Math.PI * 2 + rand(i + seed) * 0.6, dist = (110 + rand(i * 3 + seed) * 200) * size * e;
        return <circle key={i} cx={x + Math.cos(a) * dist} cy={y + Math.sin(a) * dist + 60 * p * p} r={Math.max(0, (10 + rand(i * 7 + seed) * 20) * size * (1 - p))} fill={i % 3 === 0 ? C.white : color} />;
      })}
    </g>
  );
};

/** Expanding scan / sonar rings around a point while t in [a,b] */
export const Pulse: React.FC<{ x: number; y: number; t: number; a: number; b: number; color: string; r0?: number; r1?: number }> = ({ x, y, t, a, b, color, r0 = 120, r1 = 450 }) =>
  t < a || t > b ? null : (
    <g>
      {[0, 1, 2].map((k) => {
        const ph = ((t - a) * 1.4 + k / 3) % 1;
        return <circle key={k} cx={x} cy={y} r={lerp(r0, r1, ph)} fill="none" stroke={color} strokeWidth={8 * (1 - ph)} opacity={0.6 * (1 - ph)} />;
      })}
    </g>
  );

/** Motion streaks behind a moving object (dir = angle in degrees of travel) */
export const SpeedLines: React.FC<{ x: number; y: number; amt: number; dir?: number; color?: string }> = ({ x, y, amt, dir = 0, color = "#FFFFFF" }) =>
  amt <= 0.02 ? null : (
    <g transform={`translate(${x} ${y}) rotate(${dir})`} opacity={amt * 0.7}>
      {[-90, -35, 20, 75].map((dy, k) => <rect key={k} x={-200 - 420 * amt - k * 30} y={dy} width={300 + 120 * amt} height={12} rx={6} fill={color} />)}
    </g>
  );

/** Rounded label pill */
export const Pill: React.FC<{ x: number; y: number; text: string; bg: string; fg?: string; size?: number; opacity?: number; scale?: number }> = ({ x, y, text, bg, fg = C.white, size = 40, opacity = 1, scale = 1 }) => {
  if (opacity <= 0 || scale <= 0.01) return null;
  const w = text.length * size * 0.66 + size * 1.3, h = size * 1.7;
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`} opacity={opacity}>
      <rect x={-w / 2} y={-h / 2 + 6} width={w} height={h} rx={h / 2} fill="rgba(5,0,25,0.35)" />
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2} fill={bg} />
      <text y={size * 0.36} textAnchor="middle" fontFamily={FONT} fontWeight={800} fontSize={size} fill={fg} letterSpacing={1}>{text}</text>
    </g>
  );
};

/** Pill with a pointer line to a target point (callout) */
export const Label: React.FC<{ x: number; y: number; tx: number; ty: number; text: string; bg: string; fg?: string; size?: number; p: number }> = ({ x, y, tx, ty, text, bg, fg, size = 36, p }) =>
  p <= 0.01 ? null : (
    <g>
      <line x1={x} y1={y} x2={lerp(x, tx, clamp(p))} y2={lerp(y, ty, clamp(p))} stroke={C.white} strokeWidth={5} strokeDasharray="4 10" strokeLinecap="round" opacity={0.85} />
      <circle cx={tx} cy={ty} r={10 * clamp(p)} fill={C.white} />
      <Pill x={x} y={y} text={text} bg={bg} fg={fg} size={size} scale={p} />
    </g>
  );

/** Big animated number with caption (counts up between t0 and t1) */
export const Counter: React.FC<{ x: number; y: number; t: number; t0: number; t1: number; value: number; prefix?: string; suffix?: string; caption?: string; locale?: string; size?: number; color?: string; opacity?: number }> = ({ x, y, t, t0, t1, value, prefix = "", suffix = "", caption, locale = "en-US", size = 104, color = C.white, opacity = 1 }) => {
  const p = pop(t, t0 - 0.05, 0.3);
  if (p <= 0.01 || opacity <= 0) return null;
  const v = Math.round(value * prog(t, t0, t1, easeOut));
  const txt = prefix + v.toLocaleString(locale).replace(/ /g, " ") + suffix;
  return (
    <g transform={at(x, y, p)} opacity={opacity}>
      <text x={x} y={y} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={size} fill={color} stroke={C.ink} strokeWidth={16} paintOrder="stroke">{txt}</text>
      {caption && <text x={x} y={y + size * 0.6} textAnchor="middle" fontFamily={FONT} fontWeight={700} fontSize={size * 0.38} fill={C.yellow}>{caption}</text>}
    </g>
  );
};

/** Kinetic headline: each line pops in (stagger), letters reveal left→right */
export const Title: React.FC<{ t: number; t0: number; x?: number; y: number; lines: { text: string; color?: string; size?: number }[]; gap?: number; stagger?: number }> = ({ t, t0, x = 540, y, lines, gap = 1.06, stagger = 0.18 }) => {
  let yy = y;
  return (
    <g>
      {lines.map((ln, i) => {
        const size = ln.size ?? 150, d0 = t0 + i * stagger, p = pop(t, d0, 0.32);
        const cy = yy;
        yy += size * gap;
        if (p <= 0.01) return null;
        return (
          <text key={i} x={x} y={cy} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={size} fill={ln.color ?? C.white} stroke={C.ink} strokeWidth={size * 0.11} paintOrder="stroke" transform={at(x, cy - size * 0.35, p)}>
            {ln.text.split("").map((ch, k) => <tspan key={k} opacity={t >= d0 + k * 0.025 ? 1 : 0}>{ch}</tspan>)}
          </text>
        );
      })}
    </g>
  );
};

// ---------- ambience & backgrounds ----------
export const Bokeh: React.FC<{ t: number; n?: number; color: string; seed?: number; maxR?: number; alpha?: number; speed?: number }> = ({ t, n = 18, color, seed = 0, maxR = 120, alpha = 0.08, speed = 1 }) => (
  <g>
    {Array.from({ length: n }).map((_, i) => {
      const r = 20 + rand(i + seed) * maxR;
      let x = (rand(i * 2.3 + seed) * (W + 300) - 150 + t * speed * (8 + rand(i * 5) * 20) * (rand(i * 7) > 0.5 ? 1 : -1)) % (W + 300);
      if (x < -150) x += W + 300;
      const y = ((rand(i * 3.7 + seed) * (H + 300) - 150 - t * speed * (10 + rand(i * 11) * 25) + H * 8) % (H + 300)) - 150;
      return <circle key={i} cx={x} cy={y} r={r} fill={color} opacity={alpha * (0.5 + rand(i * 13 + seed))} />;
    })}
  </g>
);

/** Faceless background blobs drifting slowly (depth layer). Draw before the main action. */
export const Drifters: React.FC<{ t: number; id: string; pal?: Pal; n?: number; alpha?: number }> = ({ t, id, pal = P.ghost, n = 6, alpha = 0.45 }) => {
  const pos: [number, number, number][] = [[110, 380, 70], [990, 330, 60], [80, 1180, 80], [1000, 1150, 66], [990, 760, 50], [60, 760, 46], [540, 1600, 90], [300, 150, 50]];
  return (
    <g opacity={alpha}>
      {pos.slice(0, n).map(([x, y, r], i) => <Cell key={i} id={`${id}d${i}`} x={x + Math.sin(t * 0.7 + i) * 14} y={y + Math.cos(t * 0.6 + i) * 14} r={r} t={t} pal={pal} seed={i * 2.1} face={false} />)}
    </g>
  );
};

/** Foreground soft blobs moving faster than the scene (parallax) — subtle depth */
export const Foreground: React.FC<{ t: number; color?: string; alpha?: number }> = ({ t, color = "#FFFFFF", alpha = 0.06 }) => (
  <g>
    <defs><radialGradient id="fgsoft"><stop offset="0%" stopColor={color} stopOpacity={1} /><stop offset="100%" stopColor={color} stopOpacity={0} /></radialGradient></defs>
    {[0, 1, 2].map((i) => <circle key={i} cx={((rand(i * 9) * W + t * (40 + i * 25)) % (W + 600)) - 300} cy={300 + i * 620 + Math.sin(t + i) * 40} r={260 + i * 60} fill="url(#fgsoft)" opacity={alpha} />)}
  </g>
);

export type BgKind = "navy" | "tissue" | "icy" | "gut" | "blood" | "warm" | "lab";
const BG: Record<BgKind, { a: string; b: string; glow: string; dots: string }> = {
  navy: { a: "#090B2B", b: "#1C1B63", glow: "#3B4BC8", dots: "#BFD0FF" },
  tissue: { a: "#14092F", b: "#3D1563", glow: "#B0306B", dots: "#FFC4DA" },
  icy: { a: "#0A1638", b: "#24508F", glow: "#5FB0FF", dots: "#EAF7FF" },
  gut: { a: "#2A0B2A", b: "#6E1F4A", glow: "#C2457A", dots: "#FFC4DA" },
  blood: { a: "#2A0712", b: "#6B1024", glow: "#FF4D6A", dots: "#FFB0BE" },
  warm: { a: "#2A0B3A", b: "#B8306B", glow: "#FF8A3D", dots: "#FFE0B0" },
  lab: { a: "#062A33", b: "#0E5A66", glow: "#3DE0D0", dots: "#C8FFF8" },
};
/** Full-frame background with gradient, glow and drifting bokeh/dust. `toward` + `mixAmt` cross-fades to another kind. */
export const Bg: React.FC<{ t: number; id: string; kind: BgKind; glow?: string; glowAmt?: number; toward?: BgKind; mixAmt?: number }> = ({ t, id, kind, glow, glowAmt = 0.5, toward, mixAmt = 0 }) => {
  const A = BG[kind], B = toward ? BG[toward] : A, m = toward ? clamp(mixAmt) : 0;
  const a = mix(A.a, B.a, m), b = mix(A.b, B.b, m), g = glow ?? mix(A.glow, B.glow, m), dots = mix(A.dots, B.dots, m);
  return (
    <g>
      <defs>
        <linearGradient id={`${id}lg`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={a} /><stop offset="100%" stopColor={b} /></linearGradient>
        <radialGradient id={`${id}rg`} cx="50%" cy="42%" r="58%"><stop offset="0%" stopColor={g} stopOpacity={glowAmt} /><stop offset="100%" stopColor={g} stopOpacity={0} /></radialGradient>
      </defs>
      <rect width={W} height={H} fill={`url(#${id}lg)`} />
      <rect width={W} height={H} fill={`url(#${id}rg)`} />
      {(kind === "gut" || toward === "gut") && [560, 900, 1240, 1580].map((y, k) => (
        <path key={k} d={`M-50,${y} ${Array.from({ length: 12 }).map((_, i) => `Q${i * 100 + 50},${y + (i % 2 ? -70 : 70) + Math.sin(t + k) * 10} ${(i + 1) * 100},${y}`).join(" ")}`} stroke="#9C3366" strokeWidth={90} fill="none" opacity={0.3 * (kind === "gut" ? 1 - m : m)} strokeLinecap="round" />
      ))}
      {(kind === "blood" || toward === "blood") && <g opacity={kind === "blood" ? 1 - m : m}>{Array.from({ length: 9 }).map((_, i) => <RBC key={i} x={((rand(i) * W + t * (90 + rand(i * 3) * 60)) % (W + 300)) - 150} y={200 + rand(i * 5) * 1500} r={40 + rand(i * 7) * 30} rot={t * 30 + i * 40} opacity={0.35} />)}</g>}
      <Bokeh t={t} n={40} color={dots} maxR={5} alpha={0.45} seed={3} />
      <Bokeh t={t} n={10} color={dots} maxR={150} alpha={0.05} seed={9} />
    </g>
  );
};
