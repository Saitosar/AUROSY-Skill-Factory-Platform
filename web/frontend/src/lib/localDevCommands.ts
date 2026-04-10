/**
 * Commands to paste in Terminal from the platform repo root
 * (`AUROSY_creators_factory_platform`). See `web/README.md` there for venv setup.
 */
export const LOCAL_BACKEND_START = `cd web/backend && source .venv/bin/activate && export PYTHONPATH="$(cd ../.. && pwd)/unitree_sdk2_python" && export G1_REPO_ROOT="$(cd ../.. && pwd)" && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`;

export const LOCAL_SIMULATOR_START =
  "cd unitree_mujoco/simulate_python && python3 unitree_mujoco.py";
