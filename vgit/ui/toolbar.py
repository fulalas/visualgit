import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf, GLib

from vgit.resources import resource_path

_ICON_PX = 24
_ICON_COLOR = '#2e3440'  # the fill/stroke the bundled SVGs are authored in


def _load_icon(name, fg_hex):
    # The authored colour is swapped for the widget's text colour: a fixed one
    # would vanish on either a light or a dark theme.
    path = resource_path('vgit', 'ui', 'icons', name + '.svg')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            svg = f.read().replace(_ICON_COLOR, fg_hex)
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.set_size(_ICON_PX, _ICON_PX)
        loader.write(svg.encode('utf-8'))
        loader.close()
        return loader.get_pixbuf()
    except (GLib.Error, OSError):
        return None


class Toolbar(Gtk.Toolbar):
    def __init__(self, on_add, on_pull, on_push, on_refresh, on_about):
        super().__init__()
        self.set_style(Gtk.ToolbarStyle.BOTH)
        self._icons = []

        self._add = self._button('add', 'Add', 'Add a local repository', on_add)
        self._pull = self._button('pull', 'Pull',
                                  'Pull from remote (Alt+Page Down)', on_pull)
        self._push = self._button('push', 'Push',
                                  'Push to remote (Alt+Page Up)', on_push)
        self._refresh = self._button('refresh', 'Refresh',
                                     'Reload everything from disk (F5)',
                                     on_refresh)

        spacer = Gtk.SeparatorToolItem()
        spacer.set_draw(False)
        spacer.set_expand(True)
        self.insert(spacer, -1)
        self._about = self._button('about', 'About', 'About VisualGit', on_about)

        self.connect('style-updated', lambda *_: self._recolor_icons())
        self._recolor_icons()

    def _button(self, icon, label, tooltip, callback):
        button = Gtk.ToolButton()
        image = Gtk.Image()
        self._icons.append((image, icon))
        button.set_icon_widget(image)
        button.set_label(label)
        button.set_tooltip_text(tooltip)
        button.connect('clicked', lambda *_: callback())
        self.insert(button, -1)
        return button

    def _recolor_icons(self):
        ctx = self.get_style_context()
        rgba = ctx.get_color(ctx.get_state())
        fg = '#%02x%02x%02x' % (round(rgba.red * 255), round(rgba.green * 255),
                                round(rgba.blue * 255))
        for image, name in self._icons:
            pixbuf = _load_icon(name, fg)
            if pixbuf is not None:
                image.set_from_pixbuf(pixbuf)
                image.show()

    def set_remote_ops_sensitive(self, sensitive):
        self._pull.set_sensitive(sensitive)
        self._push.set_sensitive(sensitive)
