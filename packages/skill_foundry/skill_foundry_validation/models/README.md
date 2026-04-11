# Robot description assets

## `g1_description/` (isri-aist/g1_description)

Vendored snapshot of [isri-aist/g1_description](https://github.com/isri-aist/g1_description) (BSD-3-Clause):

- `urdf/g1_29dof.urdf` — Pinocchio / ROS
- `meshes/` — STL assets referenced by the URDF
- `mjcf/` — optional MuJoCo scenes from upstream

Used for optional Pinocchio RNEA torque checks (`pin.buildModelFromUrdf` with `package://g1_description/` resolved via `paths.default_package_dir_for_urdf()`).

Self-collision and playback validation use the project’s **Unitree** `unitree_mujoco` MJCF (`scene_29dof.xml`), not necessarily this MJCF subtree.
