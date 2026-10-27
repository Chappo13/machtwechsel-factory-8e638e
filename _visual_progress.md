# Визуал-оверхол — ГОТОВО (луп, клиент в отъезде). НЕ задеплоено.

План: memory/visual-overhaul-plan.json. Деплой держим до возвращения клиента.

## Сделано (всё рендер/тест-проверено, закоммичено на integrate)
- [x] FlowConnection.tsx — поток A→B (замена карты-«бублика»). Рендер ✓
- [x] StatCard.tsx — 2-4 KPI-плитки. Рендер ✓
- [x] QuoteCard.tsx — цитата/вердикт/определение. Рендер ✓
- [x] Timeline.tsx — хронология дат. Рендер ✓
- [x] RankedBars.tsx — топ-N бары. Рендер ✓
- [x] ComparisonTable.tsx — многострочное A vs B. Рендер ✓
- [x] ConceptCard.tsx + icons/index.ts (16 SVG-иконок) + backend/config/concept_icons.json
      — код-иконка+подпись ВМЕСТО Flux-дудла (меньше AI-gen). Рендер ✓ (justice, mask)
- [x] remotion_validate.py — grounding-валидатор (число/место/год/цитата обязаны быть в
      тексте сцены, иначе сток). Толерантно: Mio/Mrd/Tsd + нем. слова + ±7%. 9 юнит-тестов ✓
- [x] Проводка: clips._normalize_scene_types → validate_remotion_data; новые mediums/типы;
      remotion_render роутит новые композиции + split_kind (фикс безбарного SplitScreen)
- [x] Промпт plan_scenes: контракт grounding, запрет pixel-координат, concept/flow/новые типы

## Отложено (follow-up, по возвращении — не рискуем без присмотра)
- [ ] Layer-3 второй LLM-проход (семантика: перепутанные label↔value) — трогает core plan_scenes, нужен живой прогон
- [ ] Мульти-точечная карта (3+ места) через places.json — редкий кейс (flow покрывает 2 места)
- [ ] BarComparison ratio_badge рендер + LineChart y-тики — мелкий полиш

## Деплой (по возвращении клиента)
git push integrate:master (RED). Потом клиент собирает 1 тест-видео → смотрим новые визуалы в DaVinci.
