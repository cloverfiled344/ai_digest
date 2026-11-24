import raw from "../public/timeline.json";

export type Word = { w: string; t: number };
export type Line = { i: number; id: string; text: string; start: number; dur: number; words: Word[] };
export type Timeline = { fps: number; lang: string; total: number; lines: Line[]; cues: Record<string, number> };
export const TL = raw as unknown as Timeline;
export const FPS = 30;
export const TOTAL = TL.total;
/** time of a named cue from script.json ("start", "end", line ids and L0..Ln are always present) */
export const cue = (k: string) => {
  const v = TL.cues[k];
  if (v === undefined) throw new Error(`unknown cue "${k}"`);
  return v;
};
/** start of line i / end of line i */
export const L = (i: number) => TL.lines[i].start;
export const LE = (i: number) => TL.lines[i].start + TL.lines[i].dur;
/** time of the n-th word in line i that starts with prefix (case/punctuation-insensitive) */
export const W = (i: number, prefix: string, n = 1) => {
  const nm = (s: string) => s.toLowerCase().replace(/ё/g, "е").replace(/[^a-zа-я0-9]/g, "");
  const hits = TL.lines[i].words.filter((w) => nm(w.w).startsWith(nm(prefix)));
  if (hits.length < n) throw new Error(`word "${prefix}" not in line ${i}`);
  return hits[n - 1].t;
};
