# Соответствие веб-клиента и дерева SDK (Python tools)

Веб-приложение **AUROSY Skill Factory** (`web/frontend/`) не заменяет файловую структуру репозитория **unitree_sdk2_python** (или вашего клона платформы): оно даёт HTTP/WebSocket-оболочку и JSON-артефакты, которые инженер может положить рядом с инструментами из `tools/`.

| Продуктовый уровень | Экран(ы) в вебе | Типичные пути на диске (SDK) |
|---------------------|-----------------|------------------------------|
| Действие (motion / mid-level) | Студия движений, Авторинг (keyframes), Конвейер | `mid_level_motions/basic_actions\|complex_actions/<name>/` — `pose.json`, `execute.py` (как после Pose Studio / `action_exporter`) |
| Навык (обученный) | Задачи → train, Пакеты (Skill Bundle) | Платформа: архив `.tar.gz` через API. В SDK: `library/skills/<name>/` (генерация через `skill_generator.py`) — **другая упаковка**, смысл тот же |
| Сценарий | Студия навыков + экспорт `scenario.json` v1 | `high_level_motions/<name>/scenario.json` (+ `run.py` при генерации из Tkinter Scenario Studio) |

**Совместимость `scenario.json`:** поля `version` (1), `title`, `nodes[]` с `subdir`, `action_name`, `speed`, `repeat` — как в `tools/scenario_studio/runner.py`.

Подробнее о API: [backend_references.md](backend_references.md), OpenAPI бэкенда.
