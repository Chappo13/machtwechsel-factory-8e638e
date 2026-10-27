import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT } from '../theme';

// Многострочное сравнение A vs B («vorher vs nachher», «Firma A vs Firma B» по
// нескольким параметрам). Чистая таблица в две колонки.
type Row = { label?: string; a?: string; b?: string };
type Props = { title?: string; columns?: [string, string] | string[]; rows?: Row[]; accent?: string; durationSec?: number };

export const ComparisonTable: React.FC<Props> = ({ title = '', columns = ['', ''], rows = [], accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const data = (rows || []).filter((r) => r && (r.label || r.a || r.b)).slice(0, 6);
  const colA = (columns && columns[0]) || '';
  const colB = (columns && columns[1]) || '';
  const grid = '1.2fr 1fr 1fr';

  const Cell = (txt: string, style: React.CSSProperties) => (
    <div style={{ padding: '18px 26px', display: 'flex', alignItems: 'center', ...style }}>{txt}</div>
  );

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, fontFamily: FONT_STACK, justifyContent: 'center', alignItems: 'center' }}>
      {title ? (
        <div style={{ position: 'absolute', top: 100, width: '100%', textAlign: 'center', fontSize: 54, color: TEXT, fontWeight: 600 }}>
          {title}
        </div>
      ) : null}

      <div style={{ width: 1500, marginTop: title ? 60 : 0, borderRadius: 18, overflow: 'hidden', border: '1px solid #1f2740' }}>
        {/* header */}
        <div style={{ display: 'grid', gridTemplateColumns: grid, background: '#141b30' }}>
          {Cell('', { fontSize: 30, color: '#aeb6c8' })}
          {Cell(colA, { fontSize: 34, color: TEXT, fontWeight: 700, justifyContent: 'center', borderLeft: `3px solid ${accent}` })}
          {Cell(colB, { fontSize: 34, color: TEXT, fontWeight: 700, justifyContent: 'center', borderLeft: `3px solid #3a4560` })}
        </div>
        {data.map((r, i) => {
          const d = fps * 0.2 + i * fps * 0.18;
          const op = interpolate(frame, [d, d + fps * 0.35], [0, 1], clamp);
          const x = interpolate(frame, [d, d + fps * 0.35], [-24, 0], clamp);
          return (
            <div
              key={i}
              style={{
                display: 'grid',
                gridTemplateColumns: grid,
                background: i % 2 ? 'rgba(20,27,48,0.55)' : 'rgba(10,14,26,0.55)',
                opacity: op,
                transform: `translateX(${x}px)`,
                borderTop: '1px solid #161d2e',
              }}
            >
              {Cell(r.label || '', { fontSize: 30, color: '#cfd5e2', fontWeight: 500 })}
              {Cell(r.a || '', { fontSize: 32, color: TEXT, fontWeight: 600, justifyContent: 'center' })}
              {Cell(r.b || '', { fontSize: 32, color: TEXT, fontWeight: 600, justifyContent: 'center' })}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
