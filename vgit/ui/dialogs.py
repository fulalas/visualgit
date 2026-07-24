"""Modal dialogs: add repository, credentials, edit commit, locate git."""
import os

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GdkPixbuf, GLib

LOGO_PATH = os.path.join(os.path.dirname(__file__), 'logo.svg')


def choose_repository_folder(parent):
    dialog = Gtk.FileChooserDialog(title='Add Repository — choose a local path',
                                   parent=parent,
                                   action=Gtk.FileChooserAction.SELECT_FOLDER)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
    path = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
    dialog.destroy()
    return path


def choose_git_folder(parent):
    """Ask for the folder that contains the git program. Returns the folder
    path, or None if cancelled. No validation is done here."""
    dialog = Gtk.FileChooserDialog(
        title='Locate git — choose the folder containing the git program',
        parent=parent, action=Gtk.FileChooserAction.SELECT_FOLDER)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    for guess in ('/usr/bin', '/usr/local/bin', '/bin'):
        if os.path.isdir(guess):
            dialog.set_current_folder(guess)
            break
    folder = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
    dialog.destroy()
    return folder


def input_dialog(parent, title, label, text='', note=None):
    """One-field text prompt. Returns the entered text (stripped) or None."""
    dialog = Gtk.Dialog(title=title, parent=parent, modal=True)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.set_default_size(480, -1)
    entry = Gtk.Entry(text=text, activates_default=True)
    box = dialog.get_content_area()
    box.pack_start(_labeled_grid([(label, entry)]), True, True, 0)
    if note:
        note_label = Gtk.Label(label=note, xalign=0, wrap=True,
                               max_width_chars=56,
                               margin_start=12, margin_end=12, margin_bottom=12)
        note_label.get_style_context().add_class('dim-label')
        box.pack_start(note_label, False, False, 0)
    dialog.show_all()
    result = entry.get_text().strip() if dialog.run() == Gtk.ResponseType.OK else None
    dialog.destroy()
    return result


def about_dialog(parent, version):
    dialog = Gtk.AboutDialog(transient_for=parent, modal=True)
    try:
        dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(LOGO_PATH, 96, 96))
    except GLib.Error:
        dialog.set_logo_icon_name('applications-development')
    dialog.set_program_name('VisualGit')
    dialog.set_version(version)
    dialog.set_comments('A simple, intentionally minimal git GUI client.\n'
                        'All git operations shell out to the system git.')
    dialog.set_website('https://github.com/fulalas/visualgit')
    dialog.set_website_label('Project page')
    dialog.set_copyright('Python 3 · GTK 3 (PyGObject)')
    dialog.set_license_type(Gtk.License.MIT_X11)
    dialog.run()
    dialog.destroy()


def message_dialog(parent, title, text, kind=Gtk.MessageType.WARNING):
    dialog = Gtk.MessageDialog(parent=parent, modal=True, message_type=kind,
                               buttons=Gtk.ButtonsType.OK, text=title)
    dialog.format_secondary_text(text)
    dialog.run()
    dialog.destroy()


def _labeled_grid(rows):
    grid = Gtk.Grid(column_spacing=8, row_spacing=8,
                    margin_top=12, margin_bottom=12,
                    margin_start=12, margin_end=12)
    for i, (label, widget) in enumerate(rows):
        grid.attach(Gtk.Label(label=label, xalign=1), 0, i, 1, 1)
        widget.set_hexpand(True)
        grid.attach(widget, 1, i, 1, 1)
    return grid


def credentials_dialog(parent, repo_name, username='', has_password=False,
                       note=None):
    """Ask for user/password for one repository. Returns (user, password) or
    None. `note` is an optional explanation shown at the bottom."""
    dialog = Gtk.Dialog(title='Credentials — %s' % repo_name, parent=parent,
                        modal=True)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.set_default_size(460, -1)

    user_entry = Gtk.Entry(text=username, activates_default=True)
    pass_entry = Gtk.Entry(visibility=False, activates_default=True)
    pass_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    if has_password:
        pass_entry.set_placeholder_text('leave empty to keep the current password')
    box = dialog.get_content_area()
    box.pack_start(
        _labeled_grid([('Username:', user_entry), ('Password:', pass_entry)]),
        True, True, 0)
    if note:
        note_label = Gtk.Label(label=note, xalign=0, wrap=True,
                               max_width_chars=54,
                               margin_start=12, margin_end=12, margin_bottom=12)
        note_label.get_style_context().add_class('dim-label')
        box.pack_start(note_label, False, False, 0)
    dialog.show_all()

    result = None
    if dialog.run() == Gtk.ResponseType.OK:
        result = (user_entry.get_text(), pass_entry.get_text())
    dialog.destroy()
    return result


def identity_dialog(parent, repo_name, name='', email='', note=None):
    """Ask for the commit identity of one repository (user.name / user.email).
    Returns (name, email) or None. `note` is an optional explanation shown
    at the bottom."""
    dialog = Gtk.Dialog(title='Identity — %s' % repo_name, parent=parent,
                        modal=True)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    dialog.set_default_size(460, -1)

    name_entry = Gtk.Entry(text=name, activates_default=True)
    email_entry = Gtk.Entry(text=email, activates_default=True)
    box = dialog.get_content_area()
    box.pack_start(_labeled_grid([('Name:', name_entry),
                                  ('Email:', email_entry)]), True, True, 0)
    if note:
        note_label = Gtk.Label(label=note, xalign=0, wrap=True,
                               max_width_chars=54,
                               margin_start=12, margin_end=12, margin_bottom=12)
        note_label.get_style_context().add_class('dim-label')
        box.pack_start(note_label, False, False, 0)
    dialog.show_all()

    result = None
    if dialog.run() == Gtk.ResponseType.OK:
        result = (name_entry.get_text().strip(), email_entry.get_text().strip())
    dialog.destroy()
    return result


def confirm_dialog(parent, title, text):
    """Yes/No confirmation. Returns True if the user confirmed."""
    dialog = Gtk.MessageDialog(parent=parent, modal=True,
                               message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.YES_NO,
                               text=title)
    dialog.format_secondary_text(text)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.YES


def edit_commit_dialog(parent, message, author_name, author_email):
    """Edit a commit's message and author. Returns dict or None."""
    dialog = Gtk.Dialog(title='Edit Commit', parent=parent, modal=True)
    dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                       Gtk.STOCK_OK, Gtk.ResponseType.OK)
    dialog.set_default_size(560, 340)

    name_entry = Gtk.Entry(text=author_name)
    email_entry = Gtk.Entry(text=author_email)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_shadow_type(Gtk.ShadowType.IN)
    textview = Gtk.TextView()
    textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    textview.get_buffer().set_text(message)
    scrolled.add(textview)
    scrolled.set_vexpand(True)

    box = dialog.get_content_area()
    box.pack_start(_labeled_grid([('Author name:', name_entry),
                                  ('Author email:', email_entry)]), False, False, 0)
    label = Gtk.Label(label='Message:', xalign=0,
                      margin_start=12, margin_bottom=4)
    box.pack_start(label, False, False, 0)
    scrolled.set_margin_start(12)
    scrolled.set_margin_end(12)
    scrolled.set_margin_bottom(12)
    box.pack_start(scrolled, True, True, 0)
    dialog.show_all()

    result = None
    if dialog.run() == Gtk.ResponseType.OK:
        buffer = textview.get_buffer()
        start, end = buffer.get_bounds()
        result = {'message': buffer.get_text(start, end, False).strip(),
                  'author_name': name_entry.get_text().strip(),
                  'author_email': email_entry.get_text().strip()}
    dialog.destroy()
    return result
