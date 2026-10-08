import uuid

import pytest

from core.layers import (LAYER_TYPES, ImageLayer, Layer, ShapeLayer,
                         SolidLayer, TextLayer)
from core.properties import Color, Point, Scale
from core.serialization import layer_to_dict


def all_layers():
    return [
        SolidLayer(),
        ShapeLayer(),
        TextLayer(),
        ImageLayer(path='/tmp/picture.png'),
    ]


def test_base_layer_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Layer(name='plain')


@pytest.mark.parametrize('layer', all_layers(), ids=lambda layer: layer.layer_type)
def test_transform_defaults(layer):
    assert layer.position.value_at(0.0) == Point(0, 0)
    assert layer.scale.value_at(0.0) == Scale(100, 100)
    assert layer.rotation.value_at(0.0) == 0.0
    assert layer.opacity.value_at(0.0) == 1.0
    assert layer.anchor_point == Point(0, 0)
    assert layer.visible is True
    assert not any(getattr(layer, name).is_animated
                   for name in ('position', 'scale', 'rotation', 'opacity'))


def test_ids_are_unique_uuids():
    ids = [layer.id for layer in all_layers() + all_layers()]
    assert len(set(ids)) == len(ids)
    for value in ids:
        uuid.UUID(value)


def test_explicit_id_is_kept_and_validated():
    assert SolidLayer(id='abc').id == 'abc'
    with pytest.raises(ValueError):
        SolidLayer(id='')
    with pytest.raises(TypeError):
        SolidLayer(id=5)


def test_id_is_read_only():
    layer = SolidLayer()
    with pytest.raises(AttributeError):
        layer.id = 'other'


def test_type_discriminators_are_explicit_and_unique():
    assert sorted(LAYER_TYPES) == ['image', 'shape', 'solid', 'text']
    assert LAYER_TYPES['solid'] is SolidLayer
    assert LAYER_TYPES['shape'] is ShapeLayer
    assert LAYER_TYPES['text'] is TextLayer
    assert LAYER_TYPES['image'] is ImageLayer


def test_constructor_sets_transform_base_values():
    layer = SolidLayer(position=Point(10, 20), scale=Scale(50, 200), rotation=45,
                       opacity=0.5, anchor_point=Point(5, 5), visible=False)
    assert layer.position.base_value == Point(10, 20)
    assert layer.scale.base_value == Scale(50, 200)
    assert layer.rotation.base_value == 45.0
    assert layer.opacity.base_value == 0.5
    assert layer.anchor_point == Point(5, 5)
    assert layer.visible is False


def test_opacity_is_limited_to_unit_interval():
    with pytest.raises(ValueError):
        SolidLayer(opacity=1.5)
    layer = SolidLayer()
    with pytest.raises(ValueError):
        layer.opacity.set_keyframe(0.0, -0.5)


def test_scale_and_rotation_accept_negative_values():
    layer = SolidLayer(scale=Scale(-100, 100), rotation=-90)
    assert layer.scale.base_value == Scale(-100, 100)
    assert layer.rotation.base_value == -90.0


def test_transform_properties_cannot_be_replaced():
    layer = SolidLayer()
    with pytest.raises(AttributeError):
        layer.position = Point(1, 1)


def test_anchor_point_is_static_point():
    layer = SolidLayer()
    layer.anchor_point = Point(3, 4)
    assert layer.anchor_point == Point(3, 4)
    with pytest.raises(TypeError):
        layer.anchor_point = (3, 4)


@pytest.mark.parametrize('name, value', [('name', 5), ('visible', 1)])
def test_base_attribute_types_are_checked(name, value):
    with pytest.raises(TypeError):
        setattr(SolidLayer(), name, value)


def test_solid_layer():
    layer = SolidLayer(color=Color(1, 0, 0, 1))
    assert layer.layer_type == 'solid'
    assert layer.color == Color(1, 0, 0, 1)
    with pytest.raises(TypeError):
        layer.color = (1, 0, 0, 1)


def test_shape_layer_defaults():
    layer = ShapeLayer()
    assert layer.layer_type == 'shape'
    assert layer.shape_type == 'rectangle'
    assert (layer.width, layer.height) == (100.0, 100.0)
    assert layer.fill_color == Color(1, 1, 1, 1)
    assert layer.stroke_color is None
    assert layer.stroke_width == 0.0


@pytest.mark.parametrize('shape_type', ['rectangle', 'ellipse', 'line'])
def test_shape_layer_supported_types(shape_type):
    assert ShapeLayer(shape_type=shape_type).shape_type == shape_type


def test_shape_layer_line_geometry():
    layer = ShapeLayer(shape_type='line', start=Point(0, 0), end=Point(50, 25),
                       stroke_color=Color(1, 1, 1, 1), stroke_width=4, fill_color=None)
    assert layer.start == Point(0, 0)
    assert layer.end == Point(50, 25)
    assert layer.stroke_width == 4.0
    assert layer.fill_color is None


@pytest.mark.parametrize('kwargs, error', [
    ({'shape_type': 'path'}, ValueError),
    ({'width': 0}, ValueError),
    ({'height': -1}, ValueError),
    ({'stroke_width': -1}, ValueError),
    ({'fill_color': 'red'}, TypeError),
    ({'start': (0, 0)}, TypeError),
])
def test_shape_layer_validation(kwargs, error):
    with pytest.raises(error):
        ShapeLayer(**kwargs)


def test_changing_shape_type_keeps_geometry():
    layer = ShapeLayer(width=30, height=40, end=Point(9, 9))
    layer.shape_type = 'line'
    layer.shape_type = 'ellipse'
    assert (layer.width, layer.height, layer.end) == (30.0, 40.0, Point(9, 9))


def test_text_layer():
    layer = TextLayer(text='Hello', font_family='Cantarell', font_size=48,
                      color=Color(0, 0, 0, 1), alignment='center')
    assert layer.layer_type == 'text'
    assert layer.text == 'Hello'
    assert layer.font_family == 'Cantarell'
    assert layer.font_size == 48.0
    assert layer.alignment == 'center'


@pytest.mark.parametrize('kwargs, error', [
    ({'alignment': 'justify'}, ValueError),
    ({'font_size': 0}, ValueError),
    ({'font_family': ''}, ValueError),
    ({'text': None}, TypeError),
])
def test_text_layer_validation(kwargs, error):
    with pytest.raises(error):
        TextLayer(**kwargs)


def test_text_may_be_empty():
    assert TextLayer(text='').text == ''


def test_image_layer_does_not_touch_the_file():
    layer = ImageLayer(path='/does/not/exist.png')
    assert layer.layer_type == 'image'
    assert layer.path == '/does/not/exist.png'


def test_image_layer_requires_a_path():
    with pytest.raises(TypeError):
        ImageLayer()
    with pytest.raises(ValueError):
        ImageLayer(path='')


@pytest.mark.parametrize('layer', all_layers(), ids=lambda layer: layer.layer_type)
def test_duplicate_gets_new_id_and_equal_content(layer):
    layer.position.set_keyframe(0.0, Point(1, 2))
    layer.position.set_keyframe(1.0, Point(3, 4))
    copy = layer.duplicate()
    assert copy.id != layer.id
    assert type(copy) is type(layer)
    original, duplicated = layer_to_dict(layer), layer_to_dict(copy)
    original.pop('id')
    duplicated.pop('id')
    assert original == duplicated


def test_duplicate_is_independent():
    layer = TextLayer()
    copy = layer.duplicate()
    copy.position.set_keyframe(0.0, Point(5, 5))
    copy.text = 'changed'
    assert not layer.position.is_animated
    assert layer.text == 'Text'
