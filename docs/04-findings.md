# Findings

Three defects surfaced by building and running the oracle. Each is recorded with what was observed, what
the likely cause is, and what was and was not done about it.

---

## 1. The batteries are 0.76 m below where every file says they are

**Observed.** The world file declares `battery_1` at **z = 0.81 m** — on the table top. The running
simulation reports **z = 0.050 m**. Teleporting the battery back to 0.81 m with the `set_pose` service
and watching it settle takes about two seconds, after which it reads ≈ 0.050 again.

**Cause.** The batteries fall through the table at startup. The most likely reason is that the table-top
link carries a `<visual>` but no `<collision>` element, so it is drawn but not solid.

**Why it had never been noticed.** The placeholder detector published the world-file value as a
constant. It could not have disagreed with the file, because the file was its only source. Every script,
hand-off note and conversation in the project had carried 0.81 m since July for the same reason. The
first thing that actually measured the position disagreed within seconds.

**Consequence.** Any target taken from the world file is 0.76 m too high. A motion plan built on it aims
the gripper at empty air well above the object. It also means the reachability checker's work-surface
height of 0.05 m matches the *physical* state of the world rather than its *declared* one — correct by
accident, which is worth knowing before someone "fixes" it to 0.81.

**Action.** Raised with the sub-team that owns the shared world file. Deliberately not changed here: the
world file is shared across three roles and a unilateral edit to it would have broken whatever the other
two were mid-way through.

**The general lesson, and the reason this project exists:** a coordinate that has only ever been read out
of a file is unverified until something measures it.

---

## 2. `ros_gz_bridge` silently discards the entity names

**Observed.** Bridging the Gazebo pose stream (`gz.msgs.Pose_V`) to `tf2_msgs/TFMessage` starts cleanly,
publishes at the expected rate, and produces messages whose `child_frame_id` is `''` for every single
transform.

**Cause.** The bridge populates `child_frame_id` from a header field that the Gazebo scene broadcaster
does not set. The names exist on the Gazebo side; the conversion drops them.

**Consequence.** The world publishes 29 entities in one message. Without names, there is no way to tell
which pose belongs to the target — the data is technically present and practically useless. This is the
worst shape a bug can take: no error, no warning, correct-looking output.

**Action.** Abandoned the bridge for this path. The node subscribes to the Gazebo transport stream
directly through the `gz.transport13` Python bindings, which preserve names, with a CLI fallback
(`gz topic -e`, parsed) for environments where the bindings cannot be imported.

---

## 3. Cameras and the robot arm cannot share one process

**Observed.** Launching the full scene with both the cameras and the arm aborts during startup:

```
Ogre::ItemIdentityException: scene node 'sun' already exists
```

with the simulator process dying on exit code 134. Either half alone is fine: the cameras run at
1280 × 960 and bridge into ROS 2 correctly on their own, and the arm spawns and is controllable on its
own.

**Cause.** Two systems each construct their own render scene inside a single process, and the second one
to initialise collides with the first over a scene node that already exists.

**Reproduction.** `bash perception/camera_evidence.sh crash` — kills any running simulator, launches the
full scene headless with a 120 s cap, and filters the log down to the sensor, render and process-death
lines. Under two minutes.

**Action.** Documented and escalated with three options ranked by risk, rather than fixed. The fix is a
structural decision about how the simulation is composed — which systems load in which process — and
that belonged to the role that owns the launch files, not to perception. Continuing to try fixes would
have felt like progress and been activity.
