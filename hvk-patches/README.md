# HVK — патчи: UI/UX + Архитектура + ROI правки

В этом наборе — три логические части:
1. **UI/UX passover** (`01`–`05`) — тёмный режим, адаптив, тосты, кнопки.
2. **Архитектурные правки** (`06`–`10`) — онбординг, кэш аудит-отчёта, рефакторинг чата, аналитика 2.0.
3. **ROI для роста «понимания»** (`11`–`14`) — веса по свежести голоса, семантическая antipathy, TTL уроков, обучение правок.

## Быстрое применение всех правок

```bash
cd C:\HVK
git apply --whitespace=fix hvk-full-passover.patch
```

## Построчно по блокам

```bash
# === UI/UX passover ===
git apply 01-theme.patch
git apply 02-chat-view.patch
git apply 03-app.patch
git apply 04-pages-view.patch
git apply 05-ideas-plan-delete.patch

# === Архитектурные правки ===
git apply 06-audit-cache.patch
git apply 07-onboarding-fix.patch
git apply 08a-router-new-file.patch      # НОВЫЙ файл: app/agents/router.py
git apply 08b-chat-refactor.patch
git apply 09-intent-probe.patch
git apply 10-analytics-2.patch

# === ROI для роста «понимания» ===
git apply 11-voice-freshness.patch        # Веса по свежести в build_voice_profile
git apply 12-semantic-antipathy.patch    # is_semantically_blocked через ChromaDB
git apply 13-lesson-ttl.patch            # TTL 2 года на Lesson + cron job
git apply 14-edit-learning.patch         # edit_draft учится на rejected-правках
```

> **Зависимости**: `11` не зависит от предыдущих.
> `12` требует `06` (там `audience_cache`, который использует `_get_embedder`).
> На самом деле `12` импортирует `_get_embedder` из `app/memory/chroma.py`, который уже есть в репо.
> `13` — самостоятельный (правит `scheduler/jobs.py`).
> `14` требует `12` (там `recent_style_lessons`, который использует join через `Suggestion`).

## Что меняется в ROI-итерации

### 11 — Веса по свежести в `build_voice_profile`

**Проблема**: голос строился из всех постов усреднением. За 2 года стиль мог измениться, а старые посты размывали сегодняшний голос.

**Решение**:
- `_weighted_stats(posts)` — каждому посту вес `max(0.3, 1.0 - age_days/180)`. Пост старше 6 месяцев — минимальный вес 0.3, не нулевой (голос не теряем).
- Образцы в промпте разделены: «свежие» (последние 30) как основной сигнал, «старые» (до 60) — отдельным блоком «Раньше автор писал так (контекст, но сегодня может звучать иначе)».
- В системный промпт добавлено: «Опирайся в первую очередь на свежие посты — это сегодняшний голос автора. Старые посты — только чтобы не потерять нить, не размывай ими тон.»
- В сохранённом `VoiceProfile.profile` появились поля `fresh_posts_used`, `older_posts_used`, `freshness_window`.

**Эффект**: голос перестаёт съезжать в «среднее по больнице» при росте архива. Сегодняшний стиль автора доминирует.

### 12 — Семантическая antipathy через ChromaDB

**Проблема**: `antipathy_topics()` возвращал lowercase-строки. Отвергла «Завтрак с чаем» — antipathy на эту строку. Через неделю сгенерируется «Утренний чай» — пройдёт мимо фильтра, потому что строки разные.

**Решение**:
- `MemoryStore.is_semantically_blocked(topic, threshold=0.78)` — новый метод.
- Сначала проверяет точное совпадение (быстро, без сети).
- Потом эмбеддит topic и все antipathy-темы через `ChromaDB._get_embedder()` (локальный ONNX, 384-мерный).
- Считает косинусное сходство через `numpy`. Если лучшее сходство ≥ 0.78 — `blocked=True, matched=«близкая antipathy»`.
- В `generate_ideas()` каждая сгенерированная идея проверяется. Если blocked — фильтруется, и при необходимости генератор дособирает ещё (повторный вызов с явным списком «уже предложенных»).
- Порог 0.78 — empirically «тот же смысл». Можно тюнить.

**Эффект**: «Утренний чай» больше не предлагается, если отвергнута «Завтрак с чаем». Ловит перефразированные повторы.

### 13 — TTL на Lesson (авто-удаление старых)

**Проблема**: `MemoryStore.prompt_block()` брал последние 12 уроков. Со временем они накапливались без очистки — автор меняется, а урок 2-летней давности «не зашёл тёплый свитер» всё ещё размывал сигнал.

**Решение**:
- `MemoryStore.prune_old_lessons(days=730)` — удаляет уроки старше 2 лет.
- Cron-задача `job_prune_memory` в `scheduler/jobs.py` — запускается каждый день в 02:45 (раньше остальных задач).
- Antipathy уже имеют `expires_at` (40 дней). Preference стабильны по дизайну (предпочтения долговременны).

**Эффект**: память не зарастает устаревшими уроками. Автор изменился — старые уроки автоматически выпадают через 2 года.

### 14 — Обучение `edit_draft` на фидбеке по правкам

**Проблема**: `apply_feedback` для `kind="edit"` клал `Preference(kind="style", key=title правки)`. Но title правки = «убрал пассивный залог», не признак стиля. И в `Antipathy` уходила тема правки целиком — но тема может быть ок, просто стиль не тот. Плюс `edit_draft` вообще не читал эти уроки — они шли в `prompt_block()`, но неявно.

**Решение**:
- `MemoryStore.recent_style_lessons(limit=8)` — новый метод. Берёт уроки с `outcome=fail/mixed`, `source=feedback`, `kind=edit` (через join на `Suggestion`).
- В `edit_draft` подмешивается блок «Чего автору НЕ подходит в правках (учитывай, не повторяй)» — последние 6 отвергнутых правок с причиной.
- `apply_feedback` для `kind="edit"`:
  - Больше НЕ создаёт `Preference(kind="style")` — стиль unstable, отдельная правка не должна усиливать «стиль» как предпочтение.
  - Больше НЕ создаёт `Antipathy` — тема может быть ок, просто стиль не тот.
  - Только `Lesson` — который потом читается через `recent_style_lessons`.

**Эффект**: редактор не повторяет rejected-стиль. Если автор отверг «слишком литературную правку» — в следующий раз редактор видит это в промпте и не делает так снова.

## Smoke-тест после применения

```bash
cd C:\HVK
.venv\Scripts\python.exe -m py_compile ui\theme.py ui\chat_view.py ui\app.py ui\pages_view.py ^
  app\agents\router.py app\agents\chat.py app\agents\audience.py app\agents\editor.py ^
  app\agents\ideas.py app\api\routes\chat.py app\api\routes\misc.py app\api\routes\onboarding.py ^
  app\api\routes\ideas_plan.py app\db\models.py app\memory\store.py app\memory\ingest.py ^
  app\memory\feedback.py app\scheduler\jobs.py app\voice\profile.py

# Перезапусти API — таблица audience_cache создастся сама
scripts\stop.bat
scripts\start.bat

# Проверь /chat/intent (быстрая диагностика классификатора)
curl -X POST http://127.0.0.1:8080/chat/intent -H "Content-Type: application/json" -d "{\"message\":\"дай идеи\"}"

# Проверь аналитику 2.0
curl "http://127.0.0.1:8080/analytics/heatmap?days=90"
curl "http://127.0.0.1:8080/analytics/compare?days=30"
```

## Что именно уменьшает «нейрослоп»

После всех правок:
1. **Меньше выдуманных фактов** — архив растёт, больше шансов что нужный факт уже в контексте.
2. **Меньше повторяющихся идей** — antipathy 40 дней + семантическая проверка ловит перефразы.
3. **Меньше сдвига голоса в «среднее»** — свежие посты доминируют, старые не размывают.
4. **Меньше устаревших уроков** — TTL 2 года, autor evolves, старые not relevant.
5. **Меньше повторов rejected-стиля** — редактор видит «чего не делать».
6. **Меньше ожидания на аналитике** — кэш аудит-отчёта, мгновенный ответ.
7. **Меньше угадайки в пустом чате** — skip-import удалён, нельзя войти без архива.

## Известные ограничения

1. **ChromaDB embedder** при первом запуске скачивает 79MB ONNX-модель `all-MiniLM-L6-v2`. Один раз — потом кэшируется в `~/.cache/chroma/`.
2. **Порог 0.78 для семантической antipathy** — empirically. Если слишком агрессивно (блокирует хорошие идеи) — подними до 0.82. Если слишком мягко (пропускает явные повторы) — опусти до 0.74.
3. **TTL 2 года на Lesson** — при `prune_old_lessons(days=730)`. Если автор хочет дольше помнить — подними до 1095 (3 года).
4. **Свежесть голоса** — вес 0.3 для постов старше 6 месяцев. Если автор хочет больший акцент на свежем — подними `0.3` до `0.5` в `_weighted_stats`, или сузь окно со 180 до 90 дней.
5. **Cron `job_prune_memory`** — запускается в 02:45 по Москве. Если API в это время не работает — задача пропустится, выполнится на следующий день.

## Файлы

- `hvk-full-passover.patch` — всё одним патчем (4106 строк, ~165KB).
- `01`–`14` — по логическим блокам.
- `README.md` — этот файл.
