import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT } from '../theme';

// Хронология дат («в 1998… потом 2002… к 2015»). Горизонтальная ось со
// вехами-точками; даты/подписи всплывают по очереди.
type Ev = { year: string | number; label?: string };
type Props = { title?: string; events?: Ev[]; accent?: string; durationSec?: number };

export const Timeline: React.FC<Props> = ({ title = '', events = [], accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const evs = (events || []).filter((e) => e && (e.year !== undefined && e.year !== '')).slice(0, 6);
  const n = Math.max(evs.length, 1);
  const padX = 200;
  const axisY = height / 2 + 20;
  const x0 = padX;
  const x1 = width - padX;
  const stepX = n > 1 ? (x1 - x0) / (n - 1) : 0;

  const lineProg = interpolate(frame, [fps * 0.3, fps * 1.3], [0, 1], clamp);

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, fontFamily: FONT_STACK }}>
      {title ? (
        <div
          style={{
            position: 'absolute',
            top: 110,
            width: '100%',
            textAlign: 'center',
            fontSize: 54,
            color: TEXT,
            fontWeight: 600,
          }}
        >
          {title}
        </div>
      ) : null}

      <svg width={width} height={height} style={{ position: 'absolute', inset: 0 }}>
        <line x1={x0} y1={axisY} x2={x1} y2={axisY} stroke="#1f2740" strokeWidth="4" />
        <line x1={x0} y1={axisY} x2={x0 + (x1 - x0) * lineProg} y2={axisY} stroke={accent} strokeWidth="4" />
      </svg>

      {evs.map((e, i) => {
        const x = n > 1 ? x0 + stepX * i : (x0 + x1) / 2;
        const d = fps * 0.5 + i * fps * 0.4;
        const op = interpolate(frame, [d, d + fps * 0.4], [0, 1], clamp);
        const pop = interpolate(frame, [d, d + fps * 0.4], [0, 1], clamp);
        const up = i % 2 === 0;
        return (
          <div key={i} style={{ position: 'absolute', left: x, top: axisY, opacity: op }}>
            <div
              style={{
                position: 'absolute',
                left: -13,
                top: -13,
                width: 26,
                height: 26,
                borderRadius: '50%',
                background: accent,
                transform: `scale(${pop})`,
                boxShadow: `0 0 0 6px rgba(230,57,70,0.18)`,
              }}
            />
            <div
              style={{
                position: 'absolute',
                left: -120,
                top: up ? -150 : 40,
                width: 240,
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 46, color: TEXT, fontWeight: 800 }}>{String(e.year)}</div>
              {e.label ? (
                <div style={{ fontSize: 26, color: '#aeb6c8', marginTop: 6, lineHeight: 1.2 }}>{e.label}</div>
              ) : null}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
