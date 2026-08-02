"""Shared helpers for the dockable-looking panels."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def add_external_hscrollbar(box, scrolled):
    """Put the horizontal scrollbar in `box`, right under `scrolled`, instead
    of inside the scroller. GTK draws its own one on top of the content, which
    hides the bottom row of a list; a bar packed in the box takes its own space
    and cannot cover anything. It shows only when the content is too wide."""
    scrolled.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.AUTOMATIC)
    adjustment = scrolled.get_hadjustment()
    bar = Gtk.Scrollbar(orientation=Gtk.Orientation.HORIZONTAL,
                        adjustment=adjustment)
    bar.set_no_show_all(True)  # visibility is ours, not show_all()'s
    box.pack_start(bar, False, False, 0)

    def sync(adj):
        bar.set_visible(adj.get_upper() - adj.get_page_size() > 1)

    adjustment.connect('changed', sync)
    sync(adjustment)
    return bar


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
        add_external_hscrollbar(self, self.scrolled)


# state label -> (glyph, color); distinct glyphs keep the states readable
# without relying on color alone. Shared by the Files panel and the per-commit
# changes window.
_STATE_ICONS = {
    'Untracked': ('?', '#9e9e9e'),
    'Modified': ('●', '#ff9800'),
    'Staged': ('●', '#4caf50'),
    'Added': ('+', '#4caf50'),
    'Deleted': ('−', '#ef5350'),
    'Deleted, staged': ('−', '#ef5350'),
    'Renamed': ('→', '#64b5f6'),
    'Copied': ('→', '#64b5f6'),
    'Conflict': ('!', '#d81b60'),
}


def state_icon(state):
    """Pango markup for a status glyph, given a human-readable state label."""
    if state.startswith('Staged + '):
        glyph, color = '±', '#ff9800'
    else:
        glyph, color = _STATE_ICONS.get(state, ('●', '#9e9e9e'))
    return '<span foreground="%s" weight="bold">%s</span>' % (color, glyph)


def make_name_column(icon_col, name_col):
    """Build the shared 'Name' tree column used by the Files panel and the
    per-commit changes window: a fixed-width status-glyph cell followed by an
    ellipsized file-name cell. `icon_col` / `name_col` are the model column
    indices for the glyph markup and the name text. Caller adds any sizing,
    sorting or expand behaviour it needs."""
    column = Gtk.TreeViewColumn('Name')
    icon = Gtk.CellRendererText(xalign=0.5)
    icon.set_fixed_size(22, -1)
    column.pack_start(icon, False)
    column.add_attribute(icon, 'markup', icon_col)
    name = Gtk.CellRendererText()
    name.props.ellipsize = 3  # Pango.EllipsizeMode.END
    column.pack_start(name, True)
    column.add_attribute(name, 'text', name_col)
    column.set_resizable(True)
    return column


def add_filler_column(view, expand=True):
    """Append a blank trailing column. GtkTreeView never draws a resize grip on
    its final column, so without this the last data column can't be resized —
    the filler gives it a right-hand neighbour to drag against. With `expand`
    set, the filler also absorbs any leftover width."""
    filler = Gtk.TreeViewColumn()
    filler.set_expand(expand)
    view.append_column(filler)
    return filler


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
