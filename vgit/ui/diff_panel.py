"""Middle panel: unified diff viewer with syntax coloring."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

from vgit.ui.panel import Panel


class DiffPanel(Panel):
    def __init__(self):
        super().__init__('Changes')
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_monospace(True)
        self.textview.set_left_margin(6)
        self.buffer = self.textview.get_buffer()
        self.tags = {
            'add': self.buffer.create_tag('add', foreground='#4caf50'),
            'del': self.buffer.create_tag('del', foreground='#ef5350'),
            'hunk': self.buffer.create_tag('hunk', foreground='#64b5f6'),
            'meta': self.buffer.create_tag('meta', foreground='#9e9e9e',
                                           weight=Pango.Weight.BOLD),
        }
        self.scrolled.add(self.textview)

    def clear(self):
        self.buffer.set_text('')

    def set_diff(self, text):
        self.clear()
        end = self.buffer.get_end_iter()
        for line in text.splitlines(keepends=True):
            tag = None
            if line.startswith(('diff ', 'index ', '+++', '---', 'new file',
                                'deleted file', 'old mode', 'new mode', 'Binary')):
                tag = self.tags['meta']
            elif line.startswith('@@'):
                tag = self.tags['hunk']
            elif line.startswith('+'):
                tag = self.tags['add']
            elif line.startswith('-'):
                tag = self.tags['del']
            if tag:
                self.buffer.insert_with_tags(end, line, tag)
            else:
                self.buffer.insert(end, line)
