# E2E прогон — затыки (фиксить после)

## Discover (шаг 1)
1. ideas=[] при рабочем скрейпинге: генерация идей (_generate_ideas_with_translation) и фолбэк
   _generate_ideas_standalone вернули пустой список — LLM отдаёт не-JSON/обёрнутый текст,
   `json.loads(response)` падает → []. Нужен устойчивый парсер (вырезать JSON-блок, ретрай,
   или structured output). [backend/scrapers/trending.py]
2. discover ~103с синхронно → первый запрос словил Railway gateway "upstream error".
   Нужно: discover в фон (как generate) ИЛИ урезать число search_queries/параллелить. [api/main.py, trending.py]

## Генерация (прогон task 3a647289, «Windkraft-Skandal», 13.5 мин, БЕЗ падений)
РАБОТАЕТ: голос встык (794с, music совпадает — concat-фикс ок), fcpxml относительные пути
(voiceover.mp3 / clips/clip_000.mp4 — нет offline), zip 1.83ГБ полный (23 клипа, voice, music,
fcpxml, PUBLISH_de.txt с RU, metadata, open-davinci.command). Скачивание с сайта ок.

ЗАТЫКИ (качество, не краши):
3. Длина видео 13.2 мин вместо 22: сценарий вышел ~12k символов вместо 20k. Вероятно virality_filter/
   improve укоротили (аудит: virality перетирает improve и не скорится; length enforcement до правок).
   [script.py, virality.py] — усилить enforcement ПОСЛЕ всех правок.
4. Темп нарезки: 23-27 клипов на 13 мин = ~29с на клип (длинные статичные шоты). Нужен shot-splitting
   ~6с (визуальный апгрейд из аудита). [clips.py/assembly.py]
5. progress_percent считается по 9 фазам, а их 11 → прогресс врёт (33%/44%/55%/88%). [api/main.py] минор.

## E2E #2 (после фиксов)
6. discover viral_videos=0 даже с YT Data API: фильтр max_subs=200k режет крупные каналы,
   что идут первыми по order=viewCount → после фильтров пусто → standalone-идеи (не тренды).
   Идеи ВОЗВРАЩАЮТСЯ (JSON-парсер починен), но не трендовые. Нужно: смягчить/переосмыслить
   фильтры (искать small-channel viral иначе) ИЛИ order=relevance + фильтр после. [trending.py]

## Ревью-workflow (23 подтв.) — ИСПРАВЛЕНО в этом билде
- БЛОКЕР scene_text TypeError (multi.py сигнатура) ✓
- БЛОКЕР Remotion качал chrome в рантайме → --browser-executable ✓
- search_query/scene_text в clip_map (QA-заметки) ✓; ytdlp→to_thread ✓; autorun title_original ✓; clip_map ensure_ascii ✓; фильтры скрейпинга смягчены ✓

## Ревью — ОТЛОЖЕНО (после успешного прогона с графикой)
- #4 fcpxml: клипы встык (cursor+=dur) → видеоряд короче голоса + рассинхрон к концу. Класть offset=scene_start, dur=next_start-start. [fcpxml_export.py _build_video_spine] ВАЖНО для качества.
- #7 шрифт Inter не установлен → инфографика на Liberation Sans (косметика). loadFont или ttf в образ.
- #8 нет package-lock → невоспроизводимость образа (npm ci).
- #9 YT квота ~1020 units/discover → ~9/день; сократить search_queries до 4.
- #11 cut_points alignment не заполняет → каты по таймеру, не по голосу (аудио единое, не критично).
- #13 reuse-фолбэк type-blind (дубль типа) — редкий.
