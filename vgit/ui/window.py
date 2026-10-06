import os
import shutil
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib

from vgit import __version__
from vgit import gitcmd
from vgit.config import Config
from vgit.gitcmd import Git, GitError
from vgit.ui import dialogs
from vgit.ui.branches_panel import BranchesPanel
from vgit.ui.commit_panel import CommitPanel
from vgit.ui.commit_window import CommitWindow
from vgit.ui.diff_panel import DiffPanel
from vgit.ui.files_panel import FilesPanel
from vgit.ui.journal_panel import JournalPanel
from vgit.ui.repos_panel import ReposPanel
from vgit.ui.toast import Toast
from vgit.ui.toolbar import Toolbar
from vgit.ui.watcher import FolderWatcher

CSS = b"""
.vgit-toast {
    background-color: rgba(25, 25, 25, 0.92);
    color: #ffffff;
    border-radius: 8px;
    padding: 10px 18px;
}
.vgit-panel-header {
    font-weight: bold;
    padding: 5px 8px;
    background-color: alpha(currentColor, 0.07);
}
"""


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='VisualGit - %s' % __version__)
        try:
            Gtk.Window.set_default_icon_from_file(dialogs.LOGO_PATH)
        except GLib.Error:
            pass
        self.config = Config()
        self.git = None
        self._drafts = dict(self.config.get_state('drafts', {}))
        self._last_status = None
        self._last_rev = None
        self._poll_busy = False
        self._remote_busy = False
        self._resync_pending = False
        self._refresh_pending = 0
        self._refresh_failed = False
        self._watcher = None
        self._fallback_poll_id = None
        self._commit_windows = []
        self._load_css()
        self._build_ui()
        self._restore_window_state()
        self.connect('key-press-event', self._on_key_press)
        self.connect('delete-event', self._on_close)
        self.show_all()
        self.files_panel.view.grab_focus()
        self._ensure_git()
        items = self._reload_repo_list()
        if items:
            saved = self.config.get_state('selected_repo')
            if not any(item['path'] == saved for item in items):
                saved = items[0]['path']
            self.repos_panel.select(saved)

    def _ensure_git(self):
        saved = self.config.get_state('git_binary')
        if saved:
            gitcmd.set_git_binary(saved)
        if gitcmd.git_available():
            return
        while True:
            folder = dialogs.choose_git_folder(self)
            if folder is None:
                self.toast.show_message(
                    'Git was not found — git operations are unavailable. '
                    'Restart to set its location.')
                return
            candidate = os.path.join(folder, 'git')
            if gitcmd.git_binary_works(candidate):
                gitcmd.set_git_binary(candidate)
                self.config.set_state('git_binary', candidate)
                self.toast.show_message('Using git at %s.' % candidate)
                return
            dialogs.message_dialog(
                self, 'Git not found here',
                'No working "git" program in:\n%s\n\n'
                'Choose the folder that contains the git executable.' % folder)

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.toolbar = Toolbar(on_add=self.add_repository,
                               on_pull=self.pull, on_push=self.push,
                               on_refresh=self.refresh_all,
                               on_about=self.show_about)
        root.pack_start(self.toolbar, False, False, 0)

        overlay = Gtk.Overlay()
        root.pack_start(overlay, True, True, 0)
        self.toast = Toast()
        overlay.add_overlay(self.toast)
        # Without pass-through the toast blocks clicks on the UI underneath
        # while it is shown.
        overlay.set_overlay_pass_through(self.toast, True)

        self.repos_panel = ReposPanel(on_selected=self._on_repo_selected,
                                      on_set_credentials=self.set_credentials,
                                      on_set_identity=self.set_identity,
                                      on_set_remote=self.set_remote,
                                      on_edit_path=self.edit_repository_path,
                                      on_remove=self.remove_repository)
        self.branches_panel = BranchesPanel(on_merge_from=self.merge_from,
                                            on_checkout=self.checkout_branch,
                                            on_delete=self.delete_branch,
                                            on_create=self.create_branch)
        self.files_panel = FilesPanel(on_files_selected=self._on_files_selected,
                                      on_stage=self._stage_files,
                                      on_unstage=self._unstage_files,
                                      on_open=self._open_file,
                                      on_reveal=self._reveal_file,
                                      on_discard=self._discard_files,
                                      on_delete=self._delete_files,
                                      on_untrack=self._untrack_files,
                                      on_ignore=self._ignore_files)
        self.commit_panel = CommitPanel(on_commit=self.do_commit,
                                        get_history=self._commit_history,
                                        on_info=self.toast.show_message)
        self.diff_panel = DiffPanel()
        self.journal_panel = JournalPanel(on_copy_hash=self.copy_hash,
                                          on_edit_commit=self.edit_commit,
                                          on_checkout=self.checkout_commit,
                                          on_show_changes=self.show_commit_changes)

        left = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        left.pack1(self.repos_panel, True, False)
        left.pack2(self.branches_panel, False, False)

        top = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        top.pack1(self.files_panel, True, False)
        top.pack2(self.commit_panel, False, False)

        center_bottom = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        center_bottom.pack1(self.diff_panel, True, False)
        center_bottom.pack2(self.journal_panel, False, False)

        right = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        right.pack1(top, False, False)
        right.pack2(center_bottom, True, False)

        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.pack1(left, False, False)
        main.pack2(right, True, False)
        overlay.add(main)

        self._paned = {'left': left, 'top': top, 'center_bottom': center_bottom,
                       'right': right, 'main': main}
        self._paned_defaults = {'left': 560, 'top': 850, 'center_bottom': 380,
                                'right': 300, 'main': 280}

    def _restore_window_state(self):
        geometry = self.config.get_state('window', {})
        self.set_default_size(geometry.get('width', 1500),
                              geometry.get('height', 950))
        if 'x' in geometry and 'y' in geometry:
            self.move(geometry['x'], geometry['y'])
        if geometry.get('maximized'):
            self.maximize()
        positions = self.config.get_state('paned', {})
        for name, paned in self._paned.items():
            paned.set_position(positions.get(name, self._paned_defaults[name]))
        columns = self.config.get_state('columns', {})
        self.files_panel.set_column_widths(columns.get('files', {}))
        self.journal_panel.set_column_widths(columns.get('journal', {}))

    def _save_current_draft(self):
        if self.git is None:
            return
        text = self.commit_panel.get_message()
        if text.strip():
            self._drafts[self.git.path] = text
        else:
            self._drafts.pop(self.git.path, None)

    def _on_close(self, *_args):
        self._stop_watching()
        self._save_current_draft()
        geometry = dict(self.config.get_state('window', {}))
        geometry['maximized'] = self.is_maximized()
        if not self.is_maximized():
            geometry['width'], geometry['height'] = self.get_size()
            geometry['x'], geometry['y'] = self.get_position()
        self.config.set_state('window', geometry, save=False)
        self.config.set_state(
            'paned', {name: paned.get_position()
                      for name, paned in self._paned.items()}, save=False)
        self.config.set_state(
            'columns', {'files': self.files_panel.get_column_widths(),
                        'journal': self.journal_panel.get_column_widths()},
            save=False)
        if self.git:
            self.config.set_state('selected_repo', self.git.path, save=False)
        self.config.set_state('drafts', self._drafts)
        return False

    def _on_key_press(self, _widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        alt = event.state & Gdk.ModifierType.MOD1_MASK
        if ctrl and event.keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
            return True
        if ctrl and event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.do_commit()
            return True
        if alt and event.keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self.push_staged()
            return True
        if alt and event.keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.pull()
            return True
        if event.keyval == Gdk.KEY_F5:
            self.refresh_all()
            return True
        return False

    def _require_repo(self):
        if self.git is None:
            self.toast.show_message('No repository selected.')
            return False
        return True

    def _remote_in_progress(self):
        if self._remote_busy:
            self.toast.show_message('A remote operation is in progress — please wait.')
            return True
        return False

    def _run_async(self, work, on_done):
        self._remote_busy = True
        self.toolbar.set_remote_ops_sensitive(False)

        def thread_body():
            result, error = None, None
            try:
                result = work()
            except Exception as exc:
                error = exc
            GLib.idle_add(finish, result, error)

        def finish(result, error):
            self._remote_busy = False
            self.toolbar.set_remote_ops_sensitive(True)
            on_done(result, error)
            if self._resync_pending:
                self._resync_pending = False
                self._sync_from_disk()
            return False

        threading.Thread(target=thread_body, daemon=True).start()

    def _commit_history(self):
        return self.git.messages() if self.git else []

    def _apply_status(self, entries):
        self._last_status = entries
        self.files_panel.set_files(entries)

    def _watch_repo(self, path):
        # A tree too large to watch entirely falls back to a slow timer.
        self._stop_watching()

        def on_ready(overflowed):
            if overflowed and self._fallback_poll_id is None:
                self._fallback_poll_id = GLib.timeout_add(3000, self._fallback_poll)

        self._watcher = FolderWatcher(path, self._sync_from_disk, on_ready=on_ready)

    def _stop_watching(self):
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._fallback_poll_id is not None:
            GLib.source_remove(self._fallback_poll_id)
            self._fallback_poll_id = None

    def _fallback_poll(self):
        if self.git is None:
            self._fallback_poll_id = None
            return False
        self._sync_from_disk()
        return True

    def _mark_refreshed(self):
        # Must be called after any refresh that ran `git status`, so the index
        # rewrite it causes is not taken for an external change.
        if self._watcher is not None:
            self._watcher.note_refreshed()

    def _sync_from_disk(self):
        if self.git is None:
            return
        if self._poll_busy or self._remote_busy:
            # Reconcile again once the in-flight op finishes, so a change
            # landing mid-flight is never missed.
            self._resync_pending = True
            return
        self._poll_busy = True
        git = self.git

        def work():
            data = {}
            try:
                data['rev'] = (git.head_hash(), git.current_branch())
                data['status'] = git.status()
            except (GitError, OSError):
                data = None
            GLib.idle_add(done, data)

        def done(data):
            self._poll_busy = False
            if data is None or git is not self.git:
                return False
            if data['rev'] != self._last_rev:
                self._last_rev = data['rev']
                self.refresh_repo_views()
            else:
                # The diff is always re-fetched: a content-only edit leaves
                # `git status` byte-identical yet still changes the diff.
                if data['status'] != self._last_status:
                    self._apply_status(data['status'])
                self._refresh_diff()
            self._mark_refreshed()
            if self._resync_pending:
                self._resync_pending = False
                GLib.idle_add(self._sync_from_disk)
            return False

        threading.Thread(target=work, daemon=True).start()

    def _reload_repo_list(self, on_done=None):
        # The branches are resolved in a background thread: one git call per
        # repo would block startup on slow disks.
        paths = [repo['path'] for repo in self.config.repos()]
        if self.git is not None and self.git.path not in paths:
            self._drafts.pop(self.git.path, None)
            self._close_repo()
        items = [{'path': path, 'name': os.path.basename(path), 'branch': '…'}
                 for path in paths]
        items.sort(key=lambda item: item['name'].lower())
        self.repos_panel.set_repos(items)

        def work():
            try:
                for path in paths:
                    try:
                        branch = (Git(path).current_branch()
                                  if Git.is_repo(path) else 'missing')
                    except (GitError, OSError):
                        branch = 'missing'
                    GLib.idle_add(self.repos_panel.update_branch, path,
                                  os.path.basename(path), branch)
            finally:
                if on_done is not None:
                    GLib.idle_add(on_done)

        threading.Thread(target=work, daemon=True).start()
        return items

    def refresh_repo_views(self, on_done=None):
        if self.git is None:
            return
        git = self.git

        def work():
            data, error = {}, None
            try:
                data['current'] = git.current_branch()
                data['branches'] = git.branches()
                data['remotes'] = git.remote_branches()
                data['status'] = git.status()
                data['log'] = git.log()
                data['head'] = git.head_hash()
                data['ahead'] = git.ahead_counts()
            except Exception as exc:
                error = exc
            GLib.idle_add(apply_data, data, error)

        def apply_data(data, error):
            if git is not self.git:
                pass
            elif error:
                self.toast.show_message(str(error))
            else:
                self.branches_panel.set_branches(
                    data['branches'], data['current'], data['remotes'],
                    data['ahead'])
                self._apply_status(data['status'])
                self.journal_panel.set_commits(data['log'], data['head'])
                self._refresh_diff()
                self.repos_panel.update_branch(
                    git.path, os.path.basename(git.path), data['current'])
                self._last_rev = (data['head'], data['current'])
                self._mark_refreshed()
            if on_done is not None:
                on_done(error is None)
            return False

        threading.Thread(target=work, daemon=True).start()

    def _on_repo_selected(self, path):
        self._save_current_draft()
        self.git = Git(path,
                       cred_provider=lambda p=path: self.config.credentials(p))
        self.repos_panel.set_active(path)
        self.commit_panel.set_message(self._drafts.get(path, ''))
        self.files_panel.clear_selection()
        self._last_rev = None
        self.refresh_repo_views()
        self._watch_repo(path)
        self.config.set_state('selected_repo', path, save=False)
        self.config.set_state('drafts', self._drafts)

    def show_about(self):
        dialogs.about_dialog(self, __version__)

    def add_repository(self):
        path = dialogs.choose_repository_folder(self)
        if not path:
            return
        if not Git.is_repo(path):
            self.toast.show_message('"%s" is not a git repository.' % path)
            return
        if not self.config.add_repo(path):
            self.toast.show_message('Repository is already in the list.')
            return
        self._reload_repo_list()
        self.repos_panel.select(path)

    def edit_repository_path(self, path):
        new_path = dialogs.input_dialog(
            self, dialogs.repo_title(os.path.basename(path), 'Path'),
            'Local path:',
            text=path,
            note='Where this repository lives on disk. Change it after moving '
                 'the folder; nothing is moved or copied here.')
        if not new_path:
            return
        new_path = os.path.abspath(os.path.expanduser(new_path))
        if new_path == path:
            return
        if not Git.is_repo(new_path):
            self.toast.show_message('"%s" is not a git repository.' % new_path)
            return
        if self.config.get_repo(new_path):
            self.toast.show_message('Repository is already in the list.')
            return
        was_selected = self.git is not None and self.git.path == path
        if was_selected:
            self._save_current_draft()
        self.config.set_repo_path(path, new_path)
        if path in self._drafts:
            self._drafts[new_path] = self._drafts.pop(path)
        self.config.set_state('drafts', self._drafts)
        self._reload_repo_list()
        if was_selected:
            self.repos_panel.select(new_path)
        self.toast.show_message('Path changed to %s' % new_path)

    def remove_repository(self, path):
        repo = self.config.get_repo(path) or {}
        text = ("Repository '%s' will be unregistered from VisualGit, along "
                "with its saved credentials. The files on disk are kept."
                % (repo.get('name') or path))
        if not dialogs.confirm_dialog(self, 'Remove repository?', text):
            return
        self.config.remove_repo(path)
        self._drafts.pop(path, None)
        self.config.set_state('drafts', self._drafts, save=False)
        self._reload_repo_list()

    def _close_repo(self):
        self._stop_watching()
        self.git = None
        self.repos_panel.set_active(None)
        self.branches_panel.set_branches([], None)
        self._apply_status([])
        self.journal_panel.set_commits([])
        self.diff_panel.clear()
        self.commit_panel.clear()

    def refresh_all(self):
        if self._refresh_pending or self._remote_in_progress():
            return
        self.config.reload_repos()
        self._refresh_failed = False
        self._reload_repo_list(on_done=self._refresh_part_done)
        parts = 1
        if self.git is not None:
            self.refresh_repo_views(on_done=self._refresh_part_done)
            parts += 1
        self._refresh_pending = parts

    def _refresh_part_done(self, ok=True):
        self._refresh_failed = self._refresh_failed or not ok
        self._refresh_pending -= 1
        if not self._refresh_pending and not self._refresh_failed:
            self.toast.show_message('Refreshed.')

    def _prompt_remote(self, path, note=None):
        git = self.git if self.git and self.git.path == path else Git(path)
        name = git.effective_remote()
        try:
            current = git.get_remote_url(name)
        except GitError:
            current = ''
        url = dialogs.input_dialog(
            self, dialogs.repo_title(os.path.basename(path), 'Remote'),
            'Server URL:', text=current,
            note=note or 'The repository URL, saved as remote "%s" and used '
                         'for pushing and pulling.' % name)
        if url is None:
            return False
        if not url:
            if current and dialogs.confirm_dialog(
                    self, 'Remove remote?',
                    'Remove remote "%s" (%s)?' % (name, current)):
                try:
                    git.remove_remote(name)
                    self.toast.show_message('Remote "%s" removed.' % name)
                except GitError as exc:
                    self.toast.show_message('Could not remove remote: %s' % exc)
            else:
                self.toast.show_message('No URL entered — nothing changed.')
            return False
        try:
            git.set_remote(name, url)
        except GitError as exc:
            self.toast.show_message('Could not set remote: %s' % exc)
            return False
        self.toast.show_message('Remote "%s" set to %s' % (name, url))
        return True

    def set_remote(self, path):
        self._prompt_remote(path)

    def _credentials_set(self):
        username, password = self.config.credentials(self.git.path)
        return bool(username and password)

    def _remote_preflight(self, verb):
        if not self._require_repo() or self._remote_in_progress():
            return False
        if not Git.is_repo(self.git.path):
            self.toast.show_message('"%s" is not a git repository.'
                                    % self.git.path)
            return False
        if not self.git.remotes() and not self._prompt_remote(
                self.git.path,
                note='%s needs a remote, but none is configured. Enter the '
                     'repository URL; it will be saved as "origin".' % verb):
            return False
        # SSH and local-path remotes must not be blocked by the credentials
        # modal, which only covers HTTP(S).
        if (self.git.remote_needs_password() and not self._credentials_set()
                and not self.set_credentials(
                    self.git.path,
                    note='%s needs credentials for this repository, which are '
                         'not set. Enter the username and password; they will '
                         'be saved (encrypted) and used for pushing and '
                         'pulling.' % verb)):
            return False
        return True

    def pull(self):
        if not self._remote_preflight('Pull'):
            return
        self.toast.show_message('Pulling…')
        self._run_async(self.git.pull, self._on_remote_done('Pull'))

    def push(self):
        if not self._remote_preflight('Push'):
            return
        self.toast.show_message('Pushing…')
        self._run_async(self.git.push, self._on_remote_done('Push'))

    def _on_remote_done(self, verb):
        def done(_result, error):
            if error:
                self.toast.show_message('%s failed: %s' % (verb, error))
            else:
                self.toast.show_message('%s completed.' % verb)
                self.refresh_repo_views()
        return done

    @staticmethod
    def _is_identity_error(exc):
        text = str(exc).lower()
        return ('tell me who you are' in text
                or 'auto-detect email' in text
                or 'empty ident' in text)

    def do_commit(self, ask_identity=True):
        if not self._require_repo() or self._remote_in_progress():
            return False
        message = self.commit_panel.get_message().strip()
        if not message:
            self.toast.show_message('Commit message is empty — nothing committed.')
            return False
        try:
            if not self.git.has_staged():
                self.toast.show_message('Nothing is staged — stage files before committing.')
                return False
            self.git.commit(message)
        except GitError as exc:
            if ask_identity and self._is_identity_error(exc):
                if self.set_identity(
                        self.git.path,
                        note='Git refused the commit because it does not know '
                             'who you are. Enter the name and email to record '
                             'as the author of your commits in this repository '
                             '— they will be saved in its .git/config.'):
                    return self.do_commit(ask_identity=False)
                return False
            self.toast.show_message('Commit failed: %s' % exc)
            return False
        self.commit_panel.clear()
        self._drafts.pop(self.git.path, None)
        self.config.set_state('drafts', self._drafts)
        self.toast.show_message('Committed.')
        self.refresh_repo_views()
        return True

    def push_staged(self):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            staged = self.git.has_staged()
        except GitError as exc:
            self.toast.show_message(str(exc))
            return
        if staged:
            if not self.do_commit():
                return
        self.push()

    def _refresh_diff(self):
        if self.git is None:
            return
        entry = self.files_panel.focus_entry()
        if entry is None:
            self.diff_panel.clear()
            return
        try:
            staged_only = entry['staged'] and not entry['unstaged']
            diff = self.git.diff_file(entry['path'], staged=staged_only,
                                      untracked=entry['untracked'])
            self.diff_panel.set_diff(diff)
        except GitError as exc:
            self.toast.show_message(str(exc))

    def _on_files_selected(self, _entries):
        self._refresh_diff()

    def _abs_path(self, entry):
        return os.path.join(self.git.path, entry['path'])

    def _open_file(self, entry):
        if not self._require_repo():
            return
        path = self._abs_path(entry)
        if not os.path.exists(path):
            # A deleted file, or one only a past commit touched, has no working
            # tree copy — xdg-open would fail silently.
            self.toast.show_message(
                '%s is not in the working tree.' % entry['path'])
            return
        try:
            subprocess.Popen(['xdg-open', path])
        except OSError as exc:
            self.toast.show_message('Could not open file: %s' % exc)

    def _reveal_file(self, entry):
        if not self._require_repo():
            return
        if entry is None:
            try:
                subprocess.Popen(['xdg-open', self.git.path])
            except OSError as exc:
                self.toast.show_message('Could not open file manager: %s' % exc)
            return
        path = self._abs_path(entry)
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            uri = GLib.filename_to_uri(path, None)
            bus.call_sync('org.freedesktop.FileManager1',
                          '/org/freedesktop/FileManager1',
                          'org.freedesktop.FileManager1', 'ShowItems',
                          GLib.Variant('(ass)', ([uri], '')),
                          None, Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            try:
                subprocess.Popen(['xdg-open', os.path.dirname(path)])
            except OSError as exc:
                self.toast.show_message('Could not open file manager: %s' % exc)

    def _discard_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            for entry in entries:
                self.git.discard(entry['path'])
        except GitError as exc:
            self.toast.show_message('Discard failed: %s' % exc)
            self._refresh_files_keep_diff()
            return
        if len(entries) == 1:
            self.toast.show_message('Discarded changes in %s.' % entries[0]['path'])
        else:
            self.toast.show_message('Discarded changes in %d files.' % len(entries))
        self._refresh_files_keep_diff()

    def _confirm_files(self, title, one, many, entries):
        text = one % entries[0]['path'] if len(entries) == 1 else many % len(entries)
        return dialogs.confirm_dialog(self, title, text)

    def _delete_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        one = ('"%s" and everything inside it will be permanently deleted '
               'from disk.' if entries[0]['path'].endswith('/')
               else '"%s" will be permanently deleted from disk.')
        if not self._confirm_files(
                'Delete?', one,
                '%d files will be permanently deleted from disk.', entries):
            return
        errors = 0
        for entry in entries:
            path = self._abs_path(entry)
            try:
                # An untracked nested repository is listed as a folder entry,
                # and os.remove cannot delete a folder.
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except OSError:
                errors += 1
        if errors:
            self.toast.show_message('Deleted %d file(s), %d failed.'
                                    % (len(entries) - errors, errors))
        else:
            self.toast.show_message('Deleted %d file(s).' % len(entries))
        self._refresh_files_keep_diff()

    def _untrack_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        if not self._confirm_files(
                'Stop tracking?',
                '"%s" will stop being tracked by git but kept on disk.',
                '%d files will stop being tracked by git but kept on disk.',
                entries):
            return
        try:
            for entry in entries:
                self.git.rm_cached(entry['path'])
        except GitError as exc:
            self.toast.show_message('Stop tracking failed: %s' % exc)
            # Some files may have been untracked before the failure.
            self._refresh_files_keep_diff()
            return
        if len(entries) == 1:
            self.toast.show_message('Stopped tracking %s.' % entries[0]['path'])
        else:
            self.toast.show_message('Stopped tracking %d files.' % len(entries))
        self._refresh_files_keep_diff()

    def _ignore_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        if not self._confirm_files(
                'Add to .gitignore?',
                '"%s" will be added to .gitignore.',
                '%d files will be added to .gitignore.', entries):
            return
        try:
            added = self.git.add_to_gitignore([e['path'] for e in entries])
        except OSError as exc:
            self.toast.show_message('Could not write .gitignore: %s' % exc)
            return
        if added:
            self.toast.show_message('Added %d entr%s to .gitignore.'
                                    % (len(added), 'y' if len(added) == 1 else 'ies'))
        else:
            self.toast.show_message('Already in .gitignore.')
        self._refresh_files_keep_diff()

    def _stage_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            for entry in entries:
                self.git.stage(entry['path'])
        except GitError as exc:
            self.toast.show_message('Stage failed: %s' % exc)
        self._refresh_files_keep_diff()

    def _unstage_files(self, entries):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            for entry in entries:
                self.git.unstage(entry['path'])
        except GitError as exc:
            self.toast.show_message('Unstage failed: %s' % exc)
        self._refresh_files_keep_diff()

    def _refresh_files_keep_diff(self):
        try:
            self._apply_status(self.git.status())
        except GitError as exc:
            self.toast.show_message(str(exc))
        self._refresh_diff()
        self._mark_refreshed()

    def checkout_branch(self, name, kind):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            if kind == 'remote':
                self.git.checkout_remote(name)
            else:
                self.git.checkout(name)
        except GitError as exc:
            self.toast.show_message('Checkout failed: %s' % exc)
            return
        self.toast.show_message("Switched to '%s'." % self.git.current_branch())
        self.refresh_repo_views()

    def create_branch(self):
        if not self._require_repo() or self._remote_in_progress():
            return
        name = dialogs.input_dialog(
            self, 'Create Branch', 'Name:',
            note='The branch starts at the current commit and is checked out.')
        if not name:
            return
        try:
            self.git.create_branch(name)
        except GitError as exc:
            self.toast.show_message('Create failed: %s' % exc)
            return
        self.toast.show_message("Switched to '%s'." % name)
        self.refresh_repo_views()

    def delete_branch(self, name, kind):
        if not self._require_repo() or self._remote_in_progress():
            return
        if kind == 'remote':
            text = ("Branch '%s' will be deleted on the remote for everyone."
                    % name)
        else:
            text = ("Branch '%s' will be permanently deleted, including any "
                    "commits not merged elsewhere." % name)
        if not dialogs.confirm_dialog(self, 'Delete?', text):
            return
        if kind == 'remote':
            # A network op: run it off the UI thread like pull/push, so a
            # slow or unreachable remote cannot freeze the app.
            if not self._remote_preflight('Delete'):
                return
            self.toast.show_message("Deleting '%s'…" % name)
            self._run_async(lambda: self.git.delete_remote_branch(name),
                            self._on_remote_done('Delete'))
            return
        try:
            self.git.delete_local_branch(name)
        except GitError as exc:
            self.toast.show_message('Delete failed: %s' % exc)
            return
        self.toast.show_message("Deleted '%s'." % name)
        self.refresh_repo_views()

    def merge_from(self, branch):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            self.git.merge(branch)
        except GitError as exc:
            self.toast.show_message('Merge failed: %s' % exc)
            self.refresh_repo_views()
            return
        self.toast.show_message("Merged '%s' into %s." %
                                (branch, self.git.current_branch()))
        self.refresh_repo_views()

    def copy_hash(self, commit):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(commit, -1)
        clipboard.store()
        self.toast.show_message('Commit hash copied: %s' % commit[:12])

    def show_commit_changes(self, commit, short):
        if not self._require_repo():
            return
        window = CommitWindow(self, self.git, commit, short, self.config,
                              self._open_file)
        self._commit_windows.append(window)
        window.connect('destroy', self._on_commit_window_destroyed)

    def _on_commit_window_destroyed(self, window):
        # Guard against a duplicate 'destroy' (list.remove would raise).
        if window in self._commit_windows:
            self._commit_windows.remove(window)

    def checkout_commit(self, commit):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            self.git.checkout(commit)
        except GitError as exc:
            self.toast.show_message('Checkout failed: %s' % exc)
            return
        self.toast.show_message(
            'Checked out %s — HEAD is detached; double-click a branch to return.'
            % commit[:12])
        self.refresh_repo_views()

    def edit_commit(self, commit):
        if not self._require_repo() or self._remote_in_progress():
            return
        try:
            name, email, body = self.git.commit_info(commit)
        except GitError as exc:
            self.toast.show_message(str(exc))
            return
        result = dialogs.edit_commit_dialog(self, body, name, email)
        if not result:
            return
        if not result['message']:
            self.toast.show_message('Commit message cannot be empty.')
            return
        try:
            rewritten = self.git.reword(commit, result['message'],
                                        result['author_name'],
                                        result['author_email'])
        except GitError as exc:
            self.toast.show_message('Edit failed: %s' % exc)
            self.refresh_repo_views()
            return
        if rewritten:
            self.toast.show_message('Commit updated — newer commits were rewritten '
                                    '(hashes changed).')
        else:
            self.toast.show_message('Commit updated.')
        self.refresh_repo_views()

    def set_identity(self, path, note=None):
        git = self.git if self.git and self.git.path == path else Git(path)
        try:
            name, email = git.identity()
        except GitError:
            name, email = '', ''
        result = dialogs.identity_dialog(self, os.path.basename(path),
                                         name, email, note)
        if result is None:
            return False
        if not result[0] or not result[1]:
            self.toast.show_message('Identity needs both a name and an email.')
            return False
        try:
            git.set_identity(result[0], result[1])
        except GitError as exc:
            self.toast.show_message('Could not save identity: %s' % exc)
            return False
        self.toast.show_message('Identity saved for %s.' % os.path.basename(path))
        return True

    def set_credentials(self, path, note=None):
        username, old_password = self.config.credentials(path)
        result = dialogs.credentials_dialog(self, os.path.basename(path), username,
                                            has_password=bool(old_password),
                                            note=note)
        if result is None:
            return False
        # An empty password field means "keep the stored one", not "erase it".
        username = result[0].strip()
        password = result[1] or old_password
        if not username or not password:
            self.toast.show_message('Credentials need both a username and a '
                                    'password — nothing saved.')
            return False
        self.config.set_credentials(path, username, password)
        self.toast.show_message('Credentials saved for %s.' % os.path.basename(path))
        return True
