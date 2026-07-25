"""Non-modal window showing the files changed by a single commit and their
diff. Opened by double-clicking a commit in the Journal panel."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from vgit.gitcmd import GitError
from vgit.ui.diff_panel import DiffPanel
from vgit.ui.panel import add_filler_column, state_icon

COL_ICON, COL_NAME, COL_DIR, COL_PATH, COL_STATE = range(5)


class CommitWindow(Gtk.Window):
    def __init__(self, parent, git, commit, short):
        super().__init__(title='Commit %s' % short)
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)
        self.set_default_size(1000, 640)
        self.git = git
        self.commit = commit
        self.connect('key-press-event', self._on_key_press)

        # Vertical paned so the header's message area can be resized by dragging.
        root = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        root.pack1(self._build_header(), False, False)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack2(paned, True, False)
        root.set_position(251)

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
