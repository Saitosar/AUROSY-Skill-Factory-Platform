# Skill Foundry: план реализации по фазам

Документ связывает **фазы** конвейера с детальными спецификациями в [`../archive/`](../archive/). Архитектура модулей: [02_architecture.md](02_architecture.md). Видение: [01_vision_and_approach.md](01_vision_and_approach.md).

**Репозитории:** бэкенд и SDK — **AUROSY_creators_factory_platform** (этот репозиторий: `web/backend`, сабмодуль `unitree_sdk2_python` для upstream `unitree_sdk2py`, каталог `packages/skill_foundry` для AUROSY Skill Foundry). SPA — **AUROSY_creators_factory** (`web/frontend`). Публичное зеркало/историческое имя клона может отличаться; ориентируйтесь на фактический `git remote` и структуру каталогов ниже.

---

## Оглавление фаз и задач

| Фаза | Содержание | Документ (archive) |
|------|------------|-------------------|
| **0** | Контракты Authoring / ReferenceTrajectory / DemonstrationDataset; валидация JSON | [04_phase0_contracts.md](../archive/04_phase0_contracts.md) |
| **0** | Чеклист приёмки Phase 0 | [05_phase0_acceptance_checklist.md](../archive/05_phase0_acceptance_checklist.md) |
| **2.1** | SimPlayback: ReferenceTrajectory в MuJoCo | [06_phase2_sim_playback.md](../archive/06_phase2_sim_playback.md) |
| **2.2** | Trajectory recorder → DemonstrationDataset v1 | [07_phase2_trajectory_recorder.md](../archive/07_phase2_trajectory_recorder.md) |
| **3.1** | Docker-образ RL worker, `skill-foundry-train` | [08_phase3_rl_worker_docker.md](../archive/08_phase3_rl_worker_docker.md) |
| **3.2** | Среда MuJoCo, награды, PPO | [09_phase3_env_rewards.md](../archive/09_phase3_env_rewards.md) |
| **3.3** | Behavior cloning по демонстрациям | [09b_phase3_demonstration_bc.md](../archive/09b_phase3_demonstration_bc.md) |
| **4.0** | AMP RL training pipeline (режим `skill-foundry-train --mode amp`) | [14_video_to_motion_integration.md](14_video_to_motion_integration.md) |
| **4.1** | Manifest и экспорт пакета навыка | [10_phase4_manifest_export.md](../archive/10_phase4_manifest_export.md) |
| **5** | Платформа: оркестратор, каталог, Phase 5 API | [11_phase5_platform.md](../archive/11_phase5_platform.md) |
| **6.1** | Продуктовая валидация, пороги, гейт публикации | [12_phase6_product_validation.md](../archive/12_phase6_product_validation.md) |
| **6.2** | Безопасность рантайма и целостность пакетов | [13_phase6_runtime_security.md](13_phase6_runtime_security.md) |
| **6 (video §14)** | Motion skill bundle и E2E: `POST /api/pipeline/motion/run`, валидатор пакета, UI в Motion Studio | [14_video_to_motion_integration.md](14_video_to_motion_integration.md) §Phase 6 |

Ссылки из корня репозитория на те же файлы: `docs/archive/<имя>.md`.

**Video-to-motion — оценка и экспорт (Phase 5 документа в §14):** метрики AMP rollout → `eval_motion.json`, расширение skill bundle (`manifest.motion`), поля `POST /api/jobs/train` (`eval_only`, `checkpoint_artifact`, `motion_export`) и синхронный `POST /api/pipeline/train` (`eval_only`, `checkpoint_path`) — см. [14_video_to_motion_integration.md](14_video_to_motion_integration.md).

**Video-to-motion — Phase 6 (тот же §14):** оркестрация `POST /api/pipeline/motion/run` + `GET /api/pipeline/motion/{pipeline_id}`, гейт публикации по `eval_motion.json` / `G1_MOTION_PUBLISH_MAX_MSE`, панель **Motion skill pipeline** в Motion Studio (`MotionPipelinePanel`) при `GET /api/meta` → `motion_pipeline_enabled: true`. UI: **AMP** по умолчанию (`train_mode: amp`), опциональный Smoke; связка записи камеры с `POST /api/platform/artifacts` и `landmarks_artifact` — см. §14 «Implementation status» Phase 3 и 6.

---

## Продакшен: перенос на VPS

Ниже — типовой сценарий для **Linux VPS**: один домен, reverse proxy, FastAPI только на localhost, статика SPA из **`dist/`** репозитория UI (собирается в **AUROSY_creators_factory**). Детали переменных окружения и API: [`web/README.md`](../../web/README.md).

### 1. Исходный код

Нужны **два** клона (или эквивалент: CI, который тянет оба артефакта):

```bash
# Бэкенд + SDK + документация
git clone <url-backend> AUROSY_creators_factory_platform
cd AUROSY_creators_factory_platform

# SPA (отдельный репозиторий)
cd ..
git clone <url-frontend> AUROSY_creators_factory
```

Команды бэкенда ниже — из **корня** `AUROSY_creators_factory_platform`. Сборка фронтенда — из **`AUROSY_creators_factory/web/frontend`**. Замените URL и имена каталогов на свои, если у вас другой layout.

### 2. Сервер и сеть

- ОС: современный Linux (x86_64).
- Во внешнем контуре открыты **80** и **443** (HTTPS); SSH по ключу.
- Процесс API слушает только **127.0.0.1** (например порт **8000**) — порт не должен быть доступен из интернета без proxy.

### 3. Зависимости бэкенда

Из [`web/README.md`](../../web/README.md):

```bash
cd /abs/path/to/AUROSY_creators_factory_platform
pip install -e "./unitree_sdk2_python"
pip install -e "./packages/skill_foundry[export]"
cd web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# при необходимости:
# export G1_REPO_ROOT="/abs/path/to/AUROSY_creators_factory_platform"
```

Каталоги `unitree_sdk2_python` и `packages/skill_foundry` должны существовать в клоне или задаваться через `G1_SDK_PYTHON_ROOT` / `G1_SKILL_FOUNDRY_PYTHON_ROOT`. Бэкенд при запуске пайплайна сам выставляет объединённый `PYTHONPATH` для подпроцессов.

### 4. Сборка фронтенда

Из репозитория **AUROSY_creators_factory**:

```bash
cd /path/to/AUROSY_creators_factory/web/frontend
npm ci
npm run build
```

Для **same-origin** за reverse-proxy задайте **`VITE_API_BASE` пустым** при сборке (или не задавайте), чтобы браузер ходил на `/api` и `/ws` того же хоста, что и UI. Итоговая статика — каталог **`dist/`** в этом каталоге (раздайте через nginx/Caddy или смонтируйте в корень сайта за proxy).

### 5. Reverse proxy и TLS

Настройте единый виртуальный хост:

- **`/api`** → `http://127.0.0.1:8000` (или иной внутренний upstream FastAPI).
- **`/ws`** (WebSocket, в т.ч. `/ws/telemetry`) → тот же upstream с поддержкой `Upgrade` и `Connection: upgrade`.
- **Остальные пути** → статика SPA и fallback на `index.html` для клиентского роутинга (React Router).

TLS: Let’s Encrypt (certbot) или автоматический HTTPS в Caddy. Пример фрагмента для **nginx** (идея, пути подставьте свои):

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

### 6. Запуск API под systemd

- Используйте **`uvicorn`** без `--reload` в продакшене.
- Вынесите переменные в файл окружения (например `/etc/g1-platform.env`).
- Обязательно включите очередь: **`G1_PLATFORM_WORKER_ENABLED=1`**, иначе job’ы останутся в `queued`.
- Сузьте **CORS** до доверенных origin’ов UI (см. настройки FastAPI в репозитории).
- **Не** включайте **`G1_SKIP_VALIDATION_GATE`** в продакшене.
- Заголовок **`X-User-Id`** и fallback **`G1_DEV_USER_ID`**: до появления полноценной аутентификации зафиксируйте политику (например обязательный `X-User-Id` на edge или согласованный dev-id только за VPN).

Пример unit (упрощённо; пути и пользователь — свои):

```ini
[Service]
EnvironmentFile=/etc/g1-platform.env
WorkingDirectory=/opt/AUROSY_creators_factory_platform/web/backend
ExecStart=/opt/AUROSY_creators_factory_platform/web/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
```

### 7. Данные и бэкапы

- Каталог **`G1_PLATFORM_DATA_DIR`** (по умолчанию под `web/backend/data/platform`) хранит SQLite, workspace job’ов и пакеты — вынесите на диск с резервным копированием и корректными правами пользователя сервиса.
- Учитывайте **`G1_JOB_TIMEOUT_SEC`** и нагрузку при длительном обучении.

### 8. Опционально: GPU и Docker

- Для обучения на GPU на том же хосте: драйверы NVIDIA, при необходимости Docker — см. [08_phase3_rl_worker_docker.md](../archive/08_phase3_rl_worker_docker.md).
- Тяжёлое обучение можно вынести на отдельный worker-хост; платформа в MVP использует локальный workspace и SQLite — масштабирование описано концептуально в [02_architecture.md](02_architecture.md) §5.

### 9. Альтернатива: фронт на Vercel

Статический фронт на Vercel и API на VPS возможны; тогда задаётся **`VITE_API_BASE`** на URL API и настраиваются CORS. Подробности — в репозитории **AUROSY_creators_factory** (например `docs/deployment/`, `web/frontend/README.md`).

---

## Связанные документы

- [02_architecture.md](02_architecture.md) — модули, потоки данных и §11 (развёртывание на VPS на уровне архитектуры).
- [`web/README.md`](../../web/README.md) — запуск бэкенда, переменные `G1_*`, OpenAPI.
