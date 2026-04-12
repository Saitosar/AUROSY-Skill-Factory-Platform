# Cortex Pipeline: NMR + RL для безопасного обучения движениям

## Обзор

**Cortex Pipeline** — это слой "коры головного мозга" в Skill Foundry, который автоматически корректирует пользовательские анимации и обучает политики с учетом физических ограничений и безопасности.

```
┌─────────────────────────────────────────────────────────────────┐
│                        UI (Frontend)                            │
│  Пользователь рисует анимацию → Animation JSON                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Step 1: NMR Translator                        │
│  ┌─────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │ IK Corrector│ → │ Collision Fixer │ → │ Torque Validator│   │
│  │ (Pinocchio) │   │    (MuJoCo)     │   │   (Pinocchio)   │   │
│  └─────────────┘   └─────────────────┘   └─────────────────┘   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ Corrected JSON
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Step 2: RL Teacher                            │
│  ┌─────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │G1TrackingEnv│ → │   PPO Training  │ → │ Trained Policy  │   │
│  │ + Collision │   │   (Vast.ai GPU) │   │    (.pt/.zip)   │   │
│  └─────────────┘   └─────────────────┘   └─────────────────┘   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Step 3: Protocol Generator                      │
│  ┌─────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │MuJoCo Rollout│ → │ record_result.py│ → │  Result JSON    │   │
│  └─────────────┘   └─────────────────┘   └─────────────────┘   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        UI (Frontend)                            │
│  Пользователь видит: "Я нарисовал так → Физика позволила так"   │
│  [Одобрить] [Редактировать] [Переобучить]                       │
└─────────────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. NMR Translator (`skill_foundry_nmr`)

**Neural Motion Retargeting** — адаптация анимаций под физические ограничения G1.

#### IK Corrector (`ik_corrector.py`)

Использует **Pinocchio** для:
- Проверки и коррекции joint limits
- IK-решения для достижения целевых позиций end-effectors
- Адаптации под длины звеньев G1

```python
from skill_foundry_nmr import correct_reference_trajectory

corrected = correct_reference_trajectory(
    reference,
    urdf_path="/path/to/g1.urdf",
)
```

#### Collision Fixer (`collision_fixer.py`)

Использует **MuJoCo** для:
- Детекции self-collisions (рука проходит сквозь тело)
- Итеративной коррекции углов до устранения penetration
- Сохранения плавности движения

```python
from skill_foundry_nmr import fix_reference_trajectory

fixed = fix_reference_trajectory(
    reference,
    mjcf_path="/path/to/scene_29dof.xml",
    max_iterations_per_frame=50,
)
```

### 2. RL Teacher (`skill_foundry_rl`)

Обучение политики в стиле **DeepMimic** — робот учится повторять траекторию с учетом физики.

#### G1TrackingEnv

Gymnasium environment с reward shaping:

| Reward | Описание | Вес по умолчанию |
|--------|----------|------------------|
| `r_track` | MSE между текущим и целевым углом | 1.0 |
| `r_alive` | Бонус за "не упал" | 0.02 |
| `r_energy` | Штраф за энергию (плавность) | 1e-5 |
| `r_jerk` | Штраф за рывки | 1e-6 |
| `r_collision` | Штраф за self-collision | 10.0 |

```python
from skill_foundry_rl.g1_tracking_env import G1TrackingEnv, G1TrackingEnvConfig

config = G1TrackingEnvConfig(
    mjcf_path="scene_29dof.xml",
    enable_collision_check=True,
    terminate_on_collision=False,  # или True для строгого режима
    reward_weights={
        "w_track": 1.0,
        "w_collision": 10.0,
    },
)

env = G1TrackingEnv(reference, config)
```

### 3. Protocol Generator (`skill_foundry_export`)

Экспорт обученной политики обратно в JSON для UI.

#### record_result.py

```python
from skill_foundry_export.record_result import record_and_save

result = record_and_save(
    policy_path=Path("ppo_G1TrackingEnv.zip"),
    reference_path=Path("reference.json"),
    mjcf_path="scene_29dof.xml",
    output_path=Path("result.json"),
)
```

Результат содержит:
- `joint_positions` — реальные углы из симуляции
- `_rollout_metadata` — метрики (reward, collision count)

## API Endpoints

### POST /api/cortex/correct

Коррекция траектории через NMR.

```json
// Request
{
  "animation_json": { /* ReferenceTrajectory */ },
  "options": {
    "fix_collisions": true,
    "fix_joint_limits": true
  }
}

// Response
{
  "corrected_json": { /* ReferenceTrajectory */ },
  "issues_fixed": [
    {"type": "self_collision", "count": 5, "frames_affected": 3}
  ]
}
```

### POST /api/cortex/train

Запуск обучения (async).

```json
// Request
{
  "reference_json": { /* Corrected ReferenceTrajectory */ },
  "config": {
    "total_timesteps": 100000,
    "reward_weights": {"w_track": 1.0, "w_collision": 10.0}
  }
}

// Response
{
  "job_id": "cortex_abc123",
  "status": "queued"
}
```

### GET /api/cortex/result/{job_id}

Получение результата обучения.

```json
{
  "job_id": "cortex_abc123",
  "status": "completed",
  "result_json": { /* Physics-corrected ReferenceTrajectory */ },
  "metrics": {
    "final_reward": 0.85,
    "collision_count": 0
  }
}
```

## CLI

```bash
# Полная коррекция (IK + collision)
skill-foundry-nmr correct trajectory.json \
  --mjcf scene_29dof.xml \
  --output trajectory_corrected.json

# Только joint limits
skill-foundry-nmr fix-limits trajectory.json \
  --urdf g1.urdf

# Только collisions
skill-foundry-nmr fix-collisions trajectory.json \
  --mjcf scene_29dof.xml
```

## Интеграция с Vast.ai

Для GPU-ускоренного обучения используйте `vast_training/`:

```bash
# На Vast.ai инстансе
bash setup_vast.sh --pytorch

python train_cortex.py \
  --reference /workspace/data/trajectory.json \
  --mjcf /workspace/data/scene_29dof.xml \
  --timesteps 100000
```

См. [vast-ai-training.md](../deployment/vast-ai-training.md) для подробностей.

## Безопасность

### Предотвращение падений

- `min_base_height`: терминация если таз ниже 0.35м
- `r_alive`: положительный reward за каждый шаг без падения

### Предотвращение самоповреждений

- `enable_collision_check`: детекция self-collision каждый шаг
- `r_collision`: штраф -10 за каждое столкновение
- `terminate_on_collision`: опционально — терминация при столкновении

### Joint limits

- IK Corrector автоматически clamp'ит углы в допустимые диапазоны
- URDF содержит физические лимиты из спецификации G1

## Связь с другими модулями

- **skill_foundry_validation**: использует те же collision checks
- **skill_foundry_sim**: headless playback для валидации
- **skill_foundry_runtime**: загружает обученные политики на робота
