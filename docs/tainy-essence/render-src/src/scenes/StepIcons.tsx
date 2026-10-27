import React from "react";
import { StepIcon } from "../types";

// Простые штриховые иконки 48x48 в стиле дневника (контур чернилами, без заливок).
// Рисуются кодом: без внешних файлов и лицензий.
const P: Record<StepIcon, React.ReactNode> = {
  gear: (<><circle cx="24" cy="24" r="7" /><path d="M24 6v6M24 36v6M6 24h6M36 24h6M11.3 11.3l4.2 4.2M32.5 32.5l4.2 4.2M36.7 11.3l-4.2 4.2M15.5 32.5l-4.2 4.2" /><circle cx="24" cy="24" r="13" /></>),
  flask: (<><path d="M19 6h10M21 6v12L10 38a3 3 0 0 0 2.7 4.4h22.6A3 3 0 0 0 38 38L27 18V6" /><path d="M14 30h20" /></>),
  bolt: (<path d="M27 4 12 27h11l-3 17 16-24H25z" />),
  coin: (<><circle cx="24" cy="24" r="17" /><circle cx="24" cy="24" r="11" /><path d="M18 24h12" /></>),
  sun: (<><circle cx="24" cy="24" r="8" /><path d="M24 4v7M24 37v7M4 24h7M37 24h7M9.9 9.9l5 5M33.1 33.1l5 5M38.1 9.9l-5 5M14.9 33.1l-5 5" /></>),
  water: (<><path d="M24 5C17 15 11 21 11 29a13 13 0 0 0 26 0c0-8-6-14-13-24z" /><path d="M18 30a6 6 0 0 0 6 6" /></>),
  fire: (<><path d="M24 4c2 8 11 13 11 24a11 11 0 0 1-22 0c0-5 3-8 5-11 1 3 2 4 4 4-1-6 0-11 2-17z" /><path d="M20 38a5 5 0 0 0 8 0c0-3-2-4-4-7-2 3-4 4-4 7z" /></>),
  hammer: (<><path d="M9 9h22v11H9zM31 12h8v5h-8z" /><path d="M20 20v22" /></>),
  scroll: (<><path d="M13 8h24v28a4 4 0 0 1-4 4H11a4 4 0 0 0 4-4V10a2 2 0 0 0-2-2z" /><path d="M19 16h14M19 22h14M19 28h10" /></>),
  eye: (<><path d="M3 24C9 14 16 10 24 10s15 4 21 14c-6 10-13 14-21 14S9 34 3 24z" /><circle cx="24" cy="24" r="6" /></>),
  key: (<><circle cx="15" cy="24" r="8" /><path d="M23 24h20M36 24v7M42 24v5" /></>),
  ship: (<><path d="M4 31h40l-6 10H10z" /><path d="M24 6v25M24 8l14 18H24M24 12 12 26h12" /></>),
  stone: (<><path d="M6 36 10 18l12-8 16 4 6 14-8 10H14z" /><path d="M10 18l12 8 16-12M22 26l-4 14" /></>),
  skull: (<><path d="M10 26c-4-12 4-20 14-20s18 8 14 20c-1 3-3 4-5 5v7H15v-7c-2-1-4-2-5-5z" /><circle cx="18" cy="24" r="3" /><circle cx="30" cy="24" r="3" /><path d="M20 38v-5M24 38v-5M28 38v-5" /></>),
};

export const StepIconSvg: React.FC<{ icon: StepIcon; size: number; color: string; strokeWidth?: number }> = ({ icon, size, color, strokeWidth = 2.6 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
    {P[icon]}
  </svg>
);
