#!/usr/bin/env python3
"""Perception Input — subscribes to /top_camera/image, converts via cv_bridge,
saves frames to disk. Detection/position logic plugs in here later."""

import os
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


class CameraSubscriber(Node):
    def __init__(self):
        super().__init__('top_camera_subscriber')

        self.declare_parameter('save_dir', os.path.expanduser('~/camera_frames'))
        self.declare_parameter('save_every_n', 5)  # throttle: feed is bursty, don't flood disk

        self.save_dir = self.get_parameter('save_dir').get_parameter_value().string_value
        self.save_every_n = self.get_parameter('save_every_n').get_parameter_value().integer_value
        os.makedirs(self.save_dir, exist_ok=True)

        self.bridge = CvBridge()
        self.frame_count = 0
        self.last_log_time = time.time()

        # ros_gz_bridge publishes image topics best-effort; matching QoS
        # explicitly here so this doesn't silently fail to receive anything.
        self.subscription = self.create_subscription(
            Image, '/top_camera/image', self.image_callback, qos_profile_sensor_data,
        )
        self.get_logger().info(
            f'Subscribed to /top_camera/image, saving every {self.save_every_n} frames to {self.save_dir}'
        )

    def image_callback(self, msg: Image):
        self.frame_count += 1

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'cv_bridge conversion failed: {e}')
            return

        if self.frame_count % self.save_every_n == 0:
            filename = os.path.join(self.save_dir, f'frame_{self.frame_count:06d}.png')
            cv2.imwrite(filename, cv_image)
            self.get_logger().info(f'Saved {filename}  ({cv_image.shape[1]}x{cv_image.shape[0]})')

        now = time.time()
        if now - self.last_log_time > 5.0:
            self.get_logger().info(f'{self.frame_count} frames received so far')
            self.last_log_time = now


def main(args=None):
    rclpy.init(args=args)
    node = CameraSubscriber()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
