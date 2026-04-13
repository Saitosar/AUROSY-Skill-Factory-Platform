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

Для `skill-foundry-train` поддерживаются режимы `--mode smoke` (контрактный smoke), `--mode train` (PPO/BC) и `--mode amp` (AMP pipeline с adversarial motion prior).

**AMP motion eval (Phase 5):** после обучения можно записать отчёт без повторного train:

```bash
skill-foundry-train --mode amp --eval-only \
  --config /path/to/train_config.json \
  --reference-trajectory /path/to/reference_trajectory.json \
  --checkpoint /path/to/train_out/ppo_amp_G1TrackingEnv.zip \
  --eval-output /path/to/train_out/eval_motion.json
```

Опции: `--discriminator` (путь к `amp_discriminator.pt`, иначе ищется рядом с checkpoint / из `train_run.json`).

**Упаковка с motion-метаданными:** `skill-foundry-package pack …` автоматически включает `eval_motion.json` из `--run-dir`, если файл есть; флаги `--include-amp-discriminator`, `--record-motion-metadata`, `--joint-map-version`, `--motion-source-skeleton` — см. [10_phase4_manifest_export.md](../../docs/archive/10_phase4_manifest_export.md).

**Проверка motion-пакета (Phase 6):** модуль `skill_foundry_export.motion_bundle_validate` — функция `validate_motion_skill_bundle(tarball, require_motion_section=..., max_tracking_mse=...)` для структуры архива и порога `metrics.tracking_mean_mse`; тесты: `pytest packages/skill_foundry/tests/test_motion_bundle_validation.py`.

## `tools/`

Скрипты в `tools/` не являются установленным пакетом; при запуске добавьте в `PYTHONPATH` каталог `packages/skill_foundry` (бэкенд делает это через `ensure_sdk_on_path`).
