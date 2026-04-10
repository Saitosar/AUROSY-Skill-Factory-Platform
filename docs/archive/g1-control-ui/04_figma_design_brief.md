# Figma design brief: AUROSY Skill Factory web UI

Документ для **дизайнера** или **Figma AI**: продукт, экраны, библиотека компонентов, сетка и готовый текст промпта. Визуальный референс: внешний UI-кит в духе «Design SaaS Platform UI» (тёмный SaaS, sidebar), если доступен локально — **вдохновение, не требование** к пиксельному совпадению.

Продуктовые и технические требования к данным: `frontend_developer_guide` в репозитории бэкенда ([backend_references.md](backend_references.md)). Токены и компоненты уровня реализации: [02_design_system.md](02_design_system.md).

---

## 1. Продукт (кратко)

Веб-приложение **AUROSY Skill Factory** для **авторинга движений и сценариев** человекоподобного робота Unitree G1 (29 DOF) в текущем целевом референсе: редактирование JSON Phase 0 (keyframes, motion, scenario), визуальная настройка позы (Pose Studio), сборка сценариев из библиотеки действий, запуск **локального конвейера** (preprocess → симуляция MuJoCo → обучение) через бэкенд и просмотр телеметрии. Аудитория: инженеры и продвинутые операторы; цель UX — **понятный визуальный центр**, а не «панель приборов» из одних чисел.

---

## 2. Ключевые экраны

| Экран | Цель | Примечания |
|-------|------|------------|
| **Home / Dashboard** | Входная точка: статус бэкенда, краткие ссылки в разделы, последние черновики (если будут) | Показать «offline», если API недоступен |
| **Authoring** | Редактирование keyframes / motion / scenario: табы или подстраницы, JSON-панель, кнопка Validate | Ошибки валидации списком под формой |
| **Pose Studio** | Центр: крупный визуал робота (2D схема или 3D viewport); вокруг — слайдеры по группам телу; переключатель «Эксперт: все 29 суставов» | Главный экран для снижения когнитивной нагрузки |
| **Telemetry** | Поток углов с WebSocket: таблица или слайдеры по группам | Индикатор подключения |
| **Scenario builder** | Каталог mid-level действий + конструктор цепочки нод + блок «оценка длительности» и предупреждение вне 25–35 с | Строки нод с speed/repeat |
| **Pipeline** | Три блока: Preprocess, Playback, Train — поля параметров, кнопка Run, консоль логов | Состояния: idle / running / success / error |
| **Settings / About** (опционально) | Base URL (`VITE_API_BASE`), тема, ссылки на документацию | Минимальный набор |

---

## 3. Компонентная библиотека для Figma

Создать **варианты** (default, hover, active, disabled, error) и **размеры** где уместно.

| Компонент | Содержимое вариантов |
|-----------|----------------------|
| **Sidebar** | Логотип/название, NavItem ×5–7, нижний слот (версия) |
| **TopBar** | Заголовок страницы, breadcrumbs опционально, primary action |
| **Card** | Header, body, footer; для форм pipeline |
| **DataTable** | Заголовки, сортировка (иконка), строки действий |
| **Tabs** | Для Authoring: Keyframes / Motion / Scenario |
| **JsonPanel** | Моноширинный блок, line numbers опционально, кнопки Format / Copy |
| **ValidateBanner** | Success (зелёный), Error (список строк) |
| **JointControl** | Label (человекочитаемый), Slider, Value + единица (°), optional expert row (index, internal name) |
| **JointGroupTabs** | Ноги / Торс / Левая рука / Правая рука |
| **ScenarioNodeRow** | Поля ноды + столбец estimated time |
| **DurationSummary** | Total + warning callout при выходе за целевой диапазон |
| **PipelineStep** | Form fields + Run + LogConsole вложенно |
| **LogConsole** | Тёмный фон, моноширинный текст, скролл |
| **StatusBadge** | idle, running (с индикатором), success, error |
| **EmptyState** | Иллюстрация/иконка + CTA |
| **Modal / Dialog** | Подтверждение длительной операции |
| **Toast** | Краткие сообщения об успехе/ошибке сети |

---

## 4. Сетка и брейкпоинты

- **Ориентация:** desktop-first; базовая ширина макета **1440px**, контентная сетка **12 колонок**, gutter **24px**, поля страницы **24–32px**.
- **Sidebar:** фиксированная ширина **260–280px**; основная область — fluid.
- **Pose Studio:** основная колонка под визуал **минимум 60%** ширины main; боковая панель слайдеров скроллится независимо при необходимости.
- **Брейкпоинты (для будущей адаптации):** `1280` полный UI; `1024` схлопывание sidebar в иконки/drawer; ниже — только если в scope (не обязательно для MVP макетов).

---

## 5. Состояния для ключевых потоков

- **Authoring:** пустой JSON → заполненный → validating → success / error list.
- **Pipeline:** idle → running (disabled Run, spinner в StatusBadge) → success (логи + краткое резюме) / error (акцент на stderr).
- **Telemetry:** disconnected → connecting → live (heartbeat optional).

---

## 6. Мастер-промпт (English) для Figma AI / внешнего дизайнера

Скопируйте блок ниже целиком:

---

Design a **dark-themed desktop web application** for an engineering tool called **AUROSY Skill Factory**. The product lets users author robot motion JSON, build scenarios from a library of actions, run a local ML/simulation pipeline (preprocess, MuJoCo playback, training), and view live joint telemetry for a **Unitree G1 humanoid (29 DOF)** (reference robot in the current stack).

**Visual direction:** futuristic dark UI (deep navy/black background), **one cyan/teal primary accent** for primary actions and focus rings, **purple secondary accent** for secondary highlights, **green** for success, **red** for errors. Subtle glass/slate panels for cards. **Inspiration only (do not copy pixel-perfect):** modern SaaS dashboard with left sidebar. Typography: clean sans for UI, **monospace for JSON and logs**.

**Layout:** persistent **left sidebar** with navigation: Home, Authoring, Pose Studio, Telemetry, Scenarios, Pipeline, Settings. Main content uses a **12-column grid**, generous whitespace, card-based sections.

**Key screens to design:**

1. **Dashboard/Home** — connection status to backend API, quick links, empty state when no drafts.
2. **Authoring** — **tabs**: Keyframes, Motion, Scenario. Large **JSON editor panel** (monospace), **Validate** button, **validation result banner** (success or bullet list of errors). Use **semantic colors** for validation.
3. **Pose Studio** — **large central robot visual** (placeholder frame for 2D diagram or 3D viewport). Around it: **joint sliders** grouped by body regions (Legs, Torso, Left arm, Right arm). Include a toggle **“Expert mode”** revealing internal joint indices and snake_case names. Show values with **degree symbol** for authoring.
4. **Telemetry** — live updating table or sliders; **WS connection** indicator (connected/disconnected).
5. **Scenario builder** — **data table** of available mid-level actions; builder list of **nodes** (subdir, action name, speed, repeat); **estimated duration** per node and **total**; **warning callout** if total duration falls outside ~25–35 seconds (target ~30s).
6. **Pipeline** — three stacked **cards**: Preprocess, Playback, Train — each with form fields, **Run** button, and **log console** (dark monospace area). Show **status badges**: idle, running, success, error.

**Components library:** Sidebar, TopBar, Card, Tabs, DataTable, JsonPanel, ValidateBanner, JointControl (slider + label + unit), JointGroupTabs, ScenarioNodeRow, DurationSummary, LogConsole, StatusBadge, EmptyState, Modal, Toast.

**Accessibility:** focus rings visible; status not by color alone (add text/icons).

Deliver **high-fidelity frames** for the six screens above plus **component sheet** with variants. Use **auto-layout** and consistent **8px spacing grid**.

---

## 7. Мастер-промпт (краткая версия на русском)

Тёмный инженерный веб-интерфейс **AUROSY Skill Factory**: боковая навигация, акцент бирюзовый, карточки в стиле стекла/сланца. Экраны: главная с статусом API; авторинг с табами Keyframes/Motion/Scenario и валидацией; **Pose Studio** с крупным визуалом робота и слайдерами по группам телу; телеметрия; конструктор сценариев с оценкой длительности; конвейер с логами. Шрифт UI — гротеск; JSON и логи — моноширинный. Не копировать пиксель-в-пиксель референс «Design SaaS Platform UI» — только общее настроение.

---

## 8. Связанные документы

- [01_frontend_architecture.md](01_frontend_architecture.md)
- [02_design_system.md](02_design_system.md)
- [03_implementation_roadmap_frontend.md](03_implementation_roadmap_frontend.md)
- [backend_references.md](backend_references.md)
