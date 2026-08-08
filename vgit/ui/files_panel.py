"""Top-center panel: working tree / index status table (multi-select)."""
from collections import Counter

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from vgit.ui.panel import (Panel, popup_menu, row_at_event, add_filler_column,
                           make_name_column, state_icon)

(COL_NAME, COL_STATE, COL_TYPE, COL_DIR, COL_PATH, COL_STAGED, COL_UNSTAGED,
 COL_UNTRACKED, COL_ICON) = range(9)


class FilesPanel(Panel):
    def __init__(self, on_files_selected, on_stage, on_unstage, on_open, on_reveal,
                 on_discard, on_delete, on_untrack, on_ignore):
        """on_open receives one entry; on_reveal receives one entry, or None to
        reveal the repository folder; on_files_selected / on_stage / on_unstage /
        on_discard / on_delete / on_untrack / on_ignore receive a list of
        entries."""
        super().__init__('Files')
        self.on_files_selected = on_files_selected
        self.on_stage = on_stage
        self.on_unstage = on_unstage
        self.on_open = on_open
        self.on_reveal = on_reveal
        self.on_discard = on_discard
        self.on_delete = on_delete
        self.on_untrack = on_untrack
        self.on_ignore = on_ignore
        self._rebuilding = False

        self.store = Gtk.ListStore(str, str, str, str, str, bool, bool, bool, str)
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
                                       ('Type', COL_TYPE, 'type', 80),
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
        self.view.connect('key-press-event', self._on_key_press)
        self.scrolled.add(self.view)

    def get_column_widths(self):
        return {key: column.get_width() or column.get_fixed_width()
                for key, column in self._columns.items()}

    def set_column_widths(self, widths):
        for key, column in self._columns.items():
            if widths.get(key, 0) > 0:
                column.set_fixed_width(widths[key])

    def clear_selection(self):
        """Drop the selection without loading a diff. Used when switching repos,
        where keeping the old repo's rows selected makes no sense."""
        self._rebuilding = True
        self.view.get_selection().unselect_all()
        self._rebuilding = False

    def set_files(self, entries):
        """Bring the list up to date by touching only what changed: a staged
        file just gets a new icon and state text. Emptying and refilling the
        store would make the whole list blink and reset the scroll position.
        _rebuilding stays set throughout, so the selection changes GTK makes
        while rows come and go don't each load a diff — callers refresh the
        diff once the list is settled."""
        self._rebuilding = True
        selection = self.view.get_selection()
        _model, selected = selection.get_selected_rows()
        first_row = selected[0].get_indices()[0] if selected else 0

        # A path can show up twice — `git rm --cached` leaves a file both as a
        # staged deletion and as untracked — so rows are matched by path *and*
        # count, otherwise the second entry would overwrite the first one's row
        # and one of the two would never be listed.
        wanted = Counter(e['path'] for e in entries)
        kept_above = 0  # surviving rows above the selection: its new position
        position = 0
        row_iter = self.store.get_iter_first()
        while row_iter is not None:
            path = self.store[row_iter][COL_PATH]
            if wanted[path]:
                wanted[path] -= 1
                kept_above += position < first_row
                row_iter = self.store.iter_next(row_iter)
            elif not self.store.remove(row_iter):  # removed the last row
                row_iter = None
            position += 1

        # With a sort column active the store decides where a row goes, so new
        # ones are simply appended; unsorted, they take their `git status` spot
        # (the rows that survived are still in that order).
        sort_column = self.store.get_sort_column_id()[0]  # None while unsorted
        by_column = sort_column is not None and sort_column >= 0
        rows = {}
        for row in self.store:
            rows.setdefault(row[COL_PATH], []).append(row)
        for index, e in enumerate(entries):
            values = [e['name'], e['state'], e['type'], e['dir'], e['path'],
                      e['staged'], e['unstaged'], e['untracked'],
                      state_icon(e['state'])]
            same_path = rows.get(e['path'])
            if not same_path:
                self.store.insert(len(self.store) if by_column else index, values)
                continue
            row = same_path.pop(0)
            for col, value in enumerate(values):
                if row[col] != value:
                    row[col] = value

        if selected and not selection.count_selected_rows() and len(self.store):
            # Every selected file left the list (staged, committed, discarded):
            # select whatever took its place instead of losing the position.
            index = min(kept_above, len(self.store) - 1)
            selection.select_path(Gtk.TreePath.new_from_indices([index]))
        self._rebuilding = False

    @staticmethod
    def _entry(row):
        return {'path': row[COL_PATH], 'staged': row[COL_STAGED],
                'unstaged': row[COL_UNSTAGED], 'untracked': row[COL_UNTRACKED]}

    def cursor_path(self):
        """Path of the row the keyboard cursor sits on — the file just reached
        with the arrow keys — or None when there is no cursor."""
        tree_path, _column = self.view.get_cursor()
        if tree_path is None:
            return None
        return self.store[tree_path][COL_PATH]

    def selected_entries(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [self._entry(model[p]) for p in paths]

    def _on_selection_changed(self, _selection):
        if self._rebuilding:
            return
        self.on_files_selected(self.selected_entries())

    def _on_row_activated(self, view, path, column):
        self.on_open(self._entry(self.store[path]))

    def _on_key_press(self, _view, event):
        # Delete key mirrors the context-menu 'Delete' action.
        if event.keyval != Gdk.KEY_Delete:
            return False
        entries = self.selected_entries()
        if not entries:
            return False
        self.on_delete(entries)
        return True

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
            # Empty space: only the repository folder can be acted on.
            view.get_selection().unselect_all()
            popup_menu(view, event,
                       [('Reveal in file manager', lambda: self.on_reveal(None))])
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
        ignorable = [e for e in entries if e['untracked']]
        if ignorable:
            items.append(('Add to .gitignore...', lambda: self.on_ignore(ignorable)))
        items.append(('Delete file...', lambda: self.on_delete(entries)))
        popup_menu(view, event, items)
        return True
