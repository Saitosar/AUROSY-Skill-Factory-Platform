# AUROSY Skill Factory — веб-фронтенд

Vite + React + TypeScript. Общается с FastAPI бэкендом (`/api/*`) и WebSocket телеметрии (`/ws/telemetry`).

## Запуск

Из каталога `web/frontend`:

```bash
npm install
npm run dev
```

По умолчанию Vite слушает порт **5173** (см. `vite.config.ts`). Бэкенд должен быть доступен там, куда указывает прокси — обычно `http://127.0.0.1:8000`. Запуск API — в **репозитории бэкенда** (отдельно от этого веб-репозитория); обзор связки: [`../README.md`](../README.md) в каталоге `web/`.

### MuJoCo WASM (Pose Studio, 3D G1)

- **Модель и ассеты:** официальный MJCF из [mujoco_menagerie / unitree_g1](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1) (`scene.xml`, `g1.xml`, `assets/*.STL`). Это **тот же** рекомендуемый источник, что в плане Skill Factory; каталоги вроде `unitree_mujoco/unitree_robots/g1` на платформе — другая раскладка файлов и имена/порядок суставов могут отличаться, для веб-вьюера зафиксирован menagerie + маппинг в `src/mujoco/`. После `npm install` при необходимости подтяните файлы в `public/mujoco/g1/`:

  ```bash
  npm run fetch:menagerie-g1
  ```

  Скрипт: `scripts/fetch-menagerie-g1.mjs` (нужен сетевой доступ к GitHub raw).

- **Пакет `@mujoco/mujoco`:** после установки срабатывает **`postinstall`** — `scripts/patch-mujoco-vite.mjs` правит `node_modules/@mujoco/mujoco/mujoco.js` для совместимости с Vite (Worker + динамический импорт). При чистой переустановке зависимостей патч применится снова автоматически.

- **Первый визит:** браузер загружает WASM и чанк рантайма (порядка **~9 MB** gzip-сжатого WASM в production-сборке плюс STL/XML из `public/mujoco/g1/`). Имеет смысл показывать пользователю индикатор загрузки (в Pose Studio — вкладка **WASM**).

- **macOS / «Resource temporarily unavailable»:** в MuJoCo 3.5+ компиляция MJCF по умолчанию может поднимать много Web Worker’ов (pthread). На части macOS это даёт ошибку вроде `thread constructor failed: Resource temporarily unavailable`. В загрузчике и в `public/mujoco/g1/*.xml` принудительно выставлено **`compiler usethread="false"`** (см. `src/mujoco/menagerieXmlPatch.ts` и скрипт `fetch:menagerie-g1`).

- **Сборка:** для бандла MuJoCo используется целевой уровень **ES2022** (top-level `await` в worker). См. `vite.config.ts`.

- **Экспорт keyframes:** углы из симуляции маппятся на те же ключи, что и `JOINT_MAP` на бэкенде (`src/mujoco/jointMapping.ts`, `qposToSkillAngles.ts`); экспорт в Авторинг — через `poseAuthoringBridge` как и для телеметрии.

## Базовый URL API (`VITE_API_BASE`)

| Режим | Значение | Поведение |
|--------|-----------|-----------|
| Локальная разработка | не задавать или `VITE_API_BASE=` | Запросы на относительные пути `/api/...` с того же хоста, что и страница; в dev Vite **проксирует** `/api` и `/ws` на бэкенд. |
| Сборка за reverse-proxy | `VITE_API_BASE=` | Браузер ходит на тот же origin, что и UI; прокси на сервере перенаправляет `/api` на FastAPI. |
| Отдельный хост API | `VITE_API_BASE=http://host:port` без завершающего `/` | Все `fetch` идут на этот origin; WebSocket телеметрии строится от того же хоста/схемы. |

Не смешивайте в коде абсолютные URL и относительные пути вручную: используйте только `import.meta.env.VITE_API_BASE` и функции из `src/api/client.ts` (в т.ч. `getConfiguredApiBase()`). В собранном приложении эффективное значение можно посмотреть на экране **Настройки** (`/settings`). Пользовательская справка: маршрут **`/help`** (ru/en); развёрнутый markdown — [`docs/g1-control-ui/FAQ.md`](../../docs/g1-control-ui/FAQ.md).

## Phase 5: идентификатор пользователя и `apiFetch`

Запросы к **`/api/platform/*`**, **`/api/jobs*`** и **`/api/packages*`** на бэкенде Phase 5 ожидают заголовок **`X-User-Id`** (см. [`docs/g1-control-ui/backend_references.md`](../../docs/g1-control-ui/backend_references.md)). В коде используйте **`apiFetch`** из `src/api/client.ts` для этих путей — заголовок подставится автоматически, если вы не передали свой `X-User-Id`.

| Источник | Приоритет |
|----------|-----------|
| Значение в **Настройках** (сохраняется в `localStorage`, ключ `g1_platform_user_id`) | выше |
| **`VITE_PLATFORM_USER_ID`** при сборке (см. `.env.example`) | средний |
| Встроенный fallback **`local-dev`** | если выше не задано |

Согласуйте значение с бэкендом (например с **`G1_DEV_USER_ID`** в режиме разработки), чтобы артефакты и задачи принадлежали одному «владельцу». Полноценная аутентификация — отдельная тема бэкенда; F13 обеспечивает только согласованность id в UI и запросах.

### Экран «Задачи» (F14)

Маршрут **`/jobs`**: сохранение JSON на платформу (`POST /api/platform/artifacts/{name}`), постановка **`POST /api/jobs/train`** в очередь, список и детали задач с опросом статуса. Детали: **`/jobs/:jobId`**. Тела запросов и поля ответов — в OpenAPI бэкенда (`GET /docs`); в коде см. функции **`savePlatformArtifact`**, **`enqueueTrainJob`**, **`listJobs`**, **`getJob`** в `src/api/client.ts`. Для обработки очереди на сервере должен быть включён worker (часто **`G1_PLATFORM_WORKER_ENABLED`**).

**Ручная приёмка:** с запущенным бэкендом Phase 5 и worker — сохранить тестовый артефакт, поставить train (smoke), убедиться, что задача появляется в списке и в деталях обновляется статус.

### Экран «Пакеты» (F15)

Маршрут **`/packages`**: **`GET /api/packages`**, **`GET /api/packages/{id}/download`**, **`POST /api/packages/upload`** (multipart `.tar.gz`), **`PATCH /api/packages/{id}`** для публикации. Упаковка из успешной задачи: **`POST /api/packages/from-job/{job_id}`** — кнопка на деталях job (`/jobs/:jobId`). В коде: **`listPackages`**, **`createPackageFromJob`**, **`downloadSkillBundle`**, **`uploadSkillBundle`**, **`setPackagePublished`**, типы **`PackagePublishConflictError`** / **`PlatformPackageRow`** в `src/api/client.ts`. Имя поля multipart и точные поля списка — в OpenAPI бэкенда.

**Ручная приёмка:** после успешного job создать пакет с деталей задачи, увидеть его в списке на `/packages`, скачать архив; при отклонении публикации сервером — в UI отображается тело ответа **409**.

### IA: Конвейер vs Задачи (F16)

Синхронный train — только **`POST /api/pipeline/train`** на экране **Конвейер**. Асинхронная очередь и Skill Bundle — экраны **`/jobs`** и **`/packages`**. После успешного preprocess с `reference_trajectory_json` кнопка на Конвейере открывает `/jobs` с `location.state` (ключ **`pipelineRefTrajectory`** в [`src/lib/jobsPipelineBridge.ts`](src/lib/jobsPipelineBridge.ts)); форма reference предзаполняется, **enqueue не вызывается** до нажатия «Поставить в очередь». Подробности — главная, FAQ, `/help`.

Копируйте `.env.example` в `.env` при необходимости и правьте локально; `.env` не коммитьте с секретами.

## Продакшен, CORS и credentials (F17)

- **Same-origin (предпочтительно):** отдавайте собранный `dist/` и проксируйте `/api` и `/ws` на FastAPI с одного хоста — так реже сталкиваетесь с CORS и с проксированием WebSocket.
- **CORS:** в разработке у бэкенда часто `allow_origins=["*"]`; в продакшене ограничьте origins списком доверенных URL UI. Настройки — в репозитории бэкенда.
- **`VITE_API_BASE`:** без завершающего `/`; пустое значение — запросы на тот же origin, что и страница (удобно за reverse-proxy).
- **Credentials:** клиент по умолчанию не передаёт `credentials: 'include'` в `fetch`. Phase 5 использует заголовок `X-User-Id`. Если позже понадобятся cookie-сессии, согласуйте CORS и при необходимости расширьте `apiFetch` в `src/api/client.ts`.
- **Телеметрия DDS:** при `GET /api/meta` → `telemetry_mode: dds` UI показывает предупреждение на Телеметрии и Pose Studio; без DDS-моста используйте mock на бэкенде (см. [FAQ](../../docs/g1-control-ui/FAQ.md) и [deployment](../../docs/deployment/README.md)).
- **Развёртывание на Vercel:** пошаговая инструкция — [`docs/deployment/vercel-frontend.md`](../../docs/deployment/vercel-frontend.md).

## Дизайн-система и UX (кратко)

Визуальные токены и компоненты описаны в [`docs/g1-control-ui/02_design_system.md`](../../docs/g1-control-ui/02_design_system.md). В коде: глобальные стили [`src/styles.css`](src/styles.css), переиспользуемые примитивы в [`src/components/ds/`](src/components/ds/) (`PageHeader`, `ValidateBanner`, `EmptyState`, `PipelineStatusBadge`), уведомления — [`sonner`](https://github.com/emilkowalski/sonner) (тосты при сетевых сбоях ключевых запросов). **Доступность:** единое кольцо `:focus-visible` на интерактивах; статусы этапов конвейера — бейдж с текстом и иконкой, не только цвет; при системной настройке «уменьшить движение» — ослабление анимаций тостов и индикатора «Выполняется»; у readonly-слайдеров телеметрии — `aria-labelledby` и `aria-valuetext`. Зависимости для сценариев: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities` (сортировка цепочки действий).

Подробнее о MuJoCo WASM: [`docs/mujoco-wasm-browser.md`](../../docs/mujoco-wasm-browser.md).

## Скрипты

- `npm run dev` — dev-сервер с HMR
- `npm run build` — production-сборка в `dist/`
- `npm run preview` — предпросмотр сборки
- `npm run typecheck` — проверка TypeScript без emit
- `npm test` — unit-тесты (Vitest), в т.ч. маппинг MuJoCo → Phase 0
- `npm run fetch:menagerie-g1` — загрузка MJCF/STL menagerie в `public/mujoco/g1/`

## Контракты Phase 0 (JSON Schema)

Источник правды для схем авторинга — репозиторий бэкенда: каталог `docs/skill_foundry/contracts/authoring/` (см. [`docs/g1-control-ui/backend_references.md`](../../docs/g1-control-ui/backend_references.md)).

Копии для статики фронта лежат в **`public/contracts/authoring/`** (`keyframes.schema.json`, `motion.schema.json`, `scenario.schema.json`). После изменений схем в бэкенде скопируйте файлы сюда и пересоберите фронт, иначе клиентская проверка (AJV) и подпись `schema_version` в UI разойдутся с сервером.

## Golden-фикстуры (F2 — Авторинг)

Для проверки без клона бэкенда в репозитории есть эталонные JSON в **`public/fixtures/golden/v1/`** (`keyframes.json`, `motion.json`, `scenario.json`). На экране «Авторинг» кнопка **«Загрузить golden (фикстура)»** подставляет файл, соответствующий активной вкладке.

Полный каталог golden в продукте может жить в бэкенде (`docs/skill_foundry/golden/v1/` — путь уточнять в том репозитории). Чтобы синхронизировать фикстуры с бэкендом, скопируйте нужные файлы в `public/fixtures/golden/v1/` под теми же именами.

### Приёмка F2 (ручная)

1. Запустить бэкенд FastAPI и `npm run dev` (прокси `/api` на бэкенд).
2. Открыть раздел **Авторинг**, для каждой вкладки: **Загрузить golden** → **Проверить (JSON Schema)** → **Проверить (сервер Phase 0)** — без ошибок.
3. При обновлении контрактов повторить шаг 2 после копирования схем из бэкенда.
