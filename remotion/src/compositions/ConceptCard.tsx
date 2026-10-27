import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT, fitFontSize } from '../theme';
import { ICONS } from '../icons';

// Абстрактное понятие (коррупция, давление, цикл денег) — код-иконка + подпись,
// ВМЕСТО платного AI-дудла. icon берётся из реестра ICONS; если нет — рендерим
// нейтральный маркер (валидатор на бэке такие сцены уводит в сток).
type Props = { icon?: string; caption?: string; accent?: string; durationSec?: number };

export const ConceptCard: React.FC<Props> = ({ icon = '', caption = '', accent = ACCENT }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clamp = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };

  const shapes = ICONS[icon] || null;
  const svgInner = shapes ? shapes.join('').split('{C}').join(accent) : '';

  const op = interpolate(frame, [0, fps * 0.6], [0, 1], clamp);
  const pop = interpolate(frame, [0, fps * 0.7], [0.7, 1], clamp);
  const capOp = interpolate(frame, [fps * 0.4, fps * 0.9], [0, 1], clamp);
  const ring = 360;

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
      <div
        style={{
          width: ring,
          height: ring,
          borderRadius: '50%',
          background: 'rgba(20,27,48,0.85)',
          border: `3px solid ${accent}`,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          opacity: op,
          transform: `scale(${pop})`,
          boxShadow: `0 0 60px rgba(230,57,70,0.25)`,
        }}
      >
        {shapes ? (
          <svg
            width={210}
            height={210}
            viewBox="0 0 24 24"
            dangerouslySetInnerHTML={{ __html: svgInner }}
          />
        ) : (
          <div style={{ width: 90, height: 90, borderRadius: '50%', border: `4px solid ${accent}` }} />
        )}
      </div>
      {caption ? (
        <div
          style={{
            marginTop: 60,
            maxWidth: 1300,
            textAlign: 'center',
            fontSize: fitFontSize(caption, 64, 40, 1300),
            color: TEXT,
            fontWeight: 700,
            opacity: capOp,
            lineHeight: 1.2,
          }}
        >
          {caption}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
