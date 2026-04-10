Pose Studio static assets (frontend_developer_guide §1.4 in the backend repo).

User-facing notes on placeholders and swapping assets: docs/g1-control-ui/FAQ.md (section «Pose Studio и ассеты») and in-app Help at /help. Live joint angles on Pose Studio use the same WebSocket as Telemetry; if the backend reports DDS telemetry without a bridge, see FAQ §5 (Telemetry) and docs/g1-control-ui/DEPLOYMENT.md.

- robot-diagram.svg — bundled placeholder until official PNG/SVG from §1.4 are copied here.
- Optional: add robot.png (same aspect ratio as overlay zones) and extend pose-overlay.json for custom SVG paths.

UI: when official assets are in place, set POSE_ASSETS_ARE_PLACEHOLDER to false in web/frontend/src/lib/poseAssets.ts so the placeholder banner on Pose Studio hides.

Keyboard: clickable body zones use :focus-visible (primary ring) in the app stylesheet for keyboard users.
