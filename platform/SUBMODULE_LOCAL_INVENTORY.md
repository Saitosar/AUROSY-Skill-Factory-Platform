# Локальные артефакты в `unitree_*` (на момент выноса Skill Foundry)

См. план «Extract platform code from submodules». Кратко:

## unitree_mujoco

- Неотслеживаемое: `simulate_python/stand_up.py` → перенесено в `platform/mujoco_local/`.
- Лог: `simulate_python/MUJOCO_LOG.TXT` — не в git; игнорировать локально.
- `.DS_Store` — игнор.
- Изменено относительно `origin/main`: `simulate/config.yaml`, `simulate_python/config.py`, `simulate_python/unitree_sdk2py_bridge.py`, `unitree_robots/go2w/assets/terrain.STL` — остаются в сабмодуле до политики fork/патчей.

## unitree_sdk2

- Неотслеживаемое: `thirdparty/lib/arm64/*.dylib` — не коммитим; каталог `platform/lib/cyclonedds/arm64/` + README (положить dylib локально при необходимости).

## unitree_sdk2_python

- Перенесено в `packages/skill_foundry/`: все пакеты `skill_foundry_*`, `core_control`, `high_level_motions`, `mid_level_motions`, `tools`, `MANIFEST.in`.
- `setup.py` / `README.md` / `clib_lookup.py` в сабмодуле: после выноса `setup.py` приведён к upstream-only (`unitree_sdk2py`).

## Политика после миграции

- **`unitree_sdk2_python`:** только upstream Unitree; AUROSY-код и CLI — в `packages/skill_foundry` (`pyproject.toml`). В родительском репозитории фиксируйте SHA сабмодуля на коммит Unitree; локальные dylib — см. `platform/lib/cyclonedds/arm64/README.md`.
- **`unitree_mujoco` / `unitree_sdk2`:** локальные правки остаются в сабмодулях до решения **fork** vs **`platform/patches/*.patch`** + чистый upstream; не смешивать с кодом Skill Foundry.
- **Родитель:** после `git add` новых путей и обновления `.gitmodules` (при смене URL) закоммитьте дерево платформы; PR может разделять «перенос + wiring» и «документация + политика сабмодулей».
