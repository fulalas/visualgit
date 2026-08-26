import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def add_external_hscrollbar(box, scrolled):
    # The scroller's own horizontal bar is drawn on top of the content and
    # hides the bottom row of a list, so it is packed in `box` instead.
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
    def __init__(self, title):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Label(label=title, xalign=0)
        header.get_style_context().add_class('vgit-panel-header')
        self.pack_start(header, False, False, 0)
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(self.scrolled, True, True, 0)
        add_external_hscrollbar(self, self.scrolled)


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
    if state.startswith('Staged + '):
        glyph, color = '±', '#ff9800'
    else:
        glyph, color = _STATE_ICONS.get(state, ('●', '#9e9e9e'))
    return '<span foreground="%s" weight="bold">%s</span>' % (color, glyph)


def make_name_column(icon_col, name_col):
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
    # GtkTreeView never draws a resize grip on its final column, so the last
    # data column needs a blank neighbour to be resizable at all.
    filler = Gtk.TreeViewColumn()
    filler.set_expand(expand)
    view.append_column(filler)
    return filler


def popup_menu(view, event, items):
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
    info = view.get_path_at_pos(int(event.x), int(event.y))
    if info is None:
        return None
    path = info[0]
    selection = view.get_selection()
    # Right-clicking a row that is already part of a multi-selection must keep
    # that selection.
    if not selection.path_is_selected(path):
        selection.unselect_all()
        selection.select_path(path)
    return view.get_model().get_iter(path)
