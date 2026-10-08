import math

import pytest

from core.layers import ShapeLayer, SolidLayer, TextLayer
from core.project import (PROJECT_FORMAT, PROJECT_VERSION, Composition,
                          Project)
from core.properties import Color

# Composition settings


def test_composition_defaults():
    comp = Composition()
    assert (comp.width, comp.height) == (1920, 1080)
    assert comp.fps == 30.0
    assert comp.duration == 30.0
    assert comp.background_color == Color(0.0, 0.0, 0.0, 1.0)
    assert comp.layers == ()
    assert comp.name == 'Main'


def test_composition_ids_are_unique():
    assert Composition().id != Composition().id
    assert Composition(id='main').id == 'main'


@pytest.mark.parametrize('kwargs', [
    {'width': 0}, {'width': -1}, {'height': 0},
    {'fps': 0}, {'fps': -24.0}, {'fps': math.nan}, {'fps': math.inf},
    {'duration': -0.001}, {'duration': math.nan},
])
def test_composition_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Composition(**kwargs)


@pytest.mark.parametrize('kwargs', [
    {'width': 1920.0}, {'width': True}, {'height': '1080'},
    {'fps': '30'}, {'fps': True}, {'duration': None},
    {'background_color': (0, 0, 0, 1)}, {'name': None},
])
def test_composition_rejects_wrong_types(kwargs):
    with pytest.raises(TypeError):
        Composition(**kwargs)


def test_zero_duration_is_allowed():
    comp = Composition(duration=0)
    assert comp.duration == 0.0
    assert comp.frame_count == 0


def test_setters_validate_without_clamping():
    comp = Composition()
    with pytest.raises(ValueError):
        comp.fps = 0
    assert comp.fps == 30.0
    comp.fps = 24
    assert comp.fps == 24.0
    assert isinstance(comp.fps, float)


# Time model


def test_frame_at_time_boundaries_at_30_fps():
    comp = Composition(fps=30.0, duration=30.0)
    assert comp.frame_at_time(0.0) == 0
    assert comp.frame_at_time(1 / 30) == 1
    assert comp.frame_at_time(2 / 30) == 2
    assert comp.frame_at_time(1 / 30 - 1e-6) == 0
    assert comp.frame_at_time(1.0) == 30
    assert comp.frame_at_time(comp.duration) == 900


def test_frame_time_round_trip_is_exact_for_every_frame():
    comp = Composition(fps=30.0, duration=30.0)
    for frame in range(comp.frame_count + 1):
        assert comp.frame_at_time(comp.time_at_frame(frame)) == frame


def test_frame_round_trip_with_fractional_fps():
    comp = Composition(fps=30000 / 1001, duration=60.0)
    for frame in range(comp.frame_count + 1):
        assert comp.frame_at_time(comp.time_at_frame(frame)) == frame


def test_time_at_frame():
    comp = Composition(fps=30.0)
    assert comp.time_at_frame(0) == 0.0
    assert comp.time_at_frame(30) == 1.0
    assert comp.time_at_frame(1) == 1 / 30


def test_frame_count_treats_duration_as_exclusive_end():
    assert Composition(fps=30.0, duration=30.0).frame_count == 900
    assert Composition(fps=30.0, duration=1.0).frame_count == 30
    assert Composition(fps=30.0, duration=1.01).frame_count == 31
    assert Composition(fps=24.0, duration=0.5).frame_count == 12


def test_time_helpers_reject_invalid_input():
    comp = Composition()
    with pytest.raises(ValueError):
        comp.frame_at_time(-0.1)
    with pytest.raises(ValueError):
        comp.frame_at_time(math.nan)
    with pytest.raises(ValueError):
        comp.time_at_frame(-1)
    with pytest.raises(TypeError):
        comp.time_at_frame(1.0)


# Layer stack


def make_stack():
    comp = Composition()
    bottom, middle, top = SolidLayer(name='bottom'), ShapeLayer(name='middle'), TextLayer(name='top')
    for layer in (bottom, middle, top):
        comp.add_layer(layer)
    return comp, bottom, middle, top


def test_add_layer_puts_new_layers_on_top():
    comp, bottom, middle, top = make_stack()
    assert comp.layers == (bottom, middle, top)
    assert comp.layers[0] is bottom
    assert comp.layers[-1] is top


def test_add_layer_at_index():
    comp, bottom, middle, top = make_stack()
    inserted = SolidLayer(name='inserted')
    comp.add_layer(inserted, 0)
    assert comp.layers[0] is inserted


def test_add_layer_rejects_duplicate_ids_and_bad_input():
    comp, bottom, _, _ = make_stack()
    with pytest.raises(ValueError):
        comp.add_layer(bottom)
    with pytest.raises(ValueError):
        comp.add_layer(SolidLayer(id=bottom.id))
    with pytest.raises(TypeError):
        comp.add_layer('layer')
    with pytest.raises(IndexError):
        comp.add_layer(SolidLayer(), 10)
    assert len(comp.layers) == 3


def test_get_layer_and_index_of():
    comp, bottom, middle, top = make_stack()
    assert comp.get_layer(middle.id) is middle
    assert comp.index_of(top.id) == 2
    assert comp.has_layer(bottom.id)
    with pytest.raises(KeyError):
        comp.get_layer('missing')
    assert not comp.has_layer('missing')


def test_remove_layer_returns_its_index():
    comp, bottom, middle, top = make_stack()
    assert comp.remove_layer(middle.id) == 1
    assert comp.layers == (bottom, top)
    with pytest.raises(KeyError):
        comp.remove_layer(middle.id)


def test_move_layer():
    comp, bottom, middle, top = make_stack()
    comp.move_layer(bottom.id, 2)
    assert comp.layers == (middle, top, bottom)
    comp.move_layer(bottom.id, 0)
    assert comp.layers == (bottom, middle, top)
    with pytest.raises(IndexError):
        comp.move_layer(bottom.id, 3)
    with pytest.raises(KeyError):
        comp.move_layer('missing', 0)
    with pytest.raises(TypeError):
        comp.move_layer(bottom.id, 1.0)


def test_layers_tuple_cannot_modify_the_stack():
    comp, *_ = make_stack()
    layers = comp.layers
    with pytest.raises(AttributeError):
        layers.append(SolidLayer())
    assert len(comp.layers) == 3


# Project


def test_project_format_and_version():
    project = Project(name='Demo')
    assert project.format == PROJECT_FORMAT == 'aemvp'
    assert project.version == PROJECT_VERSION == 1
    assert project.name == 'Demo'
    assert project.compositions == ()


def test_project_holds_multiple_compositions():
    project = Project()
    first, second = Composition(name='A'), Composition(name='B')
    project.add_composition(first)
    project.add_composition(second)
    assert project.compositions == (first, second)
    assert project.get_composition(second.id) is second
    assert project.remove_composition(first.id) == 0
    assert project.compositions == (second,)


def test_project_rejects_duplicate_and_invalid_compositions():
    project = Project()
    comp = Composition()
    project.add_composition(comp)
    with pytest.raises(ValueError):
        project.add_composition(Composition(id=comp.id))
    with pytest.raises(TypeError):
        project.add_composition('comp')
    with pytest.raises(KeyError):
        project.get_composition('missing')


def test_project_format_is_read_only():
    with pytest.raises(AttributeError):
        Project().format = 'other'
