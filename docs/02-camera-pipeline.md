# The camera pipeline

The overhead camera produced **no frames at all**. Not corrupt frames, not slow frames — zero, with no
warning and no error anywhere in the logs. This is what it took to find out why, and what the pipeline
actually does once it works.

---

## The cause: one missing plugin, and a fallback that stops applying

The world file declared three system plugins — physics, user-commands, scene-broadcaster — but not
`gz-sim-sensors-system`.

The trap is in how the fallback works. **Gazebo loads its default plugin set only when a world declares
no `<plugin>` tags at all.** The moment a world declares one, it declares all of them, and anything
left out is simply absent. So the camera `<sensor>` blocks were parsed, accepted, and then silently
ignored — the sensor existed in the scene graph and nothing ever rendered it.

```xml
<!-- required for the camera sensors to render. Without this system the
     <sensor type="camera"> blocks are parsed and then silently ignored:
     zero frames published, and no error anywhere.
     render_engine must match --render-engine in the launch file. -->
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
  <render_engine>ogre</render_engine>
</plugin>
```

`ogre` rather than `ogre2`: ogre2 requires OpenGL 3.3+, which this VM's driver does not provide, and
the server then refuses to start at all.

A failure with no error message is worse than a crash. The scene looked right in the GUI, the topic
existed, and the only symptom was a subscriber that sat there receiving nothing — which is also what a
mis-configured subscriber looks like, and what a paused simulation looks like.

## The resolution decision, and why 1280×960 rather than "something big enough"

The vision model takes **640 × 640** at its input, with pre-processing allowed. The overhead camera was
1280 × 720. It was changed to **1280 × 960**, and the reason is arithmetic rather than taste:

```
scale   = min(640/1280, 640/960) = 0.5
resized = 640 x 480
padding = 80 px top, 80 px bottom
```

An exact 0.5 scale with whole-number padding means a detection in model space maps back to
full-resolution pixels with **no rounding drift**:

```
x_full = x_640 / 0.5
y_full = (y_640 - 80) / 0.5
```

That matters because the pixel mapping is not the end of the chain — rounding error in it propagates
into the 3D position the arm is driven to. At the original 1280 × 720 the scale would not have been
clean.

Letterbox rather than centre-crop: cropping to a square discards 160 px from each side of the
workspace, and objects near the edge of the bin area would stop being detectable at all.

**One consequence worth stating rather than discovering later:** 720 → 960 lines changes the frame from
16:9 to 4:3. Gazebo derives vertical FOV from `horizontal_fov` and the aspect ratio, so the camera now
sees roughly 33% more vertical extent at the same horizontal FOV. At 0.49 m range that moves the view
half-extent from about 0.16 m to about 0.21 m — and since the batteries sit about 0.23 m off the camera
axis, the change moves them from outside the frame to marginally inside it. The framing was a real
problem, not just a resolution one.

The side camera was deliberately left at 640 × 480, because it letterboxes into 640 × 640 at exactly
1.0 scale with no resampling at all — already model-ready.

## What the working pipeline actually does

Server headless, GUI off, arm not spawned:

| Check | Result |
|---|---|
| Gazebo renders frames | real frame, `frame_id: table::body::top_camera` |
| Topics bridged into ROS 2 | all four camera topics present |
| Frame size in ROS 2 | **1280 × 960** |
| Measured rate | **~1.5 Hz** average (1.586, then 1.505) |
| Jitter | min 0.034 s, max 3.324 s, std dev ~1.05 s |

Two things in those numbers are worth more than the headline:

**The rate went up after adding 33% more pixels** — from ~0.7 Hz at 1280 × 720 to ~1.5 Hz at
1280 × 960 — because the GUI was no longer running and competing for the software renderer. Camera
throughput and simulation real-time factor are independent bottlenecks; the frame rate was not a
symptom of sim speed.

**The feed is not a stream.** Bursts at ~29 Hz separated by gaps over three seconds. Anything
downstream has to tolerate that, and an average rate on its own would have hidden it completely.

`perception/camera_evidence.sh` reproduces all of the above: `sdf` shows the plugin and resolutions in
the world file, `cam` bridges both cameras and measures the rate, `crash` reproduces the blocker below.

## A correction to my own earlier reporting

I had previously cited `Publisher count: 1` on both cameras as evidence the dual-camera setup was
working. That check is weaker than I presented it. **`ros_gz_bridge` creates the ROS publisher whether
or not any data ever arrives from Gazebo**, so a publisher count proves the bridge is configured — not
that frames exist. `ros2 topic hz` is the check that proves data flow, and it is what the table above
uses.

This is exactly the class of mistake the whole project kept running into: a check that passes for a
reason unrelated to the thing being checked.

## The blocker

With the sensors plugin in place, spawning the arm kills the server — which had never shown up before,
because without the plugin nothing was ever rendered. Seven configurations were tried across two render
engines and two GL drivers before escalating; the full matrix is in
[06-findings.md](06-findings.md).

## Pre-processing

`camera_preprocessor.py` implements the letterbox above — best-effort subscription, 640 × 640 with
114-grey padding, the original header preserved so detections stay tied to the right camera and
timestamp, and the letterbox geometry and inverse mapping logged on the first frame so the other roles
can read the numbers off the log rather than re-deriving them.

**It is not in this repository**, because it was written and never validated against a live feed — that
step depended on the arm-and-camera blocker being resolved, and it was not resolved before the project
ended. Shipping unvalidated code in a repository that presents everything else as verified would
undercut the distinction this project is built on.
