# Skill Foundry — документы в `docs/skill_foundry/`

Краткий указатель по темам (репозиторий **AUROSY_creators_factory_platform**).

| Документ | Содержание |
|----------|------------|
| [01_vision_and_approach.md](01_vision_and_approach.md) | Видение продукта |
| [02_architecture.md](02_architecture.md) | Модули, потоки данных, video-to-motion и Phase 6 |
| [03_implementation_plan.md](03_implementation_plan.md) | Фазы и ссылки на archive |
| [13_phase6_runtime_security.md](13_phase6_runtime_security.md) | Безопасность рантайма / целостность пакетов |
| [14_video_to_motion_integration.md](14_video_to_motion_integration.md) | Полный план video→motion (Phases 1–6), API и верификация |
| [FAQ.md](FAQ.md) | Практические вопросы по motion capture, retargeting и Phase 6 |

**Phase 6 (E2E motion):** см. §Phase 6 в [14_video_to_motion_integration.md](14_video_to_motion_integration.md) — `POST /api/pipeline/motion/run`, `skill_foundry_export.motion_bundle_validate`, SPA: AMP по умолчанию в Motion pipeline, запись landmarks → capture artifact (`aurosy_capture_v1`) → `build_reference` (`landmarks_artifact` / `capture_artifact` / `bvh_artifact`).
