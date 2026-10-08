# layer_factory.py
#
# Copyright 2026 Eiji Otieno
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Default layer constructors for the Add Layer menu."""

from core import (Color, Composition, ImageLayer, Layer, Point, ShapeLayer,
                  SolidLayer, TextLayer)
from examples.demo_project import LOGO_PATH, LOGO_SIZE

TYPE_LABELS = {
    'solid': 'Solid',
    'shape': 'Shape',
    'text': 'Text',
    'image': 'Image',
}

SHAPE_LABELS = {
    'rectangle': 'Rectangle',
    'ellipse': 'Ellipse',
    'line': 'Line',
}


def unique_name(composition: Composition, base: str) -> str:
    """Return ``base``, or ``base 2``, ``base 3``, … if already taken."""
    names = {layer.name for layer in composition.layers}
    if base not in names:
        return base
    n = 2
    while f'{base} {n}' in names:
        n += 1
    return f'{base} {n}'


def layer_type_label(layer: Layer) -> str:
    """Short type label for a layer row."""
    if isinstance(layer, ShapeLayer):
        return SHAPE_LABELS.get(layer.shape_type, 'Shape')
    return TYPE_LABELS.get(layer.layer_type, layer.layer_type.title() or 'Layer')


def _center(composition: Composition) -> Point:
    return Point(composition.width / 2, composition.height / 2)


def create_text_layer(composition: Composition) -> TextLayer:
    return TextLayer(
        name=unique_name(composition, 'Text'),
        text='Text',
        font_size=64.0,
        color=Color(1, 1, 1, 1),
        alignment='center',
        position=_center(composition),
    )


def create_rectangle_layer(composition: Composition) -> ShapeLayer:
    return ShapeLayer(
        name=unique_name(composition, 'Rectangle'),
        shape_type='rectangle',
        width=320.0,
        height=180.0,
        fill_color=Color(0.25, 0.55, 0.95, 1),
        stroke_color=Color(1, 1, 1, 1),
        stroke_width=4.0,
        position=_center(composition),
    )


def create_ellipse_layer(composition: Composition) -> ShapeLayer:
    return ShapeLayer(
        name=unique_name(composition, 'Ellipse'),
        shape_type='ellipse',
        width=240.0,
        height=240.0,
        fill_color=Color(0.95, 0.55, 0.20, 1),
        stroke_color=None,
        stroke_width=0.0,
        position=_center(composition),
    )


def create_line_layer(composition: Composition) -> ShapeLayer:
    return ShapeLayer(
        name=unique_name(composition, 'Line'),
        shape_type='line',
        start=Point(-200.0, 0.0),
        end=Point(200.0, 0.0),
        fill_color=None,
        stroke_color=Color(1, 1, 1, 1),
        stroke_width=6.0,
        position=_center(composition),
    )


def create_solid_layer(composition: Composition) -> SolidLayer:
    return SolidLayer(
        name=unique_name(composition, 'Solid'),
        color=Color(0.15, 0.18, 0.25, 1),
        position=Point(0, 0),
    )


def create_image_layer(composition: Composition) -> ImageLayer:
    return ImageLayer(
        name=unique_name(composition, 'Image'),
        path=str(LOGO_PATH),
        position=_center(composition),
        anchor_point=Point(LOGO_SIZE / 2, LOGO_SIZE / 2),
    )


FACTORIES = {
    'text': create_text_layer,
    'rectangle': create_rectangle_layer,
    'ellipse': create_ellipse_layer,
    'line': create_line_layer,
    'solid': create_solid_layer,
    'image': create_image_layer,
}
