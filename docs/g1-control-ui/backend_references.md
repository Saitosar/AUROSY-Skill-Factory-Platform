# Ссылки на репозиторий бэкенда платформы

Веб-клиент живёт в **этом** репозитории (`web/frontend/`). **HTTP API, WebSocket, OpenAPI и продуктовые гайды по данным** — в отдельном репозитории **бэкенда платформы**. Ниже — типичные пути **относительно корня того репозитория** (имена могут слегка отличаться — сверяйте с фактической структурой клона).

| Что нужно | Где искать в репозитории бэкенда |
|-----------|----------------------------------|
| Руководство по данным, роботу, чеклист экранов | `docs/frontend_developer_guide.md` |
| Handoff для агентов / автоматизации | `docs/frontend_agent_handoff.md` |
| Архитектура бэкенда Skill Foundry | `docs/skill_foundry/02_architecture.md` |
| План реализации бэкенда / конвейера / CLI | `docs/skill_foundry/03_implementation_plan.md` |
| Запуск FastAPI и связка с инструментами | `web/README.md` |
| Точка входа API (маршруты, OpenAPI) | `web/backend/app/main.py` |
| Golden-примеры для валидации | `docs/skill_foundry/golden/v1/` |
| Схемы контрактов авторинга (источник правды для синхронизации с `public/contracts`) | `docs/skill_foundry/contracts/authoring/` |

---

## Phase 5 — платформа (артефакты, очередь train, пакеты)

Маршруты реализованы в `web/backend/app/main.py`; идентичность запросов — заголовок **`X-User-Id`** (см. `web/backend/app/deps.py`), при отсутствии в dev используется **`G1_DEV_USER_ID`** (`web/backend/app/config.py`).

| Назначение | Метод и путь |
|------------|--------------|
| Сохранить JSON-артефакт пользователя | `POST /api/platform/artifacts/{name}` |
| Поставить асинхронный train в очередь | `POST /api/jobs/train` |
| Список задач пользователя | `GET /api/jobs` |
| Детали задачи (в т.ч. хвосты логов) | `GET /api/jobs/{job_id}` |
| Упаковать Skill Bundle из успешного job | `POST /api/packages/from-job/{job_id}` |
| Список пакетов | `GET /api/packages` |
| Скачать бандл | `GET /api/packages/{package_id}/download` |
| Загрузить `.tar.gz` | `POST /api/packages/upload` |
| Опубликовать / снять публикацию | `PATCH /api/packages/{package_id}` |

---

## `GET /api/meta` (дополнительные поля для UI)

Помимо `repo_root`, `sdk_python_root`, `mjcf_default`, `telemetry_mode` бэкенд отдаёт **`platform_worker_enabled`** (bool) и **`job_timeout_sec`** (число секунд) — для экрана «Настройки» и отладки очереди Phase 5.

После запуска бэкенда интерактивная схема API: `GET http://<host>:<port>/docs` (Swagger/OpenAPI).

Переменные окружения продакшена (CORS, worker платформы, DDS/mock телеметрия, таймауты job) и поведение WebSocket — в README и конфиге **репозитория бэкенда**; чеклист сопряжения с этим веб-клиентом: [../deployment/README.md](../deployment/README.md).
