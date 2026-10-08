# layers.py
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

"""Layer types.

Transform semantics
-------------------

Composition coordinates are pixels with the origin at the top-left corner
and y pointing down. Each layer draws its content in its own local pixel
coordinates, then:

1. the layer's ``anchor_point`` (local pixels) is the pivot,
2. ``scale`` (percent, 100 = original size) is applied around the pivot,
3. ``rotation`` (degrees, clockwise on screen) is applied around the pivot,
4. the pivot is placed at ``position`` (composition pixels),
5. ``opacity`` (0.0 transparent to 1.0 opaque) multiplies the content alpha.

Local content geometry:

* ``SolidLayer`` fills the rectangle from local (0, 0) to the composition's
  width and height, so a default solid covers the whole frame.
* ``ShapeLayer`` rectangles and ellipses are centered on the local origin;
  lines run from ``start`` to ``end`` in local coordinates.
* ``TextLayer`` text starts at the local origin and is aligned
  horizontally around it according to ``alignment``.
* ``ImageLayer`` places the image's top-left corner at the local origin.
"""

import copy
import uuid
from typing import ClassVar

from .properties import (AnimatableProperty, Color, Point, Scale, check_number,
                         check_str, check_type, check_unit_interval)

SHAPE_TYPES = ('rectangle', 'ellipse', 'line')
TEXT_ALIGNMENTS = ('left', 'center', 'right')

WHITE = Color(1.0, 1.0, 1.0, 1.0)


def new_id() -> str:
    """Return a new unique identifier for a layer or composition."""
    return str(uuid.uuid4())


def check_id(value: object) -> str:
    """Validate an identifier: a non-empty string."""
    if not isinstance(value, str):
        raise TypeError(f'id must be a string, got {type(value).__name__}')
    if not value:
        raise ValueError('id must not be empty')
    return value


def _check_optional_color(name: str, value: object) -> Color | None:
    if value is not None:
        check_type(name, value, Color)
    return value


def _check_positive(name: str, value: object) -> float:
    value = check_number(name, value)
    if value <= 0.0:
        raise ValueError(f'{name} must be > 0, got {value!r}')
    return value


def _check_choice(name: str, value: object, choices: tuple[str, ...]) -> str:
    if value not in choices:
        raise ValueError(f'{name} must be one of {", ".join(choices)}, got {value!r}')
    return value


class Layer:
    """Base class for all layers. Instantiate one of the subclasses.

    ``layer_type`` is the stable type discriminator used in saved files.
    ``position``, ``scale``, ``rotation`` and ``opacity`` are animatable;
    ``anchor_point`` is static. See the module docstring for the transform
    semantics.
    """

    layer_type: ClassVar[str] = ''

    def __init__(self,
                 *,
                 name: str,
                 id: str | None = None,
                 position: Point = Point(0.0, 0.0),
                 scale: Scale = Scale(100.0, 100.0),
                 rotation: float = 0.0,
                 opacity: float = 1.0,
                 anchor_point: Point = Point(0.0, 0.0),
                 visible: bool = True) -> None:
        if not self.layer_type:
            raise TypeError('Layer is a base class; create a SolidLayer, ShapeLayer, TextLayer or ImageLayer')
        self._id = new_id() if id is None else check_id(id)
        self.name = name
        self.visible = visible
        self.anchor_point = anchor_point
        self._position = AnimatableProperty(position, value_type=Point)
        self._scale = AnimatableProperty(scale, value_type=Scale)
        self._rotation = AnimatableProperty(rotation, value_type=float)
        self._opacity = AnimatableProperty(opacity, value_type=float, validator=check_unit_interval)

    def __repr__(self) -> str:
        return f'{type(self).__name__}(id={self._id!r}, name={self._name!r})'

    @property
    def id(self) -> str:
        """The layer's stable unique identifier."""
        return self._id

    @property
    def name(self) -> str:
        """The display name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = check_str('name', value)

    @property
    def visible(self) -> bool:
        """Whether the layer is rendered."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        check_type('visible', value, bool)
        self._visible = value

    @property
    def anchor_point(self) -> Point:
        """The transform pivot in local pixels. Static in this version."""
        return self._anchor_point

    @anchor_point.setter
    def anchor_point(self, value: Point) -> None:
        check_type('anchor_point', value, Point)
        self._anchor_point = value

    @property
    def position(self) -> AnimatableProperty:
        """Where the anchor point is placed, in composition pixels."""
        return self._position

    @property
    def scale(self) -> AnimatableProperty:
        """Scale in percent around the anchor point."""
        return self._scale

    @property
    def rotation(self) -> AnimatableProperty:
        """Clockwise rotation in degrees around the anchor point."""
        return self._rotation

    @property
    def opacity(self) -> AnimatableProperty:
        """Opacity from 0.0 (transparent) to 1.0 (opaque)."""
        return self._opacity

    def duplicate(self) -> 'Layer':
        """Return a deep copy of this layer with a new id."""
        clone = copy.deepcopy(self)
        clone._id = new_id()
        return clone


class SolidLayer(Layer):
    """A layer filled with a single color, covering the composition frame."""

    layer_type = 'solid'

    def __init__(self, *, name: str = 'Solid', color: Color = WHITE, **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.color = color

    @property
    def color(self) -> Color:
        """The fill color."""
        return self._color

    @color.setter
    def color(self, value: Color) -> None:
        check_type('color', value, Color)
        self._color = value


class ShapeLayer(Layer):
    """A rectangle, ellipse or line.

    ``width`` and ``height`` are used by rectangles and ellipses; ``start``
    and ``end`` are used by lines. All of them are kept regardless of
    ``shape_type`` so changing the type loses nothing. ``fill_color`` and
    ``stroke_color`` may be ``None`` for no fill or no stroke.
    """

    layer_type = 'shape'

    def __init__(self,
                 *,
                 name: str = 'Shape',
                 shape_type: str = 'rectangle',
                 width: float = 100.0,
                 height: float = 100.0,
                 start: Point = Point(0.0, 0.0),
                 end: Point = Point(100.0, 0.0),
                 fill_color: Color | None = WHITE,
                 stroke_color: Color | None = None,
                 stroke_width: float = 0.0,
                 **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.shape_type = shape_type
        self.width = width
        self.height = height
        self.start = start
        self.end = end
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width

    @property
    def shape_type(self) -> str:
        """One of ``SHAPE_TYPES``."""
        return self._shape_type

    @shape_type.setter
    def shape_type(self, value: str) -> None:
        self._shape_type = _check_choice('shape_type', value, SHAPE_TYPES)

    @property
    def width(self) -> float:
        """Rectangle or ellipse width in local pixels."""
        return self._width

    @width.setter
    def width(self, value: float) -> None:
        self._width = _check_positive('width', value)

    @property
    def height(self) -> float:
        """Rectangle or ellipse height in local pixels."""
        return self._height

    @height.setter
    def height(self, value: float) -> None:
        self._height = _check_positive('height', value)

    @property
    def start(self) -> Point:
        """Line start in local pixels."""
        return self._start

    @start.setter
    def start(self, value: Point) -> None:
        check_type('start', value, Point)
        self._start = value

    @property
    def end(self) -> Point:
        """Line end in local pixels."""
        return self._end

    @end.setter
    def end(self, value: Point) -> None:
        check_type('end', value, Point)
        self._end = value

    @property
    def fill_color(self) -> Color | None:
        """The fill color, or ``None`` for no fill. Lines ignore it."""
        return self._fill_color

    @fill_color.setter
    def fill_color(self, value: Color | None) -> None:
        self._fill_color = _check_optional_color('fill_color', value)

    @property
    def stroke_color(self) -> Color | None:
        """The stroke color, or ``None`` for no stroke."""
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value: Color | None) -> None:
        self._stroke_color = _check_optional_color('stroke_color', value)

    @property
    def stroke_width(self) -> float:
        """Stroke width in local pixels, >= 0."""
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value: float) -> None:
        value = check_number('stroke_width', value)
        if value < 0.0:
            raise ValueError(f'stroke_width must be >= 0, got {value!r}')
        self._stroke_width = value


class TextLayer(Layer):
    """A single block of static text in one font, size and color."""

    layer_type = 'text'

    def __init__(self,
                 *,
                 name: str = 'Text',
                 text: str = 'Text',
                 font_family: str = 'Sans',
                 font_size: float = 72.0,
                 color: Color = WHITE,
                 alignment: str = 'left',
                 **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.text = text
        self.font_family = font_family
        self.font_size = font_size
        self.color = color
        self.alignment = alignment

    @property
    def text(self) -> str:
        """The text content."""
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = check_str('text', value)

    @property
    def font_family(self) -> str:
        """The font family name."""
        return self._font_family

    @font_family.setter
    def font_family(self, value: str) -> None:
        self._font_family = check_str('font_family', value, allow_empty=False)

    @property
    def font_size(self) -> float:
        """Font size in composition pixels, > 0."""
        return self._font_size

    @font_size.setter
    def font_size(self, value: float) -> None:
        self._font_size = _check_positive('font_size', value)

    @property
    def color(self) -> Color:
        """The text color."""
        return self._color

    @color.setter
    def color(self, value: Color) -> None:
        check_type('color', value, Color)
        self._color = value

    @property
    def alignment(self) -> str:
        """One of ``TEXT_ALIGNMENTS``."""
        return self._alignment

    @alignment.setter
    def alignment(self, value: str) -> None:
        self._alignment = _check_choice('alignment', value, TEXT_ALIGNMENTS)


class ImageLayer(Layer):
    """An image referenced by filesystem path. The file is not opened here."""

    layer_type = 'image'

    def __init__(self, *, path: str, name: str = 'Image', **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.path = path

    @property
    def path(self) -> str:
        """Filesystem path to the image file."""
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = check_str('path', value, allow_empty=False)


LAYER_TYPES: dict[str, type[Layer]] = {
    layer_class.layer_type: layer_class
    for layer_class in (SolidLayer, ShapeLayer, TextLayer, ImageLayer)
}
"""Layer classes by their saved type discriminator."""
