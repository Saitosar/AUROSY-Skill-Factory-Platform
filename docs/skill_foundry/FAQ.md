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
