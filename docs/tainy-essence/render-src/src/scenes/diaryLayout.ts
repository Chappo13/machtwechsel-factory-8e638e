import { DiaryItem, Format } from "../types";

export type ItemBox = { id: string; x: number; y: number; w: number; h: number; item: DiaryItem };

// Раскладка заметок дневника вдоль одной оси (горизонтально для long, вертикально
// для short) — так камера естественно "едет" по странице, как в референсе.
// Если итоговый контент не шире/выше кадра — центрируем его, чтобы страница не
// выглядела пустой "запиской в углу" (это и было главной жалобой на первую версию).
export function layoutDiary(
  items: DiaryItem[],
  format: Format,
  frameW: number,
  frameH: number,
  topMargin: number
) {
  const blocks = items.filter(
    (i) => i.kind !== "arrow" && !(i.kind === "underline" && !i.text)
  );
  // мало заметок на странице — делаем их крупнее, иначе страница выглядит
  // пустой (та же логика, что у Board.sizeScale)
  const sizeScale = blocks.length <= 1 ? 1.5 : blocks.length === 2 ? 1.3 : blocks.length === 3 ? 1.15 : 1;
  const horizontal = format === "long";
  const crossSize = horizontal ? frameH - topMargin - 70 : frameW - 110;
  const boxes: ItemBox[] = [];

  const startCursor = horizontal ? 90 : topMargin + 50;
  let cursor = startCursor;
  const crossCenter = horizontal ? topMargin + crossSize / 2 + 50 : frameW / 2;

  blocks.forEach((item, idx) => {
    let w: number;
    let h: number;
    if (item.kind === "sketch") {
      w = horizontal ? Math.min(crossSize * 0.78, 440 * sizeScale) : Math.min(frameW * 0.72, 420 * sizeScale);
      h = w;
    } else if (item.kind === "circle_text") {
      w = horizontal ? Math.min(crossSize * 0.68, 380 * sizeScale) : Math.min(frameW * 0.62, 380 * sizeScale);
      h = w;
    } else {
      const len = (item.text || "").length;
      if (horizontal) {
        w = Math.max(340 * sizeScale, Math.min(700 * sizeScale, len * 19 * sizeScale));
        h = Math.min(crossSize * 0.85, 320 * sizeScale);
      } else {
        w = Math.min(frameW - 120, 860);
        h = Math.max(170 * sizeScale, Math.min(380 * sizeScale, len * 5 + 110));
      }
    }

    // лёгкий разброс по поперечной оси для "живого" эффекта заметок на странице
    const jitter = ((idx * 37) % 7) - 3;
    let x: number;
    let y: number;
    if (horizontal) {
      x = cursor;
      y = crossCenter - h / 2 + jitter * 4;
      cursor += w + 80;
    } else {
      y = cursor;
      x = crossCenter - w / 2 + jitter * 4;
      cursor += h + 60;
    }
    boxes.push({ id: item.id, x, y, w, h, item });
  });

  const contentEnd = cursor - (horizontal ? 80 : 60);
  const canvasW = horizontal ? Math.max(frameW, contentEnd + 90) : frameW;
  const canvasH = horizontal ? frameH : Math.max(frameH, contentEnd + 70);

  // центрирование, если контент не переполняет кадр по оси движения
  if (horizontal && canvasW === frameW) {
    const contentWidth = contentEnd - startCursor;
    const offset = (frameW - contentWidth) / 2 - startCursor;
    boxes.forEach((b) => (b.x += offset));
  } else if (!horizontal && canvasH === frameH) {
    const contentHeight = contentEnd - startCursor;
    const offset = (frameH - contentHeight) / 2 - startCursor;
    boxes.forEach((b) => (b.y += offset));
  }

  const posMap: Record<string, ItemBox> = {};
  boxes.forEach((b) => (posMap[b.id] = b));

  return { boxes, posMap, canvasW, canvasH, horizontal, sizeScale };
}
