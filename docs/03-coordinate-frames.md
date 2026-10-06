# Coordinate frames, axes and message types

Written to close a set of open items raised by the workspace-reachability role, whose image-to-workspace
mapping could not be treated as a real robot coordinate transformation until the frame, the axis
convention and the message types had been confirmed against what the other roles' code actually does.

The method matters as much as the answers: every row below is confirmed from source code or a published
standard, not from a document describing what the code was supposed to do. Two rows could not be
confirmed that way, and they are listed as open rather than guessed.

## Confirmed

| Question | Answer | Where it was confirmed |
|---|---|---|
| Which ROS frame does the motion planner expect? | The Gazebo **`world`** frame. The planning node subscribes to `target_pose` as `geometry_msgs/PoseStamped` and passes the message straight into the pick task, so it uses whatever `frame_id` the header carries and lets TF resolve it. Its launch attaches the arm to a frame named `world`. **Publish targets with `frame_id: world`.** | the planning node source, its grasp stage, and its integration launch file |
| Which way do the axes point? | ROS REP-103: right-handed, **X forward, Y left, Z up**, in metres. Camera *optical* frames use a different convention (Z forward, X right, Y down) — relevant only if the vision role ever supplies camera-frame XYZ rather than image coordinates. | ROS REP-103 |
| What will the vision model actually output? | **Image coordinates, not world XYZ** — a mask centroid (`cv2.moments`) and orientation (`cv2.minAreaRect`) in the 640 × 640 model input space, published on a bounding-box topic. | the vision role's mid-trimester summary |
| Who converts image coordinates to world coordinates? | Perception's responsibility: a pixel → world projection through the overhead camera's `camera_info` onto the work surface. The camera runs at 1280 × 960, so the 640 × 640 letterbox is an exact 0.5 scale with no rounding drift in the inverse mapping. | planned work, replacing the preliminary linear mapping in the reachability role's document |
| Which topic and type carries the target? | Three consumers exist today — `/target_pose` (`geometry_msgs/PoseStamped`), `/detected_battery_position` (`geometry_msgs/Point`), `/detected_objects` (`vision_msgs/Detection3DArray`). The oracle publishes all three in the `world` frame at 2 Hz, so each consumer receives a live target with no change on its side. | this repository |

## A note on the work-surface height

The shared world file declares the batteries at z = 0.81 m. The oracle showed they settle at
**z = 0.050 m** at startup and again after any `set_pose`. The reachability role's work-surface value of
0.05 m therefore matches the *physical* state of the shared world, not its *declared* one. Until the
table collision is fixed, any target read from the world file is 0.76 m too high — see
[04-findings.md](04-findings.md).

## Still open

- **The arm's base pose relative to `world`** in the integration launch — spawned at the origin, or
  published on TF? Owned by the motion-planning role.
- **The message type on the vision bounding-box topic.** Owned by the vision role.
- **Who applies the table-collision fix** to the shared world file. Owned by the sub-team lead.

Three roles had each made a locally sensible choice about topics and message types, and the result was a
pipeline with no working joint. None of the three decisions was wrong; the absence of any written
statement of them was. Reading the other roles' *code*, rather than their documents, is what surfaced it.
