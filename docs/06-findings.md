# Findings

Four defects surfaced while building the perception stage. Each is recorded with what was observed,
what the cause is, and what was and was not done about it.

Three of the four share a shape: **a check that passed for a reason unrelated to the thing being
checked.** That is the recurring failure mode in this project, and it is worth more than any individual
bug.

---

## 1. The cameras produced zero frames, with no error anywhere

**Observed.** The overhead camera published nothing. No warning, no error, no partial output. The
sensor was declared in the world file and appeared in the scene.

**Cause.** Three unrelated faults stacked on top of each other, each sufficient on its own to stop any
image reaching ROS 2: a stale workspace overlay in `.bashrc` shadowing the arm description package; the
absent `gz-sim-sensors-system` plugin, because Gazebo loads its default plugin set **only when a world
declares no `<plugin>` tags at all**, so declaring three means declaring all of them; and no camera
bridge node in the launch file at all, despite a prior contributor's TODO.

**How it was found.** By bisecting the pipeline into independently testable segments and eliminating
hypotheses one at a time, rather than applying the most likely fix and relaunching. With three faults
present, any partial fix produces no visible improvement and no information — so the obvious approach
would have yielded nothing while costing a relaunch each time.

**Consequence.** A dead camera is indistinguishable from a mis-configured subscriber and from a paused
simulation. Time went into all three before the cause was found.

**Action.** Fixed, verified end to end at the agreed resolution, and handed over **without merging** —
see finding 4 for why. Full detail: [02-camera-pipeline.md](02-camera-pipeline.md).

---

## 2. The batteries are 0.76 m below where every file says they are

**Observed.** The world file declares `battery_1` at **z = 0.81 m**, on the table top. The running
simulation reports **z = 0.050 m**. Teleporting the battery back to 0.81 m with `set_pose` and watching
it settle takes about two seconds, after which it reads ≈ 0.050 again.

**Cause.** The batteries fall through the table at startup, most likely because the table-top link
carries a `<visual>` but no `<collision>` element — drawn, but not solid.

**Why it had never been noticed.** The placeholder detector published the world-file value as a
constant — `z: 0.80`, written into `fake_detector.py` because the file was the only source available.
It could not disagree with the file. Every script and hand-off note in the project carried that number
for the same reason. The first thing that actually *measured* the position disagreed within seconds.

**Consequence.** Any target taken from the world file aims the gripper at empty air well above the
object. It also means the reachability role's work-surface height of 0.05 m matches the *physical*
state of the world rather than its *declared* one — correct by accident, which is worth knowing before
somebody "corrects" it to 0.81.

**Action.** Raised with the sub-team that owns the shared world file; deliberately not changed, because
that file is shared across three roles and a unilateral edit would have broken whatever the other two
were mid-way through.

**The general lesson, and the reason the oracle exists:** a coordinate that has only ever been read out
of a file is unverified until something measures it.

---

## 3. `ros_gz_bridge` silently discards the entity names

**Observed.** Bridging the Gazebo pose stream (`gz.msgs.Pose_V`) to `tf2_msgs/TFMessage` starts
cleanly, publishes at the expected rate, and produces messages whose `child_frame_id` is `''` for every
single transform.

**Cause.** The bridge populates `child_frame_id` from a header field that the Gazebo scene broadcaster
does not set. The names exist on the Gazebo side; the conversion drops them.

**Consequence.** The world publishes 29 entities in one message. Without names there is no way to tell
which pose belongs to the target — technically present, practically useless, and with no error to
suggest anything is wrong.

**Action.** Abandoned the bridge for this path. The node subscribes to the Gazebo transport stream
directly through the `gz.transport13` Python bindings, which preserve names, with a parsed CLI fallback
for environments where the bindings cannot be imported.

---

## 4. Cameras and the arm cannot share one process

**Observed.** With the sensors plugin in place, spawning the arm kills the server every time. This had
never appeared before, because without that plugin nothing was ever rendered. The sequence is always
the same:

```
[INFO] [controller_manager]: Successfully switched controllers!
[Err] [SceneManager.cc:224] Visual: [room] already exists
[Err] [SceneManager.cc:224] Visual: [desk] already exists
... every world entity ...
[Err] [RenderUtil.cc:1315] Failed to create sensor name[table::body::top_camera]
                            for entity [27]. Parent not found with ID[21].
-> crash
```

The scene is populated twice, the camera sensors then fail to attach to their parent, and the process
dies.

**What was tried before escalating.**

| Configuration | Outcome |
|---|---|
| ogre, GUI and server in one process | Abort (134) — Ogre exception, duplicate `sun` scene node |
| ogre2, GUI and server in one process | Server never starts (ogre2 needs OpenGL 3.3+) |
| ogre, headless server, GUI as a separate process | Abort (134), same duplicate `sun` |
| ogre, arm spawn delayed 10 s | Controllers came up cleanly, then the same abort |
| ogre2, headless server | Segfault (139) in `Ogre2MeshFactory::Create` → GL vertex buffer upload |
| ogre2 with `LIBGL_ALWAYS_SOFTWARE=1` (llvmpipe) | Identical segfault (139) |
| **ogre, headless server, no arm spawned** | **Works** — this is the verified configuration |

Both render engines fail, and swapping the GL driver for Mesa's llvmpipe changes nothing, so this is
not a driver problem. The `already exists` burst always precedes the crash, which points at the double
scene population as the cause rather than the rendering call that happens to die.

Two changes made while investigating are worth keeping regardless, because each fixed a real failure,
but **neither resolves the crash**: running the server headless with the GUI as a separate process
(they cannot share one — the GUI creates the scene first and the server segfaults in
`SensorsPrivate::WaitForInit()`), and delaying the arm spawn by 10 s, which is what got
`Successfully switched controllers!` to appear at all.

**Reproduction.** `bash perception/camera_evidence.sh crash` — kills any running simulator, launches
the full scene headless with a 120 s cap, and filters the log to the sensor, render and process-death
lines. Under two minutes.

**Action.** Escalated with three options ranked by preference and risk, rather than fixed:

1. **A separate camera-enabled world file**, so perception can develop while the arm work continues
   untouched. Lowest risk, unblocks immediately, changes nobody else's workflow.
2. **Define the arm in the world file** instead of spawning it into an already-rendering scene. If the
   double population is the cause, this removes it — but it is a structural change to how the
   simulation is composed.
3. **Accept the split**, and run cameras and arm in separate sessions until the full detect-and-pick
   loop needs both.

The fix belonged to the role that owns the launch files, not to perception. Continuing to try fixes
would have felt like progress and been activity — the useful output was a characterised failure and a
decision someone else could make in minutes.
