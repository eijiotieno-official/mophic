import pytest

from core.commands import (AddLayerCommand, MoveKeyframeCommand,
                           MoveLayerCommand, RemoveKeyframeCommand,
                           RemoveLayerCommand, SetAttributeCommand,
                           SetKeyframeCommand, SetKeyframeEasingCommand,
                           SetPropertyValueCommand, UndoStack)
from core.easing import EASE_IN, EASE_OUT, LINEAR
from core.layers import ShapeLayer, SolidLayer, TextLayer
from core.project import Composition, Project
from core.properties import Color, Keyframe, Point
from core.serialization import load_project, project_to_dict, save_project


@pytest.fixture
def comp():
    comp = Composition()
    comp.add_layer(SolidLayer(name='bottom'))
    comp.add_layer(TextLayer(name='top'))
    return comp


@pytest.fixture
def stack():
    return UndoStack()


def ids(comp):
    return [layer.id for layer in comp.layers]


def test_add_layer(comp, stack):
    before = ids(comp)
    layer = ShapeLayer(name='box')
    stack.execute(AddLayerCommand(comp, layer))
    assert ids(comp) == before + [layer.id]
    stack.undo()
    assert ids(comp) == before
    stack.redo()
    assert ids(comp) == before + [layer.id]


def test_add_layer_at_index(comp, stack):
    layer = ShapeLayer()
    stack.execute(AddLayerCommand(comp, layer, 0))
    assert comp.layers[0] is layer
    stack.undo()
    stack.redo()
    assert comp.layers[0] is layer


def test_remove_layer_restores_same_object_and_position(comp, stack):
    bottom = comp.layers[0]
    before = ids(comp)
    stack.execute(RemoveLayerCommand(comp, bottom.id))
    assert not comp.has_layer(bottom.id)
    stack.undo()
    assert ids(comp) == before
    assert comp.layers[0] is bottom
    stack.redo()
    assert not comp.has_layer(bottom.id)


def test_move_layer(comp, stack):
    bottom, top = comp.layers
    stack.execute(MoveLayerCommand(comp, bottom.id, 1))
    assert comp.layers == (top, bottom)
    stack.undo()
    assert comp.layers == (bottom, top)
    stack.redo()
    assert comp.layers == (top, bottom)


def test_set_layer_attribute(comp, stack):
    text = comp.layers[1]
    stack.execute(SetAttributeCommand(text, 'text', 'Hello'))
    stack.execute(SetAttributeCommand(text, 'color', Color(1, 0, 0, 1)))
    stack.execute(SetAttributeCommand(text, 'visible', False))
    assert (text.text, text.color, text.visible) == ('Hello', Color(1, 0, 0, 1), False)
    stack.undo()
    stack.undo()
    stack.undo()
    assert (text.text, text.color, text.visible) == ('Text', Color(1, 1, 1, 1), True)
    stack.redo()
    assert text.text == 'Hello'


def test_set_composition_attribute(comp, stack):
    stack.execute(SetAttributeCommand(comp, 'fps', 24.0))
    assert comp.fps == 24.0
    stack.undo()
    assert comp.fps == 30.0


def test_set_attribute_rejects_unknown_and_read_only_names(comp):
    layer = comp.layers[0]
    with pytest.raises(AttributeError):
        SetAttributeCommand(layer, 'does_not_exist', 1)
    with pytest.raises(AttributeError):
        SetAttributeCommand(layer, 'id', 'new')
    with pytest.raises(AttributeError):
        SetAttributeCommand(layer, 'position', Point(1, 1))


def test_set_property_value(comp, stack):
    layer = comp.layers[0]
    stack.execute(SetPropertyValueCommand(layer.position, Point(10, 20)))
    assert layer.position.base_value == Point(10, 20)
    stack.undo()
    assert layer.position.base_value == Point(0, 0)
    stack.redo()
    assert layer.position.value_at(0) == Point(10, 20)


def test_set_keyframe_new(comp, stack):
    opacity = comp.layers[0].opacity
    stack.execute(SetKeyframeCommand(opacity, 1.0, 0.5, EASE_IN))
    assert opacity.keyframes == (Keyframe(1.0, 0.5, EASE_IN),)
    stack.undo()
    assert opacity.keyframes == ()
    stack.redo()
    assert opacity.keyframes == (Keyframe(1.0, 0.5, EASE_IN),)


def test_set_keyframe_replacing_existing_restores_previous(comp, stack):
    opacity = comp.layers[0].opacity
    opacity.set_keyframe(1.0, 0.2, EASE_OUT)
    stack.execute(SetKeyframeCommand(opacity, 1.0, 0.9))
    assert opacity.keyframes == (Keyframe(1.0, 0.9, LINEAR),)
    stack.undo()
    assert opacity.keyframes == (Keyframe(1.0, 0.2, EASE_OUT),)


def test_remove_keyframe(comp, stack):
    rotation = comp.layers[0].rotation
    rotation.set_keyframe(0.0, 0.0)
    rotation.set_keyframe(1.0, 90.0, EASE_IN)
    stack.execute(RemoveKeyframeCommand(rotation, 1.0))
    assert len(rotation.keyframes) == 1
    stack.undo()
    assert rotation.get_keyframe(1.0) == Keyframe(1.0, 90.0, EASE_IN)
    stack.redo()
    assert not rotation.has_keyframe(1.0)


def test_move_keyframe(comp, stack):
    rotation = comp.layers[0].rotation
    rotation.set_keyframe(0.0, 0.0)
    rotation.set_keyframe(1.0, 90.0, EASE_IN)
    stack.execute(MoveKeyframeCommand(rotation, 1.0, 2.5))
    assert [k.time for k in rotation.keyframes] == [0.0, 2.5]
    stack.undo()
    assert rotation.keyframes == (Keyframe(0.0, 0.0), Keyframe(1.0, 90.0, EASE_IN))
    stack.redo()
    assert rotation.get_keyframe(2.5) == Keyframe(2.5, 90.0, EASE_IN)


def test_set_keyframe_easing(comp, stack):
    rotation = comp.layers[0].rotation
    rotation.set_keyframe(0.0, 0.0)
    stack.execute(SetKeyframeEasingCommand(rotation, 0.0, EASE_OUT))
    assert rotation.get_keyframe(0.0).easing == EASE_OUT
    stack.undo()
    assert rotation.get_keyframe(0.0).easing == LINEAR
    stack.redo()
    assert rotation.get_keyframe(0.0).easing == EASE_OUT


# Undo stack behaviour


def test_empty_stack(stack):
    assert not stack.can_undo
    assert not stack.can_redo
    assert stack.undo_description is None
    assert stack.redo_description is None
    with pytest.raises(IndexError):
        stack.undo()
    with pytest.raises(IndexError):
        stack.redo()


def test_descriptions_and_flags(comp, stack):
    stack.execute(SetAttributeCommand(comp.layers[0], 'name', 'Background'))
    assert stack.can_undo and not stack.can_redo
    assert stack.undo_description == 'Change name'
    stack.undo()
    assert stack.can_redo and not stack.can_undo
    assert stack.redo_description == 'Change name'


def test_new_command_clears_redo(comp, stack):
    layer = comp.layers[0]
    stack.execute(SetAttributeCommand(layer, 'name', 'one'))
    stack.undo()
    assert stack.can_redo
    stack.execute(SetAttributeCommand(layer, 'name', 'two'))
    assert not stack.can_redo
    assert layer.name == 'two'


def test_failing_command_is_not_recorded_and_changes_nothing(comp, stack):
    layer = comp.layers[0]
    before = project_snapshot(comp)
    with pytest.raises(ValueError):
        stack.execute(SetPropertyValueCommand(layer.opacity, 2.0))
    with pytest.raises(TypeError):
        stack.execute(SetAttributeCommand(layer, 'visible', 'no'))
    with pytest.raises(KeyError):
        stack.execute(RemoveKeyframeCommand(layer.opacity, 5.0))
    with pytest.raises(ValueError):
        stack.execute(AddLayerCommand(comp, layer))
    with pytest.raises(IndexError):
        stack.execute(MoveLayerCommand(comp, layer.id, 9))
    assert not stack.can_undo
    assert project_snapshot(comp) == before


def test_clear(comp, stack):
    stack.execute(SetAttributeCommand(comp.layers[0], 'name', 'x'))
    stack.undo()
    stack.clear()
    assert not stack.can_undo and not stack.can_redo


def test_many_edits_undo_back_to_original(comp, stack):
    original = project_snapshot(comp)
    text = comp.layers[1]
    commands = [
        AddLayerCommand(comp, ShapeLayer(name='box')),
        SetAttributeCommand(text, 'text', 'Title'),
        SetKeyframeCommand(text.position, 0.0, Point(0, 540), EASE_OUT),
        SetKeyframeCommand(text.position, 1.0, Point(960, 540)),
        MoveKeyframeCommand(text.position, 1.0, 1.5),
        SetKeyframeEasingCommand(text.position, 0.0, EASE_IN),
        MoveLayerCommand(comp, text.id, 0),
        RemoveLayerCommand(comp, comp.layers[0].id),
    ]
    for command in commands:
        stack.execute(command)
    edited = project_snapshot(comp)
    while stack.can_undo:
        stack.undo()
    assert project_snapshot(comp) == original
    while stack.can_redo:
        stack.redo()
    assert project_snapshot(comp) == edited


def test_ids_survive_undo_redo_and_save_load(comp, stack, tmp_path):
    removed = comp.layers[0]
    stack.execute(RemoveLayerCommand(comp, removed.id))
    stack.undo()
    project = Project()
    project.add_composition(comp)
    path = tmp_path / 'p.json'
    save_project(project, path)
    loaded = load_project(path).compositions[0]
    assert loaded.layers[0].id == removed.id
    assert ids(loaded) == ids(comp)


def project_snapshot(comp):
    project = Project()
    project.add_composition(comp)
    return project_to_dict(project)
