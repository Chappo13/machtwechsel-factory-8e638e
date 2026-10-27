import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT, num } from '../theme';

// Рейтинг / топ-N («5 крупнейших X», «страны по Y»). Горизонтальные бары,
// отсортированы по убыванию, со значениями.
type Item = { label?: string; value: number | string };
type Props = { title?: string; items?: Item[]; suffix?: string; accent?: string; durationSec?: number };

const fmtDE = (n: number): string =>
  Math.abs(Math.round(n)) >= 1000 ? Math.round(n).toLocaleString('de-DE') : String(Math.round(n));

export const RankedBars: React.FC<Props> = ({ title = '', items = [], suffix = '', accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const rows = (items || [])
    .map((it) => ({ label: it.label || '', value: num(it.value, 0) }))
    .filter((it) => it.label)
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
  const maxV = Math.max(...rows.map((r) => r.value), 1);
  const trackW = width - 560;

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, fontFamily: FONT_STACK, justifyContent: 'center' }}>
      {title ? (
        <div style={{ position: 'absolute', top: 100, width: '100%', textAlign: 'center', fontSize: 54, color: TEXT, fontWeight: 600 }}>
          {title}
        </div>
      ) : null}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 26, padding: `0 80px`, marginTop: title ? 70 : 0 }}>
        {rows.map((r, i) => {
          const d = i * fps * 0.25;
          const grow = interpolate(frame, [d, d + fps * 0.7], [0, 1], clamp);
          const op = interpolate(frame, [d, d + fps * 0.3], [0, 1], clamp);
          const w = (r.value / maxV) * trackW * grow;
          const shown = fmtDE(r.value * grow);
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 24, opacity: op }}>
              <div style={{ width: 320, textAlign: 'right', fontSize: 34, color: TEXT, fontWeight: 600, lineHeight: 1.1 }}>
                {r.label}
              </div>
              <div style={{ flex: 1, height: 56, background: '#141b30', borderRadius: 10, position: 'relative' }}>
                <div
                  style={{
                    width: w,
                    height: '100%',
                    borderRadius: 10,
                    background: `linear-gradient(90deg, ${accent}, #ff6b78)`,
                    boxShadow: `0 0 24px rgba(230,57,70,0.35)`,
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    left: w + 18,
                    top: 0,
                    height: 56,
                    display: 'flex',
                    alignItems: 'center',
                    fontSize: 32,
                    color: TEXT,
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {shown}{suffix}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
