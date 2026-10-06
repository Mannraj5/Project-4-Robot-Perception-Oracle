# Limitations and open items

What the perception stage does not do, and what was still unresolved when the work ended. Both are
stated here rather than left to be discovered.

---

## What the oracle is not

**It is not perception.** It knows the answer because the simulator told it. Its job is to unblock the
roles behind it and to be the reference the real detector is scored against — if it is ever mistaken
for a detector, it is worse than nothing, which is why its own docstring says so.

**One target per instance.** `target_model` names a single entity. Three batteries means three
instances, or extending it to take a list.

**No TF.** It publishes poses stamped `world` but broadcasts no transform frames for the cameras or the
target. Anything needing a camera-to-world transform has to get it elsewhere.

**No bounding box.** `Detection3DArray` carries an empty `bbox` and a confidence of exactly `1.0`.
Certainty by construction is the point, but it means a downstream consumer that filters on score or
reasons about object extent gets no signal from this node.

**If a bridge is preferred later**, the route that would work is the `gz-sim-pose-publisher-system`
plugin on each target model, which populates the header fields `ros_gz_bridge` needs. The bridge was
rejected for this path because those fields are unset by default, not because bridging is wrong in
principle.

## The suggested fix that was not applied

The batteries fall through the table because the top link has a visual and no collision
([06-findings.md](06-findings.md)). The fix is small and was handed over rather than applied, because
the world file is shared across three roles:

```xml
<collision name="top_collision">
  <!-- same pose and box size as the existing <visual> for the table top -->
</collision>
```

The decision that went with it was a question, not a patch: *should perception make this change, or do
you want to own it as part of the world?*

## Open with the vision role

Driven towards a written interface spec so every simulation role codes against the same assumptions.
Resolution was settled; these were not:

1. Whether the model wrapper letterboxes internally — if it does, it should be fed the raw 1280 × 960
   topic rather than having the image padded twice.
2. The detection output message type and field structure.
3. Coordinate frame and unit conventions for reported positions.
4. Feed count — one camera into the model, or both.

## Open with the motion and simulation roles

- **The arm's base pose relative to `world`** in the integration launch — spawned at the origin, or
  published on TF?
- **The frozen detection message specification.** `interfaces/msg/Detection.msg` was still empty
  upstream, and it decides whether `/target_pose` is the hand-off or whether the sub-team converges on
  something else.
- **Who applies the table-collision fix.**
- **Whether the oracle should keep publishing all three topics** or the consumers should converge on
  one. Publishing all three costs nothing — and hides the question, which is why it is written down
  here.
- **How to resolve the camera-and-arm crash**, with the three ranked options in
  [06-findings.md](06-findings.md).

## Not in this repository

`camera_preprocessor.py` — the 640 × 640 letterbox with the inverse mapping logged on the first frame.
It was written and **never validated against a live feed**, because that depended on the camera-and-arm
blocker being resolved, and it was not resolved before the project ended.

Everything else here is verified. Shipping one unvalidated file alongside it would undercut exactly the
distinction this work is built on.
