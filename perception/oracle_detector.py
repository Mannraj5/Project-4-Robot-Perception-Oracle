#!/usr/bin/env python3
"""
Role 2 — Oracle Detector (ground-truth-driven perception stand-in).

Reads the TRUE pose of a target model from Gazebo's /world/<world>/pose/info
stream and republishes it as a detection, in the formats each downstream
consumer actually subscribes to:

  /target_pose                geometry_msgs/PoseStamped     Robotics MTC node ("target_pose")
  /detected_battery_position  geometry_msgs/Point           Role 3 reachability node
  /detected_objects           vision_msgs/Detection3DArray  existing Role 2 contract

This is a test fixture, not the CV model. It lets Roles 1 and 3 run the
pick-and-place loop against a physically true target before the real detector
exists, and it is the ground-truth reference the real detector will be scored
against (error budget: MTC approach tolerance is 0.02 m).

Why it reads Gazebo transport directly instead of using ros_gz_bridge:
bridging pose/info (gz.msgs.Pose_V) to tf2_msgs/TFMessage drops the entity
names — the bridge fills child_frame_id only from a header field that the
scene broadcaster does not set — so every transform arrives as ''. Reading
the Gazebo stream itself keeps the names.

Ground-truth source (parameter `source`):
  auto   - use the gz.transport13 Python bindings if importable, else CLI
  python - gz.transport13 subscriber (event-driven, no extra processes)
  cli    - polls `gz topic -e -t <topic> -n 1` at the publish rate

Run (sim already running and unpaused):
  python3 oracle_detector.py --ros-args -p target_model:=battery_1
"""

import random
import subprocess
import threading

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion
from vision_msgs.msg import Detection3D, Detection3DArray, ObjectHypothesisWithPose


# --------------------------------------------------------------------------
# Parsing helpers for the CLI fallback live in pose_parsing.py so that they
# can be unit tested without ROS or Gazebo present.
# --------------------------------------------------------------------------

from pose_parsing import parse_pose_v_text


# --------------------------------------------------------------------------
# Ground-truth sources
# --------------------------------------------------------------------------

class GzPythonSource:
    """Subscribes to pose/info through the gz.transport13 Python bindings."""

    def __init__(self, topic, on_poses):
        from gz.transport13 import Node as GzNode          # noqa: import here so failure is catchable
        from gz.msgs10.pose_v_pb2 import Pose_V
        self._node = GzNode()
        self._on_poses = on_poses
        if not self._node.subscribe(Pose_V, topic, self._cb):
            raise RuntimeError(f'gz.transport13 subscribe to {topic} failed')

    def _cb(self, msg):
        poses = {}
        for p in msg.pose:
            poses[p.name] = (p.position.x, p.position.y, p.position.z,
                             p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w)
        self._on_poses(poses)

    def stop(self):
        pass


class GzCliSource:
    """Polls `gz topic -e -t <topic> -n 1` in a background thread."""

    def __init__(self, topic, on_poses, period_s, logger):
        self._cmd = ['gz', 'topic', '-e', '-t', topic, '-n', '1']
        self._on_poses = on_poses
        self._period = period_s
        self._log = logger
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(self._cmd, capture_output=True, text=True, timeout=5.0)
                if out.returncode == 0 and out.stdout:
                    self._on_poses(parse_pose_v_text(out.stdout))
                else:
                    self._log.warn(f'gz topic returned {out.returncode}: {out.stderr.strip()[:120]}',
                                   throttle_duration_sec=5.0)
            except subprocess.TimeoutExpired:
                self._log.warn('gz topic -e timed out (sim paused?)', throttle_duration_sec=5.0)
            except Exception as e:                       # noqa: keep polling
                self._log.warn(f'gz topic poll failed: {e}', throttle_duration_sec=5.0)
            self._stop.wait(self._period)

    def stop(self):
        self._stop.set()


# --------------------------------------------------------------------------
# The node
# --------------------------------------------------------------------------

class OracleDetector(Node):
    def __init__(self):
        super().__init__('oracle_detector')

        self.declare_parameter('world', 'ewaste_room')
        self.declare_parameter('target_model', 'battery_1')
        self.declare_parameter('class_id', 'battery')
        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('publish_rate_hz', 2.0)
        self.declare_parameter('source', 'auto')          # auto | python | cli
        self.declare_parameter('add_noise', False)        # ground truth is exact; noise is opt-in
        self.declare_parameter('noise_stddev_m', 0.01)
        self.declare_parameter('gt_timeout_s', 3.0)       # stop publishing if Gazebo goes quiet

        def gp(name):
            return self.get_parameter(name).value

        self.world = gp('world')
        self.target_model = gp('target_model')
        self.class_id = gp('class_id')
        self.frame_id = gp('frame_id')
        self.add_noise = gp('add_noise')
        self.noise_stddev = gp('noise_stddev_m')
        self.gt_timeout = gp('gt_timeout_s')
        rate = gp('publish_rate_hz')
        source = gp('source')

        self.pose_topic = f'/world/{self.world}/pose/info'
        self._lock = threading.Lock()
        self.gt = None               # (x, y, z, qx, qy, qz, qw)
        self.gt_time = None
        self.names_logged = False

        self.pub_target = self.create_publisher(PoseStamped, '/target_pose', 10)
        self.pub_point = self.create_publisher(Point, '/detected_battery_position', 10)
        self.pub_dets = self.create_publisher(Detection3DArray, '/detected_objects', 10)
        self.timer = self.create_timer(1.0 / rate, self.publish)

        self.source = self._start_source(source, 1.0 / rate)

        self.get_logger().info(
            f'Oracle detector: target="{self.target_model}" from {self.pose_topic} '
            f'via {self.source_name} @ {rate} Hz, frame={self.frame_id}, '
            f'noise={"on" if self.add_noise else "off"}'
        )

    def _start_source(self, source, period_s):
        if source in ('auto', 'python'):
            try:
                src = GzPythonSource(self.pose_topic, self.on_poses)
                self.source_name = 'gz.transport13 python bindings'
                return src
            except Exception as e:
                if source == 'python':
                    raise
                self.get_logger().info(f'python bindings unavailable ({e.__class__.__name__}: {e}); '
                                       f'falling back to gz CLI polling')
        self.source_name = 'gz CLI polling'
        return GzCliSource(self.pose_topic, self.on_poses, period_s, self.get_logger())

    # -- ground truth in --------------------------------------------------

    def on_poses(self, poses):
        if not self.names_logged:
            self.get_logger().info(f'pose/info entities seen: {sorted(poses)}')
            self.names_logged = True
        gt = poses.get(self.target_model)
        if gt is None:
            return
        with self._lock:
            first = self.gt is None
            self.gt = gt
            self.gt_time = self.get_clock().now()
        if first:
            self.get_logger().info(
                f'ground truth acquired for "{self.target_model}": '
                f'({gt[0]:.4f}, {gt[1]:.4f}, {gt[2]:.4f})'
            )

    # -- detections out ---------------------------------------------------

    def publish(self):
        with self._lock:
            gt, gt_time = self.gt, self.gt_time
        if gt is None:
            self.get_logger().warn(
                f'no ground truth yet for "{self.target_model}" on {self.pose_topic} '
                f'- is the sim running and unpaused?',
                throttle_duration_sec=5.0,
            )
            return
        age = (self.get_clock().now() - gt_time).nanoseconds * 1e-9
        if age > self.gt_timeout:
            self.get_logger().warn(f'ground truth stale ({age:.1f}s) - not publishing',
                                   throttle_duration_sec=5.0)
            return

        if self.add_noise:
            def jitter():
                return random.gauss(0.0, self.noise_stddev)
        else:
            def jitter():
                return 0.0

        pose = Pose()
        pose.position.x = gt[0] + jitter()
        pose.position.y = gt[1] + jitter()
        pose.position.z = gt[2] + jitter()
        pose.orientation = Quaternion(x=gt[3], y=gt[4], z=gt[5], w=gt[6])

        stamp = self.get_clock().now().to_msg()

        # 1. Robotics MTC node: geometry_msgs/PoseStamped on /target_pose
        ps = PoseStamped()
        ps.header.stamp = stamp
        ps.header.frame_id = self.frame_id
        ps.pose = pose
        self.pub_target.publish(ps)

        # 2. Role 3 reachability node: geometry_msgs/Point on /detected_battery_position
        self.pub_point.publish(Point(x=pose.position.x, y=pose.position.y, z=pose.position.z))

        # 3. Existing Role 2 contract: vision_msgs/Detection3DArray on /detected_objects
        arr = Detection3DArray()
        arr.header.stamp = stamp
        arr.header.frame_id = self.frame_id
        det = Detection3D()
        det.header = arr.header
        hyp = ObjectHypothesisWithPose()
        hyp.hypothesis.class_id = self.class_id
        hyp.hypothesis.score = 1.0          # oracle: certainty by construction
        hyp.pose.pose = pose
        det.results.append(hyp)
        arr.detections.append(det)
        self.pub_dets.publish(arr)

    def destroy_node(self):
        self.source.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = OracleDetector()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass                                 # SIGINT/SIGTERM: exit quietly
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
