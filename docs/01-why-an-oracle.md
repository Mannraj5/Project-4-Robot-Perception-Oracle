# Why an oracle, and why before the detector

## The situation

The simulation is a robotic cell for e-waste disassembly: an overhead camera, a work surface with
battery cells on it, a robot arm, and a drop box. The pipeline is meant to run

```
camera -> detector -> target pose -> motion planner -> pick -> place
```

Three roles own different parts of it. Perception sits in the middle, and until perception publishes
something, the two stages behind it have nothing to run against.

At the point this work started, the vision model was still being trained. The repository's placeholder
detector published a position taken from a constant that had been copied out of the world file. That is
enough to prove a subscriber is wired up correctly, and nothing more: it reports the same answer whether
the simulation is running, paused, or lying.

## The idea

The simulator already knows exactly where every object is. Gazebo publishes the true pose of every
entity in the world on its own transport bus, at simulation rate, continuously. That is a perfect
detector — no training, no latency budget, no false negatives — for everything except the one thing a
detector is actually for.

Using it as a stand-in gives three things at once:

**It unblocks the downstream roles immediately.** The motion planner and the reachability checker can
run the complete loop against a physically true target, in the exact message types they already
subscribe to, with no change on their side.

**It becomes the scoring reference.** When the real detector arrives, "is it good enough?" is not a
judgement call: it is the distance between the detector's output and the oracle's, measured over the
same run. The budget is already set by the motion planner's approach tolerance, 0.02 m.

**It tells the truth about the world.** This turned out to matter more than the other two. A constant
read from a file cannot disagree with the file. Ground truth can — and did, by 0.76 m, within seconds of
first being switched on. See [04-findings.md](04-findings.md).

## What makes it an oracle and not a detector

Everything it publishes is correct by construction. Confidence is always `1.0`, the bounding box is
empty, and there is no failure mode other than "the simulation is not running". It is a test fixture, and
the code says so in its own docstring, because a stand-in that is mistaken for the real thing is worse
than no stand-in at all.

Two affordances keep it useful rather than misleading:

- **`add_noise` / `noise_stddev_m`** — opt-in Gaussian jitter on the published position, so a downstream
  node can be tested against an imperfect detector without waiting for one to exist.
- **`gt_timeout_s`** — if the ground-truth stream goes quiet (the usual cause is a paused simulation),
  the node stops publishing rather than repeating its last known position forever. A detector that keeps
  confidently reporting a stale target is exactly the failure that is hardest to notice downstream.

## Reading Gazebo directly rather than bridging

The conventional route is `ros_gz_bridge`, which converts Gazebo messages into ROS 2 ones. Bridging the
pose stream (`gz.msgs.Pose_V`) to `tf2_msgs/TFMessage` runs without error and publishes at the right
rate — and is useless, because every transform arrives with an empty name. The bridge fills
`child_frame_id` from a header field that the scene broadcaster does not set. With 29 entities in the
world and no names on any of them, there is no way to pick out the target.

The node therefore subscribes to the Gazebo transport stream itself, through the `gz.transport13` Python
bindings, which preserve entity names. A CLI fallback (`gz topic -e`, parsed) is kept for environments
where the bindings are not importable, which is also why the parser is a separately testable module —
see [`perception/pose_parsing.py`](../perception/pose_parsing.py).
