"""Non-modal, temporary message shown as a popover at the bottom of the window."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib


class Toast(Gtk.Revealer):
    def __init__(self):
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.set_transition_duration(200)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(24)
        self._label = Gtk.Label()
        self._label.set_line_wrap(True)
        self._label.set_max_width_chars(90)
        box = Gtk.Box()
        box.get_style_context().add_class('vgit-toast')
        box.pack_start(self._label, True, True, 0)
        self.add(box)
        self._timeout_id = None

    def show_message(self, text, seconds=4):
        self._label.set_text(text)
        self.show_all()
        self.set_reveal_child(True)
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = GLib.timeout_add_seconds(seconds, self._hide)

    def _hide(self):
        self.set_reveal_child(False)
        self._timeout_id = None
        return False
