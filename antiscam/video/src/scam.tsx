// Сцены для роликов-разборов мошенничества. Всё строится из public/scenario.json — один шаблон на любой пост.
import React from "react";
import {
  at, Badge, Bg, BgKind, bump, Burst, C, Cam, Cell, clamp, Drifters, easeIn, easeInOut, easeOut, float, FONT, Foreground, lerp,
  P, Person, Pill, pop, prog, Pulse, rand, shake, SpeedLines, Title,
} from "./kit";
import { cue, L, LE, TL } from "./tl";
import raw from "../public/scenario.json";

export type Msg = { from?: "them" | "me"; text?: string; file?: string; link?: string };
export type SLine = {
  id?: string; scene: "hook" | "chat" | "trap" | "loss" | "flags" | "todo" | "outro"; text: string;
  label?: string; messages?: Msg[]; trap?: "file" | "link" | "code" | "call" | "card" | "qr"; loss?: "sms" | "account" | "money" | "contacts";
  items?: string[]; amount?: string; page?: string; button?: string;
};
export type Scenario = { title_lines: string[]; contact?: string; caller?: string; channel?: string; socials?: string[]; lines: SLine[] };
export const SC = raw as unknown as Scenario;

const S = (i: number) => L(i) - 0.06;
const ENDT = () => (TL.lines.length ? LE(TL.lines.length - 1) : 0);

// ---------- helpers ----------
/** Переносит текст по словам на строки не длиннее max символов */
export const wrap = (s: string, max: number) => {
  const out: string[] = [];
  let cur = "";
  for (const w of s.split(/\s+/)) {
    if (cur && (cur + " " + w).length > max) {
      out.push(cur);
      cur = w;
    } else cur = cur ? cur + " " + w : w;
  }
  if (cur) out.push(cur);
  return out;
};
const T: React.FC<{ x: number; y: number; size: number; text: string; fill?: string; anchor?: "start" | "middle" | "end"; weight?: number; outline?: boolean; opacity?: number }> = ({ x, y, size, text, fill = C.white, anchor = "middle", weight = 800, outline = false, opacity = 1 }) => (
  <text x={x} y={y} textAnchor={anchor} fontFamily={FONT} fontWeight={weight} fontSize={size} fill={fill} opacity={opacity}
    stroke={outline ? C.ink : undefined} strokeWidth={outline ? size * 0.12 : undefined} paintOrder="stroke">{text}</text>
);
/** время появления k-го элемента из n внутри реплики i */
const slot = (i: number, k: number, n: number) => lerp(L(i) + 0.25, LE(i) - 0.5, n <= 1 ? 0 : k / (n - 1));

// ---------- мошенник: свой персонаж (тёмный капюшон + хитрый блоб) ----------
export const Scammer: React.FC<{ id: string; x: number; y: number; r: number; t: number; mood?: "sly" | "angry" | "happy" | "shock" | "scared"; look?: [number, number]; opacity?: number; squash?: number }> = ({ id, x, y, r, t, mood = "sly", look = [0, 0], opacity = 1, squash = 0 }) => {
  if (opacity <= 0.01 || r < 1) return null;
  const [fx, fy] = float(t, 3, 6);
  const X = x + fx, Y = y + fy;
  return (
    <g opacity={opacity}>
      <path d={`M${X - r * 1.25},${Y + r * 1.25} C${X - r * 1.3},${Y - r * 0.4} ${X - r * 0.9},${Y - r * 1.45} ${X},${Y - r * 1.45} C${X + r * 0.9},${Y - r * 1.45} ${X + r * 1.3},${Y - r * 0.4} ${X + r * 1.25},${Y + r * 1.25} Z`} fill="#1A1440" stroke="#3A2E7A" strokeWidth={r * 0.08} />
      <Cell id={id} x={X} y={Y} r={r * 0.82} t={t} pal={P.ghost} mood={mood} look={look} seed={2.2} squash={squash} />
    </g>
  );
};

// ---------- телефон ----------
const PX = 270, PY = 300, PW = 540, PH = 940;
export const Phone: React.FC<{ t: number; title: string; sub?: string; children?: React.ReactNode; buzz?: number; x?: number; y?: number; s?: number; rot?: number }> = ({ t, title, sub = "в сети", children, buzz = 0, x = 0, y = 0, s = 1, rot = 0 }) => {
  const bx = buzz > 0 ? Math.sin(t * 90) * 9 * buzz : 0;
  return (
    <g transform={`translate(${x + bx} ${y}) ${at(540, 770, s, rot)}`}>
      <rect x={PX - 18} y={PY - 18} width={PW + 36} height={PH + 36} rx={70} fill="#0B0A1E" stroke="#4B4A7A" strokeWidth={6} />
      <rect x={PX} y={PY} width={PW} height={PH} rx={54} fill="#E9EEF7" />
      <clipPath id="phscr"><rect x={PX} y={PY} width={PW} height={PH} rx={54} /></clipPath>
      <g clipPath="url(#phscr)">
        <rect x={PX} y={PY + 130} width={PW} height={PH} fill="#DCE6F2" />
        {Array.from({ length: 14 }).map((_, i) => <circle key={i} cx={PX + rand(i) * PW} cy={PY + 150 + rand(i * 3.7) * PH} r={8 + rand(i * 2.1) * 16} fill="#C9D6E8" />)}
        <rect x={PX} y={PY} width={PW} height={130} fill="#FFFFFF" />
        <circle cx={PX + 80} cy={PY + 72} r={38} fill={P.hunter.main} />
        <T x={PX + 80} y={PY + 86} size={36} text={(title[0] || "?").toUpperCase()} />
        <T x={PX + 136} y={PY + 66} size={34} anchor="start" fill={C.ink} text={title} />
        <T x={PX + 136} y={PY + 104} size={26} anchor="start" weight={700} fill="#4E8FD9" text={sub} />
        {children}
      </g>
      <rect x={540 - 70} y={PY + 10} width={140} height={34} rx={17} fill="#0B0A1E" />
    </g>
  );
};

/** Пузырь сообщения в чате. p = 0..1 появление. Возвращает высоту. */
export const bubbleH = (m: Msg) => (m.file ? 150 : m.link ? 140 : 40 + 46 * wrap(m.text || "", 18).length);
export const Bubble: React.FC<{ m: Msg; y: number; p: number; t: number; glow?: number }> = ({ m, y, p, t, glow = 0 }) => {
  if (p <= 0.01) return null;
  const me = m.from === "me", w = 400, h = bubbleH(m);
  const x = me ? PX + PW - 30 - w : PX + 30;
  return (
    <g transform={at(me ? x + w : x, y + h, p)}>
      {glow > 0 && <rect x={x - 10} y={y - 10} width={w + 20} height={h + 20} rx={40} fill="none" stroke={C.red} strokeWidth={8} opacity={glow * (0.6 + 0.4 * Math.sin(t * 10))} />}
      <rect x={x} y={y} width={w} height={h} rx={32} fill={me ? "#D7F7C2" : "#FFFFFF"} />
      {m.file && (
        <g>
          <rect x={x + 26} y={y + 26} width={84} height={100} rx={14} fill="#3D7BF2" />
          <path d={`M${x + 86},${y + 26} L${x + 110},${y + 50} L${x + 86},${y + 50} Z`} fill="#A9C6FF" />
          <path d={`M${x + 56},${y + 60} L${x + 84},${y + 78} L${x + 56},${y + 96} Z`} fill="#FFFFFF" />
          <T x={x + 130} y={y + 70} size={30} anchor="start" fill={C.ink} text={m.file.length > 15 ? m.file.slice(0, 14) + "…" : m.file} />
          <T x={x + 130} y={y + 110} size={26} anchor="start" weight={700} fill="#7A86A0" text="2,4 МБ" />
        </g>
      )}
      {m.link && (
        <g>
          <T x={x + 28} y={y + 56} size={30} anchor="start" fill="#2E6FD6" text={m.link.length > 22 ? m.link.slice(0, 21) + "…" : m.link} />
          <rect x={x + 28} y={y + 72} width={Math.min(340, m.link.length * 17)} height={4} fill="#2E6FD6" />
          <T x={x + 28} y={y + 118} size={26} anchor="start" weight={700} fill="#7A86A0" text="Нажмите, чтобы открыть" />
        </g>
      )}
      {!m.file && !m.link && wrap(m.text || "", 18).map((ln, k) => <T key={k} x={x + 28} y={y + 62 + k * 46} size={36} anchor="start" weight={700} fill={C.ink} text={ln} />)}
    </g>
  );
};

/** все сообщения из реплик chat до реплики i включительно, с моментом появления */
const chatUpTo = (i: number) => {
  const out: { m: Msg; t0: number }[] = [];
  SC.lines.forEach((ln, k) => {
    if (k > i || !ln.messages) return;
    ln.messages.forEach((m, j) => out.push({ m, t0: slot(k, j, ln.messages!.length) }));
  });
  return out;
};
const ChatBody: React.FC<{ t: number; i: number; glowLast?: boolean }> = ({ t, i, glowLast }) => {
  const msgs = chatUpTo(i);
  const total = msgs.reduce((a, x) => a + bubbleH(x.m) + 24, 0);
  const scroll = Math.max(0, total - 760);
  let y = PY + 170 - scroll;
  return (
    <g>
      {msgs.map((x, k) => {
        const yy = y;
        y += bubbleH(x.m) + 24;
        return <Bubble key={k} m={x.m} y={yy} p={pop(t, x.t0, 0.35)} t={t} glow={glowLast && k === msgs.length - 1 ? prog(t, x.t0 + 0.4, x.t0 + 0.8) : 0} />;
      })}
    </g>
  );
};

// ---------- сцены ----------
const Hook: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const st = S(i), first = SC.lines.find((l) => l.messages?.length)?.messages?.[0];
  const note = first?.text || first?.file || first?.link || "Новое сообщение";
  const banner = pop(t, st + 0.35, 0.4), buzz = t < st + 1.6 ? 1 - prog(t, st + 1.1, st + 1.6) : 0;
  return (
    <g>
      <Bg t={t} id={`hk${i}`} kind="navy" glow={C.red} glowAmt={0.45} />
      <Drifters t={t} id={`hk${i}`} />
      <Cam t={t} from={st} to={LE(i)} zoom={[1.08, 1]} focus={[540, 900]} shakes={[st + 0.35]}>
        <Phone t={t} title={SC.contact || "Знакомый"} buzz={buzz} y={120} s={0.92} rot={-3}>
          <ChatBody t={t} i={-1} />
        </Phone>
        <g transform={`translate(0 ${lerp(-260, 0, easeOut(banner))})`} opacity={banner}>
          <rect x={150} y={560} width={780} height={150} rx={36} fill="#FFFFFF" />
          <circle cx={230} cy={635} r={44} fill={P.hunter.main} />
          <T x={230} y={652} size={42} text={(SC.contact || "?")[0].toUpperCase()} />
          <T x={300} y={612} size={32} anchor="start" fill="#7A86A0" text={SC.contact || "Знакомый"} />
          <T x={300} y={666} size={40} anchor="start" fill={C.ink} text={note.length > 22 ? note.slice(0, 21) + "…" : note} />
        </g>
      </Cam>
      <Title t={t} t0={st + 0.05} y={250} lines={SC.title_lines.slice(0, 2).map((s, k) => ({ text: s, color: k ? C.yellow : C.white, size: s.length > 9 ? 112 : 136 }))} />
    </g>
  );
};

const Chat: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const st = S(i), ln = SC.lines[i];
  const hasBad = (ln.messages || []).some((m) => m.file || m.link);
  return (
    <g>
      <Bg t={t} id={`ch${i}`} kind="navy" />
      <Drifters t={t} id={`ch${i}`} />
      <Cam t={t} from={st} to={LE(i)} zoom={[1, 1.07]} focus={[540, 820]}>
        <Phone t={t} title={SC.contact || "Знакомый"}>
          <ChatBody t={t} i={i} glowLast={hasBad} />
        </Phone>
      </Cam>
      {ln.label && <Pill x={540} y={200} text={ln.label} bg={C.red} size={46} scale={pop(t, st + 0.4)} />}
    </g>
  );
};

const FileTrap: React.FC<{ t: number; st: number; open: number }> = ({ t, st, open }) => {
  const name = SC.lines.flatMap((l) => l.messages || []).find((m) => m.file)?.file || "video.apk";
  const lid = easeOut(open);
  return (
    <g>
      <g transform={at(540, 760, pop(t, st + 0.05, 0.4))}>
        <rect x={360} y={480} width={360} height={460} rx={40} fill="#3D7BF2" stroke="#1C4FB8" strokeWidth={10} />
        <path d={`M600,480 L720,600 L600,600 Z`} fill="#A9C6FF" />
        <path d="M480,640 L620,720 L480,800 Z" fill="#FFFFFF" opacity={1 - lid} />
        <T x={540} y={1010} size={52} outline text={name} />
      </g>
      <Scammer id="ft" x={540} y={lerp(760, 610, lid)} r={120 * lid} t={t} mood="sly" look={[0, 0.3]} opacity={lid} />
      <Burst x={540} y={700} t={t} t0={st + 0.8} color={P.ghost.light} size={0.5} seed={3} />
    </g>
  );
};

const LinkTrap: React.FC<{ t: number; st: number; i: number }> = ({ t, st, i }) => {
  const url = SC.lines.flatMap((l) => l.messages || []).find((m) => m.link)?.link || "hxxps://video-view[.]online";
  const typed = prog(t, st + 0.9, LE(i) - 0.6);
  const code = "• • • • •".slice(0, Math.ceil(typed * 9));
  return (
    <g transform={at(540, 760, pop(t, st + 0.05, 0.4))}>
      <rect x={170} y={420} width={740} height={700} rx={36} fill="#FFFFFF" />
      <rect x={170} y={420} width={740} height={90} rx={36} fill="#E3E8F2" />
      <rect x={200} y={445} width={680} height={44} rx={22} fill="#FFFFFF" />
      <T x={540} y={478} size={28} weight={700} fill={C.red} text={url.length > 34 ? url.slice(0, 33) + "…" : url} />
      <T x={540} y={600} size={46} fill={C.ink} text={SC.lines[i].page || "Подтвердите вход"} />
      <rect x={240} y={660} width={600} height={96} rx={20} fill="#F1F4FA" stroke="#C9D3E6" strokeWidth={4} />
      <T x={270} y={722} size={38} anchor="start" weight={700} fill={C.ink} text="+996 ••• •• ••" />
      <rect x={240} y={790} width={600} height={96} rx={20} fill="#F1F4FA" stroke={typed > 0 ? C.red : "#C9D3E6"} strokeWidth={4} />
      <T x={270} y={852} size={38} anchor="start" weight={700} fill={C.ink} text={typed > 0 ? `Код: ${code}` : "Код из сообщения"} />
      <rect x={240} y={930} width={600} height={100} rx={50} fill={C.blue} />
      <T x={540} y={995} size={42} text={SC.lines[i].button || "Продолжить"} />
    </g>
  );
};

const CodeTrap: React.FC<{ t: number; st: number; i: number }> = ({ t, st, i }) => {
  const fly = prog(t, st + 1.0, LE(i) - 0.4, easeInOut);
  return (
    <g>
      <g transform={at(lerp(380, 760, fly), lerp(760, 640, fly) - Math.sin(fly * Math.PI) * 220, lerp(1, 0.55, fly))}>
        <rect x={160} y={660} width={440} height={200} rx={34} fill="#FFFFFF" transform={`translate(${-0} 0)`} />
        <T x={380} y={740} size={34} fill="#7A86A0" text="Код подтверждения" />
        <T x={380} y={815} size={66} fill={C.ink} text="4 8 2 1 7" />
      </g>
      <Scammer id="ct" x={800} y={660} r={130} t={t} mood={fly > 0.95 ? "happy" : "sly"} look={[-1, 0]} squash={bump(t, LE(i) - 0.4, 0.3)} />
      <SpeedLines x={lerp(380, 760, fly)} y={700} amt={bump(t, st + 1.0, LE(i) - st - 1.4)} dir={0} />
    </g>
  );
};

const CallTrap: React.FC<{ t: number; st: number }> = ({ t, st }) => (
  <g>
    <Phone t={t} title={SC.caller || "Служба безопасности"} sub="входящий вызов…" buzz={0.6 * (1 - prog(t, st + 2.5, st + 3))} s={0.9}>
      <circle cx={420} cy={1080} r={56} fill={C.red} />
      <circle cx={660} cy={1080} r={56} fill={C.green} />
      <Pulse x={660} y={1080} t={t} a={st} b={st + 3} color={C.green} r0={60} r1={170} />
    </Phone>
    <Scammer id="cl" x={860} y={1180} r={110} t={t} mood="sly" look={[-1, -0.5]} />
  </g>
);

const CardTrap: React.FC<{ t: number; st: number }> = ({ t, st }) => (
  <g transform={at(540, 760, pop(t, st + 0.05, 0.4), lerp(-8, 4, prog(t, st, st + 3)))}>
    <rect x={190} y={560} width={700} height={430} rx={44} fill="#2B3A8F" />
    <rect x={190} y={650} width={700} height={70} fill="#151C52" />
    <rect x={250} y={770} width={110} height={80} rx={14} fill={P.gold.main} />
    <T x={250} y={930} size={48} anchor="start" text="•••• •••• •••• 1234" />
    <Scammer id="cd" x={830} y={560} r={100} t={t} mood="sly" look={[-1, 0.5]} />
  </g>
);

const Trap: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const st = S(i), ln = SC.lines[i], kind = ln.trap || "file", open = prog(t, st + 0.8, st + 1.3);
  return (
    <g>
      <Bg t={t} id={`tr${i}`} kind="tissue" glow={P.ghost.light} glowAmt={0.35} />
      <Drifters t={t} id={`tr${i}`} pal={P.ghost} />
      <Cam t={t} from={st} to={LE(i)} zoom={[1, 1.1]} focus={[540, 760]} punches={[st + 0.8]} shakes={[st + 0.8]}>
        {kind === "file" && <FileTrap t={t} st={st} open={open} />}
        {kind === "link" && <LinkTrap t={t} st={st} i={i} />}
        {kind === "code" && <CodeTrap t={t} st={st} i={i} />}
        {kind === "call" && <CallTrap t={t} st={st} />}
        {(kind === "card" || kind === "qr") && <CardTrap t={t} st={st} />}
      </Cam>
      {ln.label && <Pill x={540} y={220} text={ln.label} bg={C.red} size={50} scale={pop(t, st + 0.9)} />}
    </g>
  );
};

const Loss: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const st = S(i), ln = SC.lines[i], kind = ln.loss || "money";
  const hit = st + 0.9;
  let body: React.ReactNode = null;
  if (kind === "contacts") {
    const pts: [number, number][] = [[260, 520], [820, 520], [180, 860], [900, 860], [300, 1150], [780, 1150]];
    body = (
      <g>
        {pts.map(([x, y], k) => {
          const tk = slot(i, k, pts.length), p = prog(t, tk - 0.35, tk, easeInOut);
          return (
            <g key={k}>
              <line x1={540} y1={830} x2={lerp(540, x, p)} y2={lerp(830, y, p)} stroke={C.red} strokeWidth={8} strokeDasharray="18 14" opacity={0.8} />
              <Person id={`lc${k}`} x={x} y={y - 60} s={0.16} fill={t > tk ? P.cancer.main : P.person.main} />
              {t > tk && <Badge x={x + 60} y={y - 90} s={0.42 * pop(t, tk)} kind="warn" tail={false} />}
            </g>
          );
        })}
        <Scammer id="lcs" x={540} y={830} r={130} t={t} mood="happy" look={[0, 0]} />
      </g>
    );
  } else if (kind === "money") {
    const left = 1 - prog(t, hit, LE(i) - 0.3, easeIn);
    body = (
      <g>
        <rect x={240} y={560} width={600} height={420} rx={44} fill="#FFFFFF" />
        <T x={540} y={650} size={40} fill="#7A86A0" text="Баланс" />
        <T x={540} y={790} size={left < 0.02 ? 120 : 96} fill={left < 0.02 ? C.red : C.ink} text={left < 0.02 ? "0" : (ln.amount || "120 000") } />
        <rect x={300} y={880} width={480} height={22} rx={11} fill="#E3E8F2" />
        <rect x={300} y={880} width={480 * left} height={22} rx={11} fill={left < 0.3 ? C.red : C.green} />
        <Scammer id="lm" x={850} y={1080} r={110} t={t} mood={left < 0.2 ? "happy" : "sly"} look={[-1, -1]} />
      </g>
    );
  } else {
    // sms / account: конверты-коды и ключ летят от телефона к мошеннику
    body = (
      <g>
        <Phone t={t} title={SC.contact || "Вы"} sub={kind === "account" ? "аккаунт недоступен" : "новые SMS"} x={-170} s={0.62}>
          {t > hit && <g transform={at(540, 770, pop(t, hit))}>
            <rect x={430} y={680} width={220} height={170} rx={30} fill={kind === "account" ? C.red : "#FFFFFF"} />
            <path d="M480,700 L480,660 A60,60 0 0 1 600,660 L600,700" stroke={kind === "account" ? C.red : C.ink} strokeWidth={22} fill="none" transform={kind === "account" ? "rotate(-25 600 700)" : undefined} />
          </g>}
        </Phone>
        {Array.from({ length: 5 }).map((_, k) => {
          const tk = hit + k * 0.35, p = prog(t, tk, tk + 0.6, easeInOut);
          if (p <= 0 || p >= 1) return null;
          return <g key={k} transform={`translate(${lerp(400, 820, p)} ${lerp(820, 760, p) - Math.sin(p * Math.PI) * 180})`}>
            <rect x={-46} y={-32} width={92} height={64} rx={10} fill={kind === "account" ? P.gold.main : "#FFFFFF"} stroke={C.ink} strokeWidth={5} />
            <path d="M-46,-32 L0,6 L46,-32" stroke={C.ink} strokeWidth={5} fill="none" />
          </g>;
        })}
        <Scammer id="ls" x={820} y={760} r={120} t={t} mood="happy" look={[-1, 0]} />
      </g>
    );
  }
  return (
    <g>
      <Bg t={t} id={`ls${i}`} kind="blood" glowAmt={0.4} />
      <Drifters t={t} id={`ls${i}`} pal={P.cancer} />
      <Cam t={t} from={st} to={LE(i)} zoom={[1.02, 1.1]} focus={[540, 820]} shakes={[hit]}>{body}</Cam>
      {ln.label && <Pill x={540} y={220} text={ln.label} bg={C.red} size={50} scale={pop(t, st + 0.5)} />}
    </g>
  );
};

const ListScene: React.FC<{ t: number; i: number; kind: "flags" | "todo" }> = ({ t, i, kind }) => {
  const st = S(i), ln = SC.lines[i], items = (ln.items || []).slice(0, 4);
  const good = kind === "todo";
  const heading = ln.label || (good ? "КАК ЗАЩИТИТЬСЯ" : "ПРИЗНАКИ ОБМАНА");
  let y = 470;
  return (
    <g>
      <Bg t={t} id={`li${i}`} kind={good ? "lab" : "warm"} glowAmt={0.35} />
      <Drifters t={t} id={`li${i}`} pal={good ? P.germ : P.gold} />
      <Cam t={t} from={st} to={LE(i)} zoom={[1, 1.05]} focus={[540, 800]}>
        {items.map((it, k) => {
          const tk = slot(i, k, items.length), p = pop(t, tk, 0.4), lines = wrap(it, 24).slice(0, 3);
          const h = 60 + lines.length * 54, yy = y;
          y += h + 30;
          if (p <= 0.01) return null;
          return (
            <g key={k} transform={at(140, yy + h / 2, p)}>
              <rect x={110} y={yy} width={860} height={h} rx={34} fill="rgba(255,255,255,0.95)" />
              <Badge x={185} y={yy + h / 2} s={0.5} kind={good ? "check" : "warn"} tail={false} />
              {lines.map((l2, j) => <T key={j} x={260} y={yy + 72 + j * 54} size={42} anchor="start" weight={800} fill={C.ink} text={l2} />)}
            </g>
          );
        })}
        {good && <Cell id={`hero${i}`} x={880} y={y + 90 > 1180 ? 1180 : y + 90} r={90} t={t} pal={P.hunter} knobs={10} mood="determined" look={[-1, -0.5]} glow={0.3} opacity={pop(t, st + 0.3)} />}
        {!good && <Scammer id={`fs${i}`} x={900} y={Math.min(1180, y + 90)} r={90} t={t} mood={t > LE(i) - 0.8 ? "scared" : "sly"} look={[-1, -0.5]} opacity={pop(t, st + 0.3)} />}
      </Cam>
      <Pill x={540} y={300} text={heading} bg={good ? C.green : C.red} size={52} scale={pop(t, st + 0.1)} />
    </g>
  );
};

const Outro: React.FC<{ t: number; i: number }> = ({ t, i }) => {
  const st = S(i), socials = (SC.socials || []).slice(0, 3);
  return (
    <g>
      <Bg t={t} id={`ou${i}`} kind="navy" glow={P.hunter.main} glowAmt={0.45} />
      <Drifters t={t} id={`ou${i}`} pal={P.hunter} />
      <Cell id="ouh" x={540} y={520} r={140} t={t} pal={P.hunter} knobs={12} mood="happy" look={[0, 0.6]} glow={0.45} squash={bump(t, st + 0.2, 0.35)} opacity={pop(t, st)} />
      <Title t={t} t0={st + 0.2} y={850} lines={[{ text: "ПОДПИШИСЬ", color: C.yellow, size: 128 }]} />
      {SC.channel && <T x={540} y={980} size={54} outline text={SC.channel} opacity={pop(t, st + 0.5)} />}
      {socials.map((s, k) => <Pill key={k} x={540} y={1120 + k * 115} text={s} bg={k ? "#2A2A6E" : C.blue} size={Math.min(46, Math.floor(1250 / Math.max(1, s.length)))}
        scale={pop(t, st + 0.7 + k * 0.12) * (1 + 0.04 * Math.sin(t * 5))} />)}
    </g>
  );
};

const COMP: Record<SLine["scene"], React.FC<{ t: number; i: number }>> = {
  hook: Hook, chat: Chat, trap: Trap, loss: Loss,
  flags: (p) => <ListScene {...p} kind="flags" />, todo: (p) => <ListScene {...p} kind="todo" />, outro: Outro,
};
const TR: Record<SLine["scene"], "cut" | "flash" | "push" | "whip" | "iris" | "zoom"> = {
  hook: "cut", chat: "zoom", trap: "flash", loss: "whip", flags: "iris", todo: "push", outro: "iris",
};

/** Сцены для Shell: подряд идущие реплики одного типа (кроме trap/loss) — одна сцена */
export const buildScenes = () => {
  const scenes: { from: number; comp: React.FC<{ t: number }>; tr: (typeof TR)[SLine["scene"]] }[] = [];
  const hide: [number, number][] = [];
  SC.lines.forEach((ln, i) => {
    const C2 = COMP[ln.scene] || Chat;
    const prev = SC.lines[i - 1];
    if (prev && prev.scene === ln.scene && ln.scene === "chat") {
      // продолжение чата: переопределяем прошлую сцену, чтобы видеть новые сообщения
      scenes[scenes.length - 1].comp = ({ t }) => <C2 t={t} i={i} />;
      return;
    }
    scenes.push({ from: i === 0 ? 0 : S(i), comp: ({ t }) => <C2 t={t} i={i} />, tr: i === 0 ? "cut" : TR[ln.scene] });
    if (ln.scene === "outro") hide.push([S(i), 999]);
  });
  // финальная карточка после речи — продолжение outro (или отдельная, если outro нет)
  if (!SC.lines.some((l) => l.scene === "outro")) {
    scenes.push({ from: cue("end"), comp: ({ t }) => <Outro t={t} i={SC.lines.length - 1} />, tr: "iris" });
  }
  return { scenes, hide };
};

export { ENDT };
