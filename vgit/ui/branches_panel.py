"""Bottom-left panel: local and remote branches, grouped by remote.

Local non-current and remote branches offer 'Checkout' and 'Merge from'
via context menu; double-click also checks out.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

from vgit.ui.panel import Panel, popup_menu, row_at_event

COL_MARKUP, COL_NAME, COL_KIND, COL_CURRENT = range(4)
# kind: 'header' (group row), 'local', 'remote'


class BranchesPanel(Panel):
    def __init__(self, on_merge_from, on_checkout, on_delete):
        """on_checkout(name, kind) and on_delete(name, kind) with kind
        'local' or 'remote'."""
        super().__init__('Branches')
        self.on_merge_from = on_merge_from
        self.on_checkout = on_checkout
        self.on_delete = on_delete

        self.store = Gtk.TreeStore(str, str, str, bool)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        self.view.set_show_expanders(True)
        column = Gtk.TreeViewColumn('Branch', Gtk.CellRendererText(), markup=COL_MARKUP)
        self.view.append_column(column)
        self.view.connect('button-press-event', self._on_button_press)
        self.view.connect('row-activated', self._on_row_activated)
        self.scrolled.add(self.view)

    def set_branches(self, names, current, remote_names=(), ahead=None):
        """`ahead` maps a local branch name to its count of unpushed commits."""
        ahead = ahead or {}
        self.store.clear()
        shown = list(names)
        if current and current not in shown:
            shown.insert(0, current)  # detached HEAD / unborn branch

        local_parent = self.store.append(None, [
            '<b>Local Branches (%d)</b>' % len(shown), '', 'header', False])
        for name in shown:
            is_current = name == current
            escaped = GLib.markup_escape_text(name)
            markup = '<b>▸ %s</b>' % escaped if is_current else escaped
            count = ahead.get(name, 0)
            if count:
                # Commits committed locally but not yet pushed to the upstream.
                markup += (' <span size="small" foreground="#ff9800">(%d)</span>'
                           % count)
            self.store.append(local_parent, [markup, name, 'local', is_current])

        remotes = {}
        for ref in remote_names:
            remote, _, short = ref.partition('/')
            if not short:
                continue
            remotes.setdefault(remote, []).append(ref)
        for remote in sorted(remotes):
            parent = self.store.append(None, [
                '<b>%s (%d)</b>' % (GLib.markup_escape_text(remote),
                                    len(remotes[remote])), '', 'header', False])
            for ref in sorted(remotes[remote], key=str.lower, reverse=True):
                short = ref.partition('/')[2]
                self.store.append(parent, [
                    GLib.markup_escape_text(short), ref, 'remote', False])

        self.view.expand_row(self.store.get_path(local_parent), False)

    def _row_info(self, itr):
        row = self.store[itr]
        return row[COL_NAME], row[COL_KIND], row[COL_CURRENT]

    def _on_row_activated(self, view, path, _column):
        itr = self.store.get_iter(path)
        name, kind, is_current = self._row_info(itr)
        if kind in ('local', 'remote') and not is_current:
            self.on_checkout(name, kind)

    def _on_button_press(self, view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 3:
            return False
        itr = row_at_event(view, event)
        if itr is None:
            return True
        name, kind, is_current = self._row_info(itr)
        if kind == 'header' or is_current:
            return True
        popup_menu(view, event, [
            ('Checkout', lambda: self.on_checkout(name, kind)),
            ('Merge from', lambda: self.on_merge_from(name)),
            ('Delete', lambda: self.on_delete(name, kind)),
        ])
        return True
