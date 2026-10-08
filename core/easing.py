# easing.py
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

"""Easing curves that map interpolation progress to eased progress.

Every curve maps progress ``t`` in [0, 1] to an eased value, with
``ease(0) == 0`` and ``ease(1) == 1``:

* ``linear``: ``t``
* ``ease-in``: ``t ** 2`` (slow start)
* ``ease-out``: ``1 - (1 - t) ** 2`` (slow finish)
* ``ease-in-out``: smoothstep, ``3t² - 2t³`` (slow start and finish)
* ``cubic-bezier``: a CSS-style cubic Bezier from (0, 0) to (1, 1) with
  control points (x1, y1) and (x2, y2). The input progress is the curve's
  x coordinate and the result is the matching y coordinate.

These are predictable, well-known curves. They are not exact
reproductions of After Effects easing.
"""

import math
from dataclasses import dataclass

EASING_KINDS = ('linear', 'ease-in', 'ease-out', 'ease-in-out', 'cubic-bezier')

_BEZIER_MAX_ITERATIONS = 64
_BEZIER_TOLERANCE = 1e-12


def _check_control_value(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f'{name} must be a number, got {type(value).__name__}')
    if not math.isfinite(value):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return float(value)


@dataclass(frozen=True)
class Easing:
    """An easing curve.

    ``kind`` is one of ``EASING_KINDS``. The control points ``x1``, ``y1``,
    ``x2`` and ``y2`` are required for ``cubic-bezier`` and must be omitted
    for every other kind. ``x1`` and ``x2`` must lie in [0, 1] so that x
    increases along the curve; ``y1`` and ``y2`` may lie outside [0, 1],
    which lets a cubic-bezier curve overshoot.
    """

    kind: str
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in EASING_KINDS:
            raise ValueError(f'unknown easing kind {self.kind!r}')

        names = ('x1', 'y1', 'x2', 'y2')
        if self.kind != 'cubic-bezier':
            for name in names:
                if getattr(self, name) is not None:
                    raise ValueError(f'{self.kind} easing does not take control points')
            return

        for name in names:
            value = getattr(self, name)
            if value is None:
                raise ValueError(f'cubic-bezier easing requires {name}')
            object.__setattr__(self, name, _check_control_value(name, value))
        for name in ('x1', 'x2'):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f'cubic-bezier {name} must be in [0, 1], got {getattr(self, name)!r}')

    def ease(self, progress: float) -> float:
        """Return the eased value for ``progress`` in [0, 1].

        Raises ``ValueError`` for progress outside [0, 1] or non-finite
        progress. Input is never clamped.
        """
        if isinstance(progress, bool) or not isinstance(progress, (int, float)):
            raise TypeError(f'progress must be a number, got {type(progress).__name__}')
        if not 0.0 <= progress <= 1.0:
            raise ValueError(f'progress must be in [0, 1], got {progress!r}')

        t = float(progress)
        if t == 0.0:
            return 0.0
        if t == 1.0:
            return 1.0

        if self.kind == 'linear':
            return t
        if self.kind == 'ease-in':
            return t * t
        if self.kind == 'ease-out':
            return 1.0 - (1.0 - t) * (1.0 - t)
        if self.kind == 'ease-in-out':
            return t * t * (3.0 - 2.0 * t)
        return self._cubic_bezier(t)

    def _cubic_bezier(self, x: float) -> float:
        # Find the curve parameter s where x(s) == x by bisection. x(s) is
        # non-decreasing because x1 and x2 are in [0, 1].
        low, high = 0.0, 1.0
        s = x
        for _ in range(_BEZIER_MAX_ITERATIONS):
            s = (low + high) / 2.0
            current = _bezier_coordinate(s, self.x1, self.x2)
            if abs(current - x) < _BEZIER_TOLERANCE:
                break
            if current < x:
                low = s
            else:
                high = s
        return _bezier_coordinate(s, self.y1, self.y2)


def _bezier_coordinate(s: float, p1: float, p2: float) -> float:
    """One coordinate of a cubic Bezier with endpoints 0 and 1."""
    inverse = 1.0 - s
    return 3.0 * inverse * inverse * s * p1 + 3.0 * inverse * s * s * p2 + s * s * s


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Easing:
    """Create a CSS-style cubic-bezier easing."""
    return Easing('cubic-bezier', x1, y1, x2, y2)


LINEAR = Easing('linear')
EASE_IN = Easing('ease-in')
EASE_OUT = Easing('ease-out')
EASE_IN_OUT = Easing('ease-in-out')
