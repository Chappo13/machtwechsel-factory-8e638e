import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill, Easing } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, num } from '../theme';

type Props = {
  leftValue: number;
  leftLabel: string;
  rightValue: number;
  rightLabel: string;
  title?: string;
};

const LEFT_COLOR = '#4A9EFF';
const RIGHT_COLOR = '#E63946';

const fmt = (n: number) => Math.round(n).toLocaleString('de-DE');

export const BarComparison: React.FC<Props> = ({ leftValue, leftLabel, rightValue, rightLabel, title = '' }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const grow = interpolate(frame, [fps * 0.3, durationInFrames * 0.6], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)
  });
  const titleOp = interpolate(frame, [0, fps * 0.5], [0.25, 1], { extrapolateRight: 'clamp' });

  // коэрсия + guard: 0/0 давал NaN-высоты, строка от LLM роняла рендер
  const leftN = num(leftValue);
  const rightN = num(rightValue);
  const maxV = Math.max(leftN, rightN, 1);
  const maxH = 460;
  // minHeight 10px: при соотношении 17 тыс. vs 3,1 млрд меньший бар был невидим —
  // выглядело как график с одной колонкой
  const barH = (v: number) => (v > 0 ? Math.max((v / maxV) * maxH * grow, 10 * grow) : 0);

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, alignItems: 'center', justifyContent: 'center', fontFamily: FONT_STACK, padding: 70 }}>
      {title && (
        <div style={{ fontSize: 52, color: TEXT, fontWeight: 600, marginBottom: 60, opacity: titleOp, maxWidth: 1600, textAlign: 'center', overflowWrap: 'break-word' }}>{title}</div>
      )}
      {/* без фиксированной height: контент колонки (значение+бар+подпись) мог быть выше
          её и вылезал ВВЕРХ (flex-end), наезжая на заголовок */}
      <div style={{ display: 'flex', gap: 200, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ fontSize: 64, color: TEXT, fontWeight: 700, marginBottom: 20, opacity: grow,
                        fontVariantNumeric: 'tabular-nums', minWidth: 320, textAlign: 'center' }}>{fmt(leftN * grow)}</div>
          <div style={{ width: 200, height: barH(leftN), backgroundColor: LEFT_COLOR, borderRadius: '12px 12px 0 0' }}/>
          <div style={{ fontSize: 38, color: TEXT, marginTop: 24, fontWeight: 500, textAlign: 'center', maxWidth: 380, overflowWrap: 'break-word' }}>{leftLabel}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ fontSize: 64, color: TEXT, fontWeight: 700, marginBottom: 20, opacity: grow,
                        fontVariantNumeric: 'tabular-nums', minWidth: 320, textAlign: 'center' }}>{fmt(rightN * grow)}</div>
          <div style={{ width: 200, height: barH(rightN), backgroundColor: RIGHT_COLOR, borderRadius: '12px 12px 0 0' }}/>
          <div style={{ fontSize: 38, color: TEXT, marginTop: 24, fontWeight: 500, textAlign: 'center', maxWidth: 380, overflowWrap: 'break-word' }}>{rightLabel}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
