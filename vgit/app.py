"""Gtk.Application entry point."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from vgit.ui.window import MainWindow


class VisualGitApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.visualgit.VisualGit')

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
        window.present()
