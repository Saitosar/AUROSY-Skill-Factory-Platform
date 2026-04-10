# Перенос фронтенда на Vercel

Пошаговая инструкция по развёртыванию веб-приложения AUROSY Skill Factory на платформе Vercel.

---

## 1. Подготовка репозитория

Фронтенд находится в каталоге `web/frontend/` относительно корня репозитория. Vercel поддерживает монорепозитории — достаточно указать **Root Directory**.

---

## 2. Создание проекта в Vercel

1. Откройте [vercel.com](https://vercel.com) и авторизуйтесь.
2. Нажмите **Add New → Project**.
3. Импортируйте репозиторий из GitHub/GitLab/Bitbucket.
4. В настройках проекта укажите:

| Параметр | Значение |
|----------|----------|
| **Root Directory** | `web/frontend` |
| **Framework Preset** | Vite |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Install Command** | `npm ci` (или `npm install`) |

---

## 3. Переменные окружения

Добавьте переменные в разделе **Settings → Environment Variables**:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `VITE_API_BASE` | URL бэкенда без завершающего `/`. Пусто — same-origin (если API на том же домене). | `https://api.example.com` |
| `VITE_PLATFORM_USER_ID` | (опционально) Идентификатор пользователя Phase 5 по умолчанию. | `production-user` |

Переменные с префиксом `VITE_` встраиваются в сборку и доступны в браузере через `import.meta.env`.

---

## 4. SPA rewrites

Все маршруты React Router должны отдавать `index.html`. Vercel поддерживает это через `vercel.json` или настройки фреймворка.

Создайте файл `web/frontend/vercel.json` (если его нет):

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Либо Vercel автоматически определит Vite и настроит rewrites.

---

## 5. Кэширование статики

Для крупных файлов (WASM, STL-меши) рекомендуется долгий `Cache-Control`. Vercel по умолчанию кэширует статику из `dist/assets/` с хэшами в именах. Для файлов в `public/` добавьте в `vercel.json`:

```json
{
  "headers": [
    {
      "source": "/mujoco/g1/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    },
    {
      "source": "/(.*)\\.wasm",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    }
  ],
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

---

## 6. Бэкенд на отдельном хосте

Если бэкенд FastAPI развёрнут отдельно (не на Vercel):

1. Задайте `VITE_API_BASE` с полным URL бэкенда.
2. На бэкенде настройте **CORS** для домена Vercel:
   ```python
   allow_origins=["https://your-app.vercel.app"]
   ```
3. WebSocket телеметрии строится от того же хоста, что и `VITE_API_BASE`. Убедитесь, что бэкенд принимает WS-соединения с origin фронтенда.

---

## 7. Проверка деплоя

После успешного деплоя:

1. Откройте Preview URL или Production URL.
2. Проверьте **Главную** — статус API должен показывать «доступен» (если бэкенд запущен и CORS настроен).
3. Откройте **Pose Studio** → вкладка **WASM** — 3D-модель должна загрузиться (первый раз может занять несколько секунд).
4. Проверьте **Настройки** — отображается эффективный `VITE_API_BASE` и версия.

---

## 8. Пример полного `vercel.json`

```json
{
  "headers": [
    {
      "source": "/mujoco/g1/(.*)",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    },
    {
      "source": "/(.*)\\.wasm",
      "headers": [
        { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
      ]
    }
  ],
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Разместите файл в `web/frontend/vercel.json`.

---

## 9. Troubleshooting

| Проблема | Решение |
|----------|---------|
| 404 на маршрутах (`/pose`, `/jobs`) | Добавьте rewrites в `vercel.json` |
| CORS-ошибки при запросах к API | Настройте `allow_origins` на бэкенде |
| WebSocket не подключается | Проверьте, что бэкенд принимает WS с origin фронтенда |
| WASM не загружается | Убедитесь, что `public/mujoco/g1/` содержит ассеты (`npm run fetch:menagerie-g1`) |
| Ошибка «Resource temporarily unavailable» | Патч XML уже применён; если ошибка повторяется — проверьте версию `@mujoco/mujoco` |

---

## Связанные документы

- [README.md](README.md) — общий чеклист продакшена
- [../mujoco-wasm-browser.md](../mujoco-wasm-browser.md) — детали MuJoCo WASM
- [../../web/frontend/README.md](../../web/frontend/README.md) — README фронтенда
