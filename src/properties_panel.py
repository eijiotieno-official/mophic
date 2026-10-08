# properties_panel.py
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

"""Properties sidebar for the selected layer."""

from collections.abc import Callable
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gdk, Gtk

from core import Color, ImageLayer, Layer, ShapeLayer, SolidLayer, TextLayer
from core.easing import EASING_KINDS, Easing
from core.layers import SHAPE_TYPES, TEXT_ALIGNMENTS
from core.properties import AnimatableProperty

EASING_LABELS = {
    'linear': _('Linear'),
    'ease-in': _('Ease In'),
    'ease-out': _('Ease Out'),
    'ease-in-out': _('Ease In-Out'),
    'cubic-bezier': _('Cubic Bezier'),
}


def color_to_rgba(color: Color) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.red = color.r
    rgba.green = color.g
    rgba.blue = color.b
    rgba.alpha = color.a
    return rgba


def rgba_to_color(rgba: Gdk.RGBA) -> Color:
    return Color(rgba.red, rgba.green, rgba.blue, rgba.alpha)


class PropertiesPanel(Gtk.Box):
    """Edits the selected layer's transform and type-specific attributes."""

    def __init__(self, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.set_size_request(240, -1)
        self.add_css_class('background')

        self._layer: Layer | None = None
        self._time = 0.0
        self._suppress = False
        self._on_edit: Callable[[str, object], None] | None = None
        self._selected_kf: tuple[str, float] | None = None
        self._resolve_image: Callable[[str], Path] | None = None

        header = Gtk.Label(label=_('Properties'), xalign=0.0)
        header.add_css_class('heading')
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(12)
        header.set_margin_bottom(6)
        self.append(header)
        self.append(Gtk.Separator())

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._empty = Gtk.Label(
            label=_('Select a layer to edit its properties.'),
            wrap=True,
            justify=Gtk.Justification.CENTER,
            margin_start=18,
            margin_end=18,
        )
        self._empty.add_css_class('dim-label')
        self._stack.add_named(self._empty, 'empty')

        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._content.set_margin_start(12)
        self._content.set_margin_end(12)
        self._content.set_margin_top(12)
        self._content.set_margin_bottom(12)
        scrolled.set_child(self._content)
        self._stack.add_named(scrolled, 'editor')
        self.append(self._stack)

        self._build_transform()
        self._build_easing()
        self._solid_box = self._section(_('Appearance'))
        self._shape_box = self._section(_('Appearance'))
        self._text_box = self._section(_('Content'))
        self._text_appearance = self._section(_('Appearance'))
        self._image_box = self._section(_('Content'))
        self._build_solid()
        self._build_shape()
        self._build_text()
        self._build_image()

        self._stack.set_visible_child_name('empty')

    def connect_handlers(self, *, on_edit: Callable[[str, object], None],
                         resolve_image: Callable[[str], Path] | None = None) -> None:
        """``on_edit(field, value)`` applies a mutation for the selected layer."""
        self._on_edit = on_edit
        self._resolve_image = resolve_image

    def clear(self) -> None:
        self._layer = None
        self._selected_kf = None
        self._stack.set_visible_child_name('empty')

    def set_selected_keyframe(self, track: str | None, time: float | None) -> None:
        if track is None or time is None:
            self._selected_kf = None
        else:
            self._selected_kf = (track, time)
        self._bind_easing()

    def bind(self, layer: Layer | None, time_seconds: float) -> None:
        """Populate controls from ``layer`` at ``time_seconds`` without mutating it."""
        self._layer = layer
        self._time = time_seconds
        if layer is None:
            self.clear()
            return
        self._stack.set_visible_child_name('editor')
        self._suppress = True
        try:
            self._bind_transform(layer, time_seconds)
            self._bind_easing()
            self._show_type_sections(layer)
            if isinstance(layer, SolidLayer):
                self._set_color(self._solid_color, layer.color)
            elif isinstance(layer, ShapeLayer):
                self._bind_shape(layer)
            elif isinstance(layer, TextLayer):
                self._bind_text(layer)
            elif isinstance(layer, ImageLayer):
                display = layer.path
                if self._resolve_image is not None:
                    resolved = self._resolve_image(layer.path)
                    display = str(resolved)
                    if not resolved.is_file():
                        display = _('Missing image')
                        self._image_path.set_tooltip_text(layer.path)
                    else:
                        self._image_path.set_tooltip_text(display)
                else:
                    self._image_path.set_tooltip_text(layer.path)
                self._image_path.set_label(display)
        finally:
            self._suppress = False

    def _section(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label = Gtk.Label(label=title, xalign=0.0)
        label.add_css_class('heading')
        box.append(label)
        self._content.append(box)
        return box

    def _row(self, parent: Gtk.Box, title: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        widget.set_hexpand(True)
        row.append(label)
        row.append(widget)
        parent.append(row)
        return row

    def _spin(self, lower: float, upper: float, step: float, digits: int = 2) -> Gtk.SpinButton:
        adjustment = Gtk.Adjustment(value=0, lower=lower, upper=upper,
                                    step_increment=step, page_increment=step * 10)
        spin = Gtk.SpinButton(adjustment=adjustment, digits=digits, numeric=True)
        spin.set_width_chars(8)
        spin.connect('value-changed', self._on_spin_changed)
        return spin

    def _kf_button(self, track: str) -> Gtk.ToggleButton:
        button = Gtk.ToggleButton()
        button.set_icon_name('starred-symbolic')
        button.set_tooltip_text(_('Toggle keyframe at playhead'))
        button._track = track  # noqa: SLF001
        button.connect('toggled', self._on_kf_toggled)
        return button

    def _anim_row(self, parent: Gtk.Box, title: str, spin: Gtk.SpinButton,
                  track: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=title, xalign=0.0, hexpand=True)
        spin.set_hexpand(True)
        button = self._kf_button(track)
        row.append(label)
        row.append(spin)
        row.append(button)
        parent.append(row)
        setattr(self, f'_kf_{track}_{spin._field}', button)  # noqa: SLF001
        return row

    def _build_transform(self) -> None:
        box = self._section(_('Transform'))
        self._pos_x = self._spin(-100_000, 100_000, 1)
        self._pos_y = self._spin(-100_000, 100_000, 1)
        self._scale_x = self._spin(0, 1000, 1)
        self._scale_y = self._spin(0, 1000, 1)
        self._rotation = self._spin(-100_000, 100_000, 1)
        self._opacity = self._spin(0, 100, 1, digits=1)
        self._pos_x._field = 'position_x'  # noqa: SLF001
        self._pos_y._field = 'position_y'  # noqa: SLF001
        self._scale_x._field = 'scale_x'  # noqa: SLF001
        self._scale_y._field = 'scale_y'  # noqa: SLF001
        self._rotation._field = 'rotation'  # noqa: SLF001
        self._opacity._field = 'opacity'  # noqa: SLF001
        self._anim_row(box, _('Position X'), self._pos_x, 'position')
        self._anim_row(box, _('Position Y'), self._pos_y, 'position')
        self._anim_row(box, _('Scale X'), self._scale_x, 'scale')
        self._anim_row(box, _('Scale Y'), self._scale_y, 'scale')
        self._anim_row(box, _('Rotation'), self._rotation, 'rotation')
        self._anim_row(box, _('Opacity'), self._opacity, 'opacity')
        self._kf_buttons = {
            'position': (getattr(self, '_kf_position_position_x'),
                         getattr(self, '_kf_position_position_y')),
            'scale': (getattr(self, '_kf_scale_scale_x'),
                      getattr(self, '_kf_scale_scale_y')),
            'rotation': (getattr(self, '_kf_rotation_rotation'),),
            'opacity': (getattr(self, '_kf_opacity_opacity'),),
        }
        self._transform_box = box

    def _build_easing(self) -> None:
        self._easing_box = self._section(_('Easing'))
        labels = [EASING_LABELS[kind] for kind in EASING_KINDS]
        self._easing_kind = Gtk.DropDown.new_from_strings(labels)
        self._easing_kind.connect('notify::selected', self._on_easing_kind_changed)
        self._row(self._easing_box, _('Curve'), self._easing_kind)
        self._ease_x1 = self._spin(0, 1, 0.01)
        self._ease_y1 = self._spin(-2, 2, 0.01)
        self._ease_x2 = self._spin(0, 1, 0.01)
        self._ease_y2 = self._spin(-2, 2, 0.01)
        self._ease_x1._field = 'easing_x1'  # noqa: SLF001
        self._ease_y1._field = 'easing_y1'  # noqa: SLF001
        self._ease_x2._field = 'easing_x2'  # noqa: SLF001
        self._ease_y2._field = 'easing_y2'  # noqa: SLF001
        self._ease_x1_row = self._row(self._easing_box, _('X1'), self._ease_x1)
        self._ease_y1_row = self._row(self._easing_box, _('Y1'), self._ease_y1)
        self._ease_x2_row = self._row(self._easing_box, _('X2'), self._ease_x2)
        self._ease_y2_row = self._row(self._easing_box, _('Y2'), self._ease_y2)
        self._easing_box.set_visible(False)

    def _color_button(self, field: str) -> Gtk.ColorDialogButton:
        button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        button._field = field  # noqa: SLF001
        button.connect('notify::rgba', self._on_color_changed)
        return button

    def _build_solid(self) -> None:
        self._solid_color = self._color_button('color')
        self._row(self._solid_box, _('Color'), self._solid_color)

    def _build_shape(self) -> None:
        self._shape_type = Gtk.DropDown.new_from_strings(list(SHAPE_TYPES))
        self._shape_type.connect('notify::selected', self._on_shape_type_changed)
        self._shape_width = self._spin(0.01, 100_000, 1)
        self._shape_height = self._spin(0.01, 100_000, 1)
        self._shape_start_x = self._spin(-100_000, 100_000, 1)
        self._shape_start_y = self._spin(-100_000, 100_000, 1)
        self._shape_end_x = self._spin(-100_000, 100_000, 1)
        self._shape_end_y = self._spin(-100_000, 100_000, 1)
        self._shape_width._field = 'width'  # noqa: SLF001
        self._shape_height._field = 'height'  # noqa: SLF001
        self._shape_start_x._field = 'start_x'  # noqa: SLF001
        self._shape_start_y._field = 'start_y'  # noqa: SLF001
        self._shape_end_x._field = 'end_x'  # noqa: SLF001
        self._shape_end_y._field = 'end_y'  # noqa: SLF001
        self._fill_color = self._color_button('fill_color')
        self._stroke_color = self._color_button('stroke_color')
        self._stroke_width = self._spin(0, 1000, 0.5)
        self._stroke_width._field = 'stroke_width'  # noqa: SLF001
        self._row(self._shape_box, _('Shape'), self._shape_type)
        self._width_row = self._row(self._shape_box, _('Width'), self._shape_width)
        self._height_row = self._row(self._shape_box, _('Height'), self._shape_height)
        self._start_x_row = self._row(self._shape_box, _('Start X'), self._shape_start_x)
        self._start_y_row = self._row(self._shape_box, _('Start Y'), self._shape_start_y)
        self._end_x_row = self._row(self._shape_box, _('End X'), self._shape_end_x)
        self._end_y_row = self._row(self._shape_box, _('End Y'), self._shape_end_y)
        self._row(self._shape_box, _('Fill'), self._fill_color)
        self._row(self._shape_box, _('Stroke'), self._stroke_color)
        self._row(self._shape_box, _('Stroke Width'), self._stroke_width)

    def _build_text(self) -> None:
        self._text_entry = Gtk.Entry()
        self._text_entry.connect('activate', self._on_text_activate)
        self._text_entry.connect('notify::has-focus', self._on_text_focus)
        self._font_family = Gtk.Entry()
        self._font_family.connect('activate', self._on_font_activate)
        self._font_family.connect('notify::has-focus', self._on_font_focus)
        self._font_size = self._spin(0.01, 10_000, 1)
        self._font_size._field = 'font_size'  # noqa: SLF001
        self._text_color = self._color_button('text_color')
        self._alignment = Gtk.DropDown.new_from_strings(list(TEXT_ALIGNMENTS))
        self._alignment.connect('notify::selected', self._on_alignment_changed)
        self._row(self._text_box, _('Text'), self._text_entry)
        self._row(self._text_appearance, _('Font'), self._font_family)
        self._row(self._text_appearance, _('Font Size'), self._font_size)
        self._row(self._text_appearance, _('Color'), self._text_color)
        self._row(self._text_appearance, _('Alignment'), self._alignment)

    def _build_image(self) -> None:
        self._image_path = Gtk.Label(xalign=0.0, wrap=True, selectable=True)
        self._image_path.add_css_class('dim-label')
        self._row(self._image_box, _('Path'), self._image_path)

    def _show_type_sections(self, layer: Layer) -> None:
        self._solid_box.set_visible(isinstance(layer, SolidLayer))
        self._shape_box.set_visible(isinstance(layer, ShapeLayer))
        self._text_box.set_visible(isinstance(layer, TextLayer))
        self._text_appearance.set_visible(isinstance(layer, TextLayer))
        self._image_box.set_visible(isinstance(layer, ImageLayer))

    def _bind_transform(self, layer: Layer, time: float) -> None:
        position = layer.position.value_at(time)
        scale = layer.scale.value_at(time)
        self._set_spin(self._pos_x, position.x, False)
        self._set_spin(self._pos_y, position.y, False)
        self._set_spin(self._scale_x, scale.x, False)
        self._set_spin(self._scale_y, scale.y, False)
        self._set_spin(self._rotation, layer.rotation.value_at(time), False)
        self._set_spin(self._opacity, layer.opacity.value_at(time) * 100.0, False)
        for track, buttons in self._kf_buttons.items():
            prop: AnimatableProperty = getattr(layer, track)
            active = prop.has_keyframe(time)
            tip = (_('Remove keyframe') if active else _('Add keyframe'))
            if prop.is_animated:
                tip = f'{tip} · {_("Animated")}'
            for button in buttons:
                button.set_active(active)
                button.set_tooltip_text(tip)

    def _bind_easing(self) -> None:
        layer = self._layer
        selected = self._selected_kf
        show = layer is not None and selected is not None
        self._easing_box.set_visible(bool(show))
        if not show:
            return
        track, time = selected
        prop: AnimatableProperty = getattr(layer, track)
        kf = prop.get_keyframe(time)
        if kf is None:
            self._easing_box.set_visible(False)
            return
        self._suppress = True
        try:
            kind_index = EASING_KINDS.index(kf.easing.kind)
            self._easing_kind.set_selected(kind_index)
            is_bezier = kf.easing.kind == 'cubic-bezier'
            for row in (self._ease_x1_row, self._ease_y1_row,
                        self._ease_x2_row, self._ease_y2_row):
                row.set_visible(is_bezier)
            if is_bezier:
                self._set_spin(self._ease_x1, kf.easing.x1 or 0.0, False)
                self._set_spin(self._ease_y1, kf.easing.y1 or 0.0, False)
                self._set_spin(self._ease_x2, kf.easing.x2 or 1.0, False)
                self._set_spin(self._ease_y2, kf.easing.y2 or 1.0, False)
        finally:
            self._suppress = False

    def _bind_shape(self, layer: ShapeLayer) -> None:
        self._shape_type.set_selected(SHAPE_TYPES.index(layer.shape_type))
        is_line = layer.shape_type == 'line'
        self._width_row.set_visible(not is_line)
        self._height_row.set_visible(not is_line)
        self._start_x_row.set_visible(is_line)
        self._start_y_row.set_visible(is_line)
        self._end_x_row.set_visible(is_line)
        self._end_y_row.set_visible(is_line)
        self._set_spin(self._shape_width, layer.width, False)
        self._set_spin(self._shape_height, layer.height, False)
        self._set_spin(self._shape_start_x, layer.start.x, False)
        self._set_spin(self._shape_start_y, layer.start.y, False)
        self._set_spin(self._shape_end_x, layer.end.x, False)
        self._set_spin(self._shape_end_y, layer.end.y, False)
        if layer.fill_color is not None:
            self._set_color(self._fill_color, layer.fill_color)
        else:
            self._set_color(self._fill_color, Color(1, 1, 1, 1))
        if layer.stroke_color is not None:
            self._set_color(self._stroke_color, layer.stroke_color)
        else:
            self._set_color(self._stroke_color, Color(1, 1, 1, 1))
        self._set_spin(self._stroke_width, layer.stroke_width, False)

    def _bind_text(self, layer: TextLayer) -> None:
        self._text_entry.set_text(layer.text)
        self._font_family.set_text(layer.font_family)
        self._set_spin(self._font_size, layer.font_size, False)
        self._set_color(self._text_color, layer.color)
        self._alignment.set_selected(TEXT_ALIGNMENTS.index(layer.alignment))

    def _set_spin(self, spin: Gtk.SpinButton, value: float, animated: bool) -> None:
        spin.set_value(value)
        spin.set_sensitive(True)
        spin.set_tooltip_text(_('Animated — edits set or update a keyframe')
                              if animated else '')

    def _set_color(self, button: Gtk.ColorDialogButton, color: Color) -> None:
        button.set_rgba(color_to_rgba(color))

    def _emit(self, field: str, value: object) -> None:
        if self._suppress or self._on_edit is None or self._layer is None:
            return
        self._on_edit(field, value)

    def _on_kf_toggled(self, button: Gtk.ToggleButton) -> None:
        if self._suppress:
            return
        track = getattr(button, '_track', None)
        if not track:
            return
        # Sync sibling buttons for the same track without re-emitting.
        self._suppress = True
        try:
            for sibling in self._kf_buttons.get(track, ()):
                sibling.set_active(button.get_active())
        finally:
            self._suppress = False
        self._emit('toggle_keyframe', track)

    def _on_easing_kind_changed(self, dropdown: Gtk.DropDown, *_args) -> None:
        if self._suppress or self._selected_kf is None:
            return
        index = dropdown.get_selected()
        if 0 <= index < len(EASING_KINDS):
            kind = EASING_KINDS[index]
            if kind == 'cubic-bezier':
                easing = Easing('cubic-bezier', 0.42, 0.0, 0.58, 1.0)
            else:
                easing = Easing(kind)
            self._emit('keyframe_easing', easing)
            is_bezier = kind == 'cubic-bezier'
            for row in (self._ease_x1_row, self._ease_y1_row,
                        self._ease_x2_row, self._ease_y2_row):
                row.set_visible(is_bezier)

    def _emit_bezier_easing(self) -> None:
        if self._suppress or self._selected_kf is None:
            return
        easing = Easing(
            'cubic-bezier',
            self._ease_x1.get_value(),
            self._ease_y1.get_value(),
            self._ease_x2.get_value(),
            self._ease_y2.get_value(),
        )
        self._emit('keyframe_easing', easing)

    def _on_spin_changed(self, spin: Gtk.SpinButton) -> None:
        field = getattr(spin, '_field', None)
        if not field:
            return
        if field.startswith('easing_'):
            self._emit_bezier_easing()
            return
        self._emit(field, spin.get_value())

    def _on_color_changed(self, button: Gtk.ColorDialogButton, *_args) -> None:
        field = getattr(button, '_field', None)
        if field:
            self._emit(field, rgba_to_color(button.get_rgba()))

    def _on_shape_type_changed(self, dropdown: Gtk.DropDown, *_args) -> None:
        index = dropdown.get_selected()
        if 0 <= index < len(SHAPE_TYPES):
            self._emit('shape_type', SHAPE_TYPES[index])

    def _on_alignment_changed(self, dropdown: Gtk.DropDown, *_args) -> None:
        index = dropdown.get_selected()
        if 0 <= index < len(TEXT_ALIGNMENTS):
            self._emit('alignment', TEXT_ALIGNMENTS[index])

    def _on_text_activate(self, entry: Gtk.Entry) -> None:
        self._emit('text', entry.get_text())

    def _on_font_activate(self, entry: Gtk.Entry) -> None:
        self._emit('font_family', entry.get_text())

    def _on_text_focus(self, entry: Gtk.Entry, *_args) -> None:
        if not entry.has_focus() and not self._suppress:
            self._emit('text', entry.get_text())

    def _on_font_focus(self, entry: Gtk.Entry, *_args) -> None:
        if not entry.has_focus() and not self._suppress:
            text = entry.get_text().strip()
            if text:
                self._emit('font_family', text)
