"""Top-center panel: working tree / index status table (multi-select)."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from vgit.ui.panel import Panel, popup_menu, row_at_event

(COL_NAME, COL_STATE, COL_DIR, COL_PATH, COL_STAGED, COL_UNSTAGED,
 COL_UNTRACKED, COL_NAME_MARKUP) = range(8)

# state label -> (glyph, color); distinct glyphs keep the states readable
# without relying on color alone.
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


def _state_icon(state):
    if state.startswith('Staged + '):
        glyph, color = '±', '#ff9800'
    else:
        glyph, color = _STATE_ICONS.get(state, ('●', '#9e9e9e'))
    return '<span foreground="%s" weight="bold">%s</span>' % (color, glyph)


class FilesPanel(Panel):
    def __init__(self, on_file_selected, on_stage, on_unstage, on_open, on_reveal,
                 on_discard, on_delete, on_ignore):
        """on_open / on_reveal receive one entry; on_stage / on_unstage /
        on_discard / on_delete / on_ignore receive a list of entries.
        on_file_selected receives one entry, or None when zero or several
        files are selected."""
        super().__init__('Files')
        self.on_file_selected = on_file_selected
        self.on_stage = on_stage
        self.on_unstage = on_unstage
        self.on_open = on_open
        self.on_reveal = on_reveal
        self.on_discard = on_discard
        self.on_delete = on_delete
        self.on_ignore = on_ignore
        self._rebuilding = False

        self.store = Gtk.ListStore(str, str, str, str, bool, bool, bool, str)
        self.view = Gtk.TreeView(model=self.store)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self._columns = {}
        for title, col, key, width in (('Name', COL_NAME, 'name', 260),
                                       ('State', COL_STATE, 'state', 130),
                                       ('Relative Directory', COL_DIR, 'dir', 300)):
            renderer = Gtk.CellRendererText()
            renderer.props.ellipsize = 3  # Pango.EllipsizeMode.END
            if col == COL_NAME:
                # Icon glyph + name in one cell; sorting stays on the plain name.
                column = Gtk.TreeViewColumn(title, renderer,
                                            markup=COL_NAME_MARKUP)
            else:
                column = Gtk.TreeViewColumn(title, renderer, text=col)
            column.set_resizable(True)
            column.set_sort_column_id(col)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            self.view.append_column(column)
            self._columns[key] = column
        self.view.get_selection().connect('changed', self._on_selection_changed)
        self.view.connect('row-activated', self._on_row_activated)
        self.view.connect('button-press-event', self._on_button_press)
        self.scrolled.add(self.view)

    def get_column_widths(self):
        return {key: column.get_width() or column.get_fixed_width()
                for key, column in self._columns.items()}

    def set_column_widths(self, widths):
        for key, column in self._columns.items():
            if widths.get(key, 0) > 0:
                column.set_fixed_width(widths[key])

    def set_files(self, entries):
        self._rebuilding = True
        selected = {e['path'] for e in self.selected_entries()}
        self.store.clear()
        for e in entries:
            markup = '%s %s' % (_state_icon(e['state']),
                                GLib.markup_escape_text(e['name']))
            self.store.append([e['name'], e['state'], e['dir'], e['path'],
                               e['staged'], e['unstaged'], e['untracked'],
                               markup])
        # Keep _rebuilding set while re-selecting: each select_iter would
        # otherwise fire selection-changed and load a diff per restored row.
        selection = self.view.get_selection()
        for row in self.store:
            if row[COL_PATH] in selected:
                selection.select_iter(row.iter)
        self._rebuilding = False

    @staticmethod
    def _entry(row):
        return {'path': row[COL_PATH], 'staged': row[COL_STAGED],
                'unstaged': row[COL_UNSTAGED], 'untracked': row[COL_UNTRACKED]}

    def selected_entries(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [self._entry(model[p]) for p in paths]

    def _on_selection_changed(self, _selection):
        if self._rebuilding:
            return
        entries = self.selected_entries()
        self.on_file_selected(entries[0] if len(entries) == 1 else None)

    def _on_row_activated(self, view, path, column):
        self.on_open(self._entry(self.store[path]))

    def _on_button_press(self, view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        if event.button == 1:
            # Left click on empty space clears the selection.
            if view.get_path_at_pos(int(event.x), int(event.y)) is None:
                view.get_selection().unselect_all()
            return False
        if event.button != 3:
            return False
        if row_at_event(view, event) is None:
            return True
        entries = self.selected_entries()
        if not entries:
            return True
        single = len(entries) == 1
        items = [
            ('Open file', lambda: self.on_open(entries[0]), single),
            ('Reveal in file manager', lambda: self.on_reveal(entries[0]), single),
            None,
        ]
        stageable = [e for e in entries if e['unstaged'] or e['untracked']]
        unstageable = [e for e in entries if e['staged']]
        if stageable:
            items.append(('Stage', lambda: self.on_stage(stageable)))
        if unstageable:
            items.append(('Unstage', lambda: self.on_unstage(unstageable)))
        if stageable or unstageable:
            items.append(None)
        discardable = [e for e in entries if not e['untracked']]
        if discardable:
            items.append(('Discard', lambda: self.on_discard(discardable)))
        items.append(('Delete', lambda: self.on_delete(entries)))
        ignorable = [e for e in entries if e['untracked']]
        if ignorable:
            items.append(('Add to .gitignore', lambda: self.on_ignore(ignorable)))
        popup_menu(view, event, items)
        return True
