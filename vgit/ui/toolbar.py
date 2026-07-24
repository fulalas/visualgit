"""Main toolbar: Add (repository), Pull, Push (left); About (right)."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class Toolbar(Gtk.Toolbar):
    def __init__(self, on_add, on_pull, on_push, on_about):
        super().__init__()
        self.set_style(Gtk.ToolbarStyle.BOTH)

        self._add = self._button('list-add', 'Add', 'Add a local repository', on_add)
        self._pull = self._button('go-down', 'Pull', 'Pull from remote', on_pull)
        self._push = self._button('go-up', 'Push', 'Push to remote', on_push)

        # Expanding, invisible separator pushes About to the right edge.
        spacer = Gtk.SeparatorToolItem()
        spacer.set_draw(False)
        spacer.set_expand(True)
        self.insert(spacer, -1)
        self._about = self._button('help-about', 'About', 'About VisualGit',
                                   on_about)

    def _button(self, icon, label, tooltip, callback):
        button = Gtk.ToolButton()
        button.set_icon_name(icon)
        button.set_label(label)
        button.set_tooltip_text(tooltip)
        button.connect('clicked', lambda *_: callback())
        self.insert(button, -1)
        return button

    def set_remote_ops_sensitive(self, sensitive):
        self._pull.set_sensitive(sensitive)
        self._push.set_sensitive(sensitive)
