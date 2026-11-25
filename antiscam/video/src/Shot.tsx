// Картинка к посту (1080×1350): телефон с перепиской мошенника. Данные — public/shot.json.
// variant "stamp" — красная печать «ОБМАН»; "flags" — выноски с признаками обмана у сообщений.
import React from "react";
import { AbsoluteFill } from "remotion";
import { Bg, C, FONT } from "./kit";
import { useFonts } from "./frame";
import { Bubble, bubbleH, Msg, Phone, Scammer, wrap } from "./scam";
import shot from "../public/shot.json";

type Flag = { msg: number; text: string };
type ShotData = { variant: "stamp" | "flags"; contact: string; sub?: string; messages: Msg[]; stamp?: string; flags?: Flag[]; footer?: string; channel?: string };
const D = shot as unknown as ShotData;

export const Shot: React.FC = () => {
  useFonts();
  const t = 1.2, flags = D.variant === "flags";
  // телефон из шаблона роликов (координаты 1080×1920) → кадр 1080×1350
  const s = flags ? 0.92 : 1.0, dx = flags ? -150 : 0, dy = -205;
  let y = 300 + 170;
  const ys = D.messages.map((m) => { const yy = y; y += bubbleH(m) + 24; return yy; });
  return (
    <AbsoluteFill>
      <svg width={1080} height={1350}>
        <Bg t={t} id="sh" kind="navy" glow={C.red} glowAmt={0.35} />
        <g transform={`translate(${dx} ${dy}) translate(540 770) scale(${s}) translate(-540 -770)`}>
          <Phone t={t} title={D.contact} sub={D.sub || "в сети"}>
            {D.messages.map((m, k) => <Bubble key={k} m={m} y={ys[k]} p={1} t={t} glow={m.link || m.file ? 1 : 0} />)}
          </Phone>
        </g>
        {!flags && D.stamp && (
          <g transform="translate(-200 230) rotate(-12 760 760)">
            <rect x={530} y={680} width={460} height={160} rx={24} fill="none" stroke={C.red} strokeWidth={14} opacity={0.92} />
            <text x={760} y={795} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={104} fill={C.red} opacity={0.92}>{D.stamp}</text>
          </g>
        )}
        {flags && (D.flags || []).map((f, k) => {
          const by = (ys[f.msg] + bubbleH(D.messages[f.msg]) / 2 - 770) * s + 770 + dy;
          const bx = (30 + 270 + 400 - 540) * s + 540 + dx + 10;
          const ty = 330 + k * 240;
          return (
            <g key={k}>
              <path d={`M${bx},${by} C${bx + 60},${by} ${700},${ty} ${720},${ty}`} stroke={C.red} strokeWidth={6} fill="none" />
              <circle cx={bx} cy={by} r={10} fill={C.red} />
              <rect x={720} y={ty - 50} width={330} height={100} rx={26} fill={C.red} />
              {(() => {
                const lines = wrap(f.text, 13).slice(0, 2);  // выноска — не шире плашки: до 13 символов в строке
                const size = Math.max(...lines.map((l) => l.length)) > 13 ? 30 : 34;
                return lines.map((ln, j) =>
                  <text key={j} x={885} y={ty + 12 + (j - (lines.length - 1) / 2) * 40} textAnchor="middle" fontFamily={FONT}
                    fontWeight={800} fontSize={size} fill={C.white}>{ln}</text>);
              })()}
            </g>
          );
        })}
        {flags && <Scammer id="shs" x={900} y={1100} r={95} t={t} mood="sly" look={[-1, -0.6]} />}
        {D.footer && <text x={flags ? 40 : 540} y={1235} textAnchor={flags ? "start" : "middle"} fontFamily={FONT} fontWeight={700} fontSize={30} fill="#B9C3E6">{D.footer}</text>}
        {D.channel && <text x={flags ? 40 : 540} y={1290} textAnchor={flags ? "start" : "middle"} fontFamily={FONT} fontWeight={800} fontSize={36} fill={C.yellow}>{D.channel}</text>}
      </svg>
    </AbsoluteFill>
  );
};
