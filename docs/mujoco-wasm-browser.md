# 3D MuJoCo в браузере (WASM)

Документ описывает **браузерную** интеграцию MuJoCo для визуализации робота Unitree G1 в **Pose Studio** (`/pose`). Это **не** нативный симулятор `unitree_mujoco` из репозитория платформы (C++/Python) — здесь только клиентский путь через WebAssembly.

---

## Назначение

- Визуализация 3D-модели G1 в реальном времени на вкладке **WASM** экрана Pose Studio.
- Управление углами суставов через слайдеры UI → запись в `qpos` MuJoCo → обновление 3D-сцены.
- Несколько keyframes: до трёх дополнительных **сохранённых поз** плюс текущая поза (до четырёх keyframes в экспорте); экспорт в Авторинг / Конвейер / черновик на платформе — один Phase 0 JSON с массивом `keyframes`.
- Скачивание **`pose.json` (SDK)** — плоский JSON-массив поз в градусах (формат `mid_level_motions/.../pose.json` на стороне Python SDK).
- **Создать движение** — предпросмотр траектории в окне: плавная интерполяция углов между текущим состоянием и сохранёнными позами (cosine ease, по духу `atomic_move.py`); без `mj_step` и без усилий на актуаторах.
- Экспорт keyframes использует ключи суставов Phase 0 в `joints_deg`: строки **`"0"`…`"28"`** (градусы), согласованно с телеметрией и валидацией.

---

## Стек

| Компонент | Пакет / файл |
|-----------|--------------|
| MuJoCo WASM | [`@mujoco/mujoco`](https://www.npmjs.com/package/@mujoco/mujoco) (v3.6+) |
| Загрузчик модели | [`web/frontend/src/mujoco/loadMenagerieG1.ts`](../web/frontend/src/mujoco/loadMenagerieG1.ts) |
| Маппинг суставов | [`web/frontend/src/mujoco/jointMapping.ts`](../web/frontend/src/mujoco/jointMapping.ts), [`qposToSkillAngles.ts`](../web/frontend/src/mujoco/qposToSkillAngles.ts) |
| Патч XML | [`web/frontend/src/mujoco/menagerieXmlPatch.ts`](../web/frontend/src/mujoco/menagerieXmlPatch.ts) |
| 3D-рендер | Three.js + @react-three/fiber в [`MuJoCoG1Viewer.tsx`](../web/frontend/src/components/mujoco/MuJoCoG1Viewer.tsx) |
| Ассеты (MJCF, STL) | `web/frontend/public/mujoco/g1/` |

---

## Источник модели

Официальный MJCF из репозитория [mujoco_menagerie / unitree_g1](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1):

- `scene.xml` — корневая сцена
- `g1.xml` — описание робота
- `assets/*.stl` — меши

Для загрузки ассетов в `public/mujoco/g1/` выполните:

```bash
npm run fetch:menagerie-g1
```

Скрипт: [`scripts/fetch-menagerie-g1.mjs`](../web/frontend/scripts/fetch-menagerie-g1.mjs) (требуется сетевой доступ к GitHub raw).

---

## Как работает загрузка

1. **`getMujocoModule()`** — ленивая инициализация WASM-модуля MuJoCo (синглтон).
2. **`loadMenagerieG1()`** — создаёт виртуальную файловую систему (`MjVFS`), загружает XML и STL через `fetch` из `public/mujoco/g1/`, применяет патч XML, компилирует модель (`MjModel.from_xml_string`), создаёт `MjData`.
3. **Патч XML** (`patchMujocoXmlForBrowserCompile`) — принудительно выставляет `compiler usethread="false"` для стабильности в браузере (избегает ошибки `Resource temporarily unavailable` на macOS и некоторых Linux).
4. **Рендер** — `MuJoCoG1Scene` в `MuJoCoG1Viewer.tsx` строит Three.js-геометрию из примитивов и мешей MuJoCo, обновляет позиции/ориентации тел на каждом кадре по `xpos`/`xquat` из `MjData`.

---

## Текущее рабочее состояние

| Аспект | Статус |
|--------|--------|
| Путь загрузки | **Однопоточный** (ST) — используется основной entry point `@mujoco/mujoco`, не `/mt` |
| COOP/COEP заголовки | **Не требуются** для текущей ST-сборки; понадобятся при переходе на MT (`@mujoco/mujoco/mt`) для `SharedArrayBuffer` |
| Vite-совместимость | Патч `postinstall` ([`scripts/patch-mujoco-vite.mjs`](../web/frontend/scripts/patch-mujoco-vite.mjs)) правит `node_modules/@mujoco/mujoco/mujoco.js` для корректной работы Worker + динамического импорта |
| Целевой ES | ES2022 (top-level `await` в worker); см. `vite.config.ts` |
| Размер первого визита | ~9 MB gzip-сжатого WASM + STL/XML из `public/mujoco/g1/`; рекомендуется кэшировать на CDN с `Cache-Control: immutable` |
| Ошибка «Resource temporarily unavailable» | Решена патчем XML (`usethread="false"`) |

---

## Маппинг суставов

Файл [`jointMapping.ts`](../web/frontend/src/mujoco/jointMapping.ts) определяет соответствие индексов `qpos` MuJoCo и имён суставов Skill Foundry. В Phase 0 JSON поле `joints_deg` сериализуется с **числовыми строковыми ключами** `"0"`…`"28"` (см. [`poseAuthoringBridge.ts`](../web/frontend/src/lib/poseAuthoringBridge.ts)), чтобы схема keyframes и Python-инструменты оставались согласованными.

---

## Отличие от нативного `unitree_mujoco`

| | Браузерный WASM | Нативный `unitree_mujoco` |
|---|-----------------|---------------------------|
| Среда | Браузер (JavaScript/WASM) | C++ / Python на хосте |
| Модель | menagerie `unitree_g1` | `unitree_robots/g1` (другая раскладка файлов) |
| Связь с DDS | Нет (только локальный `qpos`) | Да (SDK2 bridge) |
| Назначение | Визуализация и подбор позы в UI | Полноценная симуляция и мост к SDK |

---

## Связанные документы

- [web/frontend/README.md](../web/frontend/README.md) — общий README фронтенда, секция «MuJoCo WASM»
- [g1-control-ui/FAQ.md](g1-control-ui/FAQ.md) — FAQ, секция «Pose Studio и ассеты»
- [deployment/vercel-frontend.md](deployment/vercel-frontend.md) — рекомендации по кэшированию WASM и мешей
