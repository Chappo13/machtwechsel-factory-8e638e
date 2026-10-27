# Графика кодом (Remotion): что рисуется, как выбирается, что взять

Источник: `T/render/src/**` (Remotion 4.0.286, React 18.3.1), `T/pipeline/code_graphics.py`, `date_chips.py`, `scenes.py`, `T/CONTRACTS.md` (раздел «Типы сцен и data»), сравнение со старым рендером `/home/agent/worktrees/yt-factory-handoff/remotion/src` (13 композиций youtube-factory). `T/` = `/home/agent/projects/youtube-longform/tainy`. Исходники скопированы в `render-src/` (см. там `README.md`: как подключить).

## 1. Две разные модели рендера

| | Старый youtube-factory/remotion | Tainy `render/src` |
|---|---|---|
| Единица | 13 отдельных композиций (`Composition id=...`), каждая рендерится отдельно и склеивается ffmpeg | ОДНА композиция `Main`, она читает весь `scenes.json` и рисует ролик целиком (сцены, переходы, оверлеи, субтитры шортсов) |
| Вход | `props` композиции (`from, to, label, data[]...`) + `durationSec` | `scenes.json`: `scenes[{id, type, start, end, data, beats}]`, `words[]`, `chapters[]`, `overlays[]` |
| Время | 30 fps, длина через `calculateMetadata` и `durationSec` | 25 fps (из `scenes.json`), `durationInFrames = duration_sec * fps`, сцены без дыр |
| Связь со словами диктора | нет, длина фиксирована | `beats[{id, t}]`: элемент появляется на слове диктора (абсолютные секунды) |
| Стиль | тёмный современный (фон `#0A0E1A`, акцент `#E63946`, Inter) | «дневник исследователя»: пергамент, чернила, золото, рукописные шрифты (Caveat, Neucha, Marck Script, Cormorant Garamond, Playfair Display) |
| Зависимости | remotion, react | remotion, bundler, renderer, d3-geo, topojson-client, world-atlas, roughjs, sharp, @fontsource/* |

Переносимая идея Tainy это не конкретные карточки, а КОНТРАКТ: режиссёр (LLM) выдаёт сцену типа X с данными и `beats` на словах, рендер рисует. Тип сцены это ключ в словаре `COMPONENTS` в `scenes/SceneRouter.tsx`.

## 2. Старые 13 композиций youtube-factory (для сравнения)

Источник: `remotion/src/Root.tsx` (`defaultProps`) и заголовки файлов `remotion/src/compositions/*.tsx`. Все 13 рисуются на тёмном фоне (`BG_GRADIENT`, `#0A0E1A`), шрифт Inter, акцент `#E63946`, длина берётся из `durationSec` (`calculateMetadata`), для длинных немецких слов есть `fitFontSize`, для строк вида «1,9 Mrd» есть `num()` (защита от NaN).

| Композиция | Назначение (по комментариям в коде) | Параметры |
|---|---|---|
| `NumberCounter` | число набегает от `from` до `to` | `from, to, suffix, prefix, label` |
| `LineChart` | линейный график, рисуется к ~30% длительности; защита от плоской серии и NaN | `data[], title, yLabel` |
| `BarComparison` | два столбца A против B; минимальная высота меньшего столбца 10 px | `leftValue, leftLabel, rightValue, rightLabel, title` |
| `SplitScreen` | две страны или стороны с крупными значениями | `leftCountry, leftValue, leftSubtitle, rightCountry, rightValue, rightSubtitle` |
| `TitleCard` | заставка, для коротких драматических «Y.» огромный кегль, длинные компаунды с переносами | `title, subtitle, accent` |
| `MapWithPins` | схема с пинами; пины за пределами рамки отсекаются | `pins[], title` |
| `FlowConnection` | A -> B: переводы денег, связь двух узлов, анимированная стрелка с суммой; «заменяет бессмысленную карту-бублик» | `fromLabel, toLabel, fromSub, toSub, amount, direction (oneway|both), title` |
| `StatCard` | 2-4 ключевые цифры вместе | `title, items[]` |
| `QuoteCard` | цитата, вердикт суда, определение | `quote, source` |
| `Timeline` | хронология дат, веха-точки, подписи всплывают по очереди | `title, events[]` |
| `RankedBars` | рейтинг, топ-N, горизонтальные столбцы по убыванию | `title, items[], suffix` |
| `ComparisonTable` | сравнение A против B по нескольким параметрам (в комментарии: «vorher vs nachher», «Firma A vs Firma B») | `title, columns[2], rows[]` |
| `ConceptCard` | абстрактное понятие (коррупция, давление, цикл денег) иконкой и подписью вместо AI-картинки; иконки из реестра `icons/index.ts` (16 штук) | `icon, caption` |

Каких возможностей в Tainy НЕТ, а в старом рендере есть: линейный график `LineChart`, столбики `BarComparison`, рейтинг `RankedBars`, `FlowConnection` (поток денег между двумя сторонами с суммой), `SplitScreen` (две страны/цифры), иконочный `ConceptCard` на 16 SVG-иконках. Для финансового канала это самые нужные типы, их нужно доработать под модель `SceneProps` Tainy (раздел 7).

## 3. Типы сцен Tainy и их параметры

Источник: `render-src/src/scenes/*.tsx`, `types.ts`, `CONTRACTS.md`. «Слова» значит текст на экране; на канале «Тайны Древних» они отключены (мультиязычность), для одноязычного немецкого канала их можно включить.

| Тип (файл) | Что показывает | Параметры `data` | Для финансов |
|---|---|---|---|
| `media` (`Media.tsx`, 23 КБ) | фото, видео, иллюстрация; несколько планов `shots[]` в сцене; Ken Burns; аннотации `circle, arrow, box, underline, label, loupe`; плашка `lower_third`; `callout` (красный круг + стрелка + наезд на деталь реального фото); `atmos` (частицы); фокус-зум; стоп-кадр, если видео короче слота (замедление не ниже 0.6x, без зацикливания); размытая копия кадра вместо чёрных полос при `contain` | `src, kind, fit, focus{x,y}, trimStartSec, playbackRate, caption, credit, annotations[], shots[]` | брать как есть: основной тип (скриншоты документов, фото зданий, сток) |
| `number` (`NumberScene.tsx`) | одно большое число | `value, unit, label, prefix` | как есть; заменить `toLocaleString("ru-RU")` на `de-DE` |
| `counter` (`Counter.tsx`) | 1-3 числа набегают от `from` до `value` на своём beat, под числом золотая линия и подпись | `items[{id, value, unit, label, from, decimals 0..2, plain}]` | как есть, самый полезный: ставки, суммы, проценты |
| `scale` (`Scale.tsx`, 14 КБ) | силуэт человека против объекта по размеру (в метрах) | `subject{label,size_m}`, `reference`, `number` | для финансов не нужен (при необходимости адаптировать как «масштаб сумм») |
| `timeline` (`TimelineScene.tsx`) | хронология, 4 яруса подписей, чтобы не налезали | `from_year, to_year, events[{id, year, label}]` | как есть: этапы кризиса, даты решений |
| `map` (`MapScene.tsx`) | карта региона с пинами и маршрутом между ними; подложка растеризована заранее (контуры 177 стран через d3-geo, `scripts/gen-maps.mjs`), на кадре только дешёвые пины | `region (17 штук), pins[{id,label,lat,lon}], route[]` | Европа и Германия, нужен регион `germany` в `utils/regions.mjs` и `code_graphics.REGIONS` (зеркало, тест сверяет) |
| `map_route` (`RouteMap.tsx`) | линия маршрута рисуется прогрессивно, маркер корабль/человек/точка; одна точка = «место находки» с пульсирующим пином и наездом; подписи только английские КАПСОМ до 3 | `region, route_pts[{lat,lon}] 1-12, places[{lat,lon,en}], marker, year, route_from, route_to, hide_words` | потоки капитала, эмиграция (проект Massenflucht), торговые пути |
| `tally` (`Tally.tsx`, `TallyIcon.tsx`, `ShipSilhouette.tsx`) | N силуэтов (корабль, человек, монета, амфора, точка) выстраиваются сеткой; `count` (растёт 1 до N) или `lose` (часть «тонет», красное «минус N») | `icon, total 1..60, remain, tally_at, tally_dur` | эмигранты, обанкротившиеся компании: «из 100 осталось 40» |
| `compare` (`Compare.tsx`) | «было, стало» двумя рамками или шторкой `slider` на двух фото | `title, left{label,caption,src}, right{...}, mode (split|slider)` | как есть: до и после |
| `steps` (`Steps.tsx`, `StepIcons.tsx`) | процесс 3-5 звеньев с иконками и стрелками, стрелка дорисовывается на beat следующего звена | `title, steps[{id,label,icon}]`, иконки gear, flask, bolt, coin, sun, water, fire, hammer, scroll, eye, key, ship, stone, skull | механика процесса (как работает кредит, цепочка поставок), иконки заменить |
| `fact_stack` (`FactStack.tsx`) | столбик 3-4 крупных цифр с ярлыками, строки выезжают на beat | `facts[{id, big (до 12 символов), label}]` | как есть (аналог StatCard) |
| `table` (`TableScene.tsx`) | сравнительная таблица 2-4 столбца x 2-5 строк, строки проявляются на beat | `title, columns[], rows[{id, cells[]}]` | как есть (аналог ComparisonTable) |
| `board` (`Board.tsx`, 14 КБ) | доска расследования: карточки (размер подгоняется под текст, `fitText`), красные нити между карточками, штамп | `cards[{id,title,text,textId}], links[{id,from,to,label}], stamp` | «кто кому принадлежит», сеть связей, схема влияния |
| `document` (`Document.tsx`) | «рассекреченный документ»: строки проявляются, часть закрыта чёрной плашкой `redact`, которая потом снимается; штамп | `heading, date, lines[{id, text, redact[]}], stamp` | утечки, судебные документы, письма |
| `quote` (`Quote.tsx`) | цитата с автором | `text, author` | как есть |
| `title_card` (`TitleCard.tsx`) | заставка главы | `title, subtitle` | автоматическая вставка отключена (`title_card_sec: 0`) |
| `diary`, `blueprint`, `stars` | дневник с рукописными заметками и скетчами (14 наборов), чертёж (шестерня, разрез пирамиды, кладка, обелиск, артефакт), звёздное небо (4 созвездия) | см. `CONTRACTS.md` | тематически чужие (древность), для финансов не нужны |

Общие компоненты (`render-src/src/components/`): `HeaderStrip` (водяной знак канала + плашка главы), `Subtitles` (для шортсов: группы по 2-4 слова, фиксированная позиция, устойчивые), `DateChip` (стеклянная плашка с датой), `AudioHint` (подсказка о смене аудиодорожки), `Atmosphere` (частицы: снег, брызги, туман, пыль, искры), `CalloutShot`, `CameraDrift`, `PanZoomCamera`, `CrossfadeEcho`, `DipBlack`, `FilmBurn`, `SceneWipeIn`, `Reveal`, `Parchment`.

Утилиты (`render-src/src/utils/`): `quality.mjs` (30 КБ: `normalizeScenes` валидирует и канонизирует весь `scenes.json`, например одиночный `src` превращается в `shots[]`; проверка формы каждого типа сцены; отказ от кириллицы в `year`; `qualityWarnings`), `transitions.mjs` (детерминированные переходы, см. `01-DIRECTION.md`), `mediaLayout.mjs` (Ken Burns без обрезки защищённых областей, `focusZoomLayout`), `revealTiming.mjs` (`buildRevealMap`: когда появляется элемент; `boardTiming`; `annotationTiming`), `autoFitText.mjs` (`fitText`: подгон шрифта под ширину), `subtitleGroups.mjs`, `overlayFade.mjs`, `annotationLabel.mjs`, `regions.mjs` (17 регионов карт), `time.ts`.

## 4. Как план сцен выбирает композицию

1. Режиссёр (LLM, `scenes._llm_scenes_for_block`, промпт `prompts/scenes.md`) получает `SCENE_CATALOGUE` (строки 33-56 `scenes.py`: типы и поля) и для каждого плана называет `type`. Правила выбора и лестница «данные -> график, фото -> photo_real, нет фото -> иллюстрация, атмосфера -> сток» описаны в `01-DIRECTION.md`.
2. Код проверяет: `scenes.plan_scenes` нормализует и отбрасывает план с ошибками; `enforce_text_budget` оставляет текстовые карточки только при данных в озвучке, не подряд и не более 5%; для каждой графики нужен полный `graphic_spec`; `graphics_qa.run_qa` рендерит still и спрашивает vision; провал заменяет кадр на иллюстрацию.
3. Параллельно `code_graphics.py` САМ добавляет `map_route` и `tally` и расставляет `callout`, частицы и фокус-зум (раздел 5).
4. Итог пишется в `scenes.json`; в рендере `SceneRouter` ищет `COMPONENTS[scene.type]`; неизвестный тип рисует заглушку «Неизвестный тип сцены». `quality.mjs normalizeScenes` на входе отвергает сцены с невалидной формой.
5. Оверлеи поверх сцен (`overlays[]`: `date_chip`, `audio_hint`) добавляются после выбора медиа (`scenes.add_date_chips`, `add_audio_hint`) и не относятся к сценам.

## 5. `pipeline/code_graphics.py`: расстановка кодовой графики

Принцип: рисует рендерер, Python только РАССТАВЛЯЕТ. Платных генераций нет (LLM Sonnet и vision по подписке или API).

Фазы (вызываются из `scenes.run`):
- `code` (до подбора медиа, чтобы сэкономить картинки): LLM-план `PLAN_PROMPT` (ответ `{maps:[...], tallies:[...]}`, пачка по 70 кадров `llm_chunk_scenes`) -> `build_code_candidates` -> `sanitize_map` / `sanitize_tally` -> `choose_code_scenes` -> `apply_code_candidates`. Кодовая сцена ЗАМЕНЯЕТ кадры, сначала иллюстрации (`candidate_score`: иллюстрация +3, старая карта +3, сток +1.5, обычное +0.5, реальное фото -3, уже кодовая -9), границы сцены и покрытие озвучки сохраняются.
- `callouts`: LLM `CALLOUT_PROMPT` выбирает кадры с РЕАЛЬНЫМ фото, где диктор называет деталь («щель между камнями», «надпись»); vision (`locate_detail`) находит рамку детали; нет рамки значит пропуск; круг появляется на слове (`_word_time`), потом стрелка, потом наезд; проверка `circle_visible_on_cover`.
- `particles`: правила слов (`_ATMOS_RULES`) -> снег, брызги, туман, пыль, искры на 20-30% стиллов, не более 3 подряд.
- `zoom`: фокус-зум на стиллах: точка интереса по vision (`locate_subjects`, пачки по 6) или по эвристике `saliency_box`; конечный масштаб 1.22; `box` предмета целиком никогда не обрезается.

Ограничения (из `config.yaml code_graphics:`): доля времени кодовых сцен 15-25% (`code_share`), не более 2 подряд (`max_code_in_row`), не трогать первые 20 с и последние 15 с, сцена 5-10 с, карты до 14 (между картами не менее 60 с, `min_gap_sec`), счётчики до 6 (2..60 предметов), callout до 14, число в `tally` обязано звучать в озвучке этой сцены, подписи карты английские КАПСОМ до 24 символов (`clean_en`), год на карте только если назван в речи (`date_text_for`), регион подбирает код по точкам (`pick_region`: наименьший регион, в который влезают все точки с запасом), LLM даёт lat/lon.

Проверки: `grounding_issues` (число и год из графики должны звучать), `shares_report` (фактические доли), тесты `tests/test_code_graphics.py`.

## 6. `pipeline/date_chips.py` и плашки дат

Чистый код без LLM (разбор слов `words.json`). Подробности и числа в `01-DIRECTION.md`, раздел 10. Ключевое для переноса: `detect_dates(words)` распознаёт «в тысяча триста сорок девятом году», «XIV век», «сорок миллионов лет назад», римские цифры, контекстные слова «год/век/до нашей эры»; `plan_chips(...)` расставляет плашки с интервалами; `to_english_chip` переводит в формат без родного языка. Для немецкого придётся переписать лексику чисел (`_UNITS`, `_TENS`, `_HUND`, порядковые и т.д.) и слова «Jahr», «Jahrhundert», «v. Chr.», «vor ... Jahren». Для финансового канала плашка с датой подходит под «am 15. September 2008», «Q3 2022».

## 7. Что подходит финансовому каналу и что можно взять как есть

Брать как есть (после замены темы и локали, см. `render-src/README.md`):
1. `Media` целиком с аннотациями, callout, зумом, частицами, `lower_third` и защитой от обрезки: основа для документов (скриншоты отчётов, газетные вырезки как фото), зданий, людей. Аннотация `circle` или `box` на цифре в документе это ровно «красный круг на документе».
2. `Counter` и `NumberScene` (суммы, проценты, годы с `plain`), `FactStack`, `TableScene`, `Compare` (до и после), `TimelineScene` (хронология кризиса), `Quote`.
3. `Board` («доска расследования»: кто кому принадлежит, связи компаний и политиков) и `Document` (утечка, закрытая плашкой, потом снимается).
4. Переходы (`transitions.mjs`), субтитры шортсов, `DateChip`, `CrossfadeEcho`, `Reveal`, `autoFitText`, `revealTiming`, `normalizeScenes`.
5. Карты `MapScene`/`RouteMap`/`Tally` для темы эмиграции и потоков: нужен регион Германии и центровка.

Доработать (в Tainy нет):
1. Графики: перенести `LineChart`, `BarComparison`, `RankedBars`, `StatCard`, `FlowConnection` из `remotion/src/compositions` в виде сцен типов, например `chart_line`, `chart_bars`, `chart_rank`, `flow`, с `data` в `scenes.json`, `beats` на слове (по образцу `Counter`: `buildRevealMap(ids, beats, sceneStart, fps)` и `revealProgress`) и регистрацией в `COMPONENTS` и `SCENE_TYPES` (`utils/quality.mjs`, `visual_quality.py`). Это самая нужная работа для денежной темы.
2. Газетные заголовки: типа сцены `headline` нет; можно сделать на базе `Document` (строки + штамп + дата) с шрифтом газетного заголовка.
3. Тикер, бегущая строка котировок: нет.
4. Тема: пергамент и рукописные шрифты (`theme.ts COLORS`, `components/Parchment.tsx`) не подходят финансам; нужна тёмная тема из `remotion/src/theme.ts` (Inter, `BG #0A0E1A`, акцент `#E63946`). Цвета везде идут через `COLORS` и `FONT_*`, поэтому замена делается в `theme.ts` и в `Parchment`.
5. Локаль: `NumberScene.tsx:15` и `Counter.tsx:31` форматируют `toLocaleString("ru-RU")` (разделитель тысяч пробел, запятая в десятичных), для немецкого нужно `"de-DE"` (точка тысяч, запятая десятичных). `Main.tsx:100` по умолчанию рисует водяной знак «ТАЙНЫ ДРЕВНИХ» (если в `scenes.json` нет `channel_name`), `HeaderStrip.tsx` показывает «SECRETS OF THE ANCIENTS» при `brand_en`.
6. `hide_words` и правило «нет слов на экране» это политика канала Tainy (`render.on_screen_words: false`, обрезка в `scenes.strip_word_labels`). Для немецкого одноязычного канала слова на экране нужны, поэтому `config.yaml scenes.text_graphics_allowed_types` и `text_graphics_max_share` расширять, а `strip_word_labels` не вызывать.

## 8. Что я не проверял

- Я не запускал Remotion-рендер и не открывал студию: описание из чтения кода, типов, комментариев и контрактов. Тесты рендера `render-src/test/renderer.test.mjs` в копии зависят от структуры исходного проекта (`path.resolve(here, '../..')`) и отдельно не запускались.
- Внешний вид композиций (кроме вербальных описаний в `NEXT.md` и `FEEDBACK-PILOT-01.md`: «переходы под старину понравились», «финальная графика особенно понравилась», карточки доски переработаны 08.10 на крупный центрированный текст) оценить без просмотра кадров нельзя.
