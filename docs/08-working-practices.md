# Working practices

Not everything a role contributes is a file in the repository. These are the practices that kept the
work usable by other people, and two findings that came out of them.

---

## Editing files you do not own

Two of the fixes required changing files owned by another role — the shared world file and the
integration launch file. Editing those by hand is how a sub-team loses an afternoon to a merge nobody
can explain.

Every change to a shared file was made by **anchor-matched script**: the script searches for the exact
surrounding text first and **aborts before writing** if the anchor is missing, so a file that has moved
on since the script was written fails loudly instead of being corrupted quietly. The launch file was
additionally parsed with `ast.parse` before every relaunch, and every edit wrote a timestamped backup
first.

No change made this way ever needed a rollback. The world-file resolution edit, for instance, was
applied by `apply_camera_resolution_960.py` -- a tool rather than a deliverable, which is why it is
described here rather than shipped.

The same discipline applied to *not* merging: the camera fix was verified working and then handed over
**unmerged**, because on its own it would have broken the arm simulation for everyone else — see
finding 4 in [06-findings.md](06-findings.md).

## Designing for the next role rather than for yourself

`fake_detector.py` could have published any convenient format and still satisfied its own deliverable.
Matching the real message interface exactly meant extra work upfront — checking field structures
against the official `vision_msgs` definitions before writing anything — and it is the reason the
motion role's subscriber needed no change at all when the oracle replaced the placeholder months later.

A placeholder that is easy to write and hard to replace is not a placeholder; it is a future migration.

## Evidence discipline

Two habits, both of which cost something at the time:

**Measure the thing, not a proxy for it.** I had cited a ROS publisher count as evidence the cameras
were working. `ros_gz_bridge` creates that publisher whether or not a frame ever arrives, so it proved
the bridge was configured and nothing else. The correction is recorded in
[02-camera-pipeline.md](02-camera-pipeline.md) rather than quietly replaced, because the mistake is
more instructive than the fix.

**Keep the evidence in one shape.** Verification is a committed, repeatable script with its results
committed alongside it, deliberately in the same format the reachability role already used — so the
sub-team's test evidence reads the same way whoever produced it, rather than each role inventing its own
convention.

**Characterise, then escalate.** When the simulator crash turned out not to be mine to fix, the useful
output was not another attempt — it was seven configurations, the log line that always precedes the
failure, and three options ranked by risk, so the person who owned the decision could make it in
minutes.

## Environment findings handed to the team

Small things, each of which had already cost somebody time:

- **The workspace overlay was never sourced.** `~/.bashrc` sourced the ROS distribution but not the
  local workspace, so any forgotten manual step failed with `package 'kortex_description' not found` —
  which reads as a missing install rather than a sourcing problem.
- **Sensor subscribers must declare best-effort QoS.** The bridge publishes images best-effort; a
  default reliable subscriber connects with no error and then receives nothing, which is
  indistinguishable from a dead camera.
- **Camera throughput and simulation speed are independent bottlenecks.** The simulation sustained a
  real-time factor of ~0.98 with both cameras active while the cameras themselves rendered at ~0.7 Hz
  against a configured 30 Hz. Physics stepping is CPU-bound and unaffected by graphics acceleration;
  sensor rendering is not. Passed on explicitly so the two would not be conflated in the platform
  costing.

---

## A security finding outside the role

While diagnosing a communication fault, the FastRTPS transport underlying ROS 2 turned out to keep
inter-node communication in **shared memory with no process-level access control**, and to leave stale
segments behind after an unclean shutdown.

Inside a controlled simulation that is harmless. In anything deployed, it means any local process can
read — or write — the messages that drive physical actuation. For a robot arm, "write" is the word that
matters.

This sits entirely outside a perception role. It was documented and passed to the team as a
consideration for any deployment beyond simulation, rather than filed as someone else's problem.

The corresponding mitigation on the perception side is a **validator in front of `/target_pose`** that
rejects targets which are out of workspace, below a confidence threshold, in the wrong frame, or stale
— the same guard that would make a topic-injection test meaningful. The staleness half of that idea is
already implemented in the oracle as `gt_timeout_s`.
