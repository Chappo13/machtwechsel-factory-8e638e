import { useCurrentFrame, useVideoConfig, interpolate, AbsoluteFill } from 'remotion';
import { FONT_STACK, BG_GRADIENT, TEXT, ACCENT, fitFontSize } from '../theme';

// A→B движение/связь (переводы денег, «отсюда — туда», отношения). Заменяет
// бессмысленную карту-«бублик»: два подписанных узла + анимированная стрелка с
// суммой. Никаких угаданных координат — только имена из сценария.
type Props = {
  fromLabel?: string;
  toLabel?: string;
  amount?: string;
  fromSub?: string;
  toSub?: string;
  direction?: 'oneway' | 'both';
  accent?: string;
  title?: string;
  durationSec?: number;
};

export const FlowConnection: React.FC<Props> = ({
  fromLabel = '',
  toLabel = '',
  amount = '',
  fromSub = '',
  toSub = '',
  direction = 'oneway',
  accent = ACCENT,
  title = '',
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const cy = height / 2 + 30;
  const leftX = width * 0.26;
  const rightX = width * 0.74;
  const nodeW = 420;
  const nodeH = 160;

  const clampOpts = { extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const };
  const nodeIn = (d: number) => interpolate(frame, [d, d + fps * 0.5], [0, 1], clampOpts);
  const leftIn = nodeIn(0);
  const rightIn = nodeIn(fps * 0.4);

  const x0 = leftX + nodeW / 2;
  const x1 = rightX - nodeW / 2;
  const lineProg = interpolate(frame, [fps * 0.8, fps * 1.6], [0, 1], clampOpts);
  const lineEnd = x0 + (x1 - x0) * lineProg;
  const drawn = lineProg >= 0.999;
  const pulseT = (frame % Math.round(fps * 1.8)) / (fps * 1.8);
  const pulseX = x0 + (x1 - x0) * pulseT;
  const amountIn = interpolate(frame, [fps * 1.4, fps * 1.9], [0, 1], clampOpts);

  const Node = (x: number, label: string, sub: string, op: number) => (
    <div
      style={{
        position: 'absolute',
        left: x - nodeW / 2,
        top: cy - nodeH / 2,
        width: nodeW,
        height: nodeH,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'rgba(20,27,48,0.95)',
        border: `3px solid ${accent}`,
        borderRadius: 26,
        opacity: op,
        transform: `scale(${0.9 + 0.1 * op})`,
        boxShadow: '0 14px 44px rgba(0,0,0,0.45)',
        padding: '0 26px',
      }}
    >
      <div
        style={{
          fontSize: fitFontSize(label, 60, 34, nodeW - 60),
          color: TEXT,
          fontWeight: 700,
          textAlign: 'center',
          lineHeight: 1.05,
        }}
      >
        {label}
      </div>
      {sub ? (
        <div style={{ fontSize: 28, color: '#aeb6c8', marginTop: 10, textAlign: 'center' }}>{sub}</div>
      ) : null}
    </div>
  );

  return (
    <AbsoluteFill style={{ background: BG_GRADIENT, fontFamily: FONT_STACK }}>
      {title ? (
        <div
          style={{
            position: 'absolute',
            top: 96,
            width: '100%',
            textAlign: 'center',
            fontSize: 56,
            color: TEXT,
            fontWeight: 600,
            padding: '0 80px',
            boxSizing: 'border-box',
          }}
        >
          {title}
        </div>
      ) : null}

      <svg width={width} height={height} style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <marker
            id="fc-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill={accent} />
          </marker>
        </defs>
        <line x1={x0} y1={cy} x2={x1} y2={cy} stroke="#1f2740" strokeWidth="6" />
        <line
          x1={x0}
          y1={cy}
          x2={lineEnd}
          y2={cy}
          stroke={accent}
          strokeWidth="6"
          markerEnd={drawn ? 'url(#fc-arrow)' : undefined}
          markerStart={direction === 'both' && drawn ? 'url(#fc-arrow)' : undefined}
        />
        {drawn ? <circle cx={pulseX} cy={cy} r={11} fill={TEXT} opacity={0.9} /> : null}
      </svg>

      {amount ? (
        <div
          style={{
            position: 'absolute',
            left: (x0 + x1) / 2,
            top: cy - 96,
            transform: `translateX(-50%) scale(${amountIn})`,
            opacity: amountIn,
            background: accent,
            color: '#fff',
            fontWeight: 800,
            fontSize: 42,
            padding: '10px 24px',
            borderRadius: 16,
            whiteSpace: 'nowrap',
            boxShadow: '0 10px 28px rgba(0,0,0,0.45)',
          }}
        >
          {amount}
        </div>
      ) : null}

      {Node(leftX, fromLabel, fromSub, leftIn)}
      {Node(rightX, toLabel, toSub, rightIn)}
    </AbsoluteFill>
  );
};
