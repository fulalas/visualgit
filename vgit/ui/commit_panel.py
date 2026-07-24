"""Top-right panel: commit message field with Ctrl+Up/Down history navigation."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk


class CommitPanel(Gtk.Box):
    def __init__(self, on_commit, get_history, on_info):
        """get_history() -> list of past commit messages (newest first).
        on_info(text) shows a toast message."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.on_commit = on_commit
        self.get_history = get_history
        self.on_info = on_info

        header = Gtk.Label(label='Commit', xalign=0)
        header.get_style_context().add_class('vgit-panel-header')
        self.pack_start(header, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(6)
        self.textview.set_right_margin(6)
        self.textview.set_top_margin(4)
        self.textview.connect('key-press-event', self._on_key_press)
        self.buffer = self.textview.get_buffer()
        self.buffer.connect('changed', self._on_buffer_changed)
        scrolled.add(self.textview)
        self.pack_start(scrolled, True, True, 0)

        action_row = Gtk.Box(spacing=6)
        action_row.set_margin_top(4)
        action_row.set_margin_bottom(4)
        action_row.set_margin_end(4)
        commit_button = Gtk.Button(label='Commit')
        commit_button.connect('clicked', lambda *_: self.on_commit())
        action_row.pack_end(commit_button, False, False, 0)
        self.pack_start(action_row, False, False, 0)

        # Message-history navigation state.
        self._messages = None   # fetched lazily on first Ctrl+Up
        self._index = -1        # -1 = the user's own draft
        self._draft = ''
        self._navigating = False

    def get_message(self):
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, False)

    def set_message(self, text):
        self._set_text(text)
        self.reset_history()

    def clear(self):
        self.set_message('')

    def reset_history(self):
        self._messages = None
        self._index = -1
        self._draft = ''

    def _set_text(self, text):
        self._navigating = True
        self.buffer.set_text(text)
        self._navigating = False

    def _on_buffer_changed(self, _buffer):
        # A manual edit becomes the new draft; navigation restarts from it.
        if not self._navigating:
            self._messages = None
            self._index = -1

    def _on_key_press(self, _view, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        if event.keyval == Gdk.KEY_Up:
            self._history_older()
            return True
        if event.keyval == Gdk.KEY_Down:
            self._history_newer()
            return True
        return False

    def _history_older(self):
        if self._messages is None:
            self._messages = self.get_history()
            self._index = -1
            if not self._messages:
                self.on_info('No previous commit messages.')
                self._messages = None
                return
            self._draft = self.get_message()
        if self._index + 1 >= len(self._messages):
            self.on_info('Reached the oldest commit message.')
            return
        self._index += 1
        self._set_text(self._messages[self._index])

    def _history_newer(self):
        if self._messages is None or self._index < 0:
            return
        self._index -= 1
        if self._index == -1:
            self._set_text(self._draft)
        else:
            self._set_text(self._messages[self._index])
