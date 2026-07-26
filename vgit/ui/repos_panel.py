"""Top-left panel: list of registered repositories."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

from vgit.ui.panel import Panel, popup_menu, row_at_event

COL_MARKUP, COL_PATH, COL_NAME, COL_BRANCH = range(4)


class ReposPanel(Panel):
    def __init__(self, on_selected, on_set_credentials, on_set_identity,
                 on_set_remote, on_remove):
        super().__init__('Repositories')
        self.on_selected = on_selected
        self.on_set_credentials = on_set_credentials
        self.on_set_identity = on_set_identity
        self.on_set_remote = on_set_remote
        self.on_remove = on_remove
        self._rebuilding = False
        self._active = None

        self.store = Gtk.ListStore(str, str, str, str)  # markup, path, name, branch
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        column = Gtk.TreeViewColumn('Repository', Gtk.CellRendererText(), markup=COL_MARKUP)
        self.view.append_column(column)
        self.view.set_tooltip_column(COL_PATH)
        self.view.get_selection().connect('changed', self._on_selection_changed)
        self.view.connect('button-press-event', self._on_button_press)
        self.view.connect('key-press-event', self._on_key_press)
        self.scrolled.add(self.view)

    def _markup(self, name, branch, active):
        name_markup = GLib.markup_escape_text(name)
        if active:
            name_markup = '<b>▸ %s</b>' % name_markup
        else:
            name_markup = '   %s' % name_markup
        return '%s <span size="small" alpha="55%%">(%s)</span>' % (
            name_markup, GLib.markup_escape_text(branch))

    def _render_row(self, row):
        row[COL_MARKUP] = self._markup(row[COL_NAME], row[COL_BRANCH],
                                       row[COL_PATH] == self._active)

    def set_repos(self, items):
        """items: list of dicts with 'path', 'name', 'branch'."""
        self._rebuilding = True
        selected = self.selected_path()
        self.store.clear()
        for item in items:
            row = self.store.append(['', item['path'], item['name'], item['branch']])
            self._render_row(self.store[row])
        self._rebuilding = False
        if selected:
            self.select(selected)

    def set_active(self, path):
        self._active = path
        for row in self.store:
            self._render_row(row)

    def update_branch(self, path, name, branch):
        for row in self.store:
            if row[COL_PATH] == path:
                row[COL_NAME] = name
                row[COL_BRANCH] = branch
                self._render_row(row)
                break

    def select(self, path):
        for row in self.store:
            if row[COL_PATH] == path:
                self.view.get_selection().select_iter(row.iter)
                return True
        return False

    def selected_path(self):
        model, itr = self.view.get_selection().get_selected()
        return model[itr][COL_PATH] if itr else None

    def _on_selection_changed(self, selection):
        if self._rebuilding:
            return
        model, itr = selection.get_selected()
        if itr:
            self.on_selected(model[itr][COL_PATH])

    def _on_key_press(self, _view, event):
        # Delete key mirrors the context-menu 'Remove repository' action.
        if event.keyval != Gdk.KEY_Delete:
            return False
        path = self.selected_path()
        if path is None:
            return False
        self.on_remove(path)
        return True

    def _on_button_press(self, view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 3:
            return False
        itr = row_at_event(view, event)
        if itr is None:
            return True
        path = self.store[itr][COL_PATH]
        popup_menu(view, event, [
            ('Set remote…', lambda: self.on_set_remote(path)),
            ('Set credentials…', lambda: self.on_set_credentials(path)),
            ('Set identity…', lambda: self.on_set_identity(path)),
            ('Remove repository...', lambda: self.on_remove(path)),
        ])
        return True
