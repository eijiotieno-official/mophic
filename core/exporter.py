# exporter.py
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

"""Composition → H.264 MP4 export via FFmpeg rawvideo pipe.

Depends on Cairo (via the renderer) and the standard library ``subprocess``.
Does not import GTK.
"""

from __future__ import annotations

import copy
import math
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import cairo

from .project import Composition
from .properties import Color
from .renderer import CairoRenderer, RenderError


class ExportError(Exception):
    """Export failed."""


class ExportCancelled(ExportError):
    """The user cancelled the export."""


def find_ffmpeg() -> str | None:
    """Return a usable ``ffmpeg`` binary path, or ``None``."""
    env = os.environ.get('MOPHIC_FFMPEG')
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    flatpak = '/app/bin/ffmpeg'
    if os.path.isfile(flatpak) and os.access(flatpak, os.X_OK):
        return flatpak
    return shutil.which('ffmpeg')


def argb32_to_rgba(surface: cairo.ImageSurface,
                   background: Color | None = None) -> bytes:
    """Convert a Cairo ARGB32 surface to packed straight RGBA bytes.

    Premultiplied native-endian pixels are un-composited over ``background``
    (or opaque black) so every output pixel is opaque RGBA.
    """
    if surface.get_format() != cairo.FORMAT_ARGB32:
        raise ExportError(f'expected FORMAT_ARGB32, got {surface.get_format()}')
    surface.flush()
    width = surface.get_width()
    height = surface.get_height()
    stride = surface.get_stride()
    data = memoryview(surface.get_data())
    bg = background or Color(0.0, 0.0, 0.0, 1.0)
    bg_r = int(round(bg.r * 255))
    bg_g = int(round(bg.g * 255))
    bg_b = int(round(bg.b * 255))

    out = bytearray(width * height * 4)
    o = 0
    for y in range(height):
        row = y * stride
        for x in range(width):
            word = int.from_bytes(data[row + x * 4:row + x * 4 + 4], sys.byteorder)
            a = (word >> 24) & 0xFF
            r = (word >> 16) & 0xFF
            g = (word >> 8) & 0xFF
            b = word & 0xFF
            if a == 0:
                out[o:o + 4] = bytes((bg_r, bg_g, bg_b, 255))
            elif a == 255:
                out[o:o + 4] = bytes((r, g, b, 255))
            else:
                # Premultiplied over opaque background → opaque straight RGB.
                inv = 255 - a
                out[o] = min(255, r + (bg_r * inv + 127) // 255)
                out[o + 1] = min(255, g + (bg_g * inv + 127) // 255)
                out[o + 2] = min(255, b + (bg_b * inv + 127) // 255)
                out[o + 3] = 255
            o += 4
    return bytes(out)


def export_composition(
    composition: Composition,
    path: str | os.PathLike[str],
    *,
    width: int | None = None,
    height: int | None = None,
    fps: float | None = None,
    renderer: CairoRenderer | None = None,
    progress: Callable[[float], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    ffmpeg: str | None = None,
) -> None:
    """Render ``composition`` to an H.264 MP4 at ``path``.

    Snapshots the composition (deep copy), renders each frame, and pipes
    packed RGBA to FFmpeg. Raises ``ExportCancelled`` if ``cancel`` returns
    true, ``ExportError`` on FFmpeg or render failure.
    """
    path = Path(path)
    ffmpeg_bin = ffmpeg or find_ffmpeg()
    if not ffmpeg_bin:
        raise ExportError('FFmpeg not found (set MOPHIC_FFMPEG or install ffmpeg)')

    snapshot = copy.deepcopy(composition)
    out_w = int(width if width is not None else snapshot.width)
    out_h = int(height if height is not None else snapshot.height)
    out_fps = float(fps if fps is not None else snapshot.fps)
    if out_w <= 0 or out_h <= 0:
        raise ExportError('export size must be positive')
    if out_fps <= 0:
        raise ExportError('export fps must be positive')

    # Even dimensions required for yuv420p.
    if out_w % 2:
        out_w += 1
    if out_h % 2:
        out_h += 1

    if out_w != snapshot.width or out_h != snapshot.height:
        snapshot.width = out_w
        snapshot.height = out_h

    frame_count = max(0, math.ceil(snapshot.duration * out_fps - 1e-9))
    if frame_count == 0:
        raise ExportError('composition has no frames to export')

    renderer = renderer or CairoRenderer()
    cmd = [
        ffmpeg_bin,
        '-y',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgba',
        '-s', f'{out_w}x{out_h}',
        '-r', str(out_fps),
        '-i', '-',
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-an',
        str(path),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ExportError(f'could not start FFmpeg: {error}') from error

    assert proc.stdin is not None
    try:
        for index in range(frame_count):
            if cancel is not None and cancel():
                _abort(proc, path)
                raise ExportCancelled('export cancelled')
            time = index / out_fps
            try:
                frame = renderer.render_frame(snapshot, time)
            except RenderError as error:
                _abort(proc, path)
                raise ExportError(str(error)) from error
            rgba = argb32_to_rgba(frame.surface, snapshot.background_color)
            try:
                proc.stdin.write(rgba)
            except BrokenPipeError as error:
                stderr = proc.stderr.read().decode('utf-8', errors='replace') if proc.stderr else ''
                _abort(proc, path)
                raise ExportError(f'FFmpeg pipe closed: {stderr.strip() or error}') from error
            if progress is not None:
                progress((index + 1) / frame_count)
        proc.stdin.close()
        stderr = proc.stderr.read() if proc.stderr else b''
        code = proc.wait()
        if code != 0:
            if path.exists():
                path.unlink(missing_ok=True)
            message = stderr.decode('utf-8', errors='replace').strip() or f'exit {code}'
            raise ExportError(f'FFmpeg failed: {message}')
    except ExportCancelled:
        raise
    except ExportError:
        raise
    except Exception as error:
        _abort(proc, path)
        raise ExportError(str(error)) from error


def _abort(proc: subprocess.Popen, path: Path) -> None:
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except OSError:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    path.unlink(missing_ok=True)
