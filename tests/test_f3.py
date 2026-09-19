import pytest

from mcbuilder.vision.f3 import F3ReadError, normalise_yaw, parse, yaw_delta


def test_parses_a_modern_debug_screen():
    state = parse([
        "Minecraft 1.20.4",
        "XYZ: -123.456 / 64.00000 / 789.012",
        "Block: -124 64 789",
        "Facing: south (Towards positive Z) (-0.2 / 31.5)",
    ])
    assert state.x == pytest.approx(-123.456)
    assert state.y == pytest.approx(64.0)
    assert state.z == pytest.approx(789.012)
    assert state.yaw == pytest.approx(-0.2)
    assert state.pitch == pytest.approx(31.5)


def test_eye_sits_1_62_above_the_feet():
    state = parse(["XYZ: 0 / 64 / 0", "Facing: north (0 / 0)"])
    assert state.eye == (0.0, pytest.approx(65.62), 0.0)


def test_yaw_is_normalised_into_range():
    state = parse(["XYZ: 0 / 64 / 0", "Facing: north (359.5 / 0)"])
    assert state.yaw == pytest.approx(-0.5)


def test_unreadable_glyphs_do_not_produce_a_wrong_coordinate():
    # A '?' means the matcher was unsure. Parsing "1?3" as 13 would fly the
    # character somewhere entirely wrong, so the line has to be discarded.
    with pytest.raises(F3ReadError, match="XYZ"):
        parse(["XYZ: 1?3.4 / 64.0 / 20.0", "Facing: north (0 / 0)"])


def test_missing_facing_line_is_reported_separately():
    with pytest.raises(F3ReadError, match="Facing"):
        parse(["XYZ: 1.0 / 64.0 / 2.0"])


@pytest.mark.parametrize(
    "current,target,expected",
    [
        (170.0, -170.0, 20.0),    # across the wrap, the short way
        (-170.0, 170.0, -20.0),
        (0.0, 90.0, 90.0),
        (90.0, 0.0, -90.0),
    ],
)
def test_yaw_delta_takes_the_short_way_round(current, target, expected):
    assert yaw_delta(current, target) == pytest.approx(expected)


def test_normalise_yaw_maps_onto_a_half_open_range():
    assert normalise_yaw(360.0) == pytest.approx(0.0)
    assert normalise_yaw(-180.0) == pytest.approx(180.0)
    assert normalise_yaw(540.0) == pytest.approx(180.0)
