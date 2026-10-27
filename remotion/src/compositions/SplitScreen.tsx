import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG, TEXT, fitFontSize } from '../theme';

type Props = {
  leftCountry: string;
  leftValue: string;
  leftSubtitle?: string;
  rightCountry: string;
  rightValue: string;
  rightSubtitle?: string;
};

// кегль значения: колонка ~800px полезной ширины — «3,5 Milliarden Euro» в 200px
// обрезался посередине слова
const valueSize = (v: string) => fitFontSize(v, 200, 56, 760); // колонка ~760px полезной ширины

export const SplitScreen: React.FC<Props> = ({ leftCountry, leftValue, leftSubtitle = '', rightCountry, rightValue, rightSubtitle = '' }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // старт с 0.2: у композиции не было даже backgroundColor — кадр 0 был чисто чёрным
  const fadeIn = interpolate(frame, [0, fps * 0.5], [0.2, 1], { extrapolateRight: 'clamp' });
  const slideL = interpolate(frame, [0, fps * 0.7], [-12, 0], { extrapolateRight: 'clamp' });
  const slideR = interpolate(frame, [0, fps * 0.7], [12, 0], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ flexDirection: 'row', fontFamily: FONT_STACK, backgroundColor: BG }}>
      <div style={{ flex: 1, backgroundColor: '#1a2340', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: 80, transform: `translateX(${slideL}%)`, opacity: fadeIn }}>
        <div style={{ fontSize: 64, color: TEXT, fontWeight: 600, marginBottom: 40, opacity: 0.7, textAlign: 'center', overflowWrap: 'break-word', maxWidth: '100%' }}>{leftCountry}</div>
        <div lang="de" style={{ fontSize: valueSize(leftValue), color: '#4A9EFF', fontWeight: 800, letterSpacing: '-0.03em', textAlign: 'center', overflowWrap: 'break-word', hyphens: 'auto', maxWidth: '100%', lineHeight: 1.1 }}>{leftValue}</div>
        {leftSubtitle && <div style={{ fontSize: 42, color: TEXT, marginTop: 30, opacity: 0.8, textAlign: 'center', overflowWrap: 'break-word', maxWidth: '100%' }}>{leftSubtitle}</div>}
      </div>
      <div style={{ width: 4, backgroundColor: TEXT, opacity: 0.3 }}/>
      <div style={{ flex: 1, backgroundColor: '#3a1a1a', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: 80, transform: `translateX(${slideR}%)`, opacity: fadeIn }}>
        <div style={{ fontSize: 64, color: TEXT, fontWeight: 600, marginBottom: 40, opacity: 0.7, textAlign: 'center', overflowWrap: 'break-word', maxWidth: '100%' }}>{rightCountry}</div>
        <div lang="de" style={{ fontSize: valueSize(rightValue), color: '#E63946', fontWeight: 800, letterSpacing: '-0.03em', textAlign: 'center', overflowWrap: 'break-word', hyphens: 'auto', maxWidth: '100%', lineHeight: 1.1 }}>{rightValue}</div>
        {rightSubtitle && <div style={{ fontSize: 42, color: TEXT, marginTop: 30, opacity: 0.8, textAlign: 'center', overflowWrap: 'break-word', maxWidth: '100%' }}>{rightSubtitle}</div>}
      </div>
    </AbsoluteFill>
  );
};
