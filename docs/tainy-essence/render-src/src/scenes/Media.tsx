import React, { useMemo } from "react";
import { AbsoluteFill, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { revealProgress, clamp, easeInOut } from "../utils/time";
import { annotationTiming } from "../utils/revealTiming.mjs";
import { annotationLabel } from "../utils/annotationLabel.mjs";
import { mediaLayout, focusZoomLayout } from "../utils/mediaLayout.mjs";
import { Atmosphere } from "../components/Atmosphere";
import { CalloutShot } from "../components/CalloutShot";
import { pickShotTransition } from "../utils/transitions.mjs";
import { CrossfadeEcho } from "../components/CrossfadeEcho";
import { MediaAnnotation, MediaShot, LowerThird as LowerThirdData } from "../types";
import { buildRevealMap } from "../utils/revealTiming.mjs";

const SHOT_CROSSFADE_SEC = 0.4;

// 60% ролика — реальные кадры (сток/архив), а не рисунки. Сцена может содержать
// НЕСКОЛЬКО последовательных планов (shots) — разные клипы/фото с переходом
// "под старину" между ними (как между сценами), вместо растягивания/зацикливания
// одного короткого исходника. Короткое видео сначала замедляется (не больше чем
// до 0.6x — иначе выглядит неестественно тягуче), а если и этого не хватает —
// стоп-кадр на последнем доступном кадре с продолжающимся Ken Burns (без рывка,
// без перезапуска). normalizeScenes гарантирует data.shots всегда присутствует
// и плотно покрывает сцену — компонент не знает про legacy одиночный src.
const HEADER_ZONE = 0.09;
const CAPTION_ZONE = 0.22;

function getRect(a: MediaAnnotation, mediaW: number, mediaH: number) {
  return { x: a.bbox.x * mediaW, y: a.bbox.y * mediaH, w: a.bbox.w * mediaW, h: a.bbox.h * mediaH };
}

export const Media: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, durationInFrames }) => {
  const frame = useCurrentFrame();
  const shots = data.shots || [];
  const grainSrc = staticFile("textures/grain-tile.png");

  // Переход между планами: тот же ассет подряд (другой фокус/аннотации того же
  // кадра) — всегда crossfade, никогда резкий cut; разные ассеты — в основном
  // cut, изредка crossfade. Никогда wipe/dip/burn — это язык ТОЛЬКО для стыков
  // между сценами (см. Main.tsx), иначе на каждой фотографии внутри одной
  // сцены мелькала бы "страница" — раздражало в прошлой версии.
  const shotKinds = shots.map((shot, i) =>
    pickShotTransition({ shotId: shot.id, index: i, sameAsset: i > 0 && shots[i - 1].src === shot.src })
  );
  const crossfadeFrames = Math.round(fps * SHOT_CROSSFADE_SEC);

  const boundariesFrames = shots.map((s) => Math.round((s.start - sceneStart) * fps));
  const endFrames = shots.map((s) => Math.round((s.end - sceneStart) * fps));

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "radial-gradient(ellipse at 50% 45%, #3d3326 0%, #211c17 65%, #15120f 100%)" }}>
      {shots.map((shot, i) => {
        const shotStartFrame = boundariesFrames[i];
        const shotDurFrames = Math.max(1, endFrames[i] - shotStartFrame);
        const nextKind = shotKinds[i + 1];
        return (
          <Sequence key={shot.id} from={shotStartFrame} durationInFrames={shotDurFrames} layout="none">
            <ShotContent
              shot={shot}
              beats={beats}
              fps={fps}
              format={format}
              grainSrc={grainSrc}
              durationInFrames={shotDurFrames}
              fadeOutFrames={nextKind === "crossfade" ? crossfadeFrames : 0}
            />
          </Sequence>
        );
      })}
      {shots.map((shot, i) => {
        if (shotKinds[i] !== "crossfade") return null;
        const boundary = boundariesFrames[i];
        const echoFrom = Math.max(0, boundary - crossfadeFrames);
        const echoDur = boundary - echoFrom;
        if (echoDur <= 0) return null;
        const shotDurFrames = Math.max(1, endFrames[i] - boundary);
        return (
          <Sequence key={`echo-${shot.id}`} from={echoFrom} durationInFrames={echoDur} layout="none">
            <CrossfadeEcho durSec={SHOT_CROSSFADE_SEC}>
              <ShotContent shot={shot} beats={beats} fps={fps} format={format} grainSrc={grainSrc} durationInFrames={shotDurFrames} fadeOutFrames={0} />
            </CrossfadeEcho>
          </Sequence>
        );
      })}
      {data.lower_third && (
        <LowerThirdPlate lt={data.lower_third} frame={frame} fps={fps} format={format} beats={beats} sceneStart={sceneStart} durationInFrames={durationInFrames} />
      )}
    </AbsoluteFill>
  );
};

// Плашка «имя / место / год» поверх любого плана: золотая линия прорисовывается,
// затем проявляется текст; на последних 0.4 с уходит. Не трогает подпись-caption
// (стоит выше неё) и зону субтитров шортсов.
const LowerThirdPlate: React.FC<{
  lt: LowerThirdData; frame: number; fps: number; format: SceneProps["format"]; beats: SceneProps["beats"];
  sceneStart: number; durationInFrames: number;
}> = ({ lt, frame, fps, format, beats, sceneStart, durationInFrames }) => {
  const long = format === "long";
  const at = buildRevealMap([lt.id], beats, sceneStart, fps)[lt.id] + (beats.some((b) => b.id === lt.id) ? 0 : Math.round(fps * 0.8));
  const line = easeInOut(revealProgress(frame, at, fps, 0.5));
  const text = easeInOut(revealProgress(frame, at + fps * 0.25, fps, 0.55));
  const out = clamp((durationInFrames - frame) / (fps * 0.4));
  if (line <= 0) return null;
  return (
    <div style={{ position: "absolute", left: long ? 70 : 44, bottom: long ? 210 : 440, opacity: out, pointerEvents: "none" }}>
      <div style={{ display: "flex", alignItems: "stretch" }}>
        <div style={{ width: 8, background: COLORS.gold, transformOrigin: "bottom", transform: `scaleY(${line})`, boxShadow: "0 0 12px rgba(0,0,0,0.5)" }} />
        <div style={{ background: "linear-gradient(90deg, rgba(20,14,10,0.86), rgba(20,14,10,0.62))", padding: long ? "12px 30px 12px 22px" : "10px 24px 10px 18px", clipPath: `inset(0 ${(1 - text) * 100}% 0 0)`, transform: `translateX(${(1 - text) * -24}px)` }}>
          <div style={{ fontFamily: "'Playfair Display', 'PT Serif', serif", fontWeight: 700, fontSize: long ? 46 : 42, color: COLORS.parchmentLight, lineHeight: 1.1, whiteSpace: "nowrap" }}>{lt.title}</div>
          {lt.subtitle && <div style={{ fontFamily: FONT_SERIF, fontWeight: 600, fontSize: long ? 30 : 28, color: COLORS.gold, letterSpacing: 1.5, marginTop: 4, whiteSpace: "nowrap" }}>{lt.subtitle}</div>}
        </div>
      </div>
    </div>
  );
};

const ShotContent: React.FC<{
  shot: MediaShot;
  beats: SceneProps["beats"];
  fps: number;
  format: SceneProps["format"];
  grainSrc: string;
  durationInFrames: number;
  fadeOutFrames: number;
}> = ({ shot, beats, fps, format, grainSrc, durationInFrames, fadeOutFrames }) => {
  const frame = useCurrentFrame();
  const fadeOutOpacity = fadeOutFrames > 0 ? clamp((durationInFrames - frame) / fadeOutFrames) : 1;
  const meta = shot.mediaMeta;
  const mediaW = meta?.width || 1920;
  const mediaH = meta?.height || 1080;
  const focus = shot.focus || { x: 0.5, y: 0.5 };
  const kind = shot.kind || "image";
  const annotations = shot.annotations || [];

  const frameW = format === "long" ? 1920 : 1080;
  const frameH = format === "long" ? 1080 : 1920;

  // Ken Burns прогресс считаем от локальной длительности ПЛАНА (из Sequence
  // durationInFrames, переданной пропом), а не всей сцены/композиции.
  const p = easeInOut(clamp(frame / Math.max(1, durationInFrames - 1)));
  const baseLayout = mediaLayout({
    mediaW, mediaH, frameW, frameH, fit: shot.fit || "cover", focus, annotations,
    progress: p, caption: Boolean(shot.caption), format,
  });
  // 15.10: фокус-зум на стилле (только cover, без аннотаций): плавный наезд на предмет вместо слабого Ken Burns
  const fz = kind === "image" && shot.zoom && baseLayout.fit === "cover" && annotations.length === 0
    ? focusZoomLayout({ mediaW, mediaH, frameW, frameH, zoom: shot.zoom, progress: frame / Math.max(1, durationInFrames - 1), safeTop: frameH * 0.1, safeBottom: format === "short" ? frameH * 0.27 : frameH * 0.06 })
    : null;
  const { scale: kbScale, tx, ty, fit: resolvedFit } = fz ? { ...fz, fit: "cover" as const } : baseLayout;

  const revealMap = useMemo(() => annotationTiming(shot, beats, shot.start, fps), [shot, beats, fps]);
  const captionP = revealProgress(frame, fps * 0.4, fps, 0.6);

  const grainX = (frame * 0.6) % 220;
  const grainY = (frame * 0.9) % 220;

  const allowedScreenYMin = frameH * HEADER_ZONE + 24;
  const allowedScreenYMax = frameH * (1 - (format === "short" ? 0.27 : CAPTION_ZONE)) - 24;
  const allowedMediaYMin = (allowedScreenYMin - ty) / kbScale;
  const allowedMediaYMax = (allowedScreenYMax - ty) / kbScale;

  const freezeAtFrame = shot.freezeAtSec !== undefined ? Math.round(shot.freezeAtSec * fps) : undefined;
  const frozen = freezeAtFrame !== undefined && frame >= freezeAtFrame;

  // "contain" оставляет пустые поля сверху/снизу или по бокам — вместо чёрных
  // полос показываем размытую затемнённую копию того же кадра на весь экран.
  const needsBackdrop = resolvedFit === "contain";
  const backdropCover = Math.max(frameW / mediaW, frameH / mediaH) * 1.16;
  const backdropTx = frameW / 2 - (mediaW * backdropCover) / 2;
  const backdropTy = frameH / 2 - (mediaH * backdropCover) / 2;

  return (
    <AbsoluteFill style={{ opacity: fadeOutOpacity }}>
      {needsBackdrop && (
        <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: mediaW,
              height: mediaH,
              transform: `translate(${backdropTx}px, ${backdropTy}px) scale(${backdropCover})`,
              transformOrigin: "0 0",
              filter: "blur(44px) brightness(0.5) saturate(0.85) sepia(0.35)",
            }}
          >
            {frozen && shot.freezeSrc ? (
              <Img src={shot.freezeSrc} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
            ) : kind === "video" ? (
              <OffthreadVideo src={shot.src} muted startFrom={Math.round((shot.trimStartSec ?? 0) * fps)} playbackRate={shot.playbackRate ?? 1} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
            ) : (
              <Img src={shot.src} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
            )}
          </div>
        </div>
      )}
      {kind === "image" && shot.callout ? (
        <CalloutShot src={shot.src} mediaW={mediaW} mediaH={mediaH} frameW={frameW} frameH={frameH} durationInFrames={durationInFrames} focus={focus} callout={shot.callout} />
      ) : (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: mediaW,
            height: mediaH,
            transform: `translate(${tx}px, ${ty}px) scale(${kbScale})`,
            transformOrigin: "0 0",
            filter: "sepia(0.16) saturate(0.92) contrast(1.06) brightness(0.98)",
          }}
        >
          {kind === "video" ? (
            frozen && shot.freezeSrc ? (
              <Img src={shot.freezeSrc} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
            ) : (
              <OffthreadVideo
                src={shot.src} muted
                startFrom={Math.round((shot.trimStartSec ?? 0) * fps)}
                playbackRate={shot.playbackRate ?? 1}
                style={{ width: mediaW, height: mediaH, objectFit: "fill" }}
              />
            )
          ) : (
            <Img src={shot.src} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
          )}

          <svg width={mediaW} height={mediaH} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
            {annotations.map((a) => (
              <Annotation
                key={a.id}
                a={a}
                mediaW={mediaW}
                mediaH={mediaH}
                progress={revealProgress(frame, revealMap[a.id] ?? 0, fps, 0.6)}
                allowedMediaYMin={allowedMediaYMin}
                allowedMediaYMax={allowedMediaYMax}
                allowedMediaXMin={(40 - tx) / kbScale}
                allowedMediaXMax={(frameW - 40 - tx) / kbScale}
                scale={kbScale}
                imgSrc={kind === "image" ? (shot.src) : undefined}
              />
            ))}
          </svg>
        </div>
      )}
      {shot.atmos && <Atmosphere kind={shot.atmos.kind} intensity={shot.atmos.intensity} seed={[...shot.id].reduce((acc, ch) => (acc * 31 + ch.charCodeAt(0)) % 997, 7) + Math.round(shot.start * 10)} />}

      {/* единая "плёночная" цветокоррекция поверх: тёплая виньетка + зерно */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 80% 80% at 50% 48%, rgba(0,0,0,0) 55%, rgba(10,8,14,0.5) 100%)`,
          pointerEvents: "none",
        }}
      />
      <AbsoluteFill
        style={{ opacity: 0.1, backgroundImage: `url(${grainSrc})`, backgroundPosition: `${grainX}px ${grainY}px`, pointerEvents: "none" }}
      />

      {shot.caption && captionP > 0 && (
        <div
          style={{
            position: "absolute",
            left: format === "long" ? 60 : 44,
            right: format === "long" ? 60 : 44,
            bottom: format === "long" ? 90 : 220,
            opacity: captionP,
            transform: `translateY(${(1 - captionP) * 16}px)`,
          }}
        >
          <div
            style={{
              display: "inline-block",
              fontFamily: FONT_SERIF,
              fontSize: format === "long" ? 32 : 30,
              color: COLORS.parchmentLight,
              background: "rgba(20,14,10,0.72)",
              padding: "10px 20px",
              borderLeft: `4px solid ${COLORS.red}`,
            }}
          >
            {shot.caption}
          </div>
        </div>
      )}

      {shot.credit && (
        <div
          style={{
            position: "absolute",
            right: 20,
            bottom: 14,
            fontFamily: FONT_HAND,
            fontSize: 20,
            maxWidth: "70%",
            textAlign: "right",
            color: "rgba(255,255,255,0.55)",
          }}
        >
          {shot.credit}
        </div>
      )}

    </AbsoluteFill>
  );
};

const Annotation: React.FC<{
  a: MediaAnnotation;
  mediaW: number;
  mediaH: number;
  progress: number;
  allowedMediaYMin: number;
  allowedMediaYMax: number;
  allowedMediaXMin: number;
  allowedMediaXMax: number;
  scale: number;
  imgSrc?: string;
}> = ({ a: aIn, mediaW, mediaH, progress, allowedMediaYMin, allowedMediaYMax, allowedMediaXMin, allowedMediaXMax, scale, imgSrc }) => {
  if (progress <= 0) return null;
  // loupe требует неподвижного кадра; на видео деградирует до обычной подписи
  const a: MediaAnnotation = aIn.kind === "loupe" && !imgSrc ? { ...aIn, kind: (aIn.text || "").trim() ? "label" : "circle" } : aIn;
  if (a.kind === "label" && !(a.text || "").trim()) return null;
  const rect = getRect(a, mediaW, mediaH);
  const cx = rect.x + rect.w / 2;
  const cy = rect.y + rect.h / 2;
  const reveal = Math.min(1, progress * 1.4);

  if (a.kind === "loupe" && imgSrc) {
    // Лупа: кольцо на цели + круглое увеличенное окно рядом, соединённые линией, подпись под окном.
    const ease = 1 - Math.pow(1 - progress, 3);
    const tr = Math.max(rect.w, rect.h) / 2;
    const R = Math.min(Math.min(mediaW, mediaH) * 0.22, 175 / scale);
    const z = Math.max(1.5, Math.min(a.zoom ?? 2.4, R / Math.max(tr, 1)));
    const fs = 34 / scale;
    const label = (a.text || "").trim();
    const labelRoom = label ? fs * 2.3 : 0;
    // направление от цели к центру кадра: окно «выезжает» внутрь картинки
    let dx = mediaW / 2 - cx, dy = mediaH / 2 - cy;
    if (Math.hypot(dx, dy) < mediaH * 0.1) { dx = cx < mediaW / 2 ? 1 : -1; dy = -0.35; }
    const dl = Math.hypot(dx, dy);
    const dist = tr + R + 38 / scale;
    const lx0 = cx + (dx / dl) * dist, ly0 = cy + (dy / dl) * dist;
    const lx = clamp(lx0, allowedMediaXMin + R + 12 / scale, allowedMediaXMax - R - 12 / scale);
    const ly = clamp(ly0, allowedMediaYMin + R + 12 / scale, Math.max(allowedMediaYMin + R + 12 / scale, allowedMediaYMax - R - labelRoom));
    const lr = R * ease;
    const lineLen = Math.hypot(lx - cx, ly - cy) || 1;
    const ux = (lx - cx) / lineLen, uy = (ly - cy) / lineLen;
    const clipId = `loupe-${a.id}`;
    const below = ly + R + labelRoom * 0.9 <= allowedMediaYMax + fs;
    const ty = below ? ly + R + fs * 1.45 : ly - R - fs * 0.5;
    const plateW = Math.max(label.length * fs * 0.52, fs * 2) + fs;
    const px = clamp(lx, allowedMediaXMin + plateW / 2, allowedMediaXMax - plateW / 2);
    return (
      <g opacity={Math.min(1, progress * 1.6)}>
        <circle cx={cx} cy={cy} r={Math.max(tr, 10 / scale) * ease} fill="none" stroke={COLORS.gold} strokeWidth={4 / scale} />
        {lineLen > tr + R && <line x1={cx + ux * tr} y1={cy + uy * tr} x2={cx + ux * (lineLen - lr)} y2={cy + uy * (lineLen - lr)} stroke={COLORS.gold} strokeWidth={3 / scale} strokeDasharray={`${10 / scale} ${7 / scale}`} />}
        <defs><clipPath id={clipId}><circle cx={lx} cy={ly} r={lr} /></clipPath></defs>
        <circle cx={lx} cy={ly} r={lr + 6 / scale} fill="rgba(15,11,8,0.85)" />
        <g clipPath={`url(#${clipId})`}>
          <image href={imgSrc} x={lx - cx * z} y={ly - cy * z} width={mediaW * z} height={mediaH * z} preserveAspectRatio="none" />
        </g>
        <circle cx={lx} cy={ly} r={lr} fill="none" stroke={COLORS.gold} strokeWidth={6 / scale} />
        {label && progress > 0.5 && (
          <g opacity={Math.min(1, (progress - 0.5) * 3)}>
            <rect x={px - plateW / 2} y={ty - fs * 0.95} width={plateW} height={fs * 1.4} rx={fs * 0.18} fill="rgba(15,11,8,0.78)" />
            <text x={px} y={ty} textAnchor="middle" fontFamily={FONT_HAND} fontSize={fs} fill={COLORS.parchmentLight}>{label}</text>
          </g>
        )}
      </g>
    );
  }
  if (a.kind === "circle") {
    const rx = (rect.w / 2) * progress;
    const ry = (rect.h / 2) * progress;
    return (
      <g opacity={reveal}>
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke={COLORS.red} strokeWidth={5} />
        <ellipse cx={cx} cy={cy} rx={rx * 1.03} ry={ry * 0.97} fill="none" stroke={COLORS.red} strokeWidth={2} opacity={0.5} />
      </g>
    );
  }
  if (a.kind === "box") {
    const w = rect.w * progress;
    const h = rect.h * progress;
    return (
      <rect x={cx - w / 2} y={cy - h / 2} width={w} height={h} fill="none" stroke={COLORS.red} strokeWidth={5} opacity={reveal} />
    );
  }
  if (a.kind === "arrow") {
    const mediaCx = mediaW / 2;
    const mediaCy = mediaH / 2;
    let dx = cx - mediaCx;
    let dy = cy - mediaCy;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    dx /= len;
    dy /= len;
    const offset = Math.min(mediaW, mediaH) * 0.24;
    const tailX = clamp(cx + dx * offset, mediaW * 0.04, mediaW * 0.96);
    const tailY = clamp(cy + dy * offset, mediaH * 0.04, mediaH * 0.96);
    const headX = clamp(tailX, rect.x, rect.x + rect.w);
    const headY = clamp(tailY, rect.y, rect.y + rect.h);
    const curX = tailX + (headX - tailX) * progress;
    const curY = tailY + (headY - tailY) * progress;
    const ang = (Math.atan2(headY - tailY, headX - tailX) * 180) / Math.PI;
    return (
      <g opacity={reveal}>
        <line x1={tailX} y1={tailY} x2={curX} y2={curY} stroke={COLORS.red} strokeWidth={5} strokeLinecap="round" />
        {progress > 0.85 && (
          <polygon points={`${curX},${curY} ${curX - 22},${curY - 11} ${curX - 22},${curY + 11}`} fill={COLORS.red} transform={`rotate(${ang}, ${curX}, ${curY})`} />
        )}
      </g>
    );
  }
  if (a.kind === "underline") {
    const uy = rect.y + rect.h;
    const x0 = rect.x;
    const x1 = rect.x + rect.w * progress;
    return (
      <path
        d={`M ${x0} ${uy} Q ${(x0 + x1) / 2} ${uy + 10} ${x1} ${uy}`}
        stroke={COLORS.red}
        strokeWidth={5}
        fill="none"
        strokeLinecap="round"
        opacity={reveal}
      />
    );
  }

  const label = annotationLabel({ text: a.text || "", rect, scale, xMin: allowedMediaXMin, xMax: allowedMediaXMax, yMin: allowedMediaYMin, yMax: allowedMediaYMax });
  const labelX = label.x;
  const labelY = label.y;

  // тёмная полупрозрачная подложка под подписью — без неё текст теряется на
  // пёстром фоне артефакта, даже с чёрной обводкой у букв
  const padX = label.fontSize * 0.5;
  const padY = label.fontSize * 0.3;
  const plateW = label.width + padX * 2;
  const plateH = label.height + padY * 2;

  return (
    <g opacity={reveal}>
      {label.connector && (
        <line x1={cx} y1={rect.y} x2={labelX} y2={labelY} stroke={COLORS.red} strokeWidth={2} strokeDasharray="4 6" opacity={0.6} />
      )}
      <rect
        x={labelX - plateW / 2}
        y={labelY - label.fontSize * 0.86 - padY}
        width={plateW}
        height={plateH}
        rx={label.fontSize * 0.18}
        fill="rgba(15,11,8,0.72)"
        style={{ clipPath: `inset(0 ${(1 - progress) * 100}% 0 0)` }}
      />
      <text
        x={labelX}
        y={labelY}
        textAnchor="middle"
        fontFamily={FONT_HAND}
        fontSize={label.fontSize}
        fill={COLORS.parchmentLight}
        stroke={COLORS.ink}
        strokeWidth={5 / scale}
        paintOrder="stroke"
        style={{ clipPath: `inset(0 ${(1 - progress) * 100}% 0 0)` }}
      >
        {label.lines.map((line, i) => <tspan key={i} x={labelX} dy={i === 0 ? 0 : label.lineHeight}>{line}</tspan>)}
      </text>
    </g>
  );
};
