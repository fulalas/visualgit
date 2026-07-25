"""Non-modal window showing the files changed by a single commit and their
diff. Opened by double-clicking a commit in the Journal panel."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from vgit.gitcmd import GitError
from vgit.ui.diff_panel import DiffPanel
from vgit.ui.panel import add_filler_column, state_icon

COL_ICON, COL_NAME, COL_DIR, COL_PATH, COL_STATE = range(5)


class CommitWindow(Gtk.Window):
    def __init__(self, parent, git, commit, short, subject):
        super().__init__(title='Commit %s — %s' % (short, subject))
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)
        self.set_default_size(1000, 640)
        self.git = git
        self.commit = commit
        self.connect('key-press-event', self._on_key_press)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Label(label='Files', xalign=0)
        header.get_style_context().add_class('vgit-panel-header')
        left.pack_start(header, False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        left.pack_start(scrolled, True, True, 0)

        self.store = Gtk.ListStore(str, str, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        name_col = Gtk.TreeViewColumn('Name')
        icon = Gtk.CellRendererText(xalign=0.5)
        icon.set_fixed_size(22, -1)
        name_col.pack_start(icon, False)
        name_col.add_attribute(icon, 'markup', COL_ICON)
        name_renderer = Gtk.CellRendererText()
        name_renderer.props.ellipsize = 3  # Pango.EllipsizeMode.END
        name_col.pack_start(name_renderer, True)
        name_col.add_attribute(name_renderer, 'text', COL_NAME)
        name_col.set_resizable(True)
        name_col.set_expand(True)
        self.view.append_column(name_col)
        state_col = Gtk.TreeViewColumn('State', Gtk.CellRendererText(),
                                       text=COL_STATE)
        state_col.set_resizable(True)
        self.view.append_column(state_col)
        add_filler_column(self.view, expand=False)
        self.view.get_selection().connect('changed', self._on_selection_changed)
        scrolled.add(self.view)

        self.diff_panel = DiffPanel()

        paned.pack1(left, False, False)
        paned.pack2(self.diff_panel, True, False)
        paned.set_position(340)

        self._load()
        self.show_all()

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
