"""
Tkinter GUI: ноды, timeline, сохранение в high_level_motions/{name}/scenario.json.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOLS_DIR = os.path.dirname(_PKG_DIR)
_ROOT_DIR = os.path.dirname(_TOOLS_DIR)

if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from skill_generator import validate_skill_name

from scenario_studio.runner import (
    SCENARIO_VERSION,
    DiscoveredAction,
    discover_actions,
    estimate_node_duration_sec,
    high_level_motions_root,
    run_scenario,
    scenario_total_estimate_sec,
)

RUN_PY_TEMPLATE = '''"""
Запуск сценария (сгенерировано Scenario Studio).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
TOOLS = os.path.join(ROOT, "tools")
for p in (ROOT, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

from scenario_studio.runner import run_scenario_from_path

if __name__ == "__main__":
    run_scenario_from_path(os.path.join(HERE, "scenario.json"))
'''

TARGET_SEC = 30.0
WARN_LOW = 25.0
WARN_HIGH = 35.0


def _default_node(subdir: str, action_name: str) -> Dict[str, Any]:
    return {
        "subdir": subdir,
        "action_name": action_name,
        "speed": 0.5,
        "repeat": 1,
    }


class ScenarioStudioApp:
    def __init__(self) -> None:
        self._nodes: List[Dict[str, Any]] = []
        self._discovered: List[DiscoveredAction] = []
        self._current_scenario_path: Optional[str] = None
        self._play_thread: Optional[threading.Thread] = None
        self._stop_play = threading.Event()

        self.root = tk.Tk()
        self.root.title("SAI Motion Builder — Scenario Studio — G1")
        self.root.geometry("960x720")
        self.root.minsize(720, 520)

        self._name_var = tk.StringVar(value="my_scenario")
        self._speed_var = tk.StringVar(value="0.5")
        self._repeat_var = tk.StringVar(value="1")

        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Имя сценария (папка в high_level_motions):").pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Entry(top, textvariable=self._name_var, width=28).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Button(top, text="Сохранить сценарий", command=self._save_scenario).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(top, text="Загрузить…", command=self._load_scenario_dialog).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(top, text="▶ Play", command=self._play).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(top, text="■ Stop", command=self._stop).pack(side=tk.LEFT)

        row2 = ttk.Frame(self.root, padding=(8, 0, 8, 4))
        row2.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(row2, text="Добавить движение…", command=self._open_library).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(row2, text="Удалить", command=self._remove_selected).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(row2, text="Дублировать", command=self._duplicate_selected).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(row2, text="Вверх", command=lambda: self._move_selected(-1)).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(row2, text="Вниз", command=lambda: self._move_selected(1)).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(row2, text="speed:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row2, textvariable=self._speed_var, width=8).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Label(row2, text="repeat:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(row2, textvariable=self._repeat_var, width=6).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(row2, text="Применить к выбранной ноде", command=self._apply_edit).pack(
            side=tk.LEFT
        )

        mid = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        left_fr = ttk.Frame(mid, padding=4)
        mid.add(left_fr, weight=3)
        ttk.Label(left_fr, text="Ноды (порядок выполнения)").pack(anchor=tk.W)
        tree_fr = ttk.Frame(left_fr)
        tree_fr.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(tree_fr)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree = ttk.Treeview(
            tree_fr,
            columns=("move", "speed", "repeat"),
            show="headings",
            yscrollcommand=sb.set,
            height=14,
            selectmode=tk.BROWSE,
        )
        sb.config(command=self._tree.yview)
        self._tree.heading("move", text="Движение")
        self._tree.heading("speed", text="speed")
        self._tree.heading("repeat", text="repeat")
        self._tree.column("move", width=360)
        self._tree.column("speed", width=70)
        self._tree.column("repeat", width=60)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", lambda _e: self._open_library())

        right_fr = ttk.Frame(mid, padding=4)
        mid.add(right_fr, weight=2)
        ttk.Label(right_fr, text="Timeline (оценка длительности)").pack(anchor=tk.W)
        self._tl_canvas = tk.Canvas(
            right_fr,
            highlightthickness=1,
            highlightbackground="#ccc",
            background="#fafafa",
            width=320,
        )
        self._tl_canvas.pack(fill=tk.BOTH, expand=True)
        self._tl_canvas.bind("<Configure>", lambda _e: self._draw_timeline())

        self._status = ttk.Label(
            self.root,
            text="",
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=6,
            wraplength=900,
        )
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

        self._refresh_discovered()
        self._refresh_tree()
        self._update_status_bar()

    def _refresh_discovered(self) -> None:
        self._discovered = discover_actions()

    def _build_scenario_dict(self) -> Dict[str, Any]:
        return {
            "version": SCENARIO_VERSION,
            "title": self._name_var.get().strip() or "untitled",
            "nodes": [dict(n) for n in self._nodes],
        }

    def _refresh_tree(self) -> None:
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        for i, n in enumerate(self._nodes):
            label = f"{n['subdir']}/{n['action_name']}"
            self._tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(label, f"{n['speed']:.4g}", str(n["repeat"])),
            )
        self._draw_timeline()
        self._update_status_bar()

    def _selected_index(self) -> Optional[int]:
        sel = self._tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def _on_tree_select(self, _evt: Any = None) -> None:
        idx = self._selected_index()
        if idx is None or idx < 0 or idx >= len(self._nodes):
            return
        n = self._nodes[idx]
        self._speed_var.set(str(n["speed"]))
        self._repeat_var.set(str(n["repeat"]))

    def _apply_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Нода", "Выберите строку в списке.", parent=self.root)
            return
        try:
            sp = float(self._speed_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("speed", "Некорректное число speed.", parent=self.root)
            return
        try:
            rep = int(self._repeat_var.get().strip())
        except ValueError:
            messagebox.showerror("repeat", "Некорректное целое repeat.", parent=self.root)
            return
        if sp <= 0:
            messagebox.showerror("speed", "speed должен быть > 0.", parent=self.root)
            return
        if rep < 1:
            messagebox.showerror("repeat", "repeat ≥ 1.", parent=self.root)
            return
        self._nodes[idx]["speed"] = sp
        self._nodes[idx]["repeat"] = rep
        self._refresh_tree()
        self._tree.selection_set(str(idx))

    def _remove_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        del self._nodes[idx]
        self._refresh_tree()

    def _duplicate_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        copy_n = dict(self._nodes[idx])
        self._nodes.insert(idx + 1, copy_n)
        self._refresh_tree()
        self._tree.selection_set(str(idx + 1))

    def _move_selected(self, delta: int) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        j = idx + delta
        if j < 0 or j >= len(self._nodes):
            return
        self._nodes[idx], self._nodes[j] = self._nodes[j], self._nodes[idx]
        self._refresh_tree()
        self._tree.selection_set(str(j))

    def _disc_map(self) -> Dict[str, DiscoveredAction]:
        return {d.label: d for d in self._discovered}

    def _draw_timeline(self) -> None:
        self._tl_canvas.delete("all")
        w = max(self._tl_canvas.winfo_width(), 200)
        h = max(self._tl_canvas.winfo_height(), 120)
        margin_l, margin_r, margin_y = 8, 8, 4
        row_h = 22
        disc = self._disc_map()
        total = scenario_total_estimate_sec(self._nodes)
        if total <= 0:
            total = 1.0
        inner_w = w - margin_l - margin_r

        self._tl_canvas.create_text(
            margin_l,
            margin_y,
            anchor=tk.NW,
            text=f"Σ ≈ {total:.1f} s (цель ~{TARGET_SEC:.0f} s)",
            fill="#333",
        )

        y = margin_y + 22
        for i, node in enumerate(self._nodes):
            key = f"{node['subdir']}/{node['action_name']}"
            d = disc.get(key)
            kf = d.keyframe_count if d else 1
            est = estimate_node_duration_sec(
                kf, float(node["speed"]), int(node["repeat"])
            )
            frac = min(1.0, est / total)
            bar_w = max(6, int(frac * inner_w))
            self._tl_canvas.create_rectangle(
                margin_l,
                y,
                margin_l + bar_w,
                y + row_h - 4,
                fill="#6a9fd4",
                outline="#4a7fb4",
            )
            self._tl_canvas.create_text(
                margin_l + bar_w + 6,
                y + 2,
                anchor=tk.NW,
                text=f"{i + 1}. {key} (~{est:.1f}s)",
                fill="#222",
            )
            y += row_h
            if y > h - 10:
                break

    def _update_status_bar(self) -> None:
        total = scenario_total_estimate_sec(self._nodes)
        extra = ""
        if total > 0:
            if total < WARN_LOW:
                extra = f" — короче цели (~{TARGET_SEC:.0f} с)"
            elif total > WARN_HIGH:
                extra = f" — длиннее цели (~{TARGET_SEC:.0f} с)"
        path = self._current_scenario_path or "(не сохранён)"
        self._status.configure(
            text=f"Файл: {path}  |  Оценка Σ ≈ {total:.1f} с{extra}"
        )

    def _open_library(self) -> None:
        self._refresh_discovered()
        if not self._discovered:
            messagebox.showinfo(
                "Библиотека",
                "Не найдено движений с execute.py в mid_level_motions.",
                parent=self.root,
            )
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Добавить движение")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("560x400")

        ttk.Label(
            dlg,
            text="Выберите движение (basic_actions / complex_actions):",
        ).pack(anchor=tk.W, padx=8, pady=(8, 4))

        list_fr = ttk.Frame(dlg)
        list_fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        sb = ttk.Scrollbar(list_fr)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(list_fr, height=16, yscrollcommand=sb.set, exportselection=False)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=lb.yview)
        for d in self._discovered:
            lb.insert(tk.END, d.label)
        if self._discovered:
            lb.selection_set(0)

        err = ttk.Label(dlg, text="", foreground="#a00")
        err.pack(anchor=tk.W, padx=8)

        def add_selected() -> None:
            sel = lb.curselection()
            if not sel:
                err.configure(text="Выберите строку.")
                return
            d = self._discovered[int(sel[0])]
            self._nodes.append(_default_node(d.subdir, d.action_name))
            self._refresh_tree()
            self._tree.selection_set(str(len(self._nodes) - 1))
            dlg.destroy()

        br = ttk.Frame(dlg, padding=8)
        br.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(br, text="Добавить", command=add_selected).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(br, text="Отмена", command=dlg.destroy).pack(side=tk.LEFT)
        lb.bind("<Double-Button-1>", lambda _e: add_selected())

    def _scenario_dir_for_name(self, name: str) -> str:
        return os.path.join(high_level_motions_root(), name)

    def _save_scenario(self) -> None:
        raw_name = self._name_var.get().strip()
        ok, res = validate_skill_name(raw_name)
        if not ok:
            messagebox.showerror("Имя сценария", res, parent=self.root)
            return
        name = res
        data = self._build_scenario_dict()
        scen_dir = self._scenario_dir_for_name(name)
        os.makedirs(scen_dir, exist_ok=True)
        scen_path = os.path.join(scen_dir, "scenario.json")
        try:
            with open(scen_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            run_path = os.path.join(scen_dir, "run.py")
            with open(run_path, "w", encoding="utf-8") as f:
                f.write(RUN_PY_TEMPLATE)
        except OSError as e:
            messagebox.showerror("Сохранение", str(e), parent=self.root)
            return
        self._current_scenario_path = scen_path
        self._update_status_bar()
        rel = os.path.relpath(scen_path, _ROOT_DIR)
        messagebox.showinfo(
            "Сохранено",
            f"scenario.json и run.py записаны:\n{rel}",
            parent=self.root,
        )

    def _load_scenario_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Загрузить scenario.json",
            initialdir=high_level_motions_root(),
            filetypes=[("JSON", "*.json"), ("Все", "*.*")],
        )
        if not path:
            return
        self._load_scenario_path(path)

    def _load_scenario_path(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("Загрузка", str(e), parent=self.root)
            return
        if int(data.get("version", -1)) != SCENARIO_VERSION:
            messagebox.showerror(
                "Загрузка",
                f"Ожидался version={SCENARIO_VERSION}.",
                parent=self.root,
            )
            return
        nodes_in = data.get("nodes")
        if not isinstance(nodes_in, list):
            messagebox.showerror("Загрузка", "Нет списка nodes.", parent=self.root)
            return
        self._nodes = []
        for item in nodes_in:
            if not isinstance(item, dict):
                continue
            sub = item.get("subdir")
            an = item.get("action_name")
            if sub not in ("basic_actions", "complex_actions") or not an:
                continue
            self._nodes.append(
                {
                    "subdir": sub,
                    "action_name": str(an),
                    "speed": float(item.get("speed", 0.5)),
                    "repeat": max(1, int(item.get("repeat", 1))),
                }
            )
        title = data.get("title")
        if isinstance(title, str) and title.strip():
            self._name_var.set(title.strip())
        else:
            self._name_var.set(os.path.basename(os.path.dirname(path)))
        self._current_scenario_path = path
        self._refresh_tree()
        self._update_status_bar()

    def _play(self) -> None:
        if self._play_thread is not None and self._play_thread.is_alive():
            messagebox.showinfo("Play", "Уже воспроизводится.", parent=self.root)
            return
        if not self._nodes:
            messagebox.showinfo("Play", "Добавьте ноды.", parent=self.root)
            return
        self._stop_play.clear()
        data = self._build_scenario_dict()

        def on_step(ni: int, r: int, rt: int, label: str) -> None:
            msg = f"Play: нода {ni + 1} «{label}» {r}/{rt}"
            self.root.after(0, lambda m=msg: self._status.configure(text=m))

        def worker() -> None:
            try:
                run_scenario(
                    data,
                    stop_event=self._stop_play,
                    on_step=on_step,
                    hold_last_node=False,
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Play", str(e), parent=self.root
                    ),
                )
            finally:
                self.root.after(0, self._play_finished)

        self._play_thread = threading.Thread(target=worker, daemon=True)
        self._play_thread.start()
        self._status.configure(text="Play…")

    def _stop(self) -> None:
        self._stop_play.set()
        self._status.configure(text="Останов запрошен (между нодами).")

    def _play_finished(self) -> None:
        self._play_thread = None
        self._update_status_bar()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ScenarioStudioApp().run()


if __name__ == "__main__":
    main()
