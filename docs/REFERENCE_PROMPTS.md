# Референсные промпты (из Instagram reel — рабочий конвейер, $5700 за 2.5 мес)

Источник: Instagram reel от автора finance-канала на EN. Все промпты ниже — оригинал.
Наша адаптация: backend/pipeline/ и backend/scrapers/

---

## 1. Генерация тем (Topic Ideas)

Оригинал:

> Generate 20 unique video ideas for a finance and money related channel that covers
> the most interesting obscure subjects that are appealing to the mainstream audience
> but are still quite unique and lesser talked about.

Категории: Psychology, Hidden history, Hidden systems, Behaviour, Economics

Примеры тем:
- "Dead Hand Account: What Happens to Your Money If You Disappear"
- "Why the Dutch Created the First Stock Market Bubble (And It Was Tulips)"

Анализ ошибок (из его Claude-диалога):
> The weakest videos fell into traps: titles too audience-specific
> (POV format, crypto-specific), oversaturated ("Biggest Financial Mistakes in Your 20s"),
> or fear-based without promising a clear solution (defeatist framing kills watch time).

Наша адаптация: backend/scrapers/trending.py

---

## 2. Написание сценария (Script Generation)

Оригинал:

> Write a YouTube script in Nick's distinctive financial education style for the
> video titled: "[TITLE]".
> The script should follow Nick's proven format:
> Opening Hook — start with a relatable financial scenario that makes viewers think "that's exactly me".
> Introduction: "My name is Nick and I spend way too much time thinking about [relevant financial topic]."
> Style: conversational tone, natural speech patterns, shocking statistics with sources,
> concrete dollar amounts, psychological shifts behind financial decisions, relatable analogies.
> Structure: 2,500-3,500 words, both math AND psychology, actionable steps, storytelling.
> Tone: authoritative but approachable.

Результат: ~3,100 слов, 18-22 минуты.

Наша адаптация: backend/prompts/script-de.md и script-es.md

---

## 3. Фильтр вирусности (Virality Filter) — САМЫЙ ЦЕННЫЙ

Оригинал:

> You are a YouTube strategist who has analyzed 10,000+ viral finance videos.
> Review the following script and do three things:
> 1) Rate the hook from 1 to 10 and rewrite it if it's below 8.
> 2) Find the three weakest moments where a viewer would click away —
>    and rewrite them to add a curiosity loop or open new tension.
> 3) Add one "pattern interrupt" every 90 seconds of script — a shocking stat,
>    a counterintuitive claim, or a direct question to the viewer.
> Return the revised script with all changes highlighted.

Наша адаптация: backend/pipeline/virality.py (DE/ES версии)

---

## 4. Его workflow (ручной, для справки)

1. Claude -> генерация названия канала
2. Канал-референс -> расширение NextLeft -> выгрузка данных
3. Таблица -> Claude -> анализ паттернов заголовков
4. Claude -> 20 уникальных идей на базе анализа
5. Claude -> сценарий 15-18 мин
6. Claude -> фильтр вирусности (ОТДЕЛЬНЫЙ проход)
7. ElevenLabs -> озвучка
8. На КАЖДОЕ предложение -> генерация картинки
9. Анимация картинок (Hixfield)
10. Монтаж в CapCut + авто-субтитры
11. Передает команде на конвейер

Что мы автоматизировали: шаги 2-9 в одном пайплайне.
Что НЕ делаем: персонаж, субтитры, AI-видео (дорого, добавим при доходах).
