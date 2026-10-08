import math

import pytest

from core.easing import (EASE_IN, EASE_IN_OUT, EASE_OUT, LINEAR, Easing,
                         cubic_bezier)

PRESETS = [LINEAR, EASE_IN, EASE_OUT, EASE_IN_OUT]
SAMPLES = [i / 100 for i in range(101)]


@pytest.mark.parametrize('easing', PRESETS + [cubic_bezier(0.25, 0.1, 0.25, 1.0)])
def test_endpoints_are_exact(easing):
    assert easing.ease(0.0) == 0.0
    assert easing.ease(1.0) == 1.0
    assert easing.ease(0) == 0.0
    assert easing.ease(1) == 1.0


def test_linear_is_identity():
    for t in SAMPLES:
        assert LINEAR.ease(t) == t


def test_ease_in_starts_slow():
    assert EASE_IN.ease(0.5) == 0.25
    for t in SAMPLES[1:-1]:
        assert EASE_IN.ease(t) < t


def test_ease_out_finishes_slow():
    assert EASE_OUT.ease(0.5) == 0.75
    for t in SAMPLES[1:-1]:
        assert EASE_OUT.ease(t) > t


def test_ease_in_and_ease_out_mirror_each_other():
    for t in SAMPLES:
        assert EASE_IN.ease(t) == pytest.approx(1.0 - EASE_OUT.ease(1.0 - t))


def test_ease_in_out_is_smoothstep():
    assert EASE_IN_OUT.ease(0.5) == 0.5
    assert EASE_IN_OUT.ease(0.25) == pytest.approx(0.15625)
    for t in SAMPLES:
        assert EASE_IN_OUT.ease(t) == pytest.approx(1.0 - EASE_IN_OUT.ease(1.0 - t))


@pytest.mark.parametrize('easing', PRESETS + [
    cubic_bezier(0.25, 0.1, 0.25, 1.0),
    cubic_bezier(0.42, 0.0, 0.58, 1.0),
    cubic_bezier(0.9, 0.0, 0.1, 1.0),
])
def test_curves_never_decrease(easing):
    values = [easing.ease(t) for t in SAMPLES]
    assert values == sorted(values)


def test_bezier_matches_known_css_ease_value():
    # CSS "ease" at x = 0.5 is approximately 0.8024.
    assert cubic_bezier(0.25, 0.1, 0.25, 1.0).ease(0.5) == pytest.approx(0.8024, abs=1e-4)


def test_bezier_with_linear_control_points_is_identity():
    curve = cubic_bezier(0.0, 0.0, 1.0, 1.0)
    for t in SAMPLES:
        assert curve.ease(t) == pytest.approx(t, abs=1e-9)


def test_bezier_css_ease_in_and_ease_out_mirror_each_other():
    ease_in = cubic_bezier(0.42, 0.0, 1.0, 1.0)
    ease_out = cubic_bezier(0.0, 0.0, 0.58, 1.0)
    for t in SAMPLES:
        assert ease_in.ease(t) == pytest.approx(1.0 - ease_out.ease(1.0 - t), abs=1e-9)


def test_bezier_solves_for_x_instead_of_using_input_as_parameter():
    x1, y1, x2, y2 = 0.9, 0.0, 0.1, 1.0
    curve = cubic_bezier(x1, y1, x2, y2)

    def coordinate(s, p1, p2):
        return 3 * (1 - s) ** 2 * s * p1 + 3 * (1 - s) * s * s * p2 + s ** 3

    x = 0.3
    naive = coordinate(x, y1, y2)
    result = curve.ease(x)
    assert abs(result - naive) > 0.05

    # The returned y belongs to the curve point whose x is the input.
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2
        if coordinate(mid, x1, x2) < x:
            low = mid
        else:
            high = mid
    assert result == pytest.approx(coordinate(low, y1, y2), abs=1e-9)


def test_bezier_is_deterministic():
    curve = cubic_bezier(0.3, 0.7, 0.4, 1.2)
    assert [curve.ease(t) for t in SAMPLES] == [curve.ease(t) for t in SAMPLES]


def test_bezier_y_may_overshoot():
    curve = cubic_bezier(0.3, 0.0, 0.5, 1.6)
    assert max(curve.ease(t) for t in SAMPLES) > 1.0


@pytest.mark.parametrize('points', [(-0.1, 0.0, 0.5, 1.0), (0.5, 0.0, 1.1, 1.0)])
def test_bezier_rejects_x_outside_unit_interval(points):
    with pytest.raises(ValueError):
        cubic_bezier(*points)


def test_bezier_rejects_non_finite_and_non_numeric_control_points():
    with pytest.raises(ValueError):
        cubic_bezier(0.5, math.nan, 0.5, 1.0)
    with pytest.raises(TypeError):
        cubic_bezier(0.5, '0', 0.5, 1.0)
    with pytest.raises(TypeError):
        cubic_bezier(True, 0.0, 0.5, 1.0)


def test_bezier_requires_all_control_points():
    with pytest.raises(ValueError):
        Easing('cubic-bezier', 0.1, 0.2, 0.3)


def test_presets_reject_control_points():
    with pytest.raises(ValueError):
        Easing('linear', 0.1, 0.2, 0.3, 0.4)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        Easing('bounce')


@pytest.mark.parametrize('progress', [-0.01, 1.01, math.nan, math.inf])
def test_progress_outside_unit_interval_is_rejected(progress):
    with pytest.raises(ValueError):
        LINEAR.ease(progress)


def test_progress_must_be_numeric():
    with pytest.raises(TypeError):
        LINEAR.ease('0.5')
    with pytest.raises(TypeError):
        LINEAR.ease(True)
