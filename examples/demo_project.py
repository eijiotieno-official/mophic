# demo_project.py
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

"""The built-in demonstration composition.

Used by ``examples/phase3_demo.py`` and previewed by the application. The
logo is a tracked asset installed next to this module, so the composition
builds the same way from the source tree, an installed prefix or Flatpak.
"""

import pathlib

from core import (EASE_IN_OUT, EASE_OUT, Color, Composition, ImageLayer, Point,
                  Scale, ShapeLayer, SolidLayer, TextLayer, cubic_bezier)

LOGO_PATH = pathlib.Path(__file__).resolve().parent / 'assets' / 'phase3-logo.png'
LOGO_SIZE = 160

WHITE = Color(1.0, 1.0, 1.0, 1.0)


def build_demo_composition(logo_path: str | pathlib.Path = LOGO_PATH) -> Composition:
    """Build the 1920x1080, 30 fps, 5 second demonstration composition."""
    comp = Composition(name='Phase 3 demo', width=1920, height=1080, fps=30.0, duration=5.0)

    comp.add_layer(SolidLayer(name='Background', color=Color(0.07, 0.08, 0.11, 1.0)))

    title = TextLayer(name='Title', text='Mophic', font_size=140, color=WHITE, alignment='center')
    title.position.set_keyframe(0.0, Point(960, 420), cubic_bezier(0.2, 0.0, 0.0, 1.0))
    title.position.set_keyframe(1.5, Point(960, 340))
    title.opacity.set_keyframe(0.0, 0.0, EASE_OUT)
    title.opacity.set_keyframe(1.0, 1.0)
    comp.add_layer(title)

    comp.add_layer(TextLayer(name='Subtitle', text='Phase 3 — CPU Cairo renderer', font_size=44,
                             color=Color(0.75, 0.78, 0.85, 1.0), alignment='center',
                             position=Point(960, 420)))

    rectangle = ShapeLayer(name='Rectangle', shape_type='rectangle', width=520, height=280,
                           fill_color=Color(0.20, 0.45, 0.90, 1.0), stroke_color=WHITE,
                           stroke_width=6, position=Point(560, 740))
    rectangle.rotation.set_keyframe(0.0, 0.0, EASE_IN_OUT)
    rectangle.rotation.set_keyframe(4.0, 8.0)
    comp.add_layer(rectangle)

    ellipse = ShapeLayer(name='Ellipse', shape_type='ellipse', width=320, height=320,
                         fill_color=Color(0.95, 0.55, 0.15, 1.0), stroke_color=None,
                         position=Point(1360, 740))
    ellipse.scale.set_keyframe(0.0, Scale(80, 80), EASE_OUT)
    ellipse.scale.set_keyframe(2.5, Scale(100, 100))
    comp.add_layer(ellipse)

    line = ShapeLayer(name='Line', shape_type='line', start=Point(-700, 0), end=Point(700, 0),
                      fill_color=None, stroke_color=WHITE, stroke_width=6,
                      position=Point(960, 480))
    line.scale.set_keyframe(0.5, Scale(0, 100), EASE_IN_OUT)
    line.scale.set_keyframe(2.5, Scale(100, 100))
    comp.add_layer(line)

    highlight = ShapeLayer(name='Highlight', shape_type='rectangle', width=220, height=220,
                           fill_color=Color(1.0, 0.85, 0.20, 1.0), stroke_color=None,
                           position=Point(760, 640), rotation=45)
    highlight.opacity.set_keyframe(1.0, 0.0, EASE_IN_OUT)
    highlight.opacity.set_keyframe(2.5, 0.8, EASE_IN_OUT)
    highlight.opacity.set_keyframe(4.0, 0.0)
    comp.add_layer(highlight)

    comp.add_layer(ImageLayer(name='Logo', path=str(logo_path), position=Point(1760, 160),
                              anchor_point=Point(LOGO_SIZE / 2, LOGO_SIZE / 2)))
    return comp
