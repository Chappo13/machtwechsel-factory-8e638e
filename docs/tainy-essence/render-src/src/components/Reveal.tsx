import React from "react";

// Универсальное проявление элемента: вайп-маска слева направо (текст/рукопись)
// или радиальное/масштабное появление (фигуры, карточки).
export const Reveal: React.FC<{
  progress: number; // 0..1
  mode?: "wipe-x" | "scale" | "wipe-y" | "fade";
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ progress, mode = "wipe-x", children, style }) => {
  const p = Math.min(1, Math.max(0, progress));
  if (p <= 0) return null;

  if (mode === "wipe-x") {
    return (
      <div
        style={{
          ...style,
          clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`,
          opacity: p > 0 ? 1 : 0,
        }}
      >
        {children}
      </div>
    );
  }
  if (mode === "wipe-y") {
    return (
      <div style={{ ...style, clipPath: `inset(0 0 ${(1 - p) * 100}% 0)` }}>
        {children}
      </div>
    );
  }
  if (mode === "scale") {
    const s = 0.7 + 0.3 * p;
    return (
      <div
        style={{
          ...style,
          opacity: p,
          transform: `scale(${s})`,
          transformOrigin: "center",
        }}
      >
        {children}
      </div>
    );
  }
  return <div style={{ ...style, opacity: p }}>{children}</div>;
};
