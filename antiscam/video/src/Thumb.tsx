import React from "react";
import { AbsoluteFill } from "remotion";
import { Bg, C, FONT, H, W } from "./kit";
import { useFonts } from "./frame";
import { Scammer, SC } from "./scam";

// Обложка: 2 строки крупного текста + мошенник с телефоном. Всё внутри y 300–1500.
export const Thumb: React.FC = () => {
  useFonts();
  const t = 1.3;
  const [a = "", b = ""] = SC.title_lines;
  const size = (s: string) => (s.length > 10 ? 118 : 150);
  return (
    <AbsoluteFill>
      <svg width={W} height={H}>
        <Bg t={t} id="th" kind="navy" glow={C.red} glowAmt={0.6} />
        <text x={540} y={470} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={size(a)} fill={C.white} stroke={C.ink} strokeWidth={18} paintOrder="stroke">{a}</text>
        <text x={540} y={640} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={size(b)} fill={C.yellow} stroke={C.ink} strokeWidth={18} paintOrder="stroke">{b}</text>
        <g transform="rotate(-8 360 1080)">
          <rect x={200} y={780} width={330} height={600} rx={46} fill="#0B0A1E" stroke="#4B4A7A" strokeWidth={6} />
          <rect x={216} y={796} width={298} height={568} rx={36} fill="#E9EEF7" />
          <rect x={236} y={900} width={250} height={110} rx={26} fill="#FFFFFF" />
          <rect x={236} y={1040} width={210} height={150} rx={26} fill="#3D7BF2" />
          <path d="M310,1080 L370,1115 L310,1150 Z" fill="#FFFFFF" />
        </g>
        <Scammer id="ths" x={760} y={1110} r={200} t={t} mood="sly" look={[-1, -0.2]} />
        <rect x={250} y={1380} width={580} height={110} rx={55} fill={C.red} />
        <text x={540} y={1455} textAnchor="middle" fontFamily={FONT} fontWeight={900} fontSize={60} fill={C.white}>ЭТО ОБМАН</text>
      </svg>
    </AbsoluteFill>
  );
};
