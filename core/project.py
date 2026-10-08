# project.py
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

"""Projects and compositions."""

import math

from .layers import Layer, check_id, new_id
from .properties import Color, check_number, check_str, check_type

PROJECT_FORMAT = 'aemvp'
"""Format identifier written to every saved project."""

PROJECT_VERSION = 1
"""Schema version written to every saved project."""

FRAME_EPSILON = 1e-9
"""Tolerance for floating-point error when converting times to frames."""


def _check_dimension(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be an int, got {type(value).__name__}')
    if value <= 0:
        raise ValueError(f'{name} must be > 0, got {value!r}')
    return value


class Composition:
    """A timed canvas holding an ordered stack of layers.

    Defaults: 1920x1080 pixels, 30.0 fps, 30.0 seconds, opaque black
    background.

    Layer order: ``layers[0]`` is the bottom layer and ``layers[-1]`` is
    the top layer. Layers are drawn from first to last.

    Time is in seconds. Frame ``n`` starts at ``n / fps``; a time maps to
    the frame that contains it (see ``frame_at_time``). ``duration`` is
    the exclusive end of the composition.
    """

    def __init__(self,
                 *,
                 name: str = 'Main',
                 id: str | None = None,
                 width: int = 1920,
                 height: int = 1080,
                 fps: float = 30.0,
                 duration: float = 30.0,
                 background_color: Color = Color(0.0, 0.0, 0.0, 1.0)) -> None:
        self._id = new_id() if id is None else check_id(id)
        self.name = name
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.background_color = background_color
        self._layers: list[Layer] = []

    def __repr__(self) -> str:
        return f'Composition(id={self._id!r}, name={self._name!r})'

    @property
    def id(self) -> str:
        """The composition's stable unique identifier."""
        return self._id

    @property
    def name(self) -> str:
        """The display name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = check_str('name', value)

    @property
    def width(self) -> int:
        """Width in pixels, > 0."""
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        self._width = _check_dimension('width', value)

    @property
    def height(self) -> int:
        """Height in pixels, > 0."""
        return self._height

    @height.setter
    def height(self, value: int) -> None:
        self._height = _check_dimension('height', value)

    @property
    def fps(self) -> float:
        """Frames per second, > 0."""
        return self._fps

    @fps.setter
    def fps(self, value: float) -> None:
        value = check_number('fps', value)
        if value <= 0.0:
            raise ValueError(f'fps must be > 0, got {value!r}')
        self._fps = value

    @property
    def duration(self) -> float:
        """Length in seconds, >= 0."""
        return self._duration

    @duration.setter
    def duration(self, value: float) -> None:
        value = check_number('duration', value)
        if value < 0.0:
            raise ValueError(f'duration must be >= 0, got {value!r}')
        self._duration = value

    @property
    def background_color(self) -> Color:
        """The color behind all layers."""
        return self._background_color

    @background_color.setter
    def background_color(self, value: Color) -> None:
        check_type('background_color', value, Color)
        self._background_color = value

    @property
    def layers(self) -> tuple[Layer, ...]:
        """Layers from bottom (index 0) to top (last)."""
        return tuple(self._layers)

    @property
    def frame_count(self) -> int:
        """Number of frames in ``[0, duration)``."""
        return max(0, math.ceil(self._duration * self._fps - FRAME_EPSILON))

    def frame_at_time(self, time_seconds: float) -> int:
        """Return the index of the frame containing ``time_seconds``.

        Uses ``floor(time * fps)`` with a ``FRAME_EPSILON`` tolerance, so a
        time computed as ``n / fps`` always maps back to frame ``n``.
        Times past ``duration`` are not clamped.
        """
        time_seconds = check_number('time_seconds', time_seconds)
        if time_seconds < 0.0:
            raise ValueError(f'time_seconds must be >= 0, got {time_seconds!r}')
        return math.floor(time_seconds * self._fps + FRAME_EPSILON)

    def time_at_frame(self, frame_index: int) -> float:
        """Return the start time in seconds of frame ``frame_index``."""
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            raise TypeError(f'frame_index must be an int, got {type(frame_index).__name__}')
        if frame_index < 0:
            raise ValueError(f'frame_index must be >= 0, got {frame_index!r}')
        return frame_index / self._fps

    def index_of(self, layer_id: str) -> int:
        """Return the stack index of the layer with ``layer_id``. Raises ``KeyError``."""
        for index, layer in enumerate(self._layers):
            if layer.id == layer_id:
                return index
        raise KeyError(f'no layer with id {layer_id!r}')

    def get_layer(self, layer_id: str) -> Layer:
        """Return the layer with ``layer_id``. Raises ``KeyError``."""
        return self._layers[self.index_of(layer_id)]

    def has_layer(self, layer_id: str) -> bool:
        """Whether a layer with ``layer_id`` is in this composition."""
        return any(layer.id == layer_id for layer in self._layers)

    def add_layer(self, layer: Layer, index: int | None = None) -> None:
        """Insert ``layer`` at ``index``, or on top when ``index`` is ``None``.

        Raises ``ValueError`` if a layer with the same id is already present.
        """
        if not isinstance(layer, Layer):
            raise TypeError(f'expected a Layer, got {type(layer).__name__}')
        if self.has_layer(layer.id):
            raise ValueError(f'a layer with id {layer.id!r} already exists')
        if index is None:
            index = len(self._layers)
        self._check_index(index, len(self._layers))
        self._layers.insert(index, layer)

    def remove_layer(self, layer_id: str) -> int:
        """Remove the layer with ``layer_id`` and return the index it had."""
        index = self.index_of(layer_id)
        del self._layers[index]
        return index

    def move_layer(self, layer_id: str, new_index: int) -> None:
        """Move the layer with ``layer_id`` so it ends up at ``new_index``."""
        index = self.index_of(layer_id)
        self._check_index(new_index, len(self._layers) - 1)
        self._layers.insert(new_index, self._layers.pop(index))

    @staticmethod
    def _check_index(index: int, maximum: int) -> None:
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError(f'index must be an int, got {type(index).__name__}')
        if not 0 <= index <= maximum:
            raise IndexError(f'index {index} out of range 0..{maximum}')


class Project:
    """The top-level document: a name and one or more compositions."""

    def __init__(self, *, name: str = 'Untitled') -> None:
        self.name = name
        self._compositions: list[Composition] = []

    def __repr__(self) -> str:
        return f'Project(name={self._name!r})'

    @property
    def format(self) -> str:
        """The file format identifier, ``PROJECT_FORMAT``."""
        return PROJECT_FORMAT

    @property
    def version(self) -> int:
        """The schema version, ``PROJECT_VERSION``."""
        return PROJECT_VERSION

    @property
    def name(self) -> str:
        """The project name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = check_str('name', value)

    @property
    def compositions(self) -> tuple[Composition, ...]:
        """All compositions in insertion order."""
        return tuple(self._compositions)

    def add_composition(self, composition: Composition) -> None:
        """Append ``composition``. Raises ``ValueError`` on a duplicate id."""
        if not isinstance(composition, Composition):
            raise TypeError(f'expected a Composition, got {type(composition).__name__}')
        if any(existing.id == composition.id for existing in self._compositions):
            raise ValueError(f'a composition with id {composition.id!r} already exists')
        self._compositions.append(composition)

    def get_composition(self, composition_id: str) -> Composition:
        """Return the composition with ``composition_id``. Raises ``KeyError``."""
        for composition in self._compositions:
            if composition.id == composition_id:
                return composition
        raise KeyError(f'no composition with id {composition_id!r}')

    def remove_composition(self, composition_id: str) -> int:
        """Remove the composition with ``composition_id`` and return its index."""
        composition = self.get_composition(composition_id)
        index = self._compositions.index(composition)
        del self._compositions[index]
        return index
