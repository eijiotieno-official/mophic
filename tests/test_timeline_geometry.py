"""Pure timeline geometry tests."""

import pytest

from mophic.timeline_geometry import (
    LABEL_WIDTH,
    TimelineView,
    clamp_zoom,
    hit_test_keyframe,
    ruler_ticks,
    snap_time,
    time_to_x,
    track_at_y,
    track_y,
    x_to_time,
)


def test_snap_time_to_frames():
    assert snap_time(0.0, 30.0, 5.0) == 0.0
    assert snap_time(1.0 / 30 + 0.001, 30.0, 5.0) == pytest.approx(1.0 / 30)
    assert snap_time(100.0, 30.0, 5.0) == pytest.approx((5 * 30 - 1) / 30)
    assert snap_time(-1.0, 30.0, 5.0) == 0.0


def test_time_x_round_trip():
    view = TimelineView(duration=5.0, fps=30.0, px_per_second=100.0)
    for t in (0.0, 1.5, 4.9):
        x = time_to_x(t, view)
        assert x == pytest.approx(LABEL_WIDTH + t * 100.0)
        assert x_to_time(x, view) == pytest.approx(t)


def test_clamp_zoom():
    assert clamp_zoom(1) == 20.0
    assert clamp_zoom(1000) == 400.0
    assert clamp_zoom(80) == 80.0


def test_ruler_ticks_cover_duration():
    view = TimelineView(duration=5.0, fps=30.0, px_per_second=80.0)
    ticks = ruler_ticks(view)
    assert ticks[0][0] == 0.0
    assert ticks[-1][0] >= 5.0 - 1e-9


def test_track_y_and_hit():
    assert track_at_y(10) is None
    assert track_at_y(track_y(0) + 5) == 0
    assert track_at_y(track_y(2) + 5) == 2


def test_hit_test_keyframe():
    view = TimelineView(duration=5.0, fps=30.0, px_per_second=100.0)
    tracks = {'position': [1.0, 2.0], 'scale': [], 'rotation': [], 'opacity': [0.5]}
    x = time_to_x(1.0, view)
    y = track_y(0) + 14
    hit = hit_test_keyframe(x, y, tracks, view)
    assert hit is not None
    assert hit.track == 'position'
    assert hit.time == pytest.approx(1.0)
    assert hit_test_keyframe(x, track_y(1) + 14, tracks, view) is None
