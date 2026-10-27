import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT, fitFontSize, num } from '../theme';

// 2-4 ключевые цифры, названные вместе («три числа, которые всё решают»).
// Код-плитки с большими числами вместо стока/AI-картинки.
type Item = { value: number | string; label?: string; prefix?: string; suffix?: string };
type Props = { title?: string; items?: Item[]; accent?: string; durationSec?: number };

const fmtDE = (n: number): string => {
  const r = Math.round(n);
  return Math.abs(r) >= 1000 ? r.toLocaleString('de-DE') : String(r);
};

export const StatCard: React.FC<Props> = ({ title = '', items = [], accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const tiles = (items || []).filter((it) => it && (it.label || it.value !== undefined)).slice(0, 4);
  const n = Math.max(tiles.length, 1);
  const tileW = Math.min(440, (width - 160 - (n - 1) * 40) / n);

  return (
    <AbsoluteFill
      style={{
        background: BG_GRADIENT,
        fontFamily: FONT_STACK,
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
      }}
    >
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
            padding: '0 80px',
            boxSizing: 'border-box',
          }}
        >
          {title}
        </div>
      ) : null}

      <div style={{ display: 'flex', gap: 40, marginTop: title ? 60 : 0 }}>
        {tiles.map((it, i) => {
          const d = i * fps * 0.35;
          const op = interpolate(frame, [d, d + fps * 0.5], [0, 1], clamp);
          const rise = interpolate(frame, [d, d + fps * 0.5], [40, 0], clamp);
          const target = num(it.value, NaN);
          const animated = Number.isFinite(target)
            ? `${it.prefix || ''}${fmtDE(target * interpolate(frame, [d, d + fps * 0.9], [0, 1], clamp))}${it.suffix || ''}`
            : `${it.prefix || ''}${String(it.value ?? '')}${it.suffix || ''}`;
          return (
            <div
              key={i}
              style={{
                width: tileW,
                minHeight: 280,
                background: 'rgba(20,27,48,0.92)',
                border: `1px solid #1f2740`,
                borderTop: `5px solid ${accent}`,
                borderRadius: 22,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                padding: '28px 22px',
                opacity: op,
                transform: `translateY(${rise}px)`,
                boxShadow: '0 14px 40px rgba(0,0,0,0.45)',
              }}
            >
              <div
                style={{
                  fontSize: fitFontSize(animated, 96, 52, tileW - 44),
                  color: TEXT,
                  fontWeight: 800,
                  lineHeight: 1,
                  textAlign: 'center',
                }}
              >
                {animated}
              </div>
              {it.label ? (
                <div
                  style={{
                    fontSize: 28,
                    color: '#aeb6c8',
                    marginTop: 18,
                    textAlign: 'center',
                    lineHeight: 1.2,
                  }}
                >
                  {it.label}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
