"""Optional ONNX-based lower-body balance correction for live mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class BalanceOutput:
    joint_angles_rad: np.ndarray
    elapsed_ms: float


class BalanceInferencer:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.enabled = False
        self._session = None
        self._input_name = ""
        self._output_name = ""
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
            self._input_name = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name
            self.enabled = True
        except Exception:
            self.enabled = False

    def apply(self, joint_angles_rad: np.ndarray) -> BalanceOutput:
        if not self.enabled or self._session is None:
            return BalanceOutput(joint_angles_rad=joint_angles_rad, elapsed_ms=0.0)
        import time

        t0 = time.perf_counter()
        input_batch = np.asarray(joint_angles_rad, dtype=np.float32)[np.newaxis, :]
        out = self._session.run([self._output_name], {self._input_name: input_batch})[0]
        corrected = np.asarray(out[0], dtype=np.float32)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return BalanceOutput(joint_angles_rad=corrected, elapsed_ms=elapsed_ms)


def load_balance_inferencer_from_env() -> BalanceInferencer | None:
    raw = os.getenv("MOTION_CAPTURE_BALANCE_ONNX", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_file():
        return None
    inferencer = BalanceInferencer(path)
    if not inferencer.enabled:
        return None
    return inferencer
