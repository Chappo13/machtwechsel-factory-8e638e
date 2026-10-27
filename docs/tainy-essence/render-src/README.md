# render-src: копия рендерера Tainy (Remotion)

Копия `/home/agent/projects/youtube-longform/tainy/render` на 27.10.2026 (версия рендера 1.5.0 в `package.json`), только чтение оригинала. Описание композиций, параметров и логики выбора в `../03-VISUALS-CODE.md`. Размер копии около 0.7 МБ.

## Что здесь

| Путь | Что это |
|---|---|
| `src/Main.tsx`, `Root.tsx`, `index.ts` | единственная композиция `Main` (читает весь `scenes.json`), регистрация корня |
| `src/scenes/*.tsx` | 19 типов сцен: Media, Counter, NumberScene, Scale, TimelineScene, MapScene, RouteMap, Tally, Compare, Steps, FactStack, TableScene, Board, Document, Quote, TitleCard, Diary, Blueprint (+ GearMechanism), Stars; `SceneRouter.tsx` словарь `type -> компонент` |
| `src/components/*.tsx` | HeaderStrip, Subtitles, DateChip, AudioHint, Atmosphere, CalloutShot, CameraDrift, PanZoomCamera, CrossfadeEcho, DipBlack, FilmBurn, SceneWipeIn, Reveal, Parchment, TallyIcon, ShipSilhouette |
| `src/sketches/` | рукописные скетчи (roughjs): шестерня, рисованные фигуры |
| `src/utils/*.mjs/ts` | `quality.mjs` (нормализация и проверка `scenes.json`), `transitions.mjs`, `mediaLayout.mjs`, `revealTiming.mjs`, `autoFitText.mjs`, `subtitleGroups.mjs`, `overlayFade.mjs`, `annotationLabel.mjs`, `regions.mjs`, `time.ts` |
| `src/theme.ts`, `src/types.ts` | цвета и шрифты (тема «дневник», пергамент) и типы `ScenesFile`, `Scene`, `SceneData` (контракт) |
| `lib/preflight.mjs`, `lib/chunk-cache.mjs` | предполётная проверка медиа (ffprobe, sharp), раскладка медиа в bundle; кэш и возобновление чанков |
| `scripts/` | `check-scenes.mjs` (проверка `scenes.json` без рендера), `still.mjs` (одиночные кадры для QA), `gen-maps.mjs` и `gen-textures.mjs` (генерация растровых подложек карт и текстур бумаги) |
| `mac/tainy-build.mjs`, `mac/setup.sh` | сборщик на MacBook из `pack.zip` и установщик |
| `render.mjs` | серверный рендер (concurrency строго 1, чанки, QA-кадры); на сервере |
| `package.json`, `package-lock.json`, `tsconfig.json` | зависимости (Remotion зафиксирован на 4.0.286, React 18.3.1) |
| `test/renderer.test.mjs` | 59-КБ набор тестов рендерера на `node:test` (в копии пути ведут в структуру исходного проекта, отдельно не запускался) |
| `fixtures/scenes.montage-example.json` | пример `scenes.json` (без медиафайлов) |

Не скопировано: `node_modules`, `.cache` (бандлы и кэш медиа, сотни МБ), `public/textures` (8 МБ сгенерированных текстур и карт, воссоздаются скриптами), медиа из `fixtures`. Ключей и токенов в копии нет (проверено поиском по `token|secret|password|api_key|sk-|AIza`; в `mac/setup.sh` упоминаются ИМЕНА переменных `TAINY_DASHBOARD_URL/TOKEN` для скачивания рендера с пульта, значений нет).

## Как подключить к youtube-factory (ветка integrate)

Не сливайте это в существующую папку `remotion/`: другая модель (одна композиция `Main` против 13 отдельных), другой fps (25 против 30), другие зависимости. Положите рядом, например `remotion-tainy/`.

1. Требуется Node.js 20 или новее (на Mac проверка в `mac/setup.sh`; на сервере Tainy стоит Node 22).
2. `cp -r render-src ../remotion-tainy && cd ../remotion-tainy && npm ci`. Версии зафиксированы (`remotion`, `@remotion/bundler`, `@remotion/renderer` равно 4.0.286); у старой папки `remotion` версия `^4.0.0`, держите их в разных `node_modules`.
3. Сгенерируйте подложки (они не скопированы): `node scripts/gen-textures.mjs` (пергамент, зерно, пробка; можно пропустить, если уйдёте со старой темы) и `node scripts/gen-maps.mjs` (растровые карты регионов из `world-atlas`, нужен `sharp`; результат ляжет в `public/textures/maps`).
4. Проверка данных без рендера: `node scripts/check-scenes.mjs <путь к scenes.json>`. Студия: `npx remotion studio src/index.ts`, композиция `Main`, `props.scenesFile` = ваш `scenes.json`. Форма `scenes.json` описана в `../03-VISUALS-CODE.md` (раздел 1) и в `src/types.ts` (`ScenesFile`).
5. Рендер на MacBook: `mac/tainy-build.mjs` читает `pack.zip` (структура описана в `../04-ORCHESTRATION.md`, раздел 7): `scenes.json`, `media/`, `audio/long.m4a`, `manifest.json`, и рендерит `Main` через `renderMedia` (h264, crf 18, jpeg, aac 192k). Правки перед использованием: пути `~/Tainy`, имя «Тайны Древних» в уведомлениях и логах, ярлык «Собрать ролик.command», адрес пульта и токен в `setup.sh` (там спрашивает адрес и токен, значения в репозиторий не кладите).
6. `render.mjs` рассчитан на сервер Tainy: путь к браузеру `/home/agent/workspace/.playwright-browsers/chromium_headless_shell-1243` прошит в коде (`render.mjs`, `scripts/still.mjs`), `--concurrency` обязан быть 1 (или 2 со `--scenes`). Для Machtwechsel он нужен только если захотите рендерить на сервере; тогда замените путь на свой Chromium Headless Shell.
7. Что менять сразу под немецкий финансовый канал:
   - `src/theme.ts`: заменить палитру `COLORS` и шрифты `FONT_*` на тёмную тему старого `remotion/src/theme.ts` (Inter, `#0A0E1A`, акцент `#E63946`); `components/Parchment.tsx` либо убрать из `Main.tsx`, либо заменить на однотонный фон.
   - `src/scenes/NumberScene.tsx:15` и `src/scenes/Counter.tsx:31`: `toLocaleString("ru-RU")` заменить на `"de-DE"`.
   - `src/Main.tsx:100` (водяной знак по умолчанию «ТАЙНЫ ДРЕВНИХ») и `components/HeaderStrip.tsx` (строка «SECRETS OF THE ANCIENTS»): ваше название канала или пустая строка (`channel_name: ""` в `scenes.json` отключает знак).
   - `src/utils/regions.mjs` и `pipeline/code_graphics.py REGIONS` (зеркало): добавить регион `germany` (центр около 10.5 E, 51 N, `spanDeg` около 10-12), пересоздать карты `gen-maps.mjs`.
   - `src/utils/quality.mjs` и `SCENE_TYPES` в `pipeline/visual_quality.py`: туда нужно добавлять новые типы сцен (графики из старого `remotion/src/compositions`); без регистрации валидатор отвергнет сцену.
   - `src/scenes/SceneRouter.tsx`: словарь `COMPONENTS` : сюда регистрировать новые компоненты. Текст заглушки «Неизвестный тип сцены» на русском.
8. Как перенести отдельные сцены в старый рендер без `Main`: возьмите нужный файл из `src/scenes/` вместе с зависимостями : `sceneProps.ts`, `types.ts`, `theme.ts`, `utils/time.ts`, `utils/revealTiming.mjs`, `utils/autoFitText.mjs`, нужные компоненты из `src/components/`; компонент получает `{data, beats, sceneStart, durationInFrames, fps, format, frameW, frameH, seed}` и сам вычисляет появление элементов по `beats` (`buildRevealMap`). Оберните его в `Composition` с `calculateMetadata` от `durationSec`, как в `remotion/src/Root.tsx`. Но выигрыш Tainy именно в целостной связке `scenes.json` + `Main` + переходы + проверки, поэтому рекомендую вариант 5.

## Дубли имён со старым remotion

В старом `remotion/src/compositions` есть `TitleCard.tsx`; в Tainy `src/scenes/TitleCard.tsx` с тем же именем, но другой реализацией и другим интерфейсом (`SceneProps`). Остальные имена не пересекаются (в Tainy `Quote`, `TimelineScene`, `MapScene`, `Counter`, `NumberScene`, `TableScene`, `FactStack` против старых `QuoteCard`, `Timeline`, `MapWithPins`, `NumberCounter`, `ComparisonTable`, `StatCard`). Соответствия по смыслу в таблице в `../03-VISUALS-CODE.md`.
