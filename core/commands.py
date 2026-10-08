# commands.py
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

"""Undoable edits and the undo stack.

Each command captures what it needs to reverse itself when ``do()`` runs.
``do()`` validates its input before changing anything, so a command that
raises leaves the model untouched. Commands hold direct references to the
objects they edit; undoing a removal puts the same layer object back, so
its id is preserved.
"""

from typing import Any, Protocol

from .easing import LINEAR, Easing
from .layers import Layer
from .project import Composition
from .properties import AnimatableProperty, Keyframe


class Command(Protocol):
    """An undoable edit."""

    description: str

    def do(self) -> None:
        """Apply the edit. Also used to redo it after ``undo()``."""

    def undo(self) -> None:
        """Reverse the edit."""


class AddLayerCommand:
    """Add a layer to a composition, on top unless ``index`` is given."""

    def __init__(self, composition: Composition, layer: Layer, index: int | None = None) -> None:
        self.description = f'Add {layer.name}'
        self._composition = composition
        self._layer = layer
        self._index = index

    def do(self) -> None:
        self._composition.add_layer(self._layer, self._index)

    def undo(self) -> None:
        self._composition.remove_layer(self._layer.id)


class RemoveLayerCommand:
    """Remove a layer from a composition."""

    def __init__(self, composition: Composition, layer_id: str) -> None:
        self.description = f'Remove {composition.get_layer(layer_id).name}'
        self._composition = composition
        self._layer_id = layer_id
        self._layer: Layer | None = None
        self._index = 0

    def do(self) -> None:
        self._layer = self._composition.get_layer(self._layer_id)
        self._index = self._composition.remove_layer(self._layer_id)

    def undo(self) -> None:
        self._composition.add_layer(self._layer, self._index)


class MoveLayerCommand:
    """Move a layer to a new stack index (0 is the bottom)."""

    def __init__(self, composition: Composition, layer_id: str, new_index: int) -> None:
        self.description = f'Move {composition.get_layer(layer_id).name}'
        self._composition = composition
        self._layer_id = layer_id
        self._new_index = new_index
        self._old_index = 0

    def do(self) -> None:
        old_index = self._composition.index_of(self._layer_id)
        self._composition.move_layer(self._layer_id, self._new_index)
        self._old_index = old_index

    def undo(self) -> None:
        self._composition.move_layer(self._layer_id, self._old_index)


class SetAttributeCommand:
    """Set a static attribute such as ``name``, ``visible``, ``color`` or ``fps``.

    ``target`` is a layer or composition. Only settable attributes are
    accepted; animatable properties are edited with the property and
    keyframe commands instead.
    """

    def __init__(self, target: Layer | Composition, name: str, value: Any) -> None:
        descriptor = getattr(type(target), name, None)
        if not isinstance(descriptor, property) or descriptor.fset is None:
            raise AttributeError(f'{type(target).__name__} has no settable attribute {name!r}')
        self.description = f'Change {name.replace("_", " ")}'
        self._target = target
        self._name = name
        self._value = value
        self._old_value: Any = None

    def do(self) -> None:
        old_value = getattr(self._target, self._name)
        setattr(self._target, self._name, self._value)
        self._old_value = old_value

    def undo(self) -> None:
        setattr(self._target, self._name, self._old_value)


class SetPropertyValueCommand:
    """Set the base (unanimated) value of an animatable property."""

    def __init__(self, prop: AnimatableProperty, value: Any) -> None:
        self.description = 'Change value'
        self._prop = prop
        self._value = value
        self._old_value: Any = None

    def do(self) -> None:
        old_value = self._prop.base_value
        self._prop.base_value = self._value
        self._old_value = old_value

    def undo(self) -> None:
        self._prop.base_value = self._old_value


class SetKeyframeCommand:
    """Add a keyframe, or replace the keyframe already at ``time``."""

    def __init__(self, prop: AnimatableProperty, time: float, value: Any,
                 easing: Easing = LINEAR) -> None:
        self.description = 'Set keyframe'
        self._prop = prop
        self._time = time
        self._value = value
        self._easing = easing
        self._previous: Keyframe | None = None
        self._keyframe: Keyframe | None = None

    def do(self) -> None:
        previous = self._prop.get_keyframe(self._time)
        self._keyframe = self._prop.set_keyframe(self._time, self._value, self._easing)
        self._previous = previous

    def undo(self) -> None:
        if self._previous is None:
            self._prop.remove_keyframe(self._keyframe.time)
        else:
            self._prop.set_keyframe(self._previous.time, self._previous.value, self._previous.easing)


class RemoveKeyframeCommand:
    """Remove the keyframe at ``time``."""

    def __init__(self, prop: AnimatableProperty, time: float) -> None:
        self.description = 'Remove keyframe'
        self._prop = prop
        self._time = time
        self._removed: Keyframe | None = None

    def do(self) -> None:
        self._removed = self._prop.remove_keyframe(self._time)

    def undo(self) -> None:
        removed = self._removed
        self._prop.set_keyframe(removed.time, removed.value, removed.easing)


class MoveKeyframeCommand:
    """Move the keyframe at ``old_time`` to ``new_time``."""

    def __init__(self, prop: AnimatableProperty, old_time: float, new_time: float) -> None:
        self.description = 'Move keyframe'
        self._prop = prop
        self._old_time = old_time
        self._new_time = new_time
        self._original_time = old_time
        self._moved_time = new_time

    def do(self) -> None:
        original = self._prop.get_keyframe(self._old_time)
        moved = self._prop.move_keyframe(self._old_time, self._new_time)
        self._original_time = original.time
        self._moved_time = moved.time

    def undo(self) -> None:
        self._prop.move_keyframe(self._moved_time, self._original_time)


class SetKeyframeEasingCommand:
    """Change the easing of the keyframe at ``time``."""

    def __init__(self, prop: AnimatableProperty, time: float, easing: Easing) -> None:
        self.description = 'Change easing'
        self._prop = prop
        self._time = time
        self._easing = easing
        self._old_easing: Easing = LINEAR

    def do(self) -> None:
        previous = self._prop.get_keyframe(self._time)
        self._prop.set_keyframe_easing(self._time, self._easing)
        self._old_easing = previous.easing

    def undo(self) -> None:
        self._prop.set_keyframe_easing(self._time, self._old_easing)


class UndoStack:
    """Linear undo/redo history.

    ``execute()`` runs a command and records it; a command that raises is
    not recorded. Executing a new command discards the redo history.
    """

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    @property
    def can_undo(self) -> bool:
        """Whether there is a command to undo."""
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """Whether there is a command to redo."""
        return bool(self._redo)

    @property
    def undo_description(self) -> str | None:
        """Description of the command ``undo()`` would reverse."""
        return self._undo[-1].description if self._undo else None

    @property
    def redo_description(self) -> str | None:
        """Description of the command ``redo()`` would reapply."""
        return self._redo[-1].description if self._redo else None

    def execute(self, command: Command) -> None:
        """Run ``command`` and record it for undo."""
        command.do()
        self._undo.append(command)
        self._redo.clear()

    def undo(self) -> Command:
        """Reverse the most recent command. Raises ``IndexError`` if there is none."""
        if not self._undo:
            raise IndexError('nothing to undo')
        command = self._undo[-1]
        command.undo()
        self._redo.append(self._undo.pop())
        return command

    def redo(self) -> Command:
        """Reapply the most recently undone command. Raises ``IndexError`` if there is none."""
        if not self._redo:
            raise IndexError('nothing to redo')
        command = self._redo[-1]
        command.do()
        self._undo.append(self._redo.pop())
        return command

    def clear(self) -> None:
        """Forget all history."""
        self._undo.clear()
        self._redo.clear()
