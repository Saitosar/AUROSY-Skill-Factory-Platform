# Angle Mapping (Degrees <-> Radians)

Use this mapping when designing motions in degrees but sending commands in radians.

## Quick conversion

- `rad = deg * pi / 180`
- `deg = rad * 180 / pi`

Utility functions are in:
- `core_control/utils/conversions.py`

## Common values

| Degrees | Radians |
|---|---|
| 5 | 0.0873 |
| 10 | 0.1745 |
| 15 | 0.2618 |
| 20 | 0.3491 |
| 30 | 0.5236 |
| 45 | 0.7854 |
| 60 | 1.0472 |
| 75 | 1.3090 |
| 90 | 1.5708 |

## Usage examples

```python
from core_control.utils.conversions import deg2rad
from core_control.low_level_motions.atomic_move import AtomicMove

node = AtomicMove()
node.safe_move(16, deg2rad(30))      # explicit conversion
node.safe_move_deg(16, 30)           # convenience method
```

```python
from core_control.joint_controller import JointController

ctrl = JointController()
ctrl.set_joint_deg(16, 30)
ctrl.publish()
```

## Note about signs

Left and right symmetric joints can have opposite sign conventions.
Always verify final pose with `Joint` values in MuJoCo UI (not `Control`).

