# AUROSY Skill Foundry (Python)

Пакет живёт в репозитории платформы рядом с вендорным [`unitree_sdk2_python`](../../unitree_sdk2_python) (Unitree upstream как git submodule).

## Установка

Из **корня репозитория платформы**:

```bash
pip install -e "./unitree_sdk2_python"
pip install -e "./packages/skill_foundry[rl,export,runtime,validation]"
```

Порядок важен: сначала `unitree_sdk2py`, затем этот пакет (импорты `unitree_sdk2py.*`).

## Разработка и `PYTHONPATH`

Если без editable-установки, добавьте оба каталога в `PYTHONPATH` (см. `web/backend/app/config.py`: `G1_SDK_PYTHON_ROOT` и корень Skill Foundry).

## CLI

Те же entry points, что раньше: `skill-foundry-preprocess`, `skill-foundry-playback`, `skill-foundry-train`, …

## `tools/`

Скрипты в `tools/` не являются установленным пакетом; при запуске добавьте в `PYTHONPATH` каталог `packages/skill_foundry` (бэкенд делает это через `ensure_sdk_on_path`).
