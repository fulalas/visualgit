"""Non-modal window showing the files changed by a single commit and their
diff. Opened by double-clicking a commit in the Journal panel."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from vgit.gitcmd import GitError
from vgit.ui.diff_panel import DiffPanel
from vgit.ui.panel import (add_external_hscrollbar, add_filler_column,
                           make_name_column, state_icon)

COL_ICON, COL_NAME, COL_DIR, COL_PATH, COL_STATE = range(5)


class CommitWindow(Gtk.Window):
    def __init__(self, parent, git, commit, short, config):
        super().__init__(title='Commit %s' % short)
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)
        self.git = git
        self.commit = commit
        self.config = config
        state = dict(config.get_state('commit_window', {}))
        self.set_default_size(state.get('width', 1000), state.get('height', 640))
        self.connect('key-press-event', self._on_key_press)
        self.connect('delete-event', self._on_delete)

        # Vertical paned so the header's message area can be resized by dragging.
        root = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        root.pack1(self._build_header(), False, False)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack2(paned, True, False)
        root.set_position(state.get('header_pos', 251))
        self._root_paned = root

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Label(label='Files', xalign=0)
        header.get_style_context().add_class('vgit-panel-header')
        left.pack_start(header, False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        left.pack_start(scrolled, True, True, 0)
        add_external_hscrollbar(left, scrolled)

        self.store = Gtk.ListStore(str, str, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        # Fixed widths + an expanding filler (as in the Files panel) so both
        # columns stay resizable and their widths can be persisted.
        self._name_col = make_name_column(COL_ICON, COL_NAME)
        self._name_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self._name_col.set_fixed_width(state.get('name_width') or 300)
        self.view.append_column(self._name_col)
        self._state_col = Gtk.TreeViewColumn('State', Gtk.CellRendererText(),
                                             text=COL_STATE)
        self._state_col.set_resizable(True)
        self._state_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self._state_col.set_fixed_width(state.get('state_width') or 130)
        self.view.append_column(self._state_col)
        add_filler_column(self.view, expand=True)
        self.view.get_selection().connect('changed', self._on_selection_changed)
        scrolled.add(self.view)

        self.diff_panel = DiffPanel()

        paned.pack1(left, False, False)
        paned.pack2(self.diff_panel, True, False)
        paned.set_position(state.get('files_pos', 340))
        self._files_paned = paned

        self._load()
        self.show_all()
        # A selectable label highlights all its text when it gains focus during
        # setup; focus the file list and clear that selection so nothing looks
        # pre-selected on open.
        self.view.grab_focus()
        self._message_label.select_region(0, 0)

    def _build_header(self):
        """Bar above the Files/Changes sections: commit author and message."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_border_width(8)
        try:
            name, email, message = self.git.commit_info(self.commit)
        except GitError:
            name, email, message = '', '', ''
        author = Gtk.Label(xalign=0)
        author.set_markup('<b>%s</b> &lt;%s&gt;' % (
            GLib.markup_escape_text(name), GLib.markup_escape_text(email)))
        box.pack_start(author, False, False, 0)
        # Message inside a scroller so the (resizable) header can show a long
        # message without forcing the window taller. NEVER horizontally so the
        # label wraps to width instead of scrolling sideways.
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        msg = Gtk.Label(label=message, xalign=0, yalign=0)
        msg.set_line_wrap(True)
        msg.set_selectable(True)
        msg.set_margin_top(4)
        self._message_label = msg
        scrolled.add(msg)
        box.pack_start(scrolled, True, True, 0)
        return box

    def _on_delete(self, *_args):
        """Persist geometry, splitter positions and column widths so the next
        commit window opens the way the user left this one."""
        width, height = self.get_size()
        self.config.set_state('commit_window', {
            'width': width, 'height': height,
            'header_pos': self._root_paned.get_position(),
            'files_pos': self._files_paned.get_position(),
            'name_width': self._name_col.get_width(),
            'state_width': self._state_col.get_width(),
        })
        return False

    def _on_key_press(self, _widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if event.keyval == Gdk.KEY_Escape or (
                ctrl and event.keyval in (Gdk.KEY_q, Gdk.KEY_Q)):
            self.close()
            return True
        return False

    def _load(self):
        try:
            files = self.git.commit_files(self.commit)
        except GitError as exc:
            self.diff_panel.set_diff('Failed to load commit: %s' % exc)
            return
        for f in files:
            self.store.append([state_icon(f['state']), f['name'], f['dir'],
                               f['path'], f['state']])
        first = self.store.get_iter_first()
        if first is not None:
            self.view.get_selection().select_iter(first)
        else:
            self.diff_panel.set_diff('This commit changed no files.')

    def _on_selection_changed(self, selection):
        model, itr = selection.get_selected()
        if itr is None:
            self.diff_panel.clear()
            return
        try:
            diff = self.git.commit_file_diff(self.commit, model[itr][COL_PATH])
        except GitError as exc:
            diff = 'Failed to load diff: %s' % exc
        self.diff_panel.set_diff(diff)
