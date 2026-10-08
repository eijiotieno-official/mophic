"""Properties panel editing tests via MophicWindow."""

import pytest

from core import Color, Composition, Point, Scale, ShapeLayer, SolidLayer, TextLayer
from core.renderer import CairoRenderer
from examples.demo_project import build_demo_composition
from mophic.playback import FrameCache
from conftest import make_window, requires_display


def select(win, name: str):
    layer = next(layer for layer in win.composition.layers if layer.name == name)
    win._selected_id = layer.id
    win.layer_list.resync(win.composition, layer.id)
    win._bind_properties()
    return layer


@requires_display
def test_transform_edits_update_core(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Subtitle')
        win._on_property_edit('position_x', 111.0)
        win._on_property_edit('position_y', 222.0)
        win._on_property_edit('scale_x', 150.0)
        win._on_property_edit('scale_y', 80.0)
        win._on_property_edit('rotation', 45.0)
        win._on_property_edit('opacity', 50.0)
        assert layer.position.base_value == Point(111.0, 222.0)
        assert layer.scale.base_value == Scale(150.0, 80.0)
        assert layer.rotation.base_value == 45.0
        assert layer.opacity.base_value == pytest.approx(0.5)
    finally:
        win.destroy()


@requires_display
def test_animated_property_edit_sets_keyframe_at_playhead(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = select(win, 'Title')
        win.playback.set_time(1.0)
        expected = title.position.value_at(1.0)
        base_before = title.position.base_value
        win._bind_properties()
        assert win.properties._pos_x.get_value() == pytest.approx(expected.x)  # noqa: SLF001
        assert win.properties._pos_y.get_value() == pytest.approx(expected.y)  # noqa: SLF001
        assert win.properties._pos_x.get_sensitive() is True  # noqa: SLF001
        win._on_property_edit('position_x', 999.0)
        assert title.position.base_value == base_before
        kf = title.position.get_keyframe(1.0)
        assert kf is not None
        assert kf.value.x == pytest.approx(999.0)
        assert title.position.value_at(1.0).x == pytest.approx(999.0)
    finally:
        win.destroy()


@requires_display
def test_bind_does_not_mutate_layer(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Subtitle')
        before = (layer.position.base_value, layer.scale.base_value, layer.rotation.base_value,
                  layer.opacity.base_value, layer.text, layer.color)
        for _ in range(3):
            win.properties.bind(layer, 0.0)
        assert (layer.position.base_value, layer.scale.base_value, layer.rotation.base_value,
                layer.opacity.base_value, layer.text, layer.color) == before
    finally:
        win.destroy()


@requires_display
def test_text_content_edit(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Subtitle')
        win._on_property_edit('text', 'Hello Phase 5')
        assert layer.text == 'Hello Phase 5'
    finally:
        win.destroy()


@requires_display
def test_solid_color_edit(window_class, app):
    win = make_window(window_class, app, composition=Composition(width=64, height=64))
    try:
        win.add_layer_kind('solid')
        layer = win.selected_layer()
        assert isinstance(layer, SolidLayer)
        win._on_property_edit('color', Color(1, 0, 0, 1))
        assert layer.color == Color(1, 0, 0, 1)
    finally:
        win.destroy()


@requires_display
def test_shape_fill_and_size_edit(window_class, app):
    win = make_window(window_class, app, composition=Composition(width=64, height=64))
    try:
        win.add_layer_kind('rectangle')
        layer = win.selected_layer()
        assert isinstance(layer, ShapeLayer)
        win._on_property_edit('width', 50.0)
        win._on_property_edit('height', 25.0)
        win._on_property_edit('fill_color', Color(0, 1, 0, 1))
        assert layer.width == 50.0
        assert layer.height == 25.0
        assert layer.fill_color == Color(0, 1, 0, 1)
    finally:
        win.destroy()


@requires_display
def test_image_path_displayed(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Logo')
        assert win.properties._image_path.get_label() == layer.path  # noqa: SLF001
    finally:
        win.destroy()


@requires_display
def test_property_edit_changes_rendered_frame(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = select(win, 'Subtitle')
        cache = FrameCache(CairoRenderer(), win.composition)
        before = bytes(cache.frame_at(0.0).surface.get_data())
        win._on_property_edit('position_x', 200.0)
        win.frames.invalidate()
        cache.invalidate()
        after = bytes(cache.frame_at(0.0).surface.get_data())
        assert before != after
        assert layer.position.base_value.x == 200.0
    finally:
        win.destroy()


@requires_display
def test_play_after_edit_still_advances(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        select(win, 'Subtitle')
        win._on_property_edit('opacity', 80.0)
        win.activate_action('win.play-pause', None)
        assert win.playback.is_playing
        win.playback.advance(1_000_000)
        win.playback.advance(1_400_000)
        assert win.playback.current_time == pytest.approx(0.4)
    finally:
        win.destroy()


@requires_display
def test_selection_during_playback_keeps_playing(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        win.activate_action('win.play-pause', None)
        win.playback.advance(1_000_000)
        select(win, 'Logo')
        assert win.playback.is_playing
        assert win.selected_layer().name == 'Logo'
    finally:
        win.destroy()
