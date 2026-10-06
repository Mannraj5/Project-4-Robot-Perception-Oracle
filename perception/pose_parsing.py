"""
Parsing for Gazebo's protobuf *text* output (`gz topic -e -t <topic>`).

Kept separate from the ROS 2 node for one reason: this half has no dependency
on rclpy, Gazebo or a running simulation, so it can be unit tested anywhere --
including in CI, where neither ROS nor Gazebo is installed. The node imports
from here; see tests/test_pose_parsing.py for the behaviour this guarantees.

The format is protobuf text, which omits any field equal to its default. A
position with no `x:` line means x = 0.0, and a pose with no `orientation`
block at all means the identity quaternion -- not missing data.
"""

import re


# --------------------------------------------------------------------------
# Parsing helpers for the CLI fallback (protobuf text format from `gz topic -e`)
# --------------------------------------------------------------------------

_POSE_BLOCK = re.compile(r'^pose \{\n(.*?)^\}', re.M | re.S)
_NAME = re.compile(r'name: "([^"]*)"')
_POSITION = re.compile(r'position \{(.*?)\}', re.S)
_ORIENTATION = re.compile(r'orientation \{(.*?)\}', re.S)


def _field(block, key, default=0.0):
    m = re.search(rf'\b{key}: (-?[0-9.eE+-]+)', block)
    return float(m.group(1)) if m else default


def parse_pose_v_text(text):
    """Return {name: (x, y, z, qx, qy, qz, qw)} from `gz topic -e` output.
    Protobuf text omits zero-valued fields, so missing x/y/z mean 0 and a
    missing orientation block means identity."""
    poses = {}
    for block in _POSE_BLOCK.findall(text):
        nm = _NAME.search(block)
        if not nm:
            continue
        pm = _POSITION.search(block)
        pb = pm.group(1) if pm else ''
        om = _ORIENTATION.search(block)
        if om:
            ob = om.group(1)
            q = (_field(ob, 'x'), _field(ob, 'y'), _field(ob, 'z'), _field(ob, 'w'))
        else:
            q = (0.0, 0.0, 0.0, 1.0)
        poses[nm.group(1)] = (_field(pb, 'x'), _field(pb, 'y'), _field(pb, 'z'), *q)
    return poses
