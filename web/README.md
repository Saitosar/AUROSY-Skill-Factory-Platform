# Web — AUROSY Skill Factory

В этом репозитории (**AUROSY_creators_factory**) лежит только **веб-приложение** (SPA) платформы **AUROSY Skill Factory**. Бэкенд платформы — **отдельный репозиторий**; при локальной разработке фронт ходит к API через прокси Vite или через `VITE_API_BASE`.

| Каталог | Содержимое |
|---------|------------|
| [`frontend/`](frontend/) | Vite + React + TypeScript — основной код UI |

## Локальная разработка вместе с бэкендом

1. Запустите FastAPI из репозитория бэкенда (порт по умолчанию совместим с `frontend/vite.config.ts`, обычно **8000**).
2. В этом репозитории: `cd web/frontend && npm install && npm run dev`.
3. Браузер открывает Vite (порт **5173**); запросы к `/api` и `/ws` проксируются на бэкенд.

Подробности по env и прод-сборке: [`frontend/README.md`](frontend/README.md). Чеклист развёртывания (прокси `/api` и `/ws`, CORS, worker очереди, DDS/mock телеметрия, Phase 5): [`docs/g1-control-ui/DEPLOYMENT.md`](../docs/g1-control-ui/DEPLOYMENT.md). В UI маршрут **`/settings`** показывает эффективный базовый URL API, **идентификатор пользователя Phase 5** (`X-User-Id`: localStorage / `VITE_PLATFORM_USER_ID` / fallback), блок метаданных бэкенда (в т.ч. `telemetry_mode`; опционально `platform_worker_enabled`, `job_timeout_sec`, если отдаёт API) и ссылки на документацию монорепозитория; маршрут **`/help`** — встроенная справка (FAQ), полный текст также в [`docs/g1-control-ui/FAQ.md`](../docs/g1-control-ui/FAQ.md). Интерфейс использует согласованные паттерны дизайн-системы (панели, заголовки страниц, уведомления об ошибках сети через Sonner). Дорожная карта фронтенда и журнал закрытых фаз (F10 — потоки по экранам; **F11** — a11y, reduced-motion, бейджи конвейера; **F12** — FAQ и `/help`; **F14** — Phase 5: артефакты и задачи train, `/jobs`; **F15** — пакеты Skill Bundle, `/packages`; **F16** — IA Pipeline ↔ Platform, CTA preprocess → `/jobs`; **F17** — продакшен, DDS-телеметрия, worker, CORS) — [`docs/g1-control-ui/03_implementation_roadmap_frontend.md`](../docs/g1-control-ui/03_implementation_roadmap_frontend.md).

## Документация UI (архитектура, дизайн, roadmap)

См. [`docs/g1-control-ui/`](../docs/g1-control-ui/README.md) в корне этого репозитория.
