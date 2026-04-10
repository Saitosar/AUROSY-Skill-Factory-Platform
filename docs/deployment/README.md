# Развёртывание AUROSY Skill Factory

Документы в этой папке описывают варианты развёртывания **веб-фронтенда** платформы.

## Содержание

| Файл | Описание |
|------|----------|
| [vercel-frontend.md](vercel-frontend.md) | Пошаговая инструкция по переносу фронтенда на Vercel |

---

## Краткий чеклист продакшена

- [ ] **Один origin для UI и API** (рекомендуется): reverse-proxy отдаёт статику SPA и проксирует `/api` и `/ws` на процесс FastAPI — меньше проблем с CORS и WebSocket.
- [ ] **CORS**: в dev часто `allow_origins=["*"]`; в продакшене сузить до доверенных хостов UI.
- [ ] **`VITE_API_BASE`**: при сборке фронта задать URL API без завершающего `/` или оставить пустым при same-origin за прокси.
- [ ] **Прокси WebSocket**: путь `/ws/telemetry` пробрасывается с теми же правилами, что и `/api`.
- [ ] **Phase 5**: заголовок `X-User-Id` согласован между UI и бэкендом.
- [ ] **Очередь jobs**: включён фоновый worker на бэкенде (`G1_PLATFORM_WORKER_ENABLED`).
- [ ] **MuJoCo WASM**: статика `public/mujoco/g1/` и `*.wasm` отдаются с долгим `Cache-Control` (immutable, max-age от недели).
- [ ] **Credentials**: текущий фронтенд не использует `fetch(..., { credentials: 'include' })`. При введении cookie-сессий потребуется согласовать CORS и клиент.

---

## Архив

Полный исторический чеклист (фаза F17) перенесён в [`../archive/g1-control-ui/DEPLOYMENT-checklist-f17.md`](../archive/g1-control-ui/DEPLOYMENT-checklist-f17.md).

---

## Связанные документы

- [../g1-control-ui/FAQ.md](../g1-control-ui/FAQ.md) — FAQ, секция «Продакшен и развёртывание»
- [../g1-control-ui/backend_references.md](../g1-control-ui/backend_references.md) — ссылки на репозиторий бэкенда
- [../../web/frontend/README.md](../../web/frontend/README.md) — README фронтенда
