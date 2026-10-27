import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill, Easing } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, fitFontSize } from '../theme';

type Props = {
  title: string;
  subtitle?: string;
  accent?: string;
};

export const TitleCard: React.FC<Props> = ({ title, subtitle = '', accent = '#E63946' }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  // старт с 0.2: кадр 0 не пустой (превью DaVinci, чёрные вспышки на катах)
  const titleOp = interpolate(frame, [0, fps * 0.5], [0.2, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.quad) });
  const titleY = interpolate(frame, [0, fps * 0.5], [20, 0], { extrapolateRight: 'clamp' });
  const subOp = interpolate(frame, [fps * 0.3, fps * 0.8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const fadeOut = interpolate(frame, [durationInFrames - fps * 0.5, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' });

  // «Y.» (драма) — огромный кегль; длинный немецкий компаунд — уменьшенный, с переносами
  const fontSize = fitFontSize(title, 96, 52);
  const isQuote = /^[„"«']/.test((title || '').trim());

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, justifyContent: 'center', alignItems: 'center', padding: 120, fontFamily: FONT_STACK }}>
      {/* красный штрих только при непустом тексте — на «чёрном экране» он торчал одиноким артефактом */}
      {title && <div style={{ width: 80, height: 6, backgroundColor: accent, marginBottom: 50, opacity: titleOp * fadeOut }}/>}
      <div lang="de" style={{ fontSize, color: TEXT, fontWeight: isQuote ? 500 : 700, textAlign: 'center',
                    letterSpacing: '-0.02em', lineHeight: 1.15, maxWidth: 1600,
                    fontStyle: isQuote ? 'italic' : 'normal',
                    overflowWrap: 'break-word', hyphens: 'auto',
                    opacity: titleOp * fadeOut, transform: `translateY(${titleY}px)` }}>
        {title}
      </div>
      {subtitle && (
        <div style={{ fontSize: 48, color: TEXT, opacity: subOp * fadeOut * 0.7, marginTop: 40, textAlign: 'center', fontWeight: 400, maxWidth: 1500, overflowWrap: 'break-word' }}>
          {subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
