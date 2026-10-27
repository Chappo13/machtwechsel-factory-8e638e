import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill, Easing } from 'remotion';
import { FONT_STACK, BG_GRADIENT, GRID, TEXT, num } from '../theme';

type Point = { year: number; value: number };
type Props = {
  data: Point[];
  title?: string;
  yLabel?: string;
};

const LINE = '#E63946';

const fmt = (n: number) => Math.round(n).toLocaleString('de-DE');

export const LineChart: React.FC<Props> = ({ data, title = '', yLabel = '' }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();

  // draw завершается к ~30% длительности: график виден, остальное время читается
  const drawEnd = Math.min(durationInFrames * 0.3 + fps * 0.5, durationInFrames * 0.75);
  const drawProgress = interpolate(frame, [fps * 0.4, drawEnd], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)
  });

  // коэрсия LLM-данных: строки → числа, NaN/Infinity отбрасываются
  const clean = (data || [])
    .map(d => ({ year: num(d?.year), value: num(d?.value, NaN) }))
    .filter(d => Number.isFinite(d.value));

  if (clean.length === 0) return <AbsoluteFill style={{ background: BG_GRADIENT }}/>;

  const W = 1600;
  const H = 700;
  const padX = 160;  // больше отступ от краёв: длинные подписи точек не обрезаются
  const padY = 80;
  const denomX = Math.max(clean.length - 1, 1);
  const xs = clean.map((d, i) => padX + (i / denomX) * (W - 2*padX));
  const maxV = Math.max(...clean.map(d => d.value)) * 1.1;
  const minV = Math.min(...clean.map(d => d.value)) * 0.9;
  // плоская серия (все значения равны) давала range=0 → деление на 0 → NaN-координаты
  const range = (maxV - minV) || Math.abs(maxV) || 1;
  const ys = clean.map(d => padY + (1 - (d.value - minV) / range) * (H - 2*padY));

  // Build path
  const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x} ${ys[i]}`).join(' ');

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, padding: 80, fontFamily: FONT_STACK }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 30, marginBottom: 30 }}>
        {title && <div style={{ fontSize: 52, color: TEXT, fontWeight: 600 }}>{title}</div>}
        {/* yLabel рядом с заголовком: внизу по центру он читался как подпись оси X */}
        {yLabel && <div style={{ fontSize: 32, color: '#888' }}>({yLabel})</div>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: H }}>
        {/* Grid */}
        {[0.25, 0.5, 0.75].map(y => (
          <line key={y} x1={padX} y1={padY + y*(H-2*padY)} x2={W-padX} y2={padY + y*(H-2*padY)} stroke={GRID} strokeWidth="1"/>
        ))}
        {/* Axis labels */}
        {clean.map((d, i) => (
          <text key={i} x={xs[i]} y={H - padY + 50} fill={TEXT} fontSize="28" textAnchor="middle">{d.year}</text>
        ))}
        {/* Line */}
        <path d={path} fill="none" stroke={LINE} strokeWidth="6" strokeLinecap="round"
              pathLength="1" strokeDasharray="1" strokeDashoffset={1 - drawProgress}/>
        {/* Points — появляются синхронно с проходом линии (раньше последняя точка
            всплывала до того, как линия до неё дорисовалась) */}
        {xs.map((x, i) => {
          const visible = (i / denomX) <= drawProgress;
          return visible && (
            <g key={i}>
              <circle cx={x} cy={ys[i]} r="10" fill={LINE}/>
              {/* якорь по позиции: первая точка влево, последняя вправо — длинное число
                  у края больше не обрезается за пределами viewBox */}
              <text x={x} y={ys[i] - 25} fill={TEXT} fontSize="32" fontWeight="600"
                    textAnchor={i === 0 ? 'start' : i === xs.length - 1 ? 'end' : 'middle'}>{fmt(clean[i].value)}</text>
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
