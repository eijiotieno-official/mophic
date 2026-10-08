"""Layer list / editor mutation tests via MophicWindow."""

import pytest

from core import Color, Composition, Point, ShapeLayer
from core.renderer import CairoRenderer
from examples.demo_project import build_demo_composition
from mophic.playback import FrameCache
from conftest import make_window, requires_display


@requires_display
def test_initial_layers_and_title_selection(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        names = [layer.name for layer in win.composition.layers]
        assert 'Title' in names
        assert win.selected_layer().name == 'Title'
        assert win.layer_list.selected_layer_id == win.selected_layer().id
        display = [win.layer_list._store.get_item(i).name  # noqa: SLF001
                   for i in range(win.layer_list._store.get_n_items())]  # noqa: SLF001
        assert display[0] == names[-1]
        assert display[-1] == names[0]
    finally:
        win.destroy()


@requires_display
@pytest.mark.parametrize('kind', ['text', 'rectangle', 'ellipse', 'line', 'solid', 'image'])
def test_add_layer_kinds(window_class, app, kind):
    win = make_window(window_class, app, composition=Composition(width=200, height=100))
    try:
        before = len(win.composition.layers)
        win.add_layer_kind(kind)
        assert len(win.composition.layers) == before + 1
        selected = win.selected_layer()
        assert selected is win.composition.layers[-1]
        assert selected.id == win.layer_list.selected_layer_id
    finally:
        win.destroy()


@requires_display
def test_delete_selects_neighbour(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = next(layer for layer in win.composition.layers if layer.name == 'Title')
        win._selected_id = title.id
        win.layer_list.resync(win.composition, title.id)
        win.delete_selected()
        assert not win.composition.has_layer(title.id)
        # Display order places Subtitle above Title, so it becomes the neighbour.
        assert win.selected_layer() is not None
        assert win.selected_layer().name == 'Subtitle'
    finally:
        win.destroy()


@requires_display
def test_delete_last_layer_clears_selection(window_class, app):
    comp = Composition(width=100, height=100)
    win = make_window(window_class, app, composition=comp)
    try:
        win.add_layer_kind('solid')
        assert len(win.composition.layers) == 1
        win.delete_selected()
        assert win.composition.layers == ()
        assert win.selected_layer() is None
    finally:
        win.destroy()


@requires_display
def test_duplicate_has_independent_animatable_state(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        title = next(layer for layer in win.composition.layers if layer.name == 'Title')
        win._selected_id = title.id
        win.layer_list.resync(win.composition, title.id)
        win.duplicate_selected()
        dup = win.selected_layer()
        assert dup.id != title.id
        assert dup.position is not title.position
        assert dup.opacity is not title.opacity
        assert dup.position.keyframes == title.position.keyframes
        original_base = title.position.base_value
        dup.position.base_value = Point(12, 34)
        assert title.position.base_value == original_base
        assert title.position.value_at(1.0) != Point(12, 34)
    finally:
        win.destroy()


@requires_display
def test_rename_updates_core_and_row(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        layer = win.selected_layer()
        win.rename_selected('Opening Title')
        assert layer.name == 'Opening Title'
        item = win.layer_list._selection.get_selected_item()  # noqa: SLF001
        assert item.name == 'Opening Title'
    finally:
        win.destroy()


@requires_display
def test_visibility_toggle_updates_core_and_pixels(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        logo = next(layer for layer in win.composition.layers if layer.name == 'Logo')
        cache = FrameCache(CairoRenderer(), win.composition)
        before = bytes(cache.frame_at(2.0).surface.get_data())
        win._on_visibility(logo.id, False)
        assert logo.visible is False
        cache.invalidate()
        after = bytes(cache.frame_at(2.0).surface.get_data())
        assert before != after
        win._on_visibility(logo.id, True)
        assert logo.visible is True
    finally:
        win.destroy()


@requires_display
def test_move_up_down_changes_composition_order(window_class, app):
    win = make_window(window_class, app, composition=build_demo_composition())
    try:
        line = next(layer for layer in win.composition.layers if layer.name == 'Line')
        win._selected_id = line.id
        win.layer_list.resync(win.composition, line.id)
        old = win.composition.index_of(line.id)
        win.move_selected(1)  # up toward top
        assert win.composition.index_of(line.id) == old + 1
        win.move_selected(-1)
        assert win.composition.index_of(line.id) == old
    finally:
        win.destroy()


@requires_display
def test_reorder_changes_rendered_stacking(window_class, app):
    comp = Composition(width=40, height=40, background_color=Color(0, 0, 0, 1))
    bottom = ShapeLayer(name='Bottom', width=30, height=30, fill_color=Color(1, 0, 0, 1),
                        position=Point(20, 20))
    top = ShapeLayer(name='Top', width=30, height=30, fill_color=Color(0, 0, 1, 1),
                     position=Point(20, 20))
    comp.add_layer(bottom)
    comp.add_layer(top)
    win = make_window(window_class, app, composition=comp)
    try:
        renderer = CairoRenderer()
        assert renderer.render_frame(comp, 0).pixel(20, 20) == (0, 0, 255, 255)
        win._selected_id = top.id
        win.move_selected(-1)  # move top down → becomes bottom
        assert win.composition.layers[0].id == top.id
        win.frames.invalidate()
        assert renderer.render_frame(comp, 0).pixel(20, 20) == (255, 0, 0, 255)
    finally:
        win.destroy()
