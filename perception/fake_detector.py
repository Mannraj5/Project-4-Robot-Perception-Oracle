#!/usr/bin/env python3
"""
Role 2 — Fake Detector.

Publishes plausible object detections on /detected_objects so Role 1 can
develop and test arm-driving logic before the real CV model exists.

PLACEHOLDER STATUS: message type, units, and frame_id are reasonable
defaults, not the final spec — the architect owns that. Update this once
it's locked and once the CV liaison confirms real feed count/units.
"""

import random

import rclpy
from rclpy.node import Node
from vision_msgs.msg import Detection3DArray, Detection3D, ObjectHypothesisWithPose
from geometry_msgs.msg import Pose


# Only one entry here is real: the re-stage coordinate from your own
# SETUP.md `set_pose` command, so it's grounded in your actual scene.
# Do NOT add battery_2 / battery_3 guesses here — Role 3 owns real scene
# layout. Leave num_objects at 1 until they supply verified positions.
KNOWN_OBJECTS = [
    {"class_id": "battery", "x": -0.15, "y": 0.62, "z": 0.80},
]


class FakeDetector(Node):
    def __init__(self):
        super().__init__('fake_detector')

        self.declare_parameter('publish_rate_hz', 2.0)
        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('num_objects', 1)
        self.declare_parameter('add_noise', True)
        self.declare_parameter('noise_stddev_m', 0.01)  # 1cm, plausible detector jitter

        self.frame_id = self.get_parameter('frame_id').get_parameter_value().string_value
        self.num_objects = self.get_parameter('num_objects').get_parameter_value().integer_value
        self.add_noise = self.get_parameter('add_noise').get_parameter_value().bool_value
        self.noise_stddev = self.get_parameter('noise_stddev_m').get_parameter_value().double_value
        rate = self.get_parameter('publish_rate_hz').get_parameter_value().double_value

        self.publisher = self.create_publisher(Detection3DArray, '/detected_objects', 10)
        self.timer = self.create_timer(1.0 / rate, self.publish_detections)

        self.get_logger().info(
            f'Fake detector running: {self.num_objects} object(s) @ {rate}Hz, '
            f'frame={self.frame_id}, noise={"on" if self.add_noise else "off"}'
        )

    def publish_detections(self):
        msg = Detection3DArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id

        for obj in KNOWN_OBJECTS[:self.num_objects]:
            det = Detection3D()
            det.header = msg.header

            pose = Pose()
            jitter = (lambda: random.gauss(0, self.noise_stddev)) if self.add_noise else (lambda: 0.0)
            pose.position.x = obj["x"] + jitter()
            pose.position.y = obj["y"] + jitter()
            pose.position.z = obj["z"] + jitter()
            pose.orientation.w = 1.0  # no orientation estimate — identity quaternion

            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = obj["class_id"]
            hyp.hypothesis.score = round(random.uniform(0.85, 0.99), 3)
            hyp.pose.pose = pose
            det.results.append(hyp)
            msg.detections.append(det)

        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = FakeDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
