#!/usr/bin/env bash
# Role 2 - oracle_detector verification. Run inside the Team7 VM with the
# simulation ALREADY RUNNING and UNPAUSED (see ORACLE_RUN.md).
# (no "set -u": ROS setup.bash is not nounset-safe)
WORLD=ewaste_room
TARGET=battery_1
HOME_XYZ="x: -0.15, y: 0.62, z: 0.81"     # battery_1's pose in ewaste_room.sdf
MOVE_XYZ="x: 0.00, y: 0.60, z: 0.81"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE="${NODE:-$HERE/oracle_detector.py}"
# Written next to the repo's results/ when run from a checkout, else to $HOME.
OUT="${OUT:-$HERE/../results/oracle_verify_output.txt}"
[ -d "$(dirname "$OUT")" ] || OUT="$HOME/oracle_verify_output.txt"
exec > >(tee "$OUT") 2>&1

echo "=== oracle_detector verification - $(date) ==="
source /opt/ros/jazzy/setup.bash
[ -f "$HOME/ws_moveit/install/setup.bash" ] && source "$HOME/ws_moveit/install/setup.bash"

echo "--- 1. Gazebo pose topic present? ---"
if ! gz topic -l | grep -q "/world/$WORLD/pose/info"; then
  echo "FAIL: /world/$WORLD/pose/info not found. Is the sim running (and not paused)?"
  exit 1
fi
echo "OK"

echo "--- 2. start oracle_detector ---"
python3 "$NODE" --ros-args -p world:=$WORLD -p target_model:=$TARGET &
ORACLE=$!
sleep 10

echo "--- 3. ROS2 topics ---"
ros2 topic list | grep -E "target_pose|detected_"

echo "--- 4. /target_pose (PoseStamped, once) ---"
timeout 10 ros2 topic echo /target_pose geometry_msgs/msg/PoseStamped --once
echo "--- 5. /detected_battery_position (Point, once) ---"
timeout 10 ros2 topic echo /detected_battery_position geometry_msgs/msg/Point --once
echo "--- 6. /detected_objects (Detection3DArray, once) ---"
timeout 10 ros2 topic echo /detected_objects vision_msgs/msg/Detection3DArray --once
echo "--- 7. publish rate (/target_pose, ~10 s) ---"
timeout 12 ros2 topic hz /target_pose

echo "--- 8. MOVE TEST: teleport $TARGET to ($MOVE_XYZ) ---"
gz service -s "/world/$WORLD/set_pose" --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean \
  --timeout 2000 --req "name: \"$TARGET\", position: {$MOVE_XYZ}"
sleep 2
echo "--- /target_pose position after move (expect x~0.00, y~0.60; note z) ---"
timeout 10 ros2 topic echo /target_pose geometry_msgs/msg/PoseStamped --once --field pose.position

echo "--- 9. restore $TARGET to ($HOME_XYZ) ---"
gz service -s "/world/$WORLD/set_pose" --reqtype gz.msgs.Pose --reptype gz.msgs.Boolean \
  --timeout 2000 --req "name: \"$TARGET\", position: {$HOME_XYZ}"
sleep 2
echo "--- /target_pose position after restore (expect x~-0.15, y~0.62; note z) ---"
timeout 10 ros2 topic echo /target_pose geometry_msgs/msg/PoseStamped --once --field pose.position

kill $ORACLE 2>/dev/null
wait 2>/dev/null
echo "=== done - saved to $OUT ==="
