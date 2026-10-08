import math

import pytest

from core.easing import EASE_IN, EASE_OUT, LINEAR, cubic_bezier
from core.properties import (TIME_EPSILON, AnimatableProperty, Color,
                             Keyframe, Point, Scale, check_unit_interval,
                             interpolate)


def float_property(base=0.0, **kwargs):
    return AnimatableProperty(base, value_type=float, **kwargs)


# Value types


def test_point_and_scale_store_floats():
    point = Point(1, 2)
    assert point == Point(1.0, 2.0)
    assert isinstance(point.x, float)
    assert Scale() == Scale(100.0, 100.0)


@pytest.mark.parametrize('values', [(math.nan, 0), (0, math.inf)])
def test_vectors_reject_non_finite(values):
    with pytest.raises(ValueError):
        Point(*values)
    with pytest.raises(ValueError):
        Scale(*values)


def test_vectors_reject_non_numbers():
    with pytest.raises(TypeError):
        Point('1', 2)
    with pytest.raises(TypeError):
        Scale(True, 1)


def test_value_types_are_immutable():
    with pytest.raises(AttributeError):
        Point(1, 2).x = 5


def test_color_defaults_to_opaque_black():
    assert Color() == Color(0.0, 0.0, 0.0, 1.0)


@pytest.mark.parametrize('channels', [(1.1, 0, 0, 1), (0, -0.1, 0, 1), (0, 0, 0, 2)])
def test_color_rejects_out_of_range_channels(channels):
    with pytest.raises(ValueError):
        Color(*channels)


# interpolate


def test_interpolate_numbers():
    assert interpolate(0.0, 10.0, 0.25) == 2.5
    assert interpolate(0, 10, 0.5) == 5.0
    assert isinstance(interpolate(0, 10, 0.5), float)


def test_interpolate_point_component_wise():
    assert interpolate(Point(100, 200), Point(300, 400), 0.5) == Point(200, 300)


def test_interpolate_scale_component_wise():
    assert interpolate(Scale(100, 50), Scale(200, 150), 0.25) == Scale(125, 75)


@pytest.mark.parametrize('a, b', [
    (Point(0, 0), Scale(1, 1)),
    (1.0, Point(0, 0)),
    ('a', 'b'),
    (True, 1.0),
    ((0, 0), (1, 1)),
])
def test_interpolate_rejects_unsupported_combinations(a, b):
    with pytest.raises(TypeError):
        interpolate(a, b, 0.5)


# Keyframe


def test_keyframe_defaults_to_linear_easing():
    assert Keyframe(1.0, 5.0).easing == LINEAR


@pytest.mark.parametrize('time', [-1.0, math.nan, math.inf])
def test_keyframe_rejects_invalid_times(time):
    with pytest.raises(ValueError):
        Keyframe(time, 0.0)


def test_keyframe_rejects_non_easing():
    with pytest.raises(TypeError):
        Keyframe(0.0, 0.0, 'linear')


# Static behaviour


def test_no_keyframes_returns_base_value():
    prop = float_property(42.0)
    assert not prop.is_animated
    for time in (0.0, 1.0, 100.0):
        assert prop.value_at(time) == 42.0


def test_one_keyframe_returns_its_value_at_every_time():
    prop = float_property(0.0)
    prop.set_keyframe(2.0, 10.0)
    assert prop.is_animated
    for time in (0.0, 1.999, 2.0, 5.0):
        assert prop.value_at(time) == 10.0


# Multiple keyframes


def test_two_keyframes_evaluation_boundaries():
    prop = float_property(-1.0)
    prop.set_keyframe(1.0, 0.0)
    prop.set_keyframe(3.0, 100.0)
    assert prop.value_at(0.0) == 0.0
    assert prop.value_at(1.0) == 0.0
    assert prop.value_at(2.0) == 50.0
    assert prop.value_at(1.5) == 25.0
    assert prop.value_at(3.0) == 100.0
    assert prop.value_at(10.0) == 100.0


def test_three_keyframes_use_the_surrounding_pair():
    prop = float_property()
    prop.set_keyframe(0.0, 0.0)
    prop.set_keyframe(1.0, 10.0)
    prop.set_keyframe(2.0, 0.0)
    assert prop.value_at(0.5) == 5.0
    assert prop.value_at(1.0) == 10.0
    assert prop.value_at(1.5) == 5.0


def test_easing_of_earlier_keyframe_shapes_the_interval():
    prop = float_property()
    prop.set_keyframe(0.0, 0.0, EASE_OUT)
    prop.set_keyframe(1.0, 100.0, EASE_IN)
    assert prop.value_at(0.5) == pytest.approx(75.0)

    prop.set_keyframe_easing(0.0, EASE_IN)
    assert prop.value_at(0.5) == pytest.approx(25.0)


def test_cubic_bezier_easing_on_property():
    curve = cubic_bezier(0.25, 0.1, 0.25, 1.0)
    prop = float_property()
    prop.set_keyframe(0.0, 0.0, curve)
    prop.set_keyframe(2.0, 100.0)
    assert prop.value_at(1.0) == pytest.approx(100 * curve.ease(0.5))


def test_point_property_interpolates_position():
    prop = AnimatableProperty(Point(0, 0), value_type=Point)
    prop.set_keyframe(0.0, Point(100, 200))
    prop.set_keyframe(1.0, Point(300, 400))
    assert prop.value_at(0.5) == Point(200, 300)


def test_scale_property_interpolates():
    prop = AnimatableProperty(Scale(), value_type=Scale)
    prop.set_keyframe(0.0, Scale(100, 100))
    prop.set_keyframe(2.0, Scale(200, 50))
    assert prop.value_at(1.0) == Scale(150, 75)


# Keyframe operations


def test_keyframes_stay_sorted_regardless_of_insertion_order():
    prop = float_property()
    for time in (3.0, 1.0, 2.0, 0.0):
        prop.set_keyframe(time, time * 10)
    assert [k.time for k in prop.keyframes] == [0.0, 1.0, 2.0, 3.0]


def test_setting_existing_timestamp_updates_instead_of_duplicating():
    prop = float_property()
    prop.set_keyframe(1.0, 5.0)
    prop.set_keyframe(1.0, 7.0, EASE_IN)
    assert len(prop.keyframes) == 1
    assert prop.get_keyframe(1.0) == Keyframe(1.0, 7.0, EASE_IN)


def test_timestamps_within_epsilon_count_as_the_same():
    prop = float_property()
    prop.set_keyframe(1.0, 5.0)
    prop.set_keyframe(1.0 + TIME_EPSILON / 2, 6.0)
    assert len(prop.keyframes) == 1
    assert prop.keyframes[0].time == 1.0
    assert prop.has_keyframe(1.0 - TIME_EPSILON / 2)
    assert not prop.has_keyframe(1.0 + 10 * TIME_EPSILON)


def test_frame_aligned_times_are_distinct_keyframes():
    prop = float_property()
    prop.set_keyframe(1 / 30, 1.0)
    prop.set_keyframe(2 / 30, 2.0)
    assert len(prop.keyframes) == 2


def test_get_and_has_keyframe():
    prop = float_property()
    prop.set_keyframe(1.0, 5.0)
    assert prop.has_keyframe(1.0)
    assert not prop.has_keyframe(2.0)
    assert prop.get_keyframe(1.0).value == 5.0
    assert prop.get_keyframe(2.0) is None


def test_remove_keyframe():
    prop = float_property()
    prop.set_keyframe(1.0, 5.0)
    removed = prop.remove_keyframe(1.0)
    assert removed.value == 5.0
    assert prop.keyframes == ()


def test_remove_missing_keyframe_raises_key_error():
    with pytest.raises(KeyError):
        float_property().remove_keyframe(1.0)


def test_move_keyframe_keeps_order():
    prop = float_property()
    prop.set_keyframe(0.0, 0.0)
    prop.set_keyframe(1.0, 10.0, EASE_IN)
    prop.set_keyframe(2.0, 20.0)
    moved = prop.move_keyframe(1.0, 3.0)
    assert moved == Keyframe(3.0, 10.0, EASE_IN)
    assert [(k.time, k.value) for k in prop.keyframes] == [(0.0, 0.0), (2.0, 20.0), (3.0, 10.0)]


def test_move_keyframe_onto_existing_keyframe_is_rejected():
    prop = float_property()
    prop.set_keyframe(0.0, 0.0)
    prop.set_keyframe(1.0, 10.0)
    with pytest.raises(ValueError):
        prop.move_keyframe(0.0, 1.0)
    assert [k.value for k in prop.keyframes] == [0.0, 10.0]


def test_move_missing_keyframe_raises_key_error():
    with pytest.raises(KeyError):
        float_property().move_keyframe(0.0, 1.0)


def test_move_keyframe_to_negative_time_is_rejected():
    prop = float_property()
    prop.set_keyframe(1.0, 0.0)
    with pytest.raises(ValueError):
        prop.move_keyframe(1.0, -1.0)
    assert prop.has_keyframe(1.0)


def test_set_easing_on_missing_keyframe_raises_key_error():
    with pytest.raises(KeyError):
        float_property().set_keyframe_easing(1.0, EASE_IN)


def test_keyframes_cannot_be_mutated_from_outside():
    prop = float_property()
    prop.set_keyframe(0.0, 1.0)
    keyframes = prop.keyframes
    assert isinstance(keyframes, tuple)
    with pytest.raises(AttributeError):
        keyframes.append(Keyframe(5.0, 5.0))
    with pytest.raises(AttributeError):
        prop.keyframes = ()


# Validation


def test_float_property_accepts_int_and_stores_float():
    prop = float_property(1)
    assert prop.base_value == 1.0
    assert isinstance(prop.base_value, float)
    keyframe = prop.set_keyframe(0, 3)
    assert isinstance(keyframe.value, float)


@pytest.mark.parametrize('value', [True, '1', None, Point(0, 0)])
def test_float_property_rejects_wrong_types(value):
    prop = float_property()
    with pytest.raises(TypeError):
        prop.base_value = value
    with pytest.raises(TypeError):
        prop.set_keyframe(0.0, value)
    assert prop.keyframes == ()


def test_point_property_rejects_other_types():
    prop = AnimatableProperty(Point(), value_type=Point)
    with pytest.raises(TypeError):
        prop.set_keyframe(0.0, Scale())
    with pytest.raises(TypeError):
        prop.base_value = (1, 2)


def test_validator_rejects_out_of_range_values_without_changing_state():
    prop = float_property(1.0, validator=check_unit_interval)
    with pytest.raises(ValueError):
        prop.base_value = 1.5
    with pytest.raises(ValueError):
        prop.set_keyframe(0.0, -0.1)
    assert prop.base_value == 1.0
    assert prop.keyframes == ()


def test_constructor_validates_base_value():
    with pytest.raises(ValueError):
        float_property(2.0, validator=check_unit_interval)


def test_unsupported_value_type_is_rejected():
    with pytest.raises(TypeError):
        AnimatableProperty('a', value_type=str)


def test_value_at_rejects_non_finite_time():
    with pytest.raises(ValueError):
        float_property().value_at(math.nan)


def test_property_equality_compares_values_and_keyframes():
    a = float_property(1.0)
    b = float_property(1.0)
    assert a == b
    a.set_keyframe(0.0, 2.0)
    assert a != b
