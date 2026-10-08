"""Timeline widget and keyframe interaction tests."""

import pytest

from core.commands import MoveKeyframeCommand, RemoveKeyframeCommand, SetKeyframeCommand
from core.easing import EASE_IN, LINEAR
from examples.demo_project import build_demo_composition
from conftest import make_window, requires_display


def select(win, name: str):
    layer = next(layer for layer in win.composition.layers if layer.name == name)
    win._selected_id = layer.id
    win.layer_list.resync(win.composition, layer.id)
    win._bind_properties()
    win._bind_timeline()
    return layer


@requires_display
def test_timeline_hosts_selected_layer(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        assert win.timeline is not None
        title = select(win, 'Title')
        assert win.timeline._layer is title  # noqa: SLF001
        win.playback.set_time(1.0)
        win._refresh()
        assert win.timeline._time == pytest.approx(1.0)  # noqa: SLF001
    finally:
        win.destroy()


@requires_display
def test_create_and_remove_keyframe_via_toggle(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Subtitle')
        assert not layer.opacity.is_animated
        win.playback.set_time(0.5)
        win._on_property_edit('toggle_keyframe', 'opacity')
        assert layer.opacity.has_keyframe(0.5)
        win._on_property_edit('toggle_keyframe', 'opacity')
        assert not layer.opacity.has_keyframe(0.5)
    finally:
        win.destroy()


@requires_display
def test_animated_edit_sets_keyframe_at_playhead(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = select(win, 'Title')
        win.playback.set_time(1.0)
        assert title.position.is_animated
        win._on_property_edit('position_x', 999.0)
        kf = title.position.get_keyframe(1.0)
        assert kf is not None
        assert kf.value.x == pytest.approx(999.0)
    finally:
        win.destroy()


@requires_display
def test_move_keyframe_command_from_timeline(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = select(win, 'Title')
        old = title.position.keyframes[0].time
        new = 1.0 / win.composition.fps
        if abs(old - new) < 1e-9:
            new = 2.0 / win.composition.fps
        # Avoid colliding with an existing keyframe.
        while title.position.get_keyframe(new) is not None:
            new += 1.0 / win.composition.fps
        win._on_move_keyframe('position', old, new)
        assert title.position.get_keyframe(new) is not None
        assert title.position.get_keyframe(old) is None
    finally:
        win.destroy()


@requires_display
def test_delete_selected_keyframe(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = select(win, 'Title')
        time = title.position.keyframes[0].time
        win._selected_kf = ('position', time)
        win.delete_selected()
        assert title.position.get_keyframe(time) is None
    finally:
        win.destroy()


@requires_display
def test_easing_edit_for_selected_keyframe(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = select(win, 'Title')
        time = title.position.keyframes[0].time
        win._selected_kf = ('position', time)
        win.properties.set_selected_keyframe('position', time)
        win._on_property_edit('keyframe_easing', EASE_IN)
        assert title.position.get_keyframe(time).easing == EASE_IN
    finally:
        win.destroy()


def test_keyframe_commands_round_trip():
    composition = build_demo_composition()
    layer = next(layer for layer in composition.layers if layer.name == 'Subtitle')
    prop = layer.opacity
    cmd = SetKeyframeCommand(prop, 0.5, 0.25, LINEAR)
    cmd.do()
    assert prop.has_keyframe(0.5)
    MoveKeyframeCommand(prop, 0.5, 1.0).do()
    assert prop.has_keyframe(1.0)
    RemoveKeyframeCommand(prop, 1.0).do()
    assert not prop.is_animated
