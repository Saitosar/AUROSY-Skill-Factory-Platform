# Руководство для frontend-разработчика: данные и контракты G1 Control / Skill Foundry

Документ описывает **все данные и интерфейсы**, которые нужны UI: домен робота, форматы JSON (Phase 0 и legacy), REST/WebSocket API бэкенда (**AUROSY_creators_factory_platform**, каталог `web/backend/`), ожидания к экранам. Исходники SPA — в отдельном репозитории **AUROSY_creators_factory** (`web/frontend/`).

Подробное видение продукта и фазы конвейера: [skill_foundry/01_vision_and_approach.md](skill_foundry/01_vision_and_approach.md), [skill_foundry/02_architecture.md](skill_foundry/02_architecture.md).

---

## 1. Робот Unitree G1 (29 DOF)

### 1.1 Канонический порядок суставов

- Индексы моторов **0–28** (29 степеней свободы).
- Человекочитаемые имена и семантика — в [`packages/skill_foundry/core_control/joint_controller.py`](../packages/skill_foundry/core_control/joint_controller.py) (`JOINT_MAP`).
- Лимиты углов и скоростей — [`packages/skill_foundry/core_control/config/joint_limits.py`](../packages/skill_foundry/core_control/config/joint_limits.py).

### 1.2 Группы для UI (как в Pose Studio)

Логическая группировка в инструментах:

| Группа        | Индексы суставов |
|---------------|------------------|
| Левая рука    | 15–21            |
| Правая рука   | 22–28            |
| Торс (талия)  | 12–14            |
| Левая нога    | 0–5              |
| Правая нога   | 6–11             |

Те же группы отдаёт бэкенд в `GET /api/joints` (поле `groups`).

### 1.3 Телеметрия и команды (низкий уровень)

- **Телеметрия:** топик DDS `rt/lowstate` — позиции `motor_state[i].q` (радианы), опционально IMU. Реализация: [`StateListener`](../packages/skill_foundry/core_control/state_listener.py).
- **Команды:** топик `rt/lowcmd` — PD по суставам (`q`, `kp`, `kd`). Реализация: [`JointController`](../packages/skill_foundry/core_control/joint_controller.py).

В браузере прямой доступ к DDS невозможен; нужен **бэкенд-мост** (см. раздел 5).

### 1.4 Ассеты для визуала робота (MuJoCo G1)

Ниже пути **от корня репозитория** `AUROSY_creators_factory_platform/`. Их можно использовать для иллюстраций, **2D-схемы** с хотспотами, загрузки **STL в WebGL** (Three.js / react-three-fiber и т.д.) или как референс к кинематическому дереву.

#### Сцена и модель (MJCF)

| Назначение | Путь |
|------------|------|
| Сцена 29 DoF (подключает модель) | [`unitree_mujoco/unitree_robots/g1/scene_29dof.xml`](../unitree_mujoco/unitree_robots/g1/scene_29dof.xml) |
| Модель G1 29 DoF (`meshdir="meshes"`) | [`unitree_mujoco/unitree_robots/g1/g1_29dof.xml`](../unitree_mujoco/unitree_robots/g1/g1_29dof.xml) |
| Вариант 23 DoF | [`unitree_mujoco/unitree_robots/g1/g1_23dof.xml`](../unitree_mujoco/unitree_robots/g1/g1_23dof.xml) |

В [`g1_29dof.xml`](../unitree_mujoco/unitree_robots/g1/g1_29dof.xml) перечислены все `<mesh file="…STL" />` и иерархия `<body>` / `<joint name="…_joint">` — это **источник истины** для соответствия звеньев и осей в 3D.

#### Растровые изображения (обзорные PNG)

Папка: [`unitree_mujoco/unitree_robots/g1/images/`](../unitree_mujoco/unitree_robots/g1/images/)

| Файл | Смысл |
|------|--------|
| `g1_29dof.png` | Обзорная схема конфигурации 29 DoF |
| `g1_29dof_with_hand.png` | То же с акцентом на руки/кисти |
| `g1_23dof.png` | Конфигурация 23 DoF |
| `g1_dual_arm.png` | Двурукий обзор |

Дополнительно (heightfield’ы для `scene.xml` / пола, не обязательно для Pose UI): в каталоге G1 лежат [`unitree_mujoco/unitree_robots/g1/height_field.png`](../unitree_mujoco/unitree_robots/g1/height_field.png) и [`unitree_mujoco/unitree_robots/g1/unitree_hfield.png`](../unitree_mujoco/unitree_robots/g1/unitree_hfield.png) (см. ссылки в XML сцены).

#### Геометрия звеньев (STL)

Каталог: [`unitree_mujoco/unitree_robots/g1/meshes/`](../unitree_mujoco/unitree_robots/g1/meshes/)

- Файлы в формате **`.STL`** (имена в стиле `left_hip_pitch_link.STL`, `torso_link.STL`, …) совпадают с ссылками в `<asset>` модели.
- Для сборки скелета во фронте: объединить загрузку мешей с **деревом тел из `g1_29dof.xml`** (или с картой суставов из §1.1). Угол по каждому контролируемому суставу — тот же индекс **0–28**, что в API и DDS.

#### Соответствие индексов DDS ↔ имена в документации Unitree

Таблица производителя (китайский README в репо): [`unitree_mujoco/unitree_robots/g1/g1_joint_index_dds.md`](../unitree_mujoco/unitree_robots/g1/g1_joint_index_dds.md) — сверка с нотацией `L_LEG_HIP_PITCH` и т.д.; для UI лучше опираться на `JOINT_MAP` из SDK (английские имена `left_hip_pitch` …).

---

## 2. Phase 0: контракты авторинга и обучения

Нормативный текст: [archive/04_phase0_contracts.md](archive/04_phase0_contracts.md).

### 2.1 Авторинг (файлы для UI редактора)

| Файл / сущность    | Назначение | Единицы |
|--------------------|------------|---------|
| `keyframes.json`   | Временная шкала + углы по суставам | углы **градусы**, время **секунды** |
| `motion.json`      | Идентификатор motion, связь с keyframes, метаданные | логика, не «сырые углы» |
| `scenario.json`    | Упорядоченные шаги: `motion_id`, переходы (`on_complete`, `after_seconds` + `seconds`) | логика сценария |

Обязательно: `schema_version: "1.0.0"`. Идентификаторы суставов в keyframes — **строковые цифры** `"0"`…`"28"` (профиль G1 29 DoF).

**JSON Schema** (валидация в UI): каталог [`docs/skill_foundry/contracts/authoring/`](skill_foundry/contracts/authoring/) (`keyframes.schema.json`, `motion.schema.json`, `scenario.schema.json`). Копия для статики фронта в репозитории UI: `AUROSY_creators_factory/web/frontend/public/contracts/` (см. также `dist/contracts/` после сборки).

Примеры валидных файлов: [`docs/skill_foundry/golden/v1/`](skill_foundry/golden/v1/).

### 2.2 Артефакты обучения (не «ручной» авторинг, но UI может показывать/скачивать)

| Файл | Смысл | Единицы |
|------|--------|---------|
| `reference_trajectory.json` | Плотная траектория после препроцессинга | **радианы**, фиксированная `frequency_hz`, обязателен `joint_order`, MVP корня: `root_not_in_reference` |
| `demonstration_dataset.json` | Демонстрации из симуляции (опционально для RL) | см. контракт training |

Схемы: [`docs/skill_foundry/contracts/training/`](skill_foundry/contracts/training/).

### 2.3 Связь с legacy-контентом репозитория

В [`packages/skill_foundry/mid_level_motions/`](../packages/skill_foundry/mid_level_motions/) лежат пакеты `basic_actions/` и `complex_actions/` с `execute.py` + `pose.json`. Часто это **legacy**: без `schema_version`, таймкодов в стиле Phase 0. Путь миграции описан в [04_phase0_contracts.md](archive/04_phase0_contracts.md) (раздел совместимости).

High-level сценарии (формат Scenario Studio): [`packages/skill_foundry/high_level_motions/{name}/scenario.json`](../packages/skill_foundry/high_level_motions/) — ноды ссылаются на mid-level действия. Логика запуска: [`tools/scenario_studio/runner.py`](../packages/skill_foundry/tools/scenario_studio/runner.py).

---

## 3. Эталон UX (что воспроизвести в веб-UI)

### 3.0 Продуктовая цель: «понятный Pose Studio», а не панель приборов

Текущий десктопный Pose Studio задуман как инженерный инструмент: много **цифр и внутренних имён суставов** — для разработчика это нормально, для **конечного пользователя** это воспринимается как «кокпит Boeing»: высокий порог входа и медленное обучение.

**Рекомендуемое направление для пользовательского UI:**

1. **Визуал робота** — центр экрана: 2D-силуэт/схема (PNG из §1.4) и/или **3D** из STL + иерархия из `g1_29dof.xml`, с подсветкой выбранной области тела.
2. **Управление углом рядом с телом** — для каждого редактируемого сустава: **ползунок / дуга / компактный ввод** рядом с соответствующей частью визуала (или в боковой панели, но с **понятной подписью зоны**: «левое плечо — вперёд/назад», а не только `left_shoulder_pitch`).
3. **Скрытие технических деталей по умолчанию** — индексы `0…28` и `snake_case` имена вынести в «Дополнительно / Для разработчика» или подсказку по `?`, а в основном UI использовать **короткие человеческие формулировки** (и при необходимости i18n).
4. **Единицы** — для авторинга keyframes в градусах показывать **°**; при отладке можно переключать отображение радиан для reference-траекторий.
5. **Онбординг** — первый запуск: короткая подсветка зон тела и жест «потяни сюда», опираясь на тот же визуал.

Такой подход **снижает когнитивную нагрузку**, ускоряет создание движений и совместим с данными API: внутри по-прежнему те же индексы и JSON, меняется только **слой представления**.

### 3.1 Pose Studio — [`tools/pose_studio.py`](../packages/skill_foundry/tools/pose_studio.py) и веб Motion Studio

**Десктоп (`pose_studio.py`):**

- Группы суставов (см. §1.2), шаг редактирования угла порядка **0.5°**.
- Отображение текущих углов из телеметрии vs целевые команды.
- Слоты keyframes (до 3), экспорт в `pose.json` и генерация `execute.py` через [`action_exporter.py`](../packages/skill_foundry/tools/action_exporter.py).

**Веб (`AUROSY_creators_factory/web/frontend/src/pages/PoseStudio.tsx`):**

- Режим **3D MuJoCo (WASM)**: до **двух** дополнительных снимков поз («Добавить позу») вместе с **текущей** позой в симуляторе — до **трёх** keyframes в одном Phase 0 документе при отправке в Авторинг / Конвейер / `POST /api/platform/pose-drafts`.
- Скачивание **`pose.json` (SDK)** — тот же legacy-формат, что и у `save_action`: JSON-массив объектов с ключами `"0"`…`"28"` в градусах; дальше можно положить файл рядом с `execute.py` из `complex_actions|basic_actions/<name>/` или сгенерировать папку действия локально через `action_exporter.save_action`.
- **Создать движение** — только предпросмотр в браузере: плавная интерполяция углов (аналог духа [`atomic_move.py`](../packages/skill_foundry/core_control/low_level_motions/atomic_move.py)), без вызова DDS/робота из этого UI.

- Для пользовательского UI см. §3.0: визуал и подписи **рядом с зонами тела** важнее таблицы «все 29 рядов цифр».

### 3.2 Scenario Studio — [`tools/scenario_studio/app.py`](../packages/skill_foundry/tools/scenario_studio/app.py)

- Библиотия действий: папки с `execute.py` под `mid_level_motions/{basic_actions|complex_actions}/`.
- Нода: `subdir`, `action_name`, `speed`, `repeat`.
- **Оценка длительности:** эвристика порядка **~8 с на один keyframe** при `speed = 1.0` (константа `EST_SEC_PER_KEYFRAME` в runner); в веб-API повторяется логика `POST /api/scenario/estimate`.
- Целевое окно длительности сценария в десктоп-UI ~**30 с** (предупреждение вне ~25–35 с) — имеет смысл показать аналогично.

### 3.3 Низкоуровневые паттерны

- Плавное движение одного сустава: [`atomic_move.py`](../packages/skill_foundry/core_control/low_level_motions/atomic_move.py).
- Ручное управление одним суставом (клавиши): [`manual_control.py`](../packages/skill_foundry/core_control/low_level_motions/manual_control.py).

---

## 4. Конвейер Skill Foundry (CLI)

Точки входа объявлены в [`packages/skill_foundry/pyproject.toml`](../packages/skill_foundry/pyproject.toml) (`[project.scripts]`).

| Команда | Назначение |
|---------|------------|
| `skill-foundry-preprocess` | `keyframes.json` → `reference_trajectory.json` + лог |
| `skill-foundry-playback` | Проигрывание reference в MuJoCo, лог `.npz`, опционально `demonstration_dataset.json` |
| `skill-foundry-train` | Обучение (config + reference, опционально demonstration; опционально BC перед PPO — см. [09b_phase3_demonstration_bc.md](archive/09b_phase3_demonstration_bc.md)) |
| `skill-foundry-validate` | Продуктовая валидация обученной политики (пороги, `validation_report.json`) — см. [12_phase6_product_validation.md](archive/12_phase6_product_validation.md) |
| `skill-foundry-package` | Сборка skill bundle (`manifest.json` + веса) — см. [10_phase4_manifest_export.md](archive/10_phase4_manifest_export.md) |
| `skill-foundry-runtime` | Загрузка пакета, проверки целостности, цикл в симе или на железе — см. [13_phase6_runtime_security.md](skill_foundry/13_phase6_runtime_security.md) |

Параметры playback, важные для форм UI: `--mjcf`, `--mode` (`dynamic` | `kinematic`), `--dt`, `--kp`, `--kd`, `--seed`, `-o`, `--demonstration-json` — см. [`skill_foundry_sim/cli.py`](../packages/skill_foundry/skill_foundry_sim/cli.py).

Валидация Phase 0 на сервере: [`skill_foundry_phase0/contract_validator.py`](../packages/skill_foundry/skill_foundry_phase0/contract_validator.py).

---

## 5. Бэкенд для UI (FastAPI): базовый URL и OpenAPI

Реализация: [`web/backend/app/main.py`](../web/backend/app/main.py). Запуск и переменные окружения: [`web/README.md`](../web/README.md).

- **OpenAPI / Swagger:** `GET http://<host>:8000/docs` — актуальные схемы тел запросов и ответов.
- **CORS:** в текущей сборке разрешены все источники (разработка).

Ниже — смысловое описание; при расхождении с кодом приоритет у **OpenAPI и исходников**.

### 5.1 REST

| Метод и путь | Назначение | Тело / ответ (суть) |
|--------------|------------|----------------------|
| `GET /api/health` | Проверка живости | `{ "status": "ok" }` |
| `GET /api/meta` | Пути репозитория, SDK, MJCF по умолчанию, режим телеметрии | `repo_root`, `sdk_python_root`, `mjcf_default`, `telemetry_mode` (`mock` / `dds`), `platform_worker_enabled`, `job_timeout_sec`, `dds_joint_bridge`, `dds_joint_publish_hz`, `joint_command_enabled` |
| `GET /api/joints` | Карта суставов и группы для UI | `joint_map` (строковый ключ → имя), `groups[]` |
| `POST /api/joints/targets` | Задать целевые углы (градусы) для mock-телеметрии / моста | `{ "joints_deg": { "<idx>": number, ... } }`; **404**, если `joint_command_enabled` выключен |
| `POST /api/joints/release` | Сброс целей | **404**, если joint command выключен |
| `GET /api/pipeline/detect-cli` | Найдены ли в `PATH` три CLI основного UI-пайплайна | Только `commands.preprocess`, `playback`, `train` (путь или `null` каждого). Команды `skill-foundry-validate`, `skill-foundry-package`, `skill-foundry-runtime` **не** проверяются этим эндпоинтом — при необходимости проверяйте наличие вручную или через окружение деплоя |
| `POST /api/validate` | Проверка JSON Phase 0 | Тело: `{ "kind", "payload" }`. `kind`: `keyframes` \| `motion` \| `scenario` \| `reference_trajectory` \| `demonstration_dataset`. Ответ: `{ "ok": bool, "errors": string[] }` |
| `GET /api/mid-level/actions` | Список mid-level действий с диска | `actions[]`: `subdir`, `action_name`, `label`, `execute_path`, `pose_path`, `keyframe_count` |
| `POST /api/scenario/estimate` | Оценка длительности цепочки нод | Тело: `{ "nodes": [ { "subdir", "action_name", "speed", "repeat", "keyframe_count"? } ] }`. Ответ: ноды с `estimated_seconds`, `total_estimated_seconds` |
| `POST /api/pipeline/preprocess` | Запуск препроцессинга | `keyframes`, опционально `frequency_hz`, `validate_motion`, `mjcf_path`. Ответ: `exit_code`, `stdout`, `stderr`, строки `reference_trajectory_json`, `preprocess_run_json` |
| `POST /api/pipeline/validate-motion` | Офлайн-проверка ReferenceTrajectory v1 перед playback | `reference_trajectory`, опционально `mjcf_path` |
| `POST /api/pipeline/playback` | Запуск симуляции | Либо `reference_path` (абсолютный путь к файлу), либо встроенный `reference_trajectory`. Поля: `mjcf_path`, `mode`, `dt`, `kp`, `kd`, `seed`, `max_steps`, `write_demonstration_json`. Ответ: логи, опционально base64 `.npz` (если не слишком большой), `demonstration_dataset_json` |
| `POST /api/pipeline/train` | Запуск обучения | `reference_path` (обязателен), `config_path` **или** `config` (объект JSON), опционально `demonstration_path`, `mode`: `smoke` \| `train` (синхронно) |

**Phase 5 — платформа (мультипользовательский контур):** идентификация через заголовок **`X-User-Id`** (в dev без заголовка используется `G1_DEV_USER_ID`). Подробности: [11_phase5_platform.md](archive/11_phase5_platform.md).

| Метод и путь | Назначение | Тело / ответ (суть) |
|--------------|------------|----------------------|
| `POST /api/platform/artifacts/{name}` | Сохранить JSON-артефакт пользователя (`name`: `^[a-zA-Z0-9_.-]+$`) | Тело: JSON-объект; пишется в sandbox пользователя для последующего `reference_artifact` / `demonstration_artifact` |
| `POST /api/platform/pose-drafts` | Сохранить черновик keyframes с клиента (MuJoCo Pose Studio) | `{ "name", "document" }` |
| `POST /api/jobs/train` | Поставить обучение в очередь | `config` (объект), `mode`, ровно одно из: `reference_trajectory` \| `reference_artifact`; опционально одно из: `demonstration_dataset` \| `demonstration_artifact`. Ответ: `{ "job_id", "status": "queued" }` |
| `GET /api/jobs` | Список job’ов текущего пользователя | `?limit=`; `jobs[]` с полями статуса и хвостами логов |
| `GET /api/jobs/{job_id}` | Статус job | 403 если не владелец |
| `POST /api/packages/from-job/{job_id}` | Собрать `.tar.gz` через `skill-foundry-package` после успешного job | Ответ: `{ "package_id" }` |
| `POST /api/packages/upload` | Загрузить готовый skill bundle | `multipart/form-data`, поле `file` (`.tar.gz`), опционально query `label` |
| `GET /api/packages` | Список пакетов: свои + чужие с `published` | `packages[]` с метаданными |
| `GET /api/packages/{package_id}/download` | Скачать bundle | Поток файла; 403 если нет прав |
| `PATCH /api/packages/{package_id}` | Сменить `published` | Тело: `{ "published": bool }` (только владелец) |

### 5.2 WebSocket `/ws/telemetry`

- Сообщения — **строки JSON** (по одному событию на сообщение).
- В текущей сборке по умолчанию — **mock**: поля вроде `timestamp_s`, `joints` (ключи `"0"`…`"28"`, значения в радианах), `mock: true`, опционально `joint_names`.
- Режим DDS через тот же путь может быть добавлен на бэкенде отдельно (`G1_USE_DDS_TELEMETRY` — см. `web/README.md`).

---

## 6. Чеклист данных для типичных экранов UI

| Экран | Данные |
|-------|--------|
| Редактор keyframes / motion / scenario | JSON по схемам из `contracts/authoring/`; серверная проверка `POST /api/validate`; подписи единиц (° в авторинге, rad в reference) |
| **Визуальный Pose Studio (пользовательский)** | Ассеты §1.4 (PNG / STL / MJCF); `GET /api/joints` для скрытой карты id→имя; опционально телеметрия `WebSocket`; **подписи зон тела** поверх визуала (см. §3.0) |
| Слайдеры / таблица 29 суставов (экспертный режим) | `GET /api/joints` + поток `WebSocket /ws/telemetry`; сравнение цели и факта — если бэкенд отдаёт оба |
| Каталог mid-level и сборка сценария | `GET /api/mid-level/actions` + `POST /api/scenario/estimate` |
| Конвейер preprocess → playback → train | Эндпоинты `/api/pipeline/*`, пути к MJCF и файлам на машине, отображение `exit_code` и stderr |
| Очередь обучения и каталог навыков (Phase 5) | Заголовок `X-User-Id`; `POST /api/jobs/train` и опрос `GET /api/jobs*`; артефакты `POST /api/platform/artifacts/*`; пакеты `/api/packages/*` |
| Безопасность | Предупреждения по лимитам (из документации лимитов), по длительности сценария, кнопка аварийной остановки — только если бэкенд реализует команды на робота |

---

## 7. Где лежит фронтенд

Репозиторий **AUROSY_creators_factory** (отдельно от бэкенда):

- Приложение: `web/frontend/` (Vite, React).
- Прокси dev-сервера на API: `web/frontend/vite.config.ts`.
- Обзор и сценарии запуска с бэкендом: `web/README.md` в том же репозитории.

---

## 8. Ссылки на документацию по фазам

- План реализации: [skill_foundry/03_implementation_plan.md](skill_foundry/03_implementation_plan.md).
- Симуляция и запись траекторий: [06_phase2_sim_playback.md](archive/06_phase2_sim_playback.md), [07_phase2_trajectory_recorder.md](archive/07_phase2_trajectory_recorder.md).
- RL worker: [08_phase3_rl_worker_docker.md](archive/08_phase3_rl_worker_docker.md), [09_phase3_env_rewards.md](archive/09_phase3_env_rewards.md), опционально BC: [09b_phase3_demonstration_bc.md](archive/09b_phase3_demonstration_bc.md).
- Экспорт и manifest: [10_phase4_manifest_export.md](archive/10_phase4_manifest_export.md).
- Платформа (очередь обучения, каталог пакетов): [11_phase5_platform.md](archive/11_phase5_platform.md).
- Продуктовая валидация и гейт публикации: [12_phase6_product_validation.md](archive/12_phase6_product_validation.md).
- Безопасность рантайма и целостность пакетов: [13_phase6_runtime_security.md](skill_foundry/13_phase6_runtime_security.md).

Этого набора достаточно, чтобы спроектировать и реализовать UI (в том числе заново), согласовав с бэкенд-командой только базовый URL и политику аутентификации, если она появится позже.

**Дополнение по визуалу:** ассеты и продуктовые принципы Pose UI — §1.4 и §3.0; техническая карта суставов по-прежнему в §1.1 и `GET /api/joints`.
