"""Bottom panel: commit log (journal) with a commit context menu."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from vgit.ui.panel import Panel, popup_menu, row_at_event, add_filler_column

COL_HASH, COL_SHORT, COL_REFS, COL_SUBJECT, COL_AUTHOR, COL_DATE, COL_WEIGHT = \
    range(7)

WEIGHT_NORMAL, WEIGHT_BOLD = 400, 700


class JournalPanel(Panel):
    def __init__(self, on_copy_hash, on_edit_commit, on_checkout, on_show_changes):
        super().__init__('Journal')
        self.on_copy_hash = on_copy_hash
        self.on_edit_commit = on_edit_commit
        self.on_checkout = on_checkout
        self.on_show_changes = on_show_changes

        self.store = Gtk.ListStore(str, str, str, str, str, str, int)
        self.view = Gtk.TreeView(model=self.store)
        self._columns = {}
        for title, col, key, width in (('Hash', COL_SHORT, 'hash', 90),
                                       ('Refs', COL_REFS, 'refs', 120),
                                       ('Subject', COL_SUBJECT, None, 0),
                                       ('Author', COL_AUTHOR, 'author', 140),
                                       ('Date', COL_DATE, 'date', 140)):
            renderer = Gtk.CellRendererText()
            if col in (COL_SUBJECT, COL_AUTHOR):
                renderer.props.ellipsize = 3  # Pango.EllipsizeMode.END
            column = Gtk.TreeViewColumn(title, renderer, text=col,
                                        weight=COL_WEIGHT)
            column.set_resizable(True)
            if key is None:
                # Subject fills the remaining space; its width is derived,
                # so it is not persisted.
                column.set_expand(True)
            else:
                column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                column.set_fixed_width(width)
                self._columns[key] = column
            self.view.append_column(column)
        # Subject already soaks up the slack, so keep the filler width-less;
        # it exists only to give the Date column a resize grip.
        add_filler_column(self.view, expand=False)
        self.view.connect('button-press-event', self._on_button_press)
        self.view.connect('row-activated', self._on_row_activated)
        self.scrolled.add(self.view)

    def get_column_widths(self):
        return {key: column.get_width() or column.get_fixed_width()
                for key, column in self._columns.items()}

    def set_column_widths(self, widths):
        for key, column in self._columns.items():
            if widths.get(key, 0) > 0:
                column.set_fixed_width(widths[key])

    def set_commits(self, commits, head=None):
        self.store.clear()
        for c in commits:
            weight = WEIGHT_BOLD if c['hash'] == head else WEIGHT_NORMAL
            self.store.append([c['hash'], c['short'], c['refs'],
                               c['subject'], c['author'], c['date'], weight])

    def _on_row_activated(self, view, path, _column):
        row = self.store[path]
        self.on_show_changes(row[COL_HASH], row[COL_SHORT])

    def _on_button_press(self, view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 3:
            return False
        itr = row_at_event(view, event)
        if itr is None:
            return True
        commit = self.store[itr][COL_HASH]
        short = self.store[itr][COL_SHORT]
        popup_menu(view, event, [
            ('Show details...', lambda: self.on_show_changes(commit, short)),
            ('Copy commit hash', lambda: self.on_copy_hash(commit)),
            ('Edit message and author…', lambda: self.on_edit_commit(commit)),
            ('Checkout this commit', lambda: self.on_checkout(commit)),
        ])
        return True
