# Что передать фронтенд-агенту (handoff)

Этот файл можно **отправить агенту целиком** (как вложение или путь в репозитории), чтобы не копировать ответ из чата — форматирование таблиц и путей сохранится.

**Два репозитория:** бэкенд/SDK/доки — **AUROSY_creators_factory_platform**; SPA — **AUROSY_creators_factory**. Примеры путей ниже — замени на свой корень клонов.

---

## Зачем это нужно

Фронтенд-агенту нужен **один согласованный набор документов и путей**: домен робота, контракты JSON, REST/WebSocket API, ассеты для визуала (PNG, STL, MJCF), продуктовый UX для Pose Studio. Ниже — минимальный обязательный набор и опциональное углубление.

---

## Главное (обязательно)

### Репозиторий бэкенда (`AUROSY_creators_factory_platform`)

| Что | Путь от корня |
|-----|----------------|
| Основное руководство (данные, API, ассеты PNG/STL/MJCF, UX Pose Studio) | `docs/frontend_developer_guide.md` |
| Запуск API, переменные `G1_*`, сводка HTTP/WebSocket | `web/README.md` |

**Пример абсолютных путей:**

- `/Users/sarkhan/AUROSY_creators_factory_platform/docs/frontend_developer_guide.md`
- `/Users/sarkhan/AUROSY_creators_factory_platform/web/README.md`

### Репозиторий UI (`AUROSY_creators_factory`)

| Что | Путь от корня |
|-----|----------------|
| Локальная разработка с бэкендом, ссылки на деплой | `web/README.md` |
| Копия JSON Schema для статики | `web/frontend/public/contracts/` |

---

## Полезно приложить как контекст (по желанию)

Все пути ниже — от корня **AUROSY_creators_factory_platform**, если не указано иначе.

| Тема | Путь |
|------|------|
| Видение Skill Foundry | `docs/skill_foundry/01_vision_and_approach.md` |
| Архитектура модулей | `docs/skill_foundry/02_architecture.md` |
| Контракты Phase 0 (текст) | `docs/archive/04_phase0_contracts.md` |
| JSON Schema (авторинг) | `docs/skill_foundry/contracts/authoring/` |
| Примеры golden JSON | `docs/skill_foundry/golden/v1/` |
| Копия схем для статики фронта (в репо UI) | `AUROSY_creators_factory/web/frontend/public/contracts/` |
| Реализация API (источник правды после OpenAPI в рантайме) | `web/backend/app/main.py` |
| Manifest и упаковка навыка (Phase 4) | `docs/archive/10_phase4_manifest_export.md` |
| BC по демонстрациям перед PPO (Phase 3.3) | `docs/archive/09b_phase3_demonstration_bc.md` |
| Продуктовая валидация и пороги (Phase 6.1) | `docs/archive/12_phase6_product_validation.md` |
| Безопасность рантайма (Phase 6.2) | `docs/skill_foundry/13_phase6_runtime_security.md` |

---

## Одна фраза для агента

Источник требований и данных — **`docs/frontend_developer_guide.md`** (в репозитории platform); запуск и контракт HTTP/WebSocket — **`web/README.md`** platform и живой **`http://<host>:8000/docs`** после старта бэкенда; исходники UI — репозиторий **AUROSY_creators_factory**.

---

## Этот файл

Путь к самому handoff-файлу:

- От корня platform: `docs/frontend_agent_handoff.md`
- Пример: `/Users/sarkhan/AUROSY_creators_factory_platform/docs/frontend_agent_handoff.md`
