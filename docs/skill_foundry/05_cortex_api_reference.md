# Cortex API Reference

REST API для Cortex Pipeline — коррекция траекторий и управление обучением.

## Base URL

```
/api/cortex
```

## Endpoints

### POST /api/cortex/correct

Коррекция траектории через NMR pipeline (IK + collision fixing).

#### Request

```json
{
  "animation_json": {
    "joint_positions": [[0.1, 0.2, ...], [0.15, 0.25, ...], ...],
    "joint_order": ["0", "1", "2", ...],
    "frequency_hz": 50.0
  },
  "options": {
    "fix_collisions": true,
    "fix_joint_limits": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `animation_json` | object | Yes | ReferenceTrajectory из UI |
| `animation_json.joint_positions` | array | Yes | Массив кадров, каждый кадр — массив углов |
| `animation_json.joint_order` | array | Yes | Порядок моторов в кадре |
| `animation_json.frequency_hz` | number | Yes | Частота кадров |
| `options.fix_collisions` | boolean | No | Исправлять self-collisions (default: true) |
| `options.fix_joint_limits` | boolean | No | Исправлять joint limits (default: true) |

#### Response

```json
{
  "corrected_json": {
    "joint_positions": [[0.1, 0.2, ...], ...],
    "joint_order": ["0", "1", ...],
    "frequency_hz": 50.0
  },
  "issues_fixed": [
    {
      "type": "self_collision",
      "count": 5,
      "frames_affected": 3
    },
    {
      "type": "joint_limits",
      "count": 12,
      "frames_affected": 8
    }
  ],
  "metadata": {
    "user_id": "user_123",
    "timestamp": "2026-04-12T16:30:00Z",
    "options_applied": {
      "fix_collisions": true,
      "fix_joint_limits": true
    }
  }
}
```

#### Errors

| Code | Description |
|------|-------------|
| 400 | Invalid reference: missing joint_positions or joint_order |
| 500 | IK correction failed / Collision fixing failed |
| 503 | NMR module not available / MJCF path not configured |

---

### POST /api/cortex/train

Запуск асинхронного RL обучения.

#### Request

```json
{
  "reference_json": {
    "joint_positions": [[...], ...],
    "joint_order": ["0", "1", ...],
    "frequency_hz": 50.0
  },
  "config": {
    "total_timesteps": 100000,
    "reward_weights": {
      "w_track": 1.0,
      "w_alive": 0.02,
      "w_energy": 1e-5,
      "w_jerk": 1e-6,
      "w_collision": 10.0
    }
  },
  "name": "my_training_job"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reference_json` | object | Yes | Скорректированная траектория |
| `config.total_timesteps` | integer | No | Количество шагов обучения (default: 100000) |
| `config.reward_weights` | object | No | Веса наград |
| `name` | string | No | Имя задачи (default: "cortex_training") |

#### Response

```json
{
  "job_id": "cortex_abc123def456",
  "status": "queued",
  "message": "Training job cortex_abc123def456 queued. Use Vast.ai for GPU training."
}
```

#### Notes

- Обучение выполняется асинхронно
- Для GPU-обучения используйте Vast.ai (см. [vast-ai-training.md](../deployment/vast-ai-training.md))
- Статус проверяется через `GET /api/cortex/result/{job_id}`

---

### GET /api/cortex/result/{job_id}

Получение результата обучения.

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `job_id` | string | ID задачи из `/train` |

#### Response (completed)

```json
{
  "job_id": "cortex_abc123def456",
  "status": "completed",
  "result_json": {
    "joint_positions": [[...], ...],
    "joint_order": ["0", "1", ...],
    "frequency_hz": 200.0,
    "source": "rl_policy_rollout",
    "_rollout_metadata": {
      "total_steps": 1000,
      "total_reward": 85.5,
      "policy_checkpoint": "/path/to/policy.zip"
    }
  },
  "metrics": {
    "final_reward": 0.85,
    "collision_count": 0,
    "fallen_count": 0
  }
}
```

#### Response (in progress)

```json
{
  "job_id": "cortex_abc123def456",
  "status": "running",
  "result_json": null,
  "metrics": null
}
```

#### Response (failed)

```json
{
  "job_id": "cortex_abc123def456",
  "status": "failed",
  "result_json": null,
  "metrics": null,
  "error": "Training failed: CUDA out of memory"
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `queued` | Задача в очереди |
| `running` | Обучение выполняется |
| `completed` | Обучение завершено успешно |
| `failed` | Обучение завершено с ошибкой |

#### Errors

| Code | Description |
|------|-------------|
| 404 | Job not found |

---

### GET /api/cortex/jobs

Список всех Cortex задач текущего пользователя.

#### Response

```json
[
  {
    "job_id": "cortex_abc123",
    "name": "wave_motion",
    "status": "completed",
    "created_at": "2026-04-12T15:00:00Z"
  },
  {
    "job_id": "cortex_def456",
    "name": "walk_cycle",
    "status": "running",
    "created_at": "2026-04-12T16:00:00Z"
  }
]
```

Список отсортирован по `created_at` (новые первыми).

---

### DELETE /api/cortex/jobs/{job_id}

Удаление задачи и её результатов.

#### Parameters

| Name | Type | Description |
|------|------|-------------|
| `job_id` | string | ID задачи |

#### Response

```json
{
  "status": "deleted",
  "job_id": "cortex_abc123"
}
```

#### Errors

| Code | Description |
|------|-------------|
| 404 | Job not found |

---

## Authentication

Все endpoints требуют аутентификации через `X-User-ID` header или session cookie (зависит от конфигурации бэкенда).

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/correct` | 10 req/min |
| `/train` | 5 req/hour |
| `/result`, `/jobs` | 60 req/min |

---

## Examples

### cURL: Коррекция траектории

```bash
curl -X POST http://localhost:8000/api/cortex/correct \
  -H "Content-Type: application/json" \
  -H "X-User-ID: user_123" \
  -d '{
    "animation_json": {
      "joint_positions": [[0.1, 0.2, 0.3], [0.15, 0.25, 0.35]],
      "joint_order": ["0", "1", "2"],
      "frequency_hz": 50.0
    },
    "options": {
      "fix_collisions": true
    }
  }'
```

### Python: Полный workflow

```python
import requests

BASE_URL = "http://localhost:8000/api/cortex"
HEADERS = {"X-User-ID": "user_123"}

# 1. Коррекция
resp = requests.post(
    f"{BASE_URL}/correct",
    json={
        "animation_json": reference,
        "options": {"fix_collisions": True}
    },
    headers=HEADERS,
)
corrected = resp.json()["corrected_json"]

# 2. Запуск обучения
resp = requests.post(
    f"{BASE_URL}/train",
    json={
        "reference_json": corrected,
        "config": {"total_timesteps": 100000},
        "name": "my_motion"
    },
    headers=HEADERS,
)
job_id = resp.json()["job_id"]

# 3. Проверка статуса
import time
while True:
    resp = requests.get(f"{BASE_URL}/result/{job_id}", headers=HEADERS)
    status = resp.json()["status"]
    if status in ["completed", "failed"]:
        break
    time.sleep(30)

# 4. Получение результата
result = resp.json()["result_json"]
```

---

## Related Documentation

- [04_cortex_pipeline.md](04_cortex_pipeline.md) — архитектура Cortex
- [vast-ai-training.md](../deployment/vast-ai-training.md) — GPU обучение на Vast.ai
- [02_architecture.md](02_architecture.md) — общая архитектура Skill Foundry
