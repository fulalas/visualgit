"""Shared helpers for the dockable-looking panels."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class Panel(Gtk.Box):
    """A titled panel with a scrollable content area."""

    def __init__(self, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Label(label=title, xalign=0)
        header.get_style_context().add_class('vgit-panel-header')
        self.pack_start(header, False, False, 0)
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(self.scrolled, True, True, 0)


def popup_menu(view, event, items):
    """Build and show a context menu. `items` is a list of (label, callback)
    or (label, callback, sensitive); a None entry inserts a separator."""
    menu = Gtk.Menu()
    menu.attach_to_widget(view, None)
    for entry in items:
        if entry is None:
            menu.append(Gtk.SeparatorMenuItem())
            continue
        item = Gtk.MenuItem(label=entry[0])
        item.connect('activate', lambda _w, cb=entry[1]: cb())
        if len(entry) > 2:
            item.set_sensitive(entry[2])
        menu.append(item)
    menu.show_all()
    menu.popup_at_pointer(event)


def row_at_event(view, event):
    """Return the model iter under a mouse event, or None. Selects the row,
    but keeps an existing multi-selection if the row is already part of it."""
    info = view.get_path_at_pos(int(event.x), int(event.y))
    if info is None:
        return None
    path = info[0]
    selection = view.get_selection()
    if not selection.path_is_selected(path):
        selection.unselect_all()
        selection.select_path(path)
    return view.get_model().get_iter(path)
