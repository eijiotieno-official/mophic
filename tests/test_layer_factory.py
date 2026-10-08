"""Default layer factory tests (no GTK)."""

from core import Composition, ImageLayer, ShapeLayer, SolidLayer, TextLayer
from examples.demo_project import LOGO_PATH
from mophic.layer_factory import (FACTORIES, create_ellipse_layer, create_image_layer,
                                  create_line_layer, create_rectangle_layer,
                                  create_solid_layer, create_text_layer, unique_name)


def test_unique_name():
    comp = Composition()
    assert unique_name(comp, 'Text') == 'Text'
    comp.add_layer(create_text_layer(comp))
    assert unique_name(comp, 'Text') == 'Text 2'


def test_all_factories_produce_renderable_types():
    comp = Composition(width=640, height=360)
    assert isinstance(create_text_layer(comp), TextLayer)
    assert create_rectangle_layer(comp).shape_type == 'rectangle'
    assert create_ellipse_layer(comp).shape_type == 'ellipse'
    assert create_line_layer(comp).shape_type == 'line'
    assert isinstance(create_solid_layer(comp), SolidLayer)
    image = create_image_layer(comp)
    assert isinstance(image, ImageLayer)
    assert image.path == str(LOGO_PATH)
    assert set(FACTORIES) == {'text', 'rectangle', 'ellipse', 'line', 'solid', 'image'}
