# REFACTOR-SUMMARY.md — рефакторинг FIXTURE_ROM

Дата: 2026-07-27. Фаза 2: исполнение (комбо cost-saver) на основе REVIEW.md.

---

## Исправлено

### Важно

| # | Пункт | Статус |
|---|-------|--------|
| 1 | **Сужение `except Exception`** — sync.py (37→1, остался авто-установщик), diff_engine.py (3→0), gui.py (6→0). Сетевые → `requests.RequestException`, файловые → `OSError`/`json.JSONDecodeError` | ✅ Полностью |
| 2 | **Реестр брендов в `main()`** — 16 копипаст-блоков заменены на `BRAND_REGISTRY` + единый цикл. Все 36 golden-тестов проходят | ✅ |
| 3 | **rename.py: предупреждение о смене поведения** — dry-run по умолчанию, README обновлён | ✅ |
| 4 | **Golden-тесты `clean_model_and_version`** — 36 тестов на корпусе имён из metadata.json | ✅ |
| 5 | **SCRAPE_DELAY + `_scrape_get`** — пауза 1-2с между запросами скраперов, 22 `requests.get` заменены | ✅ |
| 6 | **`/api/logs` валидация offset** — `try/except ValueError → 400` | ✅ |
| 7 | **Атомарная запись JSON** — metadata.json, config.json через temp + `os.replace` | ✅ |

### Незначительно

| # | Пункт | Статус |
|---|-------|--------|
| 8 | **ThreadingTCPServer** — gui.py: однопоточный `TCPServer` → `ThreadingTCPServer` | ✅ |
| 9 | **cleanup_empty_directories** — удаляет только известный мусор (`.DS_Store`, `Thumbs.db`, `desktop.ini`), прочие dotfiles не трогает | ✅ |
| 10 | **beautifulsoup4** — удалена неиспользуемая зависимость из requirements.txt | ✅ |
| 11 | **`datetime.utcnow()`** → `datetime.now(datetime.timezone.utc)` в snapshot.py | ✅ |
| 12 | **Кэш хэшей SHA-256 по (size, mtime)** — snapshot.py пересчитывает только изменённые файлы | ✅ |
| 13 | **Комментарий к буквам дисков** — rom_common.py: пояснение, что D в конце (системный диск последним) | ✅ |

---

## Не исправлено

- `sync.py:29` — `except Exception` в блоке авто-установки `requests`. Оставлен намеренно: широкий перехват корректен для установки зависимостей (разные версии pip, подпроцессы и т.д.).

---

## Требует решения (эскалация на kimi-coder)

Нет архитектурных вопросов, требующих эскалации в рамках текущего рефакторинга.

---

## Новые проблемы, замеченные по ходу

Без исправления (не входили в REVIEW.md):

1. **`rename.py:198` (except Exception)`** — не было в scope #1; сузить тип, если доработка rename.py будет в плане.
2. **`rom_common.py:40,58` (except Exception)`** — не было в scope #1; сузить до `OSError` (чтение файлов).
3. **`snapshot.py:19,89` (except Exception)`** — не было в scope #1; сузить до `(OSError, PermissionError)` (чтение/запись файлов).
