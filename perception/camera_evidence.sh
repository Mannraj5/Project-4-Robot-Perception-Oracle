#!/usr/bin/env bash
# Role 2 - reproduce the 26 Aug camera-pipeline evidence for screenshots.
#   bash camera_evidence.sh sdf     -> show the sensors plugin + camera resolutions in the shared world file
#   bash camera_evidence.sh cam     -> (sim running headless) bridge the cameras, show 1280x960 in ROS 2, measure rate
#   bash camera_evidence.sh crash   -> kill the sim, launch team7_sim WITH the arm, show the crash sequence
# Point these at the shared simulation package; defaults match the VM layout
# the evidence in docs/ was captured on.
SIM_PKG="${SIM_PKG:-$HOME/ws_moveit/src/team7_sim}"
WORLD="${WORLD:-$SIM_PKG/worlds/ewaste_room.sdf}"
LAUNCH="${LAUNCH:-$SIM_PKG/launch/team7_sim.launch.py}"
source /opt/ros/jazzy/setup.bash
[ -f ~/ws_moveit/install/setup.bash ] && source ~/ws_moveit/install/setup.bash 2>/dev/null

case "$1" in
  sdf)
    echo "=== $WORLD - system plugins ==="
    grep -n 'plugin filename="gz-sim' "$WORLD"
    echo
    echo "=== sensors plugin block ==="
    grep -n -A3 'gz-sim-sensors-system' "$WORLD"
    echo
    echo "=== camera image blocks (top_camera then side_camera) ==="
    grep -n -A3 '<image>' "$WORLD"
    ;;
  cam)
    echo "=== $(date) - camera verification in ROS 2 (sim must be running: gz sim -s -r ... ewaste_room.sdf) ==="
    if ! gz topic -l | grep -q '/top_camera/image'; then
      echo "FAIL: /top_camera/image not on the Gazebo bus - start the sim first (Terminal 1)."; exit 1; fi
    echo "--- Gazebo side: one frame header ---"
    gz topic -e -t /top_camera/image -n 1 | grep -E '^(width|height|pixel_format_type)|frame_id|value:' | head -6
    echo "--- start ros_gz_bridge for both cameras ---"
    ros2 run ros_gz_bridge parameter_bridge \
      /top_camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
      /top_camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
      /side_camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
      /side_camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo >/dev/null 2>&1 &
    BR=$!; sleep 4
    echo "--- ROS 2 topics ---"
    ros2 topic list | grep -E 'camera'
    echo "--- frame size in ROS 2 (/top_camera/image) ---"
    timeout 30 ros2 topic echo /top_camera/image --field width  --once --qos-reliability best_effort
    timeout 30 ros2 topic echo /top_camera/image --field height --once --qos-reliability best_effort
    echo "--- measured rate, ~25 s (expect ~1.5 Hz with heavy jitter) ---"
    timeout 25 ros2 topic hz /top_camera/image
    kill $BR 2>/dev/null
    ;;
  crash)
    echo "=== $(date) - camera + arm crash reproduction ==="
    pkill -f 'gz sim'; pkill -f 'gz-sim'; pkill -f parameter_bridge; sleep 3
    echo "--- launching $LAUNCH (GUI off) with the arm spawn; capped at 120 s ---"
    timeout 120 ros2 launch "$LAUNCH" launch_gui:=false 2>&1 \
      | grep -nE 'Sensors|render|switched controllers|already exists|Failed to create sensor|Parent not found|process has died|exit code|Abort|Segmentation|terminate' \
      | head -40
    echo "--- done (a died gazebo process with exit code -6/-11 = the crash) ---"
    pkill -f 'gz sim'; pkill -f 'gz-sim'; pkill -f parameter_bridge; pkill -f spawner
    ;;
  *) echo "usage: bash camera_evidence.sh sdf|cam|crash";;
esac
