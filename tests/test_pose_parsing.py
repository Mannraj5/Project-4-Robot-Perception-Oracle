"""Unit tests for the Gazebo protobuf-text parser used by the CLI fallback.

The thing that makes this parser worth testing is that protobuf text output is
*lossy by omission*: any field equal to its default is simply not printed. A
battery sitting exactly on the world origin's X axis produces no `x:` line at
all, and an unrotated object produces no `orientation` block. A parser that
treats "absent" as "unknown" rather than "zero" would silently drop the target,
and the node would publish nothing while the simulation looked perfectly fine.

Every fixture below is in the format `gz topic -e -t /world/<world>/pose/info`
actually emits.
"""

import pytest

from pose_parsing import _field, parse_pose_v_text


FULL = """pose {
  name: "battery_1"
  id: 12
  position {
    x: -0.15
    y: 0.62
    z: 0.05
  }
  orientation {
    x: 0.1
    y: 0.2
    z: 0.3
    w: 0.927
  }
}
"""

TWO_ENTITIES = """pose {
  name: "battery_1"
  position {
    x: -0.15
    y: 0.62
    z: 0.05
  }
}
pose {
  name: "drop_box"
  position {
    x: 0.4
    y: -0.2
    z: 0.0
  }
}
"""


class TestASinglePose:
    def test_the_entity_is_keyed_by_name(self):
        assert list(parse_pose_v_text(FULL)) == ["battery_1"]

    def test_position_is_read_in_order_x_y_z(self):
        assert parse_pose_v_text(FULL)["battery_1"][:3] == (-0.15, 0.62, 0.05)

    def test_orientation_is_read_in_order_x_y_z_w(self):
        assert parse_pose_v_text(FULL)["battery_1"][3:] == (0.1, 0.2, 0.3, 0.927)


class TestFieldsOmittedBecauseTheyAreZero:
    """Protobuf text prints nothing for a default value. Absent means zero."""

    def test_a_missing_axis_is_zero_not_missing(self):
        text = 'pose {\n  name: "battery_1"\n  position {\n    y: 0.62\n  }\n}\n'
        assert parse_pose_v_text(text)["battery_1"][:3] == (0.0, 0.62, 0.0)

    def test_an_empty_position_block_is_the_origin(self):
        text = 'pose {\n  name: "sun"\n  position {\n  }\n}\n'
        assert parse_pose_v_text(text)["sun"][:3] == (0.0, 0.0, 0.0)

    def test_no_position_block_at_all_is_still_the_origin(self):
        text = 'pose {\n  name: "world"\n}\n'
        assert parse_pose_v_text(text)["world"][:3] == (0.0, 0.0, 0.0)

    def test_a_missing_orientation_block_is_the_identity_quaternion(self):
        text = 'pose {\n  name: "battery_1"\n  position {\n    z: 0.05\n  }\n}\n'
        assert parse_pose_v_text(text)["battery_1"][3:] == (0.0, 0.0, 0.0, 1.0)

    def test_a_partial_orientation_block_fills_the_rest_with_zero(self):
        text = 'pose {\n  name: "battery_1"\n  orientation {\n    w: 1.0\n  }\n}\n'
        assert parse_pose_v_text(text)["battery_1"][3:] == (0.0, 0.0, 0.0, 1.0)


class TestSeveralEntities:
    def test_every_entity_is_returned(self):
        assert set(parse_pose_v_text(TWO_ENTITIES)) == {"battery_1", "drop_box"}

    def test_each_entity_keeps_its_own_values(self):
        poses = parse_pose_v_text(TWO_ENTITIES)
        assert poses["battery_1"][:3] == (-0.15, 0.62, 0.05)
        assert poses["drop_box"][:3] == (0.4, -0.2, 0.0)

    def test_a_pose_block_with_no_name_is_skipped(self):
        text = TWO_ENTITIES + "pose {\n  position {\n    x: 9.9\n  }\n}\n"
        assert set(parse_pose_v_text(text)) == {"battery_1", "drop_box"}

    def test_a_later_block_does_not_leak_into_an_earlier_one(self):
        """The world publishes ~29 entities in one message; the orientation of
        the second must not be read as the orientation of the first."""
        text = (
            'pose {\n  name: "a"\n  position {\n    x: 1.0\n  }\n}\n'
            'pose {\n  name: "b"\n  position {\n    x: 2.0\n  }\n'
            "  orientation {\n    w: 0.5\n  }\n}\n"
        )
        poses = parse_pose_v_text(text)
        assert poses["a"] == (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
        assert poses["b"][3:] == (0.0, 0.0, 0.0, 0.5)


class TestNumberFormats:
    def test_negative_values_survive(self):
        assert parse_pose_v_text(FULL)["battery_1"][0] == -0.15

    @pytest.mark.parametrize(
        "literal,expected",
        [
            ("6.409880918794619e-19", 6.409880918794619e-19),
            ("-2.882889520271306e-17", -2.882889520271306e-17),
            ("1e3", 1000.0),
            ("0", 0.0),
        ],
    )
    def test_scientific_notation_is_read_as_written(self, literal, expected):
        """Gazebo reports a teleport to x = 0 as 6.4e-19, not as 0."""
        text = 'pose {\n  name: "n"\n  position {\n    x: %s\n  }\n}\n' % literal
        assert parse_pose_v_text(text)["n"][0] == expected


class TestFieldLookup:
    def test_an_absent_key_returns_the_default(self):
        assert _field("y: 1.0", "x") == 0.0
        assert _field("y: 1.0", "x", default=7.5) == 7.5

    def test_a_key_is_not_matched_inside_a_longer_name(self):
        """`x:` must not be found inside `max_x:`, or every bounding box in the
        message would be read as a position."""
        assert _field("max_x: 4.0\nx: 1.0", "x") == 1.0


class TestEmptyAndMalformedInput:
    def test_empty_input_gives_no_poses(self):
        assert parse_pose_v_text("") == {}

    def test_output_with_no_pose_blocks_gives_no_poses(self):
        assert parse_pose_v_text("header {\n  stamp {\n    sec: 1\n  }\n}\n") == {}


class TestTheRecordedVerificationRun:
    """The values the detector reported during the 13 Sep verification, in the
    format the CLI fallback would have had to parse to produce them."""

    RECORDED = """pose {
  name: "battery_1"
  position {
    x: -0.15
    y: 0.62
    z: 0.049999610465892526
  }
  orientation {
    x: -2.882889520271306e-17
    y: -7.537624813813734e-18
    z: -1.2014379718207232e-18
    w: 1.0
  }
}
"""

    def test_the_target_is_found(self):
        assert "battery_1" in parse_pose_v_text(self.RECORDED)

    def test_the_position_matches_the_published_detection(self):
        x, y, z = parse_pose_v_text(self.RECORDED)["battery_1"][:3]
        assert (round(x, 4), round(y, 4), round(z, 4)) == (-0.15, 0.62, 0.05)

    def test_the_orientation_is_identity_to_within_float_noise(self):
        qx, qy, qz, qw = parse_pose_v_text(self.RECORDED)["battery_1"][3:]
        assert abs(qx) < 1e-15 and abs(qy) < 1e-15 and abs(qz) < 1e-15
        assert qw == 1.0

    def test_the_declared_table_height_is_not_what_the_simulation_reports(self):
        """The world file declares the batteries at z = 0.81; the simulation
        reports 0.05. The 0.76 m gap is the table-collision defect recorded in
        docs/04-findings.md, and it is the reason this detector exists."""
        z = parse_pose_v_text(self.RECORDED)["battery_1"][2]
        assert round(0.81 - z, 2) == 0.76
