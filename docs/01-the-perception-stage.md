# The perception stage

This repository is one role's contribution to a robotic e-waste disassembly simulation: the
**perception input** stage, sitting between the cameras and everything that drives the arm.

```
camera  ->  PERCEPTION  ->  target pose  ->  motion planning  ->  pick  ->  place
```

Three nodes were built, in this order, and each one exists because the previous one ran out of road.

---

## 1. `camera_subscriber.py` — get the frames into ROS 2 at all

The first job was simply to receive images: subscribe to the overhead camera, convert through
`cv_bridge`, and write throttled frames to disk so the vision team had something real to train
against.

Two things in that file are not boilerplate, and both came from being bitten:

- **Best-effort QoS, stated explicitly.** `ros_gz_bridge` publishes image topics best-effort. A
  default *reliable* subscriber connects with no error and then receives nothing at all, which looks
  exactly like a dead camera. The subscription declares `qos_profile_sensor_data` with a comment
  saying why.
- **Frame throttling.** The feed is bursty rather than steady — bursts at ~29 Hz separated by
  multi-second gaps — so saving every frame floods the disk while telling you nothing extra.

That node could not work at first, for a reason that had nothing to do with the node. The world file
was never rendering camera frames in the first place:
[02-camera-pipeline.md](02-camera-pipeline.md).

## 2. `fake_detector.py` — unblock the downstream roles

With frames arriving but no trained model, the motion role still had nothing to drive against. This
node publishes plausible detections on `/detected_objects` at 2 Hz, with optional Gaussian jitter, so
arm-driving logic could be developed against the real message type.

It is deliberately honest about what it is. Its own docstring is headed **PLACEHOLDER STATUS**, the
position list carries a comment saying only one entry is real and that guesses for the other
batteries must not be added, and the confidence score is randomised between 0.85 and 0.99 so nothing
downstream can mistake it for certainty.

It also carries, hard-coded, the line this whole repository ends up being about:

```python
KNOWN_OBJECTS = [
    {"class_id": "battery", "x": -0.15, "y": 0.62, "z": 0.80},
]
```

That `z` came from the world file, which was the only source available. It is wrong by 0.76 m. The
placeholder could not have discovered that, because the file it was copied from was the only thing it
could ever be checked against.

## 3. `oracle_detector.py` — replace the constant with a measurement

The third node reads the *true* pose of the target out of the simulator's own transport stream and
republishes it in the three message types the downstream nodes subscribe to. It unblocks the same
roles the placeholder did, but with a position that can disagree with the world file — and did, within
seconds of first being switched on.

Why ground truth rather than waiting for the model, and what makes it an oracle rather than a
detector: [03-why-an-oracle.md](03-why-an-oracle.md).

---

## What each one is for, in one table

| Node | Publishes | Exists to | Status |
|---|---|---|---|
| `camera_subscriber.py` | frames to disk | give the vision model real images, at the agreed resolution | working |
| `fake_detector.py` | `/detected_objects` | unblock arm-driving logic before any model exists | superseded by the oracle |
| `oracle_detector.py` | `/target_pose`, `/detected_battery_position`, `/detected_objects` | run the full loop against a physically true target, and score the real detector later | working, verified |

## The rest of the role

Not everything in a perception role is a node. The other half of the work was finding out why the
cameras produced nothing, what the real pipeline numbers are, and what the other roles were actually
expecting:

- [02-camera-pipeline.md](02-camera-pipeline.md) — zero frames, the one-line cause, and the resolution decision
- [05-coordinate-frames.md](05-coordinate-frames.md) — frames, axes and message types confirmed from three roles' source
- [06-findings.md](06-findings.md) — four defects, with reproduction steps and what was escalated rather than fixed
- [08-working-practices.md](08-working-practices.md) — editing files you do not own, evidence discipline, and a transport-layer security finding outside the role
- [09-limitations-and-open-items.md](09-limitations-and-open-items.md) — what the oracle is not, and what was still unresolved
