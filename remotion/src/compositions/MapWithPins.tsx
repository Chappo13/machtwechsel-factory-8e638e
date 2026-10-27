import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, num } from '../theme';

type Pin = { x: number; y: number; label: string; value?: string; color?: string };
type Props = { pins: Pin[]; title?: string };

const MAP_COLOR = '#2a3550';
const PIN_DEFAULT = '#E63946';

export const MapWithPins: React.FC<Props> = ({ pins, title = '' }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // координаты пинов придумывает LLM — точки за пределами viewBox рисовались
  // в пустоте у края кадра
  const validPins = (pins || []).filter(p => {
    const x = num(p?.x, -1), y = num(p?.y, -1);
    return x >= 40 && x <= 760 && y >= 40 && y <= 660 && (p.label || '').length > 0;
  });

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, justifyContent: 'center', alignItems: 'center', fontFamily: FONT_STACK }}>
      {title && <div style={{ position: 'absolute', top: 80, fontSize: 56, color: TEXT, fontWeight: 600, maxWidth: 1600, textAlign: 'center', overflowWrap: 'break-word' }}>{title}</div>}
      <svg viewBox="0 0 800 700" style={{ width: 1400, height: 700 }}>
        {/* Simplified Germany outline (SVG path approximation) */}
        <path d="M 400 100 Q 500 120 520 200 L 540 320 Q 530 450 480 540 L 400 600 L 320 580 Q 270 480 280 380 L 270 240 Q 320 150 400 100 Z"
              fill={MAP_COLOR} stroke={TEXT} strokeWidth="2" opacity="0.6"/>
        {validPins.map((p, i) => {
          const delay = i * fps * 0.3;
          const pinFadeIn = interpolate(frame, [delay, delay + fps * 0.4], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          const pinScale = interpolate(frame, [delay, delay + fps * 0.6], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          // лейбл справа от пина вылезает за карту → у правого края рисуем слева
          const labelLeft = num(p.x) > 600;
          const tx = labelLeft ? num(p.x) - 35 : num(p.x) + 35;
          const anchor = labelLeft ? 'end' : 'start';
          return (
            <g key={i} opacity={pinFadeIn}>
              <circle cx={num(p.x)} cy={num(p.y)} r={20 * pinScale} fill={p.color || PIN_DEFAULT}/>
              <circle cx={num(p.x)} cy={num(p.y)} r={30 * pinScale} fill={p.color || PIN_DEFAULT} opacity="0.3"/>
              <text x={tx} y={num(p.y) + 5} fill={TEXT} fontSize="32" fontWeight="600" textAnchor={anchor}
                    style={{ paintOrder: 'stroke', stroke: '#0A0E1A', strokeWidth: 6 }}>{p.label}</text>
              {p.value && <text x={tx} y={num(p.y) + 40} fill={p.color || PIN_DEFAULT} fontSize="28" fontWeight="500" textAnchor={anchor}
                    style={{ paintOrder: 'stroke', stroke: '#0A0E1A', strokeWidth: 5 }}>{p.value}</text>}
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
