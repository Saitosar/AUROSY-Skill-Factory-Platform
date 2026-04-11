"""
Pose Studio — Tkinter GUI для управления 29 DOF Unitree G1 (SAI / MuJoCo bridge).

При запуске только читает rt/lowstate и выставляет углы в полях; в симулятор ничего не шлёт,
пока вы не измените угол (↑/↓ или ввод) — тогда этот сустав попадает в «активные» и получает PD.

Запуск из каталога unitree_sdk2_python:
  python tools/pose_studio.py
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from typing import Dict, List, Optional, Set, Tuple

# Bootstrap: родитель tools/ — корень пакета unitree_sdk2_python
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import action_exporter

from core_control.config.joint_limits import get_limit
from core_control.joint_controller import JointController
from core_control.state_listener import StateListener
from core_control.utils.conversions import rad2deg

# Порядок групп: левая рука, правая рука, торс, левая нога, правая нога
GROUPS: List[Tuple[str, List[int]]] = [
    ("Левая рука", list(range(15, 22))),
    ("Правая рука", list(range(22, 29))),
    ("Торс", list(range(12, 15))),
    ("Левая нога", list(range(0, 6))),
    ("Правая нога", list(range(6, 12))),
]

PUBLISH_HZ = 75.0
SCALE_RESOLUTION_DEG = 0.5
# Удержание стрелки: до FAST_AFTER — медленный повтор; после — быстрый (интервал и шаг)
ANGLE_HOLD_SLOW_REPEAT_MS = 175
ANGLE_HOLD_FAST_AFTER_MS = 500
ANGLE_HOLD_FAST_REPEAT_MS = 50
ANGLE_HOLD_FAST_STEP_MULT = 4.0
# Слоты HG LowCmd (как в JointController.__init__)
NUM_MOTOR_SLOTS = 35
MAX_KEYFRAMES = 3


def _basic_actions_dir() -> str:
    return os.path.join(_root_dir, "mid_level_motions", "basic_actions")


def discover_basic_action_poses() -> List[Tuple[str, str, Optional[int]]]:
    """
    Сканирует basic_actions/<имя>/pose.json.
    Возвращает список (подпись, путь к pose.json, индекс кадра или None для одиночного объекта).
    """
    entries: List[Tuple[str, str, Optional[int]]] = []
    base = _basic_actions_dir()
    if not os.path.isdir(base):
        return entries
    for folder_name in sorted(os.listdir(base)):
        sub = os.path.join(base, folder_name)
        if not os.path.isdir(sub):
            continue
        path = os.path.join(sub, "pose.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if isinstance(raw, dict):
            entries.append((folder_name, path, None))
        elif isinstance(raw, list):
            n = len(raw)
            for i, item in enumerate(raw):
                if isinstance(item, dict):
                    entries.append((f"{folder_name} [{i + 1}/{n}]", path, i))
    return entries


def _human_label(joint_id: int) -> str:
    name = JointController.JOINT_MAP[joint_id]
    return " ".join(part.capitalize() for part in name.split("_"))


def _deg_limits(joint_id: int) -> Tuple[float, float]:
    lim = get_limit(joint_id)
    return rad2deg(lim["min"]), rad2deg(lim["max"])


def _clamp_deg(joint_id: int, deg: float) -> float:
    lo, hi = _deg_limits(joint_id)
    return max(lo, min(hi, deg))


def _format_deg_str(deg: float) -> str:
    s = f"{deg:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _clamp_speed_rad(joint_id: int, rad_s: float) -> float:
    mx = float(get_limit(joint_id)["max_vel"])
    return max(0.0, min(float(rad_s), mx))


def _format_speed_str(rad_s: float) -> str:
    s = f"{rad_s:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def load_pose_frame_deg(pose_json_path: str, frame_index: Optional[int]) -> Dict[int, float]:
    """Читает один кадр из pose.json (градусы), дополняет суставы нулями, clamp по лимитам."""
    with open(pose_json_path, encoding="utf-8") as f:
        raw = json.load(f)
    if frame_index is None:
        if not isinstance(raw, dict):
            raise ValueError("pose.json: ожидался один JSON-объект")
        frame = raw
    else:
        if not isinstance(raw, list) or frame_index < 0 or frame_index >= len(raw):
            raise ValueError("pose.json: неверный список кадров или индекс")
        item = raw[frame_index]
        if not isinstance(item, dict):
            raise ValueError("pose.json: кадр не является объектом")
        frame = item
    partial = {int(k): float(v) for k, v in frame.items()}
    out: Dict[int, float] = {}
    for jid in JointController.JOINT_MAP:
        out[jid] = _clamp_deg(jid, float(partial.get(jid, 0.0)))
    return out


class PoseStudioApp:
    def __init__(self) -> None:
        self.ctrl = JointController()
        self.listener = StateListener()

        self._targets: Dict[int, float] = {}
        # Суставы, по которым пользователь уже двигал слайдер — только им шлём PD.
        self._active_joints: Set[int] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._angle_entries: Dict[int, tk.Entry] = {}
        self._speed_entries: Dict[int, tk.Entry] = {}
        self._suppress_angle_callback = False

        self._current_sequence: List[Dict[int, float]] = []
        self._startup_pose_deg: Dict[int, float] = {}
        self._last_execute_path: Optional[str] = None

        self._angle_hold_after_id: Optional[str] = None
        self._angle_hold_joint: int = 0
        self._angle_hold_direction: int = 1
        self._angle_hold_start: float = 0.0
        self._angle_hold_held: bool = False

        self.root = tk.Tk()
        self.root.title("SAI Motion Builder — Pose Studio — G1 (29 DOF)")
        self.root.geometry("980x780")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._action_name_var = tk.StringVar(value="")

        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(top, text="Save Pose", command=self._save_pose).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Reset", command=self._reset_pose).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            top,
            text="Синхр. с роботом / отпустить моторы",
            command=self._sync_and_release,
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._status = ttk.Label(top, text="")
        self._status.pack(side=tk.LEFT, padx=(12, 0))

        seq_row = ttk.Frame(self.root, padding=(8, 0, 8, 4))
        seq_row.pack(side=tk.TOP, fill=tk.X)
        self._btn_add_keyframe = ttk.Button(
            seq_row, text="Add Keyframe", command=self._add_keyframe
        )
        self._btn_add_keyframe.pack(side=tk.LEFT, padx=(0, 8))
        self._btn_add_from_library = ttk.Button(
            seq_row,
            text="Из basic_actions…",
            command=self._open_pose_library,
        )
        self._btn_add_from_library.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(seq_row, text="Clear", command=self._clear_sequence).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        self._sequence_label = ttk.Label(seq_row, text="")
        self._sequence_label.pack(side=tk.LEFT)

        spd_global_row = ttk.Frame(self.root, padding=(8, 0, 8, 4))
        spd_global_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(spd_global_row, text="Скорость для всех (рад/с):").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._global_speed_var = tk.StringVar(value="")
        ttk.Entry(
            spd_global_row, textvariable=self._global_speed_var, width=12
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            spd_global_row,
            text="Применить ко всем",
            command=self._apply_global_speed,
        ).pack(side=tk.LEFT)

        action_row = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        action_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(action_row, text="Action Name:").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(action_row, textvariable=self._action_name_var, width=28).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(action_row, text="Save Action", command=self._save_action).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._btn_play = ttk.Button(
            action_row,
            text="\u25B6",
            width=4,
            command=self._play_last_action,
            state=tk.DISABLED,
        )
        self._btn_play.pack(side=tk.LEFT)

        self._action_status = ttk.Label(
            self.root,
            text="",
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=6,
            wraplength=680,
        )
        self._action_status.pack(side=tk.BOTTOM, fill=tk.X)

        # Прокручиваемая область с углами и скоростями
        canvas = tk.Canvas(self.root, highlightthickness=0)
        vsb = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        def _wheel(event: tk.Event) -> None:
            if getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            elif getattr(event, "delta", 0):
                d = event.delta
                steps = int(-d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1)
                canvas.yview_scroll(steps, "units")

        canvas.bind_all("<MouseWheel>", _wheel)
        canvas.bind_all("<Button-4>", _wheel)
        canvas.bind_all("<Button-5>", _wheel)

        self.listener.wait_for_ready()

        for title, joint_ids in GROUPS:
            lf = ttk.LabelFrame(inner, text=title, padding=8)
            lf.pack(fill=tk.X, padx=4, pady=6)
            for jid in joint_ids:
                self._add_joint_row(lf, jid)

        self._init_from_state()
        self._startup_pose_deg = dict(self._snapshot_all_joints_deg())
        self._update_status()
        self._refresh_sequence_ui()

        self._worker = threading.Thread(target=self._publish_loop, daemon=True)
        self._worker.start()

    def _add_joint_row(self, parent: ttk.Frame, joint_id: int) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=_human_label(joint_id), width=20, anchor=tk.W).pack(
            side=tk.LEFT, padx=(0, 6)
        )

        ang_fr = ttk.Frame(row)
        ang_fr.pack(side=tk.LEFT, padx=(0, 10))
        btn_dec = ttk.Button(ang_fr, text="▼", width=3)
        btn_dec.pack(side=tk.LEFT)
        btn_dec.bind(
            "<ButtonPress-1>",
            lambda _e, j=joint_id: self._on_angle_btn_press(j, -1),
        )
        btn_dec.bind("<ButtonRelease-1>", lambda _e: self._on_angle_btn_release())
        ent = ttk.Entry(ang_fr, width=11, justify=tk.CENTER)
        ent.pack(side=tk.LEFT, padx=3)
        btn_inc = ttk.Button(ang_fr, text="▲", width=3)
        btn_inc.pack(side=tk.LEFT)
        btn_inc.bind(
            "<ButtonPress-1>",
            lambda _e, j=joint_id: self._on_angle_btn_press(j, 1),
        )
        btn_inc.bind("<ButtonRelease-1>", lambda _e: self._on_angle_btn_release())
        self._angle_entries[joint_id] = ent
        ent.bind(
            "<Return>",
            lambda _e, j=joint_id: self._on_angle_entry_commit(j),
        )
        ent.bind(
            "<FocusOut>",
            lambda _e, j=joint_id: self._on_angle_entry_commit(j),
        )

        spd = ttk.Entry(row, width=9)
        spd.pack(side=tk.LEFT, padx=(0, 4))
        self._speed_entries[joint_id] = spd
        spd.bind(
            "<Return>",
            lambda _e, j=joint_id: self._on_speed_entry_commit(j),
        )
        spd.bind(
            "<FocusOut>",
            lambda _e, j=joint_id: self._on_speed_entry_commit(j),
        )
        ttk.Label(row, text="рад/с", width=6).pack(side=tk.LEFT)

    def _on_angle_btn_press(self, joint_id: int, direction: int) -> None:
        """Один шаг сразу; при удержании — повтор с ускорением после ANGLE_HOLD_FAST_AFTER_MS."""
        self._on_angle_btn_release()
        self._angle_hold_held = True
        self._angle_hold_joint = joint_id
        self._angle_hold_direction = direction
        self._angle_hold_start = time.monotonic()
        self._bump_angle_deg(joint_id, direction * SCALE_RESOLUTION_DEG)
        self._angle_hold_after_id = self.root.after(
            ANGLE_HOLD_SLOW_REPEAT_MS, self._angle_hold_step
        )

    def _on_angle_btn_release(self) -> None:
        self._angle_hold_held = False
        aid = self._angle_hold_after_id
        self._angle_hold_after_id = None
        if aid is not None:
            try:
                self.root.after_cancel(aid)
            except (tk.TclError, ValueError):
                pass

    def _angle_hold_step(self) -> None:
        if not self._angle_hold_held:
            return
        self._angle_hold_after_id = None
        jid = self._angle_hold_joint
        direction = self._angle_hold_direction
        elapsed_ms = (time.monotonic() - self._angle_hold_start) * 1000.0
        if elapsed_ms < float(ANGLE_HOLD_FAST_AFTER_MS):
            step = SCALE_RESOLUTION_DEG
            delay_ms = ANGLE_HOLD_SLOW_REPEAT_MS
        else:
            step = SCALE_RESOLUTION_DEG * ANGLE_HOLD_FAST_STEP_MULT
            delay_ms = ANGLE_HOLD_FAST_REPEAT_MS
        self._bump_angle_deg(jid, direction * step)
        if self._angle_hold_held:
            self._angle_hold_after_id = self.root.after(delay_ms, self._angle_hold_step)

    def _bump_angle_deg(self, joint_id: int, delta: float) -> None:
        if self._suppress_angle_callback:
            return
        with self._lock:
            cur = float(self._targets.get(joint_id, 0.0))
        new_deg = _clamp_deg(joint_id, cur + delta)
        self._set_joint_angle_deg(joint_id, new_deg, from_user=True)

    def _set_joint_angle_deg(
        self, joint_id: int, deg: float, *, from_user: bool
    ) -> None:
        deg = _clamp_deg(joint_id, deg)
        self._suppress_angle_callback = True
        try:
            e = self._angle_entries[joint_id]
            e.delete(0, tk.END)
            e.insert(0, _format_deg_str(deg))
            self._targets[joint_id] = deg
            if from_user:
                with self._lock:
                    self._active_joints.add(joint_id)
        finally:
            self._suppress_angle_callback = False
        if from_user:
            self.root.after(0, self._update_status)

    def _on_angle_entry_commit(self, joint_id: int) -> None:
        if self._suppress_angle_callback:
            return
        raw = self._angle_entries[joint_id].get().strip()
        if raw == "":
            with self._lock:
                fallback = float(self._targets.get(joint_id, 0.0))
            self._set_joint_angle_deg(joint_id, fallback, from_user=False)
            return
        try:
            val = float(raw.replace(",", "."))
        except ValueError:
            with self._lock:
                fallback = float(self._targets.get(joint_id, 0.0))
            self._set_joint_angle_deg(joint_id, fallback, from_user=False)
            return
        self._set_joint_angle_deg(joint_id, val, from_user=True)

    def _on_speed_entry_commit(self, joint_id: int) -> None:
        raw = self._speed_entries[joint_id].get().strip()
        if raw == "":
            return
        try:
            val = float(raw.replace(",", "."))
        except ValueError:
            self._speed_entries[joint_id].delete(0, tk.END)
            return
        v = _clamp_speed_rad(joint_id, val)
        self._speed_entries[joint_id].delete(0, tk.END)
        self._speed_entries[joint_id].insert(0, _format_speed_str(v))

    def _apply_global_speed(self) -> None:
        s = self._global_speed_var.get().strip()
        if not s:
            self._action_status.configure(
                text="Введите число в поле «Скорость для всех» или оставьте пустым."
            )
            return
        try:
            val = float(s.replace(",", "."))
        except ValueError:
            self._action_status.configure(text="Некорректное число скорости.")
            return
        val = max(0.0, val)
        for jid in JointController.JOINT_MAP:
            v = min(val, float(get_limit(jid)["max_vel"]))
            e = self._speed_entries[jid]
            e.delete(0, tk.END)
            e.insert(0, _format_speed_str(v))
        self._action_status.configure(text="Скорости применены ко всем суставам (с учётом max_vel).")

    def _collect_speed_overrides(self) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for jid in JointController.JOINT_MAP:
            raw = self._speed_entries[jid].get().strip()
            if not raw:
                continue
            try:
                v = float(raw.replace(",", "."))
            except ValueError:
                continue
            out[jid] = _clamp_speed_rad(jid, v)
        return out

    def _init_from_state(self) -> None:
        self._suppress_angle_callback = True
        try:
            for jid in JointController.JOINT_MAP:
                q = self.listener.get_joint_pos(jid)
                if q is None:
                    q = 0.0
                deg = _clamp_deg(jid, rad2deg(q))
                e = self._angle_entries[jid]
                e.delete(0, tk.END)
                e.insert(0, _format_deg_str(deg))
                self._targets[jid] = deg
        finally:
            self._suppress_angle_callback = False

    def _update_status(self) -> None:
        with self._lock:
            n = len(self._active_joints)
        if n == 0:
            self._status.configure(
                text="DDS: только приём — в симулятор команды не идут (измените угол ↑/↓ или ввод)."
            )
        else:
            self._status.configure(
                text=f"DDS: PD на {n} сустав(ах); остальные пассивны."
            )

    def _sync_and_release(self) -> None:
        """Перечитать углы из listener, снять захват, один раз отдать полностью пассивный LowCmd."""
        with self._lock:
            self._active_joints.clear()
        self._suppress_angle_callback = True
        try:
            for jid in JointController.JOINT_MAP:
                q = self.listener.get_joint_pos(jid)
                if q is None:
                    q = 0.0
                deg = _clamp_deg(jid, rad2deg(q))
                e = self._angle_entries[jid]
                e.delete(0, tk.END)
                e.insert(0, _format_deg_str(deg))
                self._targets[jid] = deg
        finally:
            self._suppress_angle_callback = False
        self.ctrl.set_all_motors_passive(NUM_MOTOR_SLOTS)
        self.ctrl.publish()
        self._update_status()

    def _publish_loop(self) -> None:
        period = 1.0 / PUBLISH_HZ
        while not self._stop.is_set():
            with self._lock:
                active = frozenset(self._active_joints)
                snapshot = {j: self._targets[j] for j in active}
            if not active:
                time.sleep(period)
                continue
            t0 = time.perf_counter()
            for jid in sorted(active):
                self.ctrl.set_joint_deg(jid, snapshot[jid])
            self.ctrl.publish()
            elapsed = time.perf_counter() - t0
            sleep_for = period - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            elif self._stop.wait(0):
                break

    def _snapshot_all_joints_deg(self) -> Dict[int, float]:
        """Полный снимок углов в градусах (с clamp по лимитам)."""
        out: Dict[int, float] = {}
        for jid in JointController.JOINT_MAP:
            v = float(self._targets[jid])
            out[jid] = _clamp_deg(jid, v)
        return out

    def _refresh_sequence_ui(self) -> None:
        n = len(self._current_sequence)
        if n == 0:
            self._sequence_label.configure(text="Sequence: (empty)")
        else:
            labels = " ".join(f"[{i + 1}]" for i in range(n))
            self._sequence_label.configure(text=f"Sequence: {labels}")
        seq_state = tk.NORMAL if n < MAX_KEYFRAMES else tk.DISABLED
        self._btn_add_keyframe.configure(state=seq_state)
        self._btn_add_from_library.configure(state=seq_state)

    def _apply_pose_deg_to_ui(self, pose_deg: Dict[int, float]) -> None:
        """Выставить поля углов и targets из полного кадра (градусы).

        Все суставы помечаются активными для PD, чтобы симулятор/робот принял позу целиком
        (иначе команды шли бы только по ранее «тронутым» суставам).
        """
        self._suppress_angle_callback = True
        try:
            for jid in JointController.JOINT_MAP:
                v = _clamp_deg(jid, float(pose_deg.get(jid, 0.0)))
                e = self._angle_entries[jid]
                e.delete(0, tk.END)
                e.insert(0, _format_deg_str(v))
                self._targets[jid] = v
        finally:
            self._suppress_angle_callback = False
        with self._lock:
            self._active_joints.clear()
            self._active_joints.update(JointController.JOINT_MAP.keys())
        self.root.after(0, self._update_status)

    def _open_pose_library(self) -> None:
        with self._lock:
            if len(self._current_sequence) >= MAX_KEYFRAMES:
                self._action_status.configure(
                    text="Последовательность заполнена (макс. 3 кадра)."
                )
                return
        entries = discover_basic_action_poses()
        if not entries:
            messagebox.showinfo(
                "Библиотека поз",
                "Не найдено ни одной позы в mid_level_motions/basic_actions/*/pose.json.",
                parent=self.root,
            )
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Выбор позы из basic_actions")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("520x360")

        ttk.Label(
            dlg,
            text="Выберите позу и нажмите «Добавить в последовательность»:",
        ).pack(anchor=tk.W, padx=8, pady=(8, 4))

        list_fr = ttk.Frame(dlg)
        list_fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        sb = ttk.Scrollbar(list_fr)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(list_fr, height=14, yscrollcommand=sb.set, exportselection=False)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=lb.yview)
        for label, _p, _idx in entries:
            lb.insert(tk.END, label)
        if entries:
            lb.selection_set(0)

        err_lbl = ttk.Label(dlg, text="", foreground="#a00")
        err_lbl.pack(anchor=tk.W, padx=8, pady=(0, 4))

        def add_selected() -> None:
            sel = lb.curselection()
            if not sel:
                err_lbl.configure(text="Выберите строку в списке.")
                return
            i = int(sel[0])
            _label, path, frame_idx = entries[i]
            with self._lock:
                if len(self._current_sequence) >= MAX_KEYFRAMES:
                    err_lbl.configure(text="Последовательность уже заполнена.")
                    return
            try:
                pose = load_pose_frame_deg(path, frame_idx)
            except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
                err_lbl.configure(text=str(e))
                return
            with self._lock:
                self._current_sequence.append(dict(pose))
            self._refresh_sequence_ui()
            self._apply_pose_deg_to_ui(pose)
            dlg.destroy()

        btn_row = ttk.Frame(dlg, padding=(8, 0, 8, 8))
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(
            btn_row, text="Добавить в последовательность", command=add_selected
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Отмена", command=dlg.destroy).pack(side=tk.LEFT)

        lb.bind("<Double-Button-1>", lambda _e: add_selected())

    def _add_keyframe(self) -> None:
        with self._lock:
            if len(self._current_sequence) >= MAX_KEYFRAMES:
                return
            self._current_sequence.append(self._snapshot_all_joints_deg())
        self._refresh_sequence_ui()

    def _clear_sequence(self) -> None:
        self._current_sequence.clear()
        self._refresh_sequence_ui()

    def _save_pose(self) -> None:
        with self._lock:
            pose = {jid: round(self._targets[jid], 4) for jid in sorted(self._targets)}
        print("[Pose Studio] Current pose (degrees, joint_id -> angle):")
        print(json.dumps(pose, indent=2, ensure_ascii=False))

    def _save_action(self) -> None:
        name = self._action_name_var.get().strip()
        try:
            with self._lock:
                if self._current_sequence:
                    frames = [dict(f) for f in self._current_sequence]
                else:
                    frames = [self._snapshot_all_joints_deg()]
            spd = self._collect_speed_overrides()
            _, execute_path = action_exporter.save_action(
                name, frames, motor_speed_overrides=spd if spd else None
            )
        except ValueError as e:
            self._action_status.configure(text=str(e))
            return
        except OSError as e:
            self._action_status.configure(text=f"Ошибка записи: {e}")
            return

        rel = os.path.relpath(execute_path, _root_dir)
        self._last_execute_path = os.path.abspath(execute_path)
        self._btn_play.configure(state=tk.NORMAL)
        self._action_status.configure(
            text=(
                f'Действие "{name}" сохранено. '
                f"Кнопка ▶ запускает execute.py. Терминал: python3 {rel}"
            )
        )

    def _play_last_action(self) -> None:
        path = self._last_execute_path
        if not path or not os.path.isfile(path):
            messagebox.showwarning(
                "Play",
                "Нет сохранённого execute.py. Сначала нажмите Save Action.",
                parent=self.root,
            )
            return
        cwd = os.path.dirname(path)
        try:
            subprocess.Popen(
                [sys.executable, path],
                cwd=cwd,
                start_new_session=True,
            )
            self._action_status.configure(
                text=f"Запущено: {path}",
            )
        except OSError as e:
            messagebox.showerror(
                "Play",
                f"Не удалось запустить действие:\n{e}",
                parent=self.root,
            )

    def _reset_pose(self) -> None:
        with self._lock:
            if self._current_sequence:
                pose = dict(self._current_sequence[0])
                msg = "Сброс к первому keyframe."
            else:
                pose = dict(self._startup_pose_deg)
                msg = "Сброс к позе при запуске Pose Studio."
        self._apply_pose_deg_to_ui(pose)
        self._action_status.configure(text=msg)

    def _on_close(self) -> None:
        self._on_angle_btn_release()
        self._stop.set()
        self._worker.join(timeout=2.0)
        try:
            self.ctrl.set_all_motors_passive(NUM_MOTOR_SLOTS)
            self.ctrl.publish()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = PoseStudioApp()
    app.run()


if __name__ == "__main__":
    main()
