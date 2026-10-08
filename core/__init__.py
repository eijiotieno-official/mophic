# __init__.py
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

"""Mophic's headless motion graphics model.

This package depends only on the Python standard library. It must never
import GTK, libadwaita or any rendering library.
"""

from .commands import (AddLayerCommand, Command, MoveKeyframeCommand,
                       MoveLayerCommand, RemoveKeyframeCommand,
                       RemoveLayerCommand, SetAttributeCommand,
                       SetKeyframeCommand, SetKeyframeEasingCommand,
                       SetPropertyValueCommand, UndoStack)
from .easing import (EASE_IN, EASE_IN_OUT, EASE_OUT, LINEAR, Easing,
                     cubic_bezier)
from .layers import (ImageLayer, Layer, ShapeLayer, SolidLayer, TextLayer,
                     new_id)
from .project import (PROJECT_FORMAT, PROJECT_VERSION, Composition, Project)
from .properties import (AnimatableProperty, Color, Keyframe, Point, Scale,
                         interpolate)
from .serialization import (ProjectFormatError, load_project,
                            project_from_dict, project_to_dict, save_project)

__all__ = [
    'AddLayerCommand', 'AnimatableProperty', 'Color', 'Command', 'Composition',
    'EASE_IN', 'EASE_IN_OUT', 'EASE_OUT', 'Easing', 'ImageLayer', 'Keyframe',
    'LINEAR', 'Layer', 'MoveKeyframeCommand', 'MoveLayerCommand',
    'PROJECT_FORMAT', 'PROJECT_VERSION', 'Point', 'Project',
    'ProjectFormatError', 'RemoveKeyframeCommand', 'RemoveLayerCommand',
    'Scale', 'SetAttributeCommand', 'SetKeyframeCommand',
    'SetKeyframeEasingCommand', 'SetPropertyValueCommand', 'ShapeLayer',
    'SolidLayer', 'TextLayer', 'UndoStack', 'cubic_bezier', 'interpolate',
    'load_project', 'new_id', 'project_from_dict', 'project_to_dict',
    'save_project',
]
