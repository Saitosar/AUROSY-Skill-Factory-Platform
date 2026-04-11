"""
Scenario Studio — сборка сценариев из basic_actions / complex_actions.

Запуск из каталога unitree_sdk2_python:
  python tools/motion_scenario_studio.py
"""

import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_current_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from scenario_studio.app import main

if __name__ == "__main__":
    main()
