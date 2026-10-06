# Robot Perception Oracle

**A ground-truth perception node for a robotic e-waste disassembly simulation — built to unblock two downstream roles whose work could not start until something published a battery's position, and to serve as the reference the real computer-vision detector gets scored against.**

The robot arm could plan. The reachability checker could run. Neither could be tested, because the
perception stage in front of them did not exist yet: the vision model was still being trained, and the
placeholder in the repository published a position copied out of the world file — a constant, dressed as
a measurement.

This node replaces that constant with the simulator's own truth. It reads the real pose of a target
object out of Gazebo's internal transport stream and republishes it in the three message types the
downstream nodes already subscribe to, so the full pick-and-place loop can be exercised against a
physically true target months before the detector lands.

The first thing it did on being switched on was disprove a number every file in the project had been
built around.

---

## What it publishes

One ground truth in, three contracts out — because three different consumers had each settled on a
different message type, and discovering that is half of what this node is for.

| Topic | Type | Who subscribes |
|---|---|---|
| `/target_pose` | `geometry_msgs/PoseStamped` | the motion-planning node, which feeds it straight into a MoveIt Task Constructor pick task |
| `/detected_battery_position` | `geometry_msgs/Point` | the workspace reachability checker |
| `/detected_objects` | `vision_msgs/Detection3DArray` | the perception contract the vision model will eventually fill |

Published at 2 Hz in the `world` frame, with a confidence of `1.0` — certainty by construction, which is
exactly what makes it an oracle rather than a detector.

```bash
python3 perception/oracle_detector.py --ros-args -p target_model:=battery_1
```

Optional Gaussian jitter (`add_noise`, `noise_stddev_m`) lets a downstream node be tested against an
imperfect detector without waiting for a real one.

---

## Verified, not asserted

`perception/oracle_verify.sh` is a nine-step end-to-end check that runs against a live simulation: it
confirms the pose stream exists, starts the node, echoes a full payload from each of the three topics,
measures the publish rate, teleports the target with Gazebo's `set_pose` service, confirms the published
detection follows it, then puts it back. The full captured output is in
[`results/`](results/oracle_verify_output_2026-09-13.txt).

| Check | Result |
|---|---|
| Ground-truth source | `gz.transport13` Python bindings, event-driven |
| Entities visible in the pose stream | 29, all named |
| Publish rate over ~10 s | **2.000 Hz**, min 0.491 s / max 0.510 s, std dev ≤ 0.0041 s |
| Teleport to (0.00, 0.60) | published x = 6.4 × 10⁻¹⁹, y = 0.600 |
| Restore to (−0.15, 0.62) | published x = −0.150, y = 0.620 |

Tracking is exact in x and y to floating-point precision. The error budget it has to stay inside is the
motion planner's approach tolerance, 0.02 m.

---

## Three things it found

### 🔻 The objects were not where every file in the project said they were

The world file declares the batteries at **z = 0.81 m**, on the table top. The simulation reports
**z = 0.050 m** — the floor. Teleporting one back up to 0.81 m and watching it settle takes about two
seconds. They fall through the table at startup, because the table-top link has a visual but no
`<collision>` element.

Every script, document and conversation in the project had carried 0.81 m since July, because that is
what the world file said and nothing had ever measured it. The placeholder detector could not have
caught this: it reported the world-file value by construction. **A coordinate that has only ever been
read out of a file is unverified until something measures it** — that is the whole argument for building
the oracle before building the detector.

### 🔻 The obvious shortcut silently destroys the data

The first attempt used the standard `ros_gz_bridge` to convert the pose stream
(`gz.msgs.Pose_V`) into `tf2_msgs/TFMessage`. It runs, it publishes, it looks correct — and every
transform arrives with an empty name, because the bridge fills `child_frame_id` from a header field the
scene broadcaster never sets. With 29 unnamed entities there is no way to tell which one is the target.
The node reads the Gazebo transport stream directly instead, which keeps the names.

### 🔻 Adding the camera to the arm crashes the simulator

Launching the full scene with both the cameras and the robot arm aborts during rendering —
`Ogre::ItemIdentityException: scene node 'sun' already exists`, exit 134 — because two systems each
build their own render scene in one process. `perception/camera_evidence.sh crash` reproduces it in
under two minutes. Documented, escalated with three ranked options, and deliberately **not** fixed here:
it is a structural decision about how the simulation is composed, and that was not this role's call to
make.

---

## How it is tested

The parser that reads Gazebo's protobuf text output lives in its own module,
[`perception/pose_parsing.py`](perception/pose_parsing.py), with no dependency on ROS, Gazebo or a
running simulation — so it can be tested anywhere, including in CI where none of those are installed.

```bash
python -m pytest tests -q        # 25 passed
```

The suite exists because protobuf text output is **lossy by omission**: every field equal to its default
is simply not printed. An object sitting exactly on the X axis emits no `x:` line; an unrotated object
emits no `orientation` block at all. A parser that treats absent as *unknown* rather than as *zero*
drops the target, and the node publishes nothing while the simulation looks perfectly healthy. The tests
pin that behaviour down, along with field isolation between the 29 entities in a single message,
scientific-notation values (Gazebo reports a teleport to exactly 0 as `6.4e-19`), and a key not being
matched inside a longer one.

---

## Layout

```
perception/
  oracle_detector.py     the ROS 2 node: Gazebo ground truth -> three detection topics
  pose_parsing.py        protobuf-text parsing, dependency-free and unit tested
  oracle_verify.sh       nine-step end-to-end verification against a live simulation
  camera_evidence.sh     camera pipeline inspection and crash reproduction
tests/                   pytest suite over the parser
docs/
  01-why-an-oracle.md    what was blocked, and why ground truth was the unblock
  02-verification.md     the verification run in full, with evidence images
  03-coordinate-frames.md  frames, axes and message types confirmed across three roles
  04-findings.md         the three defects above, with reproduction steps
  05-running-it.md       how to run the node and the scripts
results/                 captured verification output
```

---

## Stack

ROS 2 Jazzy · Gazebo Harmonic 8.11.0 · `gz.transport13` Python bindings · `rclpy` ·
`vision_msgs` / `geometry_msgs` · MoveIt Task Constructor (downstream) · pytest · Ubuntu 24.04

## Licence

[MIT](LICENSE).
