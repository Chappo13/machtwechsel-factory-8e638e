import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT, fitFontSize } from '../theme';

// Цитата / вердикт суда / определение — текст, который раньше уходил в сток или
// AI-картинку. Типографская выноска с кавычками и атрибуцией.
type Props = { quote?: string; source?: string; accent?: string; durationSec?: number };

export const QuoteCard: React.FC<Props> = ({ quote = '', source = '', accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const op = interpolate(frame, [0, fps * 0.7], [0, 1], clamp);
  const rise = interpolate(frame, [0, fps * 0.7], [30, 0], clamp);
  const srcOp = interpolate(frame, [fps * 0.6, fps * 1.1], [0, 1], clamp);
  const size = fitFontSize(quote, 78, 40, 1400);

  return (
    <AbsoluteFill
      style={{
        background: BG_GRADIENT,
        fontFamily: FONT_STACK,
        justifyContent: 'center',
        alignItems: 'center',
        padding: '0 200px',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ position: 'relative', maxWidth: 1500, opacity: op, transform: `translateY(${rise}px)` }}>
        <div
          style={{
            position: 'absolute',
            left: -70,
            top: -90,
            fontSize: 200,
            lineHeight: 1,
            color: accent,
            fontFamily: 'Georgia, serif',
            fontWeight: 700,
            opacity: 0.85,
          }}
        >
          „
        </div>
        <div
          style={{
            fontSize: size,
            color: TEXT,
            fontWeight: 600,
            lineHeight: 1.28,
            textAlign: 'center',
            fontStyle: 'italic',
          }}
        >
          {quote}
        </div>
        {source ? (
          <div
            style={{
              marginTop: 44,
              textAlign: 'center',
              opacity: srcOp,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 18,
            }}
          >
            <span style={{ width: 48, height: 3, background: accent, display: 'inline-block' }} />
            <span style={{ fontSize: 32, color: '#aeb6c8', fontWeight: 500 }}>{source}</span>
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
