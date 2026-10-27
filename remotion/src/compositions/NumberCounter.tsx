import { useCurrentFrame, useVideoConfig, interpolate, Easing, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, ACCENT, TEXT, fitFontSize, num } from '../theme';

type Props = {
  from: number;
  to: number;
  suffix?: string;
  label?: string;
  prefix?: string;
};

const fmt = (n: number) => Math.round(n).toLocaleString('de-DE');

export const NumberCounter: React.FC<Props> = ({ from, to, suffix = '', label = '', prefix = '' }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const fromN = num(from);
  const toN = num(to, 1);
  const animDuration = durationInFrames * 0.7;
  const current = interpolate(frame, [0, animDuration], [fromN, toN], {
    extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)
  });
  // старт с 0.25, не с нуля: кадр 0 не должен быть пустым (превью DaVinci, каты)
  const fadeIn = interpolate(frame, [0, fps * 0.3], [0.25, 1], { extrapolateRight: 'clamp' });
  const labelOpacity = interpolate(frame, [animDuration * 0.9, animDuration * 1.1], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  const fullText = `${prefix}${fmt(toN)}${suffix}`;
  const fontSize = fitFontSize(fullText, 240, 96);

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, justifyContent: 'center', alignItems: 'center', fontFamily: FONT_STACK }}>
      <div style={{ opacity: fadeIn, textAlign: 'center', maxWidth: '90%' }}>
        <div style={{ fontSize, fontWeight: 800, color: TEXT, letterSpacing: '-0.04em', lineHeight: 1,
                      fontVariantNumeric: 'tabular-nums' }}>
          {prefix}{fmt(current)}{suffix}
        </div>
        {label && (
          <div style={{ fontSize: 56, fontWeight: 500, color: ACCENT, marginTop: 40, opacity: labelOpacity, letterSpacing: '0.02em' }}>
            {label}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
