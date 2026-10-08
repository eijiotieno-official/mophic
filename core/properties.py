# properties.py
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

"""Value types, keyframes and animatable properties.

Time is always expressed in seconds as a float.
"""

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .easing import LINEAR, Easing

TIME_EPSILON = 1e-9
"""Two keyframe times closer than this are treated as the same timestamp."""


def check_number(name: str, value: object) -> float:
    """Return ``value`` as a float, rejecting bools, non-numbers and non-finite values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f'{name} must be a number, got {type(value).__name__}')
    if not math.isfinite(value):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return float(value)


def check_str(name: str, value: object, *, allow_empty: bool = True) -> str:
    """Return ``value`` if it is a string, optionally rejecting the empty string."""
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string, got {type(value).__name__}')
    if not allow_empty and not value:
        raise ValueError(f'{name} must not be empty')
    return value


def check_type(name: str, value: object, expected: type) -> None:
    """Raise ``TypeError`` unless ``value`` is exactly of type ``expected``."""
    if type(value) is not expected:
        raise TypeError(f'{name} must be a {expected.__name__}, got {type(value).__name__}')


@dataclass(frozen=True)
class Point:
    """A 2D point in pixels."""

    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, 'x', check_number('x', self.x))
        object.__setattr__(self, 'y', check_number('y', self.y))


@dataclass(frozen=True)
class Scale:
    """A 2D scale in percent, where 100 is the original size."""

    x: float = 100.0
    y: float = 100.0

    def __post_init__(self) -> None:
        object.__setattr__(self, 'x', check_number('x', self.x))
        object.__setattr__(self, 'y', check_number('y', self.y))


@dataclass(frozen=True)
class Color:
    """An RGBA color with each channel normalized to [0, 1]."""

    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 1.0

    def __post_init__(self) -> None:
        for name in ('r', 'g', 'b', 'a'):
            value = check_number(name, getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f'color channel {name} must be in [0, 1], got {value!r}')
            object.__setattr__(self, name, value)


AnimatableValue = float | Point | Scale
ANIMATABLE_TYPES: tuple[type, ...] = (float, Point, Scale)


def interpolate(a: AnimatableValue, b: AnimatableValue, t: float) -> AnimatableValue:
    """Linearly interpolate from ``a`` to ``b`` by the eased progress ``t``.

    Numbers interpolate as floats. ``Point`` and ``Scale`` interpolate
    component by component and must both be of the same type. Any other
    combination raises ``TypeError``.
    """
    t = check_number('t', t)
    if _is_number(a) and _is_number(b):
        return float(a) + (float(b) - float(a)) * t
    if type(a) is type(b) and type(a) in (Point, Scale):
        return type(a)(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
    raise TypeError(f'cannot interpolate {type(a).__name__} and {type(b).__name__}')


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_unit_interval(value: float) -> None:
    """Validator for values that must lie in [0, 1], such as opacity."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f'value must be in [0, 1], got {value!r}')


@dataclass(frozen=True)
class Keyframe:
    """A value at a point in time.

    ``easing`` shapes the interpolation from this keyframe to the next
    one. It is unused on the last keyframe of a property.
    """

    time: float
    value: AnimatableValue
    easing: Easing = LINEAR

    def __post_init__(self) -> None:
        time = check_number('time', self.time)
        if time < 0.0:
            raise ValueError(f'keyframe time must be >= 0, got {time!r}')
        object.__setattr__(self, 'time', time)
        if not isinstance(self.easing, Easing):
            raise TypeError(f'easing must be an Easing, got {type(self.easing).__name__}')


class AnimatableProperty:
    """A property that is either static or animated by keyframes.

    ``value_type`` is ``float``, ``Point`` or ``Scale``. ``validator`` is an
    optional callable that raises ``ValueError`` for out-of-range values.

    Evaluation rules for ``value_at(time)``:

    * no keyframes: the base value
    * one keyframe: that keyframe's value at every time
    * at or before the first keyframe: the first keyframe's value
    * at or after the last keyframe: the last keyframe's value
    * between two keyframes: interpolation between them, shaped by the
      easing of the earlier keyframe

    Keyframes are kept sorted by time. Setting a keyframe at an existing
    timestamp (within ``TIME_EPSILON``) replaces that keyframe.
    """

    def __init__(self,
                 base_value: Any,
                 *,
                 value_type: type,
                 validator: Callable[[Any], None] | None = None) -> None:
        if value_type not in ANIMATABLE_TYPES:
            raise TypeError(f'unsupported property type {value_type!r}')
        self._value_type = value_type
        self._validator = validator
        self._keyframes: list[Keyframe] = []
        self._base_value = self._check_value(base_value)

    def __repr__(self) -> str:
        return (f'AnimatableProperty(base_value={self._base_value!r}, '
                f'keyframes={self._keyframes!r})')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnimatableProperty):
            return NotImplemented
        return (self._value_type is other._value_type
                and self._base_value == other._base_value
                and self._keyframes == other._keyframes)

    __hash__ = None

    @property
    def value_type(self) -> type:
        """The type of every value this property holds."""
        return self._value_type

    @property
    def base_value(self) -> AnimatableValue:
        """The value used when the property has no keyframes."""
        return self._base_value

    @base_value.setter
    def base_value(self, value: Any) -> None:
        self._base_value = self._check_value(value)

    @property
    def keyframes(self) -> tuple[Keyframe, ...]:
        """All keyframes in chronological order."""
        return tuple(self._keyframes)

    @property
    def is_animated(self) -> bool:
        """Whether the property has at least one keyframe."""
        return bool(self._keyframes)

    def has_keyframe(self, time: float) -> bool:
        """Whether a keyframe exists at ``time``."""
        return self._find_index(time) is not None

    def get_keyframe(self, time: float) -> Keyframe | None:
        """Return the keyframe at ``time``, or ``None``."""
        index = self._find_index(time)
        return None if index is None else self._keyframes[index]

    def set_keyframe(self, time: float, value: Any, easing: Easing = LINEAR) -> Keyframe:
        """Add a keyframe, or replace the one already at ``time``."""
        keyframe = Keyframe(time, self._check_value(value), easing)
        index = self._find_index(keyframe.time)
        if index is not None:
            keyframe = Keyframe(self._keyframes[index].time, keyframe.value, keyframe.easing)
            self._keyframes[index] = keyframe
        else:
            self._insert(keyframe)
        return keyframe

    def remove_keyframe(self, time: float) -> Keyframe:
        """Remove and return the keyframe at ``time``. Raises ``KeyError`` if there is none."""
        return self._keyframes.pop(self._require_index(time))

    def move_keyframe(self, old_time: float, new_time: float) -> Keyframe:
        """Move the keyframe at ``old_time`` to ``new_time``.

        Raises ``KeyError`` if no keyframe is at ``old_time``, and
        ``ValueError`` if a different keyframe already exists at
        ``new_time``.
        """
        index = self._require_index(old_time)
        current = self._keyframes[index]
        moved = Keyframe(new_time, current.value, current.easing)
        other = self._find_index(moved.time)
        if other is not None and other != index:
            raise ValueError(f'a keyframe already exists at {moved.time!r}')
        del self._keyframes[index]
        self._insert(moved)
        return moved

    def set_keyframe_easing(self, time: float, easing: Easing) -> Keyframe:
        """Change the easing of the keyframe at ``time``."""
        index = self._require_index(time)
        current = self._keyframes[index]
        updated = Keyframe(current.time, current.value, easing)
        self._keyframes[index] = updated
        return updated

    def value_at(self, time: float) -> AnimatableValue:
        """Evaluate the property at ``time`` seconds."""
        time = check_number('time', time)
        keyframes = self._keyframes
        if not keyframes:
            return self._base_value
        first, last = keyframes[0], keyframes[-1]
        if time <= first.time:
            return first.value
        if time >= last.time:
            return last.value

        index = bisect.bisect_right([keyframe.time for keyframe in keyframes], time)
        start, end = keyframes[index - 1], keyframes[index]
        progress = (time - start.time) / (end.time - start.time)
        return interpolate(start.value, end.value, start.easing.ease(progress))

    def _check_value(self, value: Any) -> AnimatableValue:
        if self._value_type is float:
            value = check_number('value', value)
        elif type(value) is not self._value_type:
            raise TypeError(f'expected {self._value_type.__name__}, got {type(value).__name__}')
        if self._validator is not None:
            self._validator(value)
        return value

    def _find_index(self, time: float) -> int | None:
        time = check_number('time', time)
        times = [keyframe.time for keyframe in self._keyframes]
        index = bisect.bisect_left(times, time - TIME_EPSILON)
        if index < len(times) and abs(times[index] - time) <= TIME_EPSILON:
            return index
        return None

    def _require_index(self, time: float) -> int:
        index = self._find_index(time)
        if index is None:
            raise KeyError(f'no keyframe at {time!r}')
        return index

    def _insert(self, keyframe: Keyframe) -> None:
        times = [existing.time for existing in self._keyframes]
        self._keyframes.insert(bisect.bisect_left(times, keyframe.time), keyframe)
