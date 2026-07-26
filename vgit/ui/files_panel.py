"""Top-center panel: working tree / index status table (multi-select)."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from vgit.ui.panel import (Panel, popup_menu, row_at_event, add_filler_column,
                           make_name_column, state_icon)

(COL_NAME, COL_STATE, COL_DIR, COL_PATH, COL_STAGED, COL_UNSTAGED,
 COL_UNTRACKED, COL_ICON) = range(8)


class FilesPanel(Panel):
    def __init__(self, on_file_selected, on_stage, on_unstage, on_open, on_reveal,
                 on_discard, on_delete, on_untrack, on_ignore):
        """on_open / on_reveal receive one entry; on_stage / on_unstage /
        on_discard / on_delete / on_untrack / on_ignore receive a list of
        entries. on_file_selected receives one entry, or None when zero or
        several files are selected."""
        super().__init__('Files')
        self.on_file_selected = on_file_selected
        self.on_stage = on_stage
        self.on_unstage = on_unstage
        self.on_open = on_open
        self.on_reveal = on_reveal
        self.on_discard = on_discard
        self.on_delete = on_delete
        self.on_untrack = on_untrack
        self.on_ignore = on_ignore
        self._rebuilding = False

        self.store = Gtk.ListStore(str, str, str, str, bool, bool, bool, str)
        self.view = Gtk.TreeView(model=self.store)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self._columns = {}

        # Name column: a fixed-width icon cell + the name cell, so names line
        # up regardless of the state glyph's natural width.
        name_col = make_name_column(COL_ICON, COL_NAME)
        name_col.set_sort_column_id(COL_NAME)
        name_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        name_col.set_fixed_width(260)
        self.view.append_column(name_col)
        self._columns['name'] = name_col

        for title, col, key, width in (('State', COL_STATE, 'state', 130),
                                       ('Relative Directory', COL_DIR, 'dir', 300)):
            renderer = Gtk.CellRendererText()
            renderer.props.ellipsize = 3  # Pango.EllipsizeMode.END
            column = Gtk.TreeViewColumn(title, renderer, text=col)
            column.set_resizable(True)
            column.set_sort_column_id(col)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            self.view.append_column(column)
            self._columns[key] = column
        # Trailing filler absorbs leftover width and gives the last real column
        # a resize grip (GTK won't draw one on the final column).
        add_filler_column(self.view, expand=True)
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
            self.store.append([e['name'], e['state'], e['dir'], e['path'],
                               e['staged'], e['unstaged'], e['untracked'],
                               state_icon(e['state'])])
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
        trackable = [e for e in entries if not e['untracked']]
        if trackable:
            items.append(('Stop tracking...', lambda: self.on_untrack(trackable)))
        items.append(('Delete...', lambda: self.on_delete(entries)))
        ignorable = [e for e in entries if e['untracked']]
        if ignorable:
            items.append(('Add to .gitignore...', lambda: self.on_ignore(ignorable)))
        popup_menu(view, event, items)
        return True
