# Running it

Requires ROS 2 Jazzy and Gazebo Harmonic on Ubuntu 24.04. The node itself needs `rclpy`,
`geometry_msgs` and `vision_msgs`, all of which come with a standard ROS 2 desktop install, plus the
`gz.transport13` Python bindings if you want the event-driven source rather than the CLI fallback.

## Terminal 1 — the simulation

```bash
source /opt/ros/jazzy/setup.bash
gz sim -s -r -v 3 <path-to>/worlds/ewaste_room.sdf
```

`-r` matters. The node only publishes while the simulation is stepping; the pose stream goes quiet the
moment it is paused, and after `gt_timeout_s` the node stops publishing rather than repeating a stale
position.

Headless (`-s`) is fine, and the arm is not needed — see finding 3 in
[04-findings.md](04-findings.md) for why running both at once does not currently work.

## Terminal 2 — the node

```bash
source /opt/ros/jazzy/setup.bash
python3 perception/oracle_detector.py --ros-args -p target_model:=battery_1
```

### Parameters

| Parameter | Default | What it does |
|---|---|---|
| `world` | `ewaste_room` | which world's pose stream to read |
| `target_model` | `battery_1` | the entity to publish detections for |
| `class_id` | `battery` | the class name on the `Detection3DArray` hypothesis |
| `frame_id` | `world` | the frame stamped on every published message |
| `publish_rate_hz` | `2.0` | output rate; also the poll period for the CLI source |
| `source` | `auto` | `auto` \| `python` \| `cli` — `auto` tries the `gz.transport13` bindings and falls back to polling `gz topic -e` |
| `add_noise` | `false` | opt-in Gaussian jitter on the published position |
| `noise_stddev_m` | `0.01` | the standard deviation of that jitter, in metres |
| `gt_timeout_s` | `3.0` | stop publishing if ground truth goes stale rather than repeating it |

## Verification

```bash
bash perception/oracle_verify.sh
```

Nine checks against the live simulation: topic presence, node start, all three topics advertised, one
payload from each, rate measured over ~10 s, a `set_pose` teleport with the published pose confirmed to
follow it, and a restore. Output is written to `/mnt/claude_share/oracle_verify_output.txt` if that mount
exists, otherwise to the home directory. A captured run is in
[`results/`](../results/oracle_verify_output_2026-09-13.txt).

> The script does not use `set -u`. ROS 2's `setup.bash` is not safe under `nounset` and will abort the
> script on sourcing.

## Camera pipeline

```bash
bash perception/camera_evidence.sh sdf     # the sensors plugin and camera resolutions in the world file
bash perception/camera_evidence.sh cam     # bridge both cameras, confirm 1280x960 in ROS 2, measure rate
bash perception/camera_evidence.sh crash   # reproduce the camera + arm crash
```

The `cam` mode reads image topics with best-effort QoS, which sensor streams use; the default reliable
QoS will simply never receive a frame.

## Unit tests

No ROS, no Gazebo, no simulation:

```bash
python -m pytest tests -q
```
