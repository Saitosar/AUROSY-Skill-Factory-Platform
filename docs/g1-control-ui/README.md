# AUROSY Skill Factory — документация веб-UI

Документы в этой папке описывают **архитектуру фронтенда**, **design system** и **справочные материалы** для платформы **AUROSY Skill Factory**: авторинг скиллов, движений и сценариев поведения роботов (Unitree G1 в текущем стеке).

## Где лежит код

| Ресурс | Расположение |
|--------|--------------|
| Веб-приложение (Vite, React) | [`web/frontend/`](../../web/frontend/) |
| Документы в этой папке | [`docs/g1-control-ui/`](./) |

Бэкенд — отдельный репозиторий. Ссылки на документы и пути в том репозитории собраны в [backend_references.md](backend_references.md). Контракт HTTP/WebSocket — в OpenAPI у запущенного сервера (`/docs`).

## Документы в этой папке

| Файл | Описание |
|------|----------|
| [01_frontend_architecture.md](01_frontend_architecture.md) | Слои приложения, фиче-модули, потоки данных, границы с бэкендом |
| [02_design_system.md](02_design_system.md) | Принципы UX, токены, компоненты, доступность |
| [FAQ.md](FAQ.md) | Частые вопросы для пользователей; дублируется в UI на `/help` (ru/en) |
| [backend_references.md](backend_references.md) | Типичные пути к документам и коду в репозитории бэкенда |

## Маршруты приложения

| Путь | Экран |
|------|-------|
| `/` | Главная (dashboard, статус API, шорткаты) |
| `/authoring` | Авторинг (keyframes, motion, scenario) |
| `/pose` | Pose Studio (2D-схема, WASM 3D) |
| `/scenarios` | Сценарии (mid-level действия, оценка длительности) |
| `/pipeline` | Конвейер (preprocess, playback, train) |
| `/jobs`, `/jobs/:jobId` | Задачи Phase 5 (очередь train) |
| `/packages` | Пакеты (Skill Bundle) |
| `/telemetry` | Телеметрия (WebSocket) |
| `/help` | Справка (FAQ ru/en) |
| `/settings` | Настройки (язык, API base, версия) |

## Архив

Исторические документы (планы реализации, бриф для Figma, бэклоги) перенесены в [`docs/archive/g1-control-ui/`](../archive/g1-control-ui/).
