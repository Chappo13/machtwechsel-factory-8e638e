import { Composition } from 'remotion';
import { NumberCounter } from './compositions/NumberCounter';
import { LineChart } from './compositions/LineChart';
import { BarComparison } from './compositions/BarComparison';
import { SplitScreen } from './compositions/SplitScreen';
import { TitleCard } from './compositions/TitleCard';
import { MapWithPins } from './compositions/MapWithPins';
import { FlowConnection } from './compositions/FlowConnection';
import { StatCard } from './compositions/StatCard';
import { QuoteCard } from './compositions/QuoteCard';
import { Timeline } from './compositions/Timeline';
import { RankedBars } from './compositions/RankedBars';
import { ComparisonTable } from './compositions/ComparisonTable';
import { ConceptCard } from './compositions/ConceptCard';

const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;

export const RemotionRoot: React.FC = () => {
  // durationSec в props переопределяет длину композиции — анимация тянется на всю
  // длину сцены (TitleCard гаснет в самом конце, счётчик считает до финала).
  const calcDur = (fallbackSec: number) => ({ props }: { props: { durationSec?: number } }) => ({
    durationInFrames: Math.max(1, Math.round((props.durationSec ?? fallbackSec) * FPS)),
  });

  return (
    <>
      <Composition
        id="NumberCounter"
        component={NumberCounter}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ from: 0, to: 295000, suffix: '', label: '', durationSec: 6 }}
      />
      <Composition
        id="LineChart"
        component={LineChart}
        durationInFrames={FPS * 8}
        calculateMetadata={calcDur(8)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ data: [], title: '', yLabel: '', durationSec: 8 }}
      />
      <Composition
        id="BarComparison"
        component={BarComparison}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ leftValue: 0, leftLabel: '', rightValue: 0, rightLabel: '', title: '', durationSec: 6 }}
      />
      <Composition
        id="SplitScreen"
        component={SplitScreen}
        durationInFrames={FPS * 8}
        calculateMetadata={calcDur(8)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ leftCountry: '', leftValue: '', leftSubtitle: '', rightCountry: '', rightValue: '', rightSubtitle: '', durationSec: 8 }}
      />
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={FPS * 5}
        calculateMetadata={calcDur(5)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ title: '', subtitle: '', accent: '#E63946', durationSec: 5 }}
      />
      <Composition
        id="MapWithPins"
        component={MapWithPins}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ pins: [], durationSec: 6 }}
      />
      <Composition
        id="FlowConnection"
        component={FlowConnection}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ fromLabel: '', toLabel: '', amount: '', direction: 'oneway', durationSec: 6 }}
      />
      <Composition
        id="StatCard"
        component={StatCard}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ title: '', items: [], durationSec: 6 }}
      />
      <Composition
        id="QuoteCard"
        component={QuoteCard}
        durationInFrames={FPS * 6}
        calculateMetadata={calcDur(6)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ quote: '', source: '', durationSec: 6 }}
      />
      <Composition
        id="Timeline"
        component={Timeline}
        durationInFrames={FPS * 8}
        calculateMetadata={calcDur(8)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ title: '', events: [], durationSec: 8 }}
      />
      <Composition
        id="RankedBars"
        component={RankedBars}
        durationInFrames={FPS * 7}
        calculateMetadata={calcDur(7)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ title: '', items: [], suffix: '', durationSec: 7 }}
      />
      <Composition
        id="ComparisonTable"
        component={ComparisonTable}
        durationInFrames={FPS * 7}
        calculateMetadata={calcDur(7)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ title: '', columns: ['', ''], rows: [], durationSec: 7 }}
      />
      <Composition
        id="ConceptCard"
        component={ConceptCard}
        durationInFrames={FPS * 5}
        calculateMetadata={calcDur(5)}
        fps={FPS} width={WIDTH} height={HEIGHT}
        defaultProps={{ icon: '', caption: '', durationSec: 5 }}
      />
    </>
  );
};
