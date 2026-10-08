# layer_list.py
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

"""Layer list sidebar: Gtk.ListView over composition.layers (top first)."""

from collections.abc import Callable
from gettext import gettext as _

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GObject, Gtk, Pango

from core import Composition, Layer

from .layer_factory import layer_type_label


class LayerItem(GObject.Object):
    """One row in the layer list. Identity is the core layer id."""

    __gtype_name__ = 'MophicLayerItem'

    layer_id = GObject.Property(type=str, default='')
    name = GObject.Property(type=str, default='')
    visible = GObject.Property(type=bool, default=True)
    type_label = GObject.Property(type=str, default='')

    def __init__(self, layer: Layer) -> None:
        super().__init__()
        self.sync_from_layer(layer)

    def sync_from_layer(self, layer: Layer) -> None:
        self.layer_id = layer.id
        self.name = layer.name
        self.visible = layer.visible
        self.type_label = layer_type_label(layer)


class LayerListPanel(Gtk.Box):
    """Sidebar showing composition layers with add/delete/reorder controls."""

    def __init__(self, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.set_size_request(220, -1)
        self.add_css_class('background')

        self._composition: Composition | None = None
        self._suppress_selection = False
        self._on_select: Callable[[str | None], None] | None = None
        self._on_visibility: Callable[[str, bool], None] | None = None
        self._on_add: Callable[[str], None] | None = None
        self._on_delete: Callable[[], None] | None = None
        self._on_duplicate: Callable[[], None] | None = None
        self._on_move: Callable[[int], None] | None = None
        self._on_rename: Callable[[str], None] | None = None

        self._store = Gio.ListStore.new(LayerItem)
        self._selection = Gtk.SingleSelection(model=self._store)
        self._selection.set_can_unselect(True)
        self._selection.connect('notify::selected-item', self._on_selected_item)

        self._build_toolbar()
        scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._list = Gtk.ListView(model=self._selection, factory=self._make_factory())
        self._list.add_css_class('navigation-sidebar')
        scrolled.set_child(self._list)
        self.append(scrolled)

    def connect_handlers(self, *, on_select, on_visibility, on_add, on_delete,
                         on_duplicate, on_move, on_rename) -> None:
        self._on_select = on_select
        self._on_visibility = on_visibility
        self._on_add = on_add
        self._on_delete = on_delete
        self._on_duplicate = on_duplicate
        self._on_move = on_move
        self._on_rename = on_rename

    @property
    def selected_layer_id(self) -> str | None:
        item = self._selection.get_selected_item()
        return item.layer_id if item is not None else None

    def resync(self, composition: Composition, selected_id: str | None) -> None:
        """Rebuild the list from ``composition.layers`` (top first) and restore selection."""
        self._composition = composition
        self._suppress_selection = True
        try:
            self._store.remove_all()
            for layer in reversed(composition.layers):
                self._store.append(LayerItem(layer))
            self._select_id(selected_id)
        finally:
            self._suppress_selection = False
        self._update_action_sensitivity()

    def _select_id(self, layer_id: str | None) -> None:
        if layer_id is None:
            self._selection.set_selected(Gtk.INVALID_LIST_POSITION)
            return
        for i in range(self._store.get_n_items()):
            item = self._store.get_item(i)
            if item.layer_id == layer_id:
                self._selection.set_selected(i)
                return
        self._selection.set_selected(Gtk.INVALID_LIST_POSITION)

    def _build_toolbar(self) -> None:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        bar.set_margin_start(6)
        bar.set_margin_end(6)
        bar.set_margin_top(6)
        bar.set_margin_bottom(6)

        add_button = Gtk.MenuButton(
            icon_name='list-add-symbolic',
            tooltip_text=_('Add Layer'),
            menu_model=self._add_menu(),
        )
        add_button.set_has_frame(False)
        bar.append(add_button)

        self._delete_button = self._icon_button(
            'user-trash-symbolic', _('Delete Layer'), lambda *_: self._emit(self._on_delete))
        self._duplicate_button = self._icon_button(
            'edit-copy-symbolic', _('Duplicate Layer'), lambda *_: self._emit(self._on_duplicate))
        self._up_button = self._icon_button(
            'go-up-symbolic', _('Move Layer Up'), lambda *_: self._emit(self._on_move, 1))
        self._down_button = self._icon_button(
            'go-down-symbolic', _('Move Layer Down'), lambda *_: self._emit(self._on_move, -1))
        self._rename_button = self._icon_button(
            'document-edit-symbolic', _('Rename Layer'), self._prompt_rename)

        for button in (self._delete_button, self._duplicate_button, self._up_button,
                       self._down_button, self._rename_button):
            bar.append(button)

        header = Gtk.Label(label=_('Layers'), xalign=0.0, hexpand=True)
        header.add_css_class('heading')
        header.set_margin_start(6)
        header.set_margin_end(6)
        header.set_margin_top(6)

        self.append(header)
        self.append(bar)
        self.append(Gtk.Separator())

    def _add_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        for kind, label in (
            ('text', _('Text')),
            ('rectangle', _('Rectangle')),
            ('ellipse', _('Ellipse')),
            ('line', _('Line')),
            ('solid', _('Solid')),
            ('image', _('Image')),
        ):
            menu.append(label, f'win.add-layer::{kind}')
        return menu

    def _icon_button(self, icon: str, tooltip: str, callback) -> Gtk.Button:
        button = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
        button.set_has_frame(False)
        button.connect('clicked', callback)
        return button

    def _make_factory(self) -> Gtk.SignalListItemFactory:
        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self._on_setup)
        factory.connect('bind', self._on_bind)
        return factory

    def _on_setup(self, _factory, list_item: Gtk.ListItem) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_start(4)
        row.set_margin_end(8)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        visibility = Gtk.ToggleButton()
        visibility.set_has_frame(False)
        visibility.set_tooltip_text(_('Toggle Visibility'))
        visibility.connect('toggled', self._on_visibility_toggled, list_item)

        name = Gtk.Label(xalign=0.0, hexpand=True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        type_label = Gtk.Label(xalign=1.0)
        type_label.add_css_class('dim-label')
        type_label.add_css_class('caption')

        row.append(visibility)
        row.append(name)
        row.append(type_label)
        list_item.set_child(row)
        list_item._visibility = visibility  # noqa: SLF001
        list_item._name = name  # noqa: SLF001
        list_item._type = type_label  # noqa: SLF001

    def _on_bind(self, _factory, list_item: Gtk.ListItem) -> None:
        item: LayerItem = list_item.get_item()
        visibility: Gtk.ToggleButton = list_item._visibility  # noqa: SLF001
        visibility.set_active(item.visible)
        visibility.set_icon_name(
            'view-reveal-symbolic' if item.visible else 'view-conceal-symbolic')
        list_item._name.set_label(item.name)  # noqa: SLF001
        list_item._type.set_label(item.type_label)  # noqa: SLF001

    def _on_visibility_toggled(self, button: Gtk.ToggleButton, list_item: Gtk.ListItem) -> None:
        item = list_item.get_item()
        if item is None or self._suppress_selection:
            return
        button.set_icon_name(
            'view-reveal-symbolic' if button.get_active() else 'view-conceal-symbolic')
        if self._on_visibility is not None:
            self._on_visibility(item.layer_id, button.get_active())

    def _on_selected_item(self, *_args) -> None:
        if self._suppress_selection:
            return
        self._update_action_sensitivity()
        if self._on_select is not None:
            self._on_select(self.selected_layer_id)

    def _update_action_sensitivity(self) -> None:
        has_selection = self.selected_layer_id is not None
        position = self._selection.get_selected()
        n = self._store.get_n_items()
        self._delete_button.set_sensitive(has_selection)
        self._duplicate_button.set_sensitive(has_selection)
        self._rename_button.set_sensitive(has_selection)
        self._up_button.set_sensitive(has_selection and position > 0)
        self._down_button.set_sensitive(has_selection and position < n - 1)

    def _emit(self, callback, *args) -> None:
        if callback is not None:
            callback(*args) if args else callback()

    def _prompt_rename(self, *_args) -> None:
        layer_id = self.selected_layer_id
        if layer_id is None or self._composition is None:
            return
        layer = self._composition.get_layer(layer_id)
        entry = Gtk.Entry()
        entry.set_text(layer.name)
        entry.set_activates_default(True)

        dialog = Adw.AlertDialog(
            heading=_('Rename Layer'),
            body=_('Enter a new name for “{}”.').format(layer.name),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('rename', _('Rename'))
        dialog.set_response_appearance('rename', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('rename')
        dialog.set_close_response('cancel')
        dialog.set_extra_child(entry)

        def on_response(_dialog, response):
            if response != 'rename' or self._on_rename is None:
                return
            name = entry.get_text().strip()
            if name:
                self._on_rename(name)

        dialog.connect('response', on_response)
        root = self.get_root()
        dialog.present(root if isinstance(root, Gtk.Window) else None)
        entry.grab_focus()
