# G1 Control Web API (Skill Foundry backend)

В этом репозитории (**AUROSY_creators_factory_platform**) — **бэкенд** FastAPI, сабмодуль **Unitree** `unitree_sdk2_python` (upstream `unitree_sdk2py`), пакет **AUROSY** `packages/skill_foundry` (CLI `skill-foundry-*`) и документация. **SPA (Vite + React)** живёт в отдельном репозитории **AUROSY_creators_factory** (`web/frontend/`); см. `web/README.md` в корне того репозитория (типичный соседний клон: `../AUROSY_creators_factory/web/README.md`).

Функциональность: авторинг Phase 0, телеметрия (mock WebSocket / DDS), сценарии mid/high level, CLI `skill-foundry-*`, video-to-motion retarget API, Phase 5 (очередь обучения, каталог пакетов).

## Бэкенд

Из каталога `web/backend`:

```bash
cd web/backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Рекомендуется из корня репозитория платформы (один раз на venv; из web/backend: cd ../..):
#   pip install -e "./unitree_sdk2_python" && pip install -e "./packages/skill_foundry[export]"
# Для ручного запуска CLI без pip install можно выставить:
#   export PYTHONPATH="/abs/path/to/AUROSY_creators_factory_platform/packages/skill_foundry:/abs/path/to/AUROSY_creators_factory_platform/unitree_sdk2_python"
export G1_REPO_ROOT="/abs/path/to/AUROSY_creators_factory_platform"   # опционально; по умолчанию вычисляется из app/config.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Переменные окружения (префикс `G1_`):

| Переменная | Описание |
|------------|----------|
| `G1_SDK_PYTHON_ROOT` | Путь к `unitree_sdk2_python` (если не рядом с репо) |
| `G1_SKILL_FOUNDRY_PYTHON_ROOT` | Путь к `packages/skill_foundry` (если не рядом с репо) |
| `G1_MJCF_PATH` | MJCF для playback (по умолчанию ищется `unitree_mujoco/.../scene_29dof.xml`) |
| `G1_TELEMETRY_MOCK_HZ` | Частота mock WebSocket (по умолчанию 10) |
| `G1_USE_DDS_TELEMETRY` | `1` для DDS (не реализовано в этой сборке) |
| `G1_PLATFORM_DATA_DIR` | Данные Phase 5: SQLite, workspace job’ов, пакеты (по умолчанию `web/backend/data/platform`) |
| `G1_JOB_TIMEOUT_SEC` | Таймаут одного training job (сек), по умолчанию `7200` |
| `G1_MAX_CONCURRENT_JOBS_PER_USER` | Сколько job’ов в `running` на одного пользователя, по умолчанию `1` |
| `G1_DEV_USER_ID` | Пользователь по умолчанию, если нет заголовка `X-User-Id` (только dev) |
| `G1_PLATFORM_WORKER_ENABLED` | `0` — не запускать фоновый воркер очереди (job’ы останутся в `queued`) |
| `G1_SKIP_VALIDATION_GATE` | `1` / `true` — разрешить `PATCH` с `published: true` без успешной продуктовой валидации пакета (**только разработка**; в продакшене не использовать) |
| `G1_MOTION_PUBLISH_MAX_MSE` | Опционально: верхняя граница `metrics.tracking_mean_mse` из `eval_motion.json` при публикации пакетов с `manifest.motion` (Phase 6) |

Спецификация Phase 5: [docs/archive/11_phase5_platform.md](../docs/archive/11_phase5_platform.md). Безопасность рантайма и целостность пакетов (Phase 6.2): [docs/skill_foundry/13_phase6_runtime_security.md](../docs/skill_foundry/13_phase6_runtime_security.md).

OpenAPI: `http://127.0.0.1:8000/docs`

### Контракт API (кратко)

Источник правды после деплоя — Swagger по адресу выше. Ниже — сводка по `app/main.py`.

**Общие**

- `GET /api/health` — `{ "status": "ok" }`
- `GET /api/meta` — `repo_root`, `sdk_python_root`, `skill_foundry_python_root`, `mjcf_default`, `telemetry_mode` (`mock` / `dds`), `platform_worker_enabled`, `job_timeout_sec`, `dds_joint_bridge`, `dds_joint_publish_hz`, `joint_command_enabled`, ретаргетинг (`retargeting_enabled`, `retargeting_source_skeleton`, `retargeting_target_robot`), Phase 6: `motion_pipeline_enabled`, `motion_publish_max_mse`

**Суставы и пайплайн**

- `GET /api/joints` — `joint_map`, `groups`
- `POST /api/joints/targets` — тело `{ "joints_deg": { "<index>": градусы, ... } }`; **404**, если `joint_command_enabled` выключен в конфиге
- `POST /api/joints/release` — сброс целей; **404**, если joint command выключен
- `GET /api/pipeline/detect-cli` — в `PATH` проверяются только три CLI основного UI: preprocess, playback, train (не `validate` / `package` / `runtime`)
- `POST /api/validate` — `{ "kind": "keyframes"|"motion"|"scenario"|"reference_trajectory"|"demonstration_dataset", "payload": { ... } }`
- `POST /api/pipeline/preprocess` — `keyframes`, опционально `frequency_hz`, `validate_motion`, `mjcf_path`
- `POST /api/pipeline/validate-motion` — офлайн-проверка ReferenceTrajectory v1 (перед playback)
- `POST /api/pipeline/retarget` — конвертация MediaPipe landmarks (`[33,3]` или `[N,33,3]`) в углы G1 (`joint_order` + `joint_angles_rad`) с лимитами из `joint_map.json`
- `POST /api/pipeline/motion/run` — Phase 6: оркестрация motion-пайплайна (`pipeline_id`, `action`: `init` \| `attach_capture` \| `build_reference` \| `enqueue_train` \| `sync` \| `request_pack`, опционально `reference_artifact`, `landmarks_artifact`, `train_config`, `train_mode`, `motion_export`, `force`, …); требуется заголовок `X-User-Id` (как для Phase 5)
- `GET /api/pipeline/motion/{pipeline_id}` — чтение и обновление стадий из job workspace (sync)
- `POST /api/pipeline/playback` — `reference_trajectory` или `reference_path`, опционально `mjcf_path`, `mode`, `dt`, `kp`, `kd`, `seed`, `max_steps`, `write_demonstration_json`
- `POST /api/pipeline/train` — `reference_path`, `config_path` или `config`, опционально `demonstration_path`, `mode` (`smoke` \| `train` \| `amp`, синхронно); для AMP **eval-only**: `eval_only: true`, `checkpoint_path` (путь к policy `.zip` на хосте), `mode: amp`

**Сценарии и mid-level**

- `GET /api/mid-level/actions`
- `POST /api/scenario/estimate` — `{ "nodes": [ { "subdir", "action_name", "speed", "repeat", "keyframe_count"? } ] }`

**Phase 5** (заголовок `X-User-Id` или `G1_DEV_USER_ID`)

- `POST /api/platform/artifacts/{name}` — сохранить JSON-артефакт пользователя
- `POST /api/platform/pose-drafts` — `{ "name", "document" }` — черновик keyframes с клиента (MuJoCo Pose Studio)
- `POST /api/jobs/train` — очередь обучения (`config` опционально, по умолчанию `{}`; `mode`: `smoke` \| `train` \| `amp`; сервер добавляет `output_dir` в workspace). **AMP eval-only job:** `eval_only: true`, `checkpoint_artifact` (имя файла из `POST /api/platform/artifacts/{name}`), опционально `motion_export` (dict, попадает в `platform_motion.json` и далее в флаги `skill-foundry-package` при сборке пакета из job)
- `GET /api/jobs`, `GET /api/jobs/{job_id}`
- `POST /api/packages/from-job/{job_id}`, `POST /api/packages/upload`, `GET /api/packages`, `GET /api/packages/{package_id}/download`, `PATCH /api/packages/{package_id}` — для пакетов с `manifest.motion` публикация дополнительно требует `eval_motion.json` в tarball и (если задано) `tracking_mean_mse` ≤ `G1_MOTION_PUBLISH_MAX_MSE`

**WebSocket**

- `WebSocket /ws/telemetry` — строки JSON (`joints`, `timestamp_s`, `mock: true` в mock-режиме)

### Motion capture service topology

- Endpoint `WS /ws/capture` **не** входит в FastAPI процесс на `:8000`; он обслуживается отдельным сервисом `packages/motion_capture` (обычно `:8001`).
- Frontend route `/pose` (в соседнем репозитории `AUROSY_creators_factory`) использует связку:
  1. Camera frames -> `WS /ws/capture`
  2. Landmarks -> `POST /api/pipeline/retarget`
  3. Retargeted angles -> live MuJoCo preview
  4. Опционально: после записи — `POST /api/platform/artifacts/{name}` с JSON `{ "frames": [N,33,3] }`, затем `POST /api/pipeline/motion/run` с `action: build_reference` и `landmarks_artifact` (см. §14 Phase 6).
- Сервис `motion_capture` выбирает бэкенд по **`MOTION_CAPTURE_BACKEND`** (`mediapipe` по умолчанию; `vitpose` зарезервировано — см. `packages/motion_capture/README.md`).
- Для настройки frontend endpoint capture-сервиса используйте `VITE_MOTION_CAPTURE_WS_URL` в UI-репозитории.

## Фронтенд (отдельный репозиторий)

Исходники UI не входят в этот репозиторий. Клонируйте **AUROSY_creators_factory**, затем:

```bash
cd ../AUROSY_creators_factory/web/frontend   # путь от соседнего клона
npm install
npm run dev
```

Откройте `http://127.0.0.1:5173`. Запросы к `/api` и `/ws` проксируются на порт бэкенда (см. `vite.config.ts` во фронтенд-репо).

## Сборка статики SPA

Выполняется в репозитории UI:

```bash
cd /path/to/AUROSY_creators_factory/web/frontend
npm ci
npm run build
```

Артефакт — `dist/`. Статические схемы Phase 0: `public/contracts/` в том же каталоге фронтенда.

Docker-образ API (без UI): [Dockerfile](./Dockerfile), [docker-compose.prod.yml](./docker-compose.prod.yml).
