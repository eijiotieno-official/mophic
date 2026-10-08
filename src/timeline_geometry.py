# timeline_geometry.py
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

"""Pure timeline geometry: time ↔ pixels, snapping, hit-testing."""

from __future__ import annotations

import math
from dataclasses import dataclass

TRACK_NAMES = ('position', 'scale', 'rotation', 'opacity')
TRACK_LABELS = {
    'position': 'Position',
    'scale': 'Scale',
    'rotation': 'Rotation',
    'opacity': 'Opacity',
}

LABEL_WIDTH = 88.0
RULER_HEIGHT = 24.0
TRACK_HEIGHT = 28.0
DEFAULT_PX_PER_SECOND = 80.0
MIN_PX_PER_SECOND = 20.0
MAX_PX_PER_SECOND = 400.0
KEYFRAME_HIT_RADIUS = 8.0


@dataclass(frozen=True)
class TimelineView:
    """Visible timeline mapping."""

    duration: float
    fps: float
    px_per_second: float
    scroll_x: float = 0.0
    width: float = 800.0

    @property
    def content_width(self) -> float:
        return max(self.width, self.duration * self.px_per_second + LABEL_WIDTH + 40.0)


def clamp_zoom(px_per_second: float) -> float:
    return min(MAX_PX_PER_SECOND, max(MIN_PX_PER_SECOND, float(px_per_second)))


def snap_time(time_seconds: float, fps: float, duration: float) -> float:
    """Snap ``time_seconds`` to a frame start in ``[0, last_frame]``."""
    if fps <= 0 or duration <= 0:
        return 0.0
    frame_count = max(0, math.ceil(duration * fps - 1e-9))
    last = max(frame_count - 1, 0)
    frame = int(round(max(0.0, time_seconds) * fps))
    frame = min(max(frame, 0), last)
    return frame / fps


def time_to_x(time_seconds: float, view: TimelineView) -> float:
    """Pixel x of ``time_seconds`` in the scrollable content (includes label gutter)."""
    return LABEL_WIDTH + time_seconds * view.px_per_second


def x_to_time(x: float, view: TimelineView) -> float:
    """Time for content x (including label gutter)."""
    return max(0.0, (x - LABEL_WIDTH) / view.px_per_second)


def track_y(track_index: int) -> float:
    return RULER_HEIGHT + track_index * TRACK_HEIGHT


def track_at_y(y: float) -> int | None:
    if y < RULER_HEIGHT:
        return None
    index = int((y - RULER_HEIGHT) / TRACK_HEIGHT)
    if 0 <= index < len(TRACK_NAMES):
        return index
    return None


def timeline_height() -> float:
    return RULER_HEIGHT + len(TRACK_NAMES) * TRACK_HEIGHT


def ruler_ticks(view: TimelineView) -> list[tuple[float, str]]:
    """Return ``(time, label)`` major ticks for the visible range."""
    if view.duration <= 0 or view.px_per_second <= 0:
        return [(0.0, '0.0s')]
    # Aim for ~80 px between major ticks.
    raw = 80.0 / view.px_per_second
    candidates = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
    step = candidates[-1]
    for candidate in candidates:
        if candidate >= raw:
            step = candidate
            break
    ticks = []
    t = 0.0
    while t <= view.duration + 1e-9:
        if step < 1.0:
            label = f'{t:.1f}s'
        else:
            label = f'{t:.0f}s' if abs(t - round(t)) < 1e-9 else f'{t:.1f}s'
        ticks.append((t, label))
        t += step
    return ticks


@dataclass(frozen=True)
class KeyframeHit:
    track: str
    time: float


def hit_test_keyframe(x: float, y: float, tracks: dict[str, list[float]],
                      view: TimelineView, radius: float = KEYFRAME_HIT_RADIUS) -> KeyframeHit | None:
    """Return the nearest keyframe under ``(x, y)``, or ``None``."""
    track_index = track_at_y(y)
    if track_index is None:
        return None
    track = TRACK_NAMES[track_index]
    times = tracks.get(track, ())
    best: KeyframeHit | None = None
    best_dist = radius
    cy = track_y(track_index) + TRACK_HEIGHT / 2.0
    for time in times:
        kx = time_to_x(time, view)
        dist = math.hypot(x - kx, y - cy)
        if dist <= best_dist:
            best_dist = dist
            best = KeyframeHit(track, time)
    return best
