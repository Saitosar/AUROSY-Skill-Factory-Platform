# FAQ — Skill Foundry video-to-motion

Короткий справочник для команды платформы по `motion_capture`, ретаргетингу и Phase 6.

## Где работает `WS /ws/capture`?

Это отдельный сервис `packages/motion_capture` (обычно `:8001`), а не FastAPI API-процесс на `:8000`.

## Какой payload сохраняет UI после записи камеры?

UI сохраняет платформенный артефакт формата:

```json
{
  "schema_version": "aurosy_capture_v1",
  "source": "motion_capture_ws",
  "frames": [[[0.0, 0.0, 0.0]]],
  "bvh": "HIERARCHY\n..."
}
```

`frames` — основной источник для построения `reference_trajectory`.

## Какие артефакты принимает `build_reference`?

`POST /api/pipeline/motion/run` с `action: "build_reference"` принимает:

- `reference_artifact` (готовый `reference_trajectory.json`)
- `landmarks_artifact` (JSON с `frames`/`landmarks`)
- `capture_artifact` (например `aurosy_capture_v1`)
- `bvh_artifact` (`.bvh`, конвертируется через `skill_foundry_retarget.bvh_to_trajectory`)

## Почему BVH-конверсия помечена как lossy?

Текущий `BVHExporter` пишет root-centric каналы. Этого недостаточно для полного восстановления 33 landmarks. Конвертер строит синтетические landmarks для совместимости pipeline, но для лучшего качества используйте `frames` из capture JSON.

## Можно ли включить `MOTION_CAPTURE_BACKEND=vitpose`?

Пока нет. Этот путь формально отложен: при выборе `vitpose` сервер выдаёт понятную ошибку (`ViTPosePoseBackend.DEFERRED_REASON`) с шагами для будущей реализации (deps + mapping в 33 MediaPipe landmarks).

## Как фронтенд находит endpoint capture-сервиса?

Через `VITE_MOTION_CAPTURE_WS_URL`. Если переменная не задана, клиент использует URL по умолчанию (`ws://<host>:8001/ws/capture`).

## Где включается сглаживание retarget-последовательностей?

На backend в `web/backend/app/services/retargeting.py`: после `Retargeter.compute_batch(...)` применяется EMA (`alpha=0.6`) для последовательностей (`N > 1`).

## Как включить ONNX-балансировщик в live capture?

Задайте `MOTION_CAPTURE_BALANCE_ONNX=/abs/path/to/balance_policy.onnx` перед запуском `motion_capture` сервиса. Если переменная не задана или модель невалидна, сервис работает без balance-коррекции.

## Что отправляет `pose` сообщение из capture-сервиса?

Базовые поля: `landmarks`, `confidence`, `timestamp_ms`.  
Если доступен retarget-модуль, дополнительно отправляются `joint_order` и `joint_angles_rad`; при включенном ONNX-балансе также поле `balance_timing_ms`.

## Какие основные проблемы с Live Mode встречаются в проде?

- `WS /ws/capture` доступен, но API `:8000` недоступен (или наоборот).
- Неправильный shape landmarks (должно быть `[33,3]`).
- Несогласованный `joint_map` между frontend/platform.
- Отсутствие DDS-моста при `telemetry_mode=dds` (нужен fallback на mock для UI-проверок).
