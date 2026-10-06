# Robot Perception Oracle

**A ground-truth perception node for a robotic e-waste disassembly simulation — built to unblock two
downstream roles whose work could not start until something published a battery's position, and to
serve as the reference the real computer-vision detector gets scored against.**

That node is the centrepiece, and this repository is the whole perception role it came out of: getting
the cameras to produce a frame at all, unblocking the roles behind perception before any vision model
existed, and then replacing a number the project had trusted for months with one that was measured.

Perception sits between the cameras and everything that drives the arm:

```
camera  ->  PERCEPTION  ->  target pose  ->  motion planning  ->  pick  ->  place
```

Three nodes were built, in order, each because the previous one ran out of road — the frame grabber,
the placeholder that unblocked the motion role, and the oracle that proved the placeholder's central
assumption wrong by 0.76 m. [01-the-perception-stage.md](docs/01-the-perception-stage.md) is the
shortest way in.

---

## 1. The cameras published nothing — and said nothing about it

No warning, no error, no partial output. The sensor was declared in the world file and appeared in the
scene.

It turned out to be **three unrelated faults stacked on top of each other**, each sufficient on its own
to stop any image reaching ROS 2 — a stale workspace overlay shadowing a package, a missing sensors
plugin (Gazebo falls back to its default plugin set *only* when a world declares no plugins at all, so
declaring three means declaring all of them), and no camera bridge node in the launch file at all.
Found by bisecting the pipeline and eliminating hypotheses one at a time, because with three faults
present any partial fix shows no improvement and tells you nothing.

Fixed and verified end to end at **1280 × 960**, which is the resolution the vision model's 640 × 640
input letterboxes into at exactly 0.5 scale with 80 px of whole-number padding — so a detection maps
back to full-resolution pixels with no rounding drift, and that drift would otherwise have propagated
straight into the 3D position the arm is driven to.

The pipeline turned out to run at **~1.5 Hz with over three seconds of jitter** — bursts at ~29 Hz
separated by long gaps, not a stream. The average alone would have hidden that completely.

→ [02-camera-pipeline.md](docs/02-camera-pipeline.md)

## 2. Unblocking the roles behind perception

The arm could plan and the reachability checker could run, but neither could be tested without
something publishing a target. `fake_detector.py` published plausible detections on `/detected_objects`
so arm-driving logic could be developed against the real message type — labelled **PLACEHOLDER STATUS**
in its own docstring, with randomised confidence so nothing downstream could mistake it for certainty,
and a comment forbidding guessed positions for the other objects.

Its one hard-coded coordinate came from the world file, because the world file was the only source
that existed. That coordinate is the subject of the next section.

## 3. Replacing the constant with a measurement

`oracle_detector.py` reads the **true** pose of the target out of the simulator's own transport stream
and republishes it in the three message types the downstream nodes already subscribe to:

| Topic | Type | Who subscribes |
|---|---|---|
| `/target_pose` | `geometry_msgs/PoseStamped` | the motion-planning node, straight into a MoveIt Task Constructor pick task |
| `/detected_battery_position` | `geometry_msgs/Point` | the workspace reachability checker |
| `/detected_objects` | `vision_msgs/Detection3DArray` | the perception contract the vision model will fill |

Three consumers, three different message types — because three roles had each made a locally sensible
choice, and finding that out is half of what this node is for.

```bash
python3 perception/oracle_detector.py --ros-args -p target_model:=battery_1
```

**Verified, not asserted.** A nine-step script runs against a live simulation: topic presence, node
start, all three contracts, one full payload from each, rate stability, then a `set_pose` teleport with
the published pose confirmed to follow it, and a restore.

| Check | Result |
|---|---|
| Publish rate over ~10 s | **2.000 Hz**, min 0.491 s / max 0.510 s, std dev ≤ 0.0041 s |
| Teleport to (0.00, 0.60) | published x = 6.4 × 10⁻¹⁹, y = 0.600 |
| Restore to (−0.15, 0.62) | published x = −0.150, y = 0.620 |

The teleport is the step that matters. Everything before it proves the node is publishing; only moving
the object proves it is publishing *the object's position* rather than a constant that happens to look
right. → [04-verification.md](docs/04-verification.md)

---

## What it found

**The batteries sat 0.76 m below where every file in the project said they were.** The world file
declares 0.81 m; the simulation reports 0.050 m. They fall through a table whose top has no collision
geometry. The placeholder could never have caught it — the file it copied from was the only thing it
could be checked against, and every script and hand-off note in the project had carried 0.81 m for
months for exactly the same reason.

**`ros_gz_bridge` silently discards every entity name.** Bridging the pose stream to `TFMessage` runs,
publishes at the right rate, and delivers 29 objects that are all called `''`. No error. The node reads
Gazebo transport directly instead.

**Cameras and the arm cannot share a process.** Seven configurations across two render engines and two
GL drivers, all failing the same way, with the working one isolated. Escalated with three options
ranked by risk rather than fixed — the fix was a structural decision about how the simulation is
composed, and that belonged to the role that owns the launch files.

Three of the four findings — counting the silent camera failure above — have the same shape: **a check
that passed for a reason unrelated to the thing being checked.** Including one of my own: I had cited a
ROS publisher count as proof the cameras were working, and `ros_gz_bridge` creates that publisher
whether or not a single frame ever arrives.

→ [06-findings.md](docs/06-findings.md)

One more, found while chasing a communication fault and well outside a perception role: the FastRTPS
transport under ROS 2 keeps inter-node messages in **shared memory with no process-level access
control**, and leaves stale segments behind after an unclean shutdown. Harmless in simulation; in a
deployed system it means any local process can read — or write — the messages driving physical
actuation. Documented and passed to the team, with the matching perception-side mitigation, a validator
in front of `/target_pose`, written down next to it.

→ [08-working-practices.md](docs/08-working-practices.md)

---

## How it is tested

The parser that reads Gazebo's protobuf text output lives in its own module,
[`perception/pose_parsing.py`](perception/pose_parsing.py), with no dependency on ROS, Gazebo or a
running simulation — so it can be tested anywhere, including in CI where none of those are installed.

```bash
python -m pytest tests -q        # 25 passed
```

The suite exists because protobuf text output is **lossy by omission**: every field equal to its
default is simply not printed. An object sitting exactly on the X axis emits no `x:` line; an unrotated
object emits no `orientation` block at all. A parser that treats absent as *unknown* rather than as
*zero* drops the target, and the node publishes nothing while the simulation looks perfectly healthy.
The tests pin that down, along with field isolation between the 29 entities in a single message,
scientific-notation values (a teleport to exactly 0 comes back as `6.4e-19`), and a key not being
matched inside a longer one.

---

## Layout

```
perception/
  camera_subscriber.py   overhead camera -> ROS 2, best-effort QoS, throttled frame capture
  fake_detector.py       the placeholder that unblocked the motion role
  oracle_detector.py     Gazebo ground truth -> three detection contracts
  pose_parsing.py        protobuf-text parsing, dependency-free and unit tested
  oracle_verify.sh       nine-step end-to-end verification against a live simulation
  camera_evidence.sh     camera pipeline inspection and crash reproduction
tests/                   pytest suite over the parser
docs/
  01-the-perception-stage.md  the three nodes and why each exists
  02-camera-pipeline.md       zero frames, the cause, the resolution decision, the real numbers
  03-why-an-oracle.md         why ground truth beat waiting for the model
  04-verification.md          the verification run in full, with evidence images
  05-coordinate-frames.md     frames, axes and message types confirmed across three roles
  06-findings.md              four defects, with reproduction steps
  07-running-it.md            how to run the nodes and the scripts
  08-working-practices.md     shared-file edits, evidence discipline, a security finding
  09-limitations-and-open-items.md  what this is not, and what was left unresolved
results/                 captured verification output
```

## Stack

ROS 2 Jazzy · Gazebo Harmonic 8.11.0 · `gz.transport13` Python bindings · `rclpy` · OpenCV /
`cv_bridge` · `vision_msgs` / `geometry_msgs` · MoveIt Task Constructor (downstream) · pytest ·
Ubuntu 24.04

## Licence

[MIT](LICENSE).
