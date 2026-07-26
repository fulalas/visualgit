"""Recursively watch a repository folder and fire a debounced callback when
anything changes on disk — working-tree edits and git-state changes (commits,
checkouts) alike, since .git is watched too.

GIO's file monitors use inotify where available and transparently fall back to
their own polling on filesystems that don't (e.g. NFS), so this works
everywhere without a fixed timer. The initial tree walk runs off the UI thread;
monitors are created back on the GLib main loop.
"""
import os
import threading

from gi.repository import Gio, GLib


class FolderWatcher:
    MAX_WATCHES = 4000          # bound inotify usage on huge trees
    DEBOUNCE_MS = 400           # collapse bursts of events into one refresh
    # .git internal *directories* that churn constantly but need no UI refresh;
    # the parts that matter (HEAD, refs, logs) live directly under .git.
    IGNORE_PREFIXES = (os.path.join('.git', 'objects'),
                       os.path.join('.git', 'lfs'))
    # .git internal *files* to ignore, matched exactly. index.lock is pure
    # churn (created/renamed on every index write). .git/index itself is NOT
    # ignored outright: `git status` — which our own refresh runs — rewrites it
    # every single time (new mtime and inode) to update its stat cache, so
    # reacting to that would spin an endless watch -> status -> rewrite loop;
    # but an external CLI `git add` / `reset` / `rm --cached` also writes only
    # the index and must still refresh the panel. Since git status gives no
    # stable signature to compare against, _on_event instead ignores index
    # events that land inside the grace window opened by note_refreshed() right
    # after each of our own refreshes — those are our own rewrites; anything
    # outside it is external.
    IGNORE_FILES = frozenset({os.path.join('.git', 'index.lock')})
    # Ephemeral directories (matched by name, at any depth) that would blow the
    # watch budget and are virtually always git-ignored anyway.
    IGNORE_NAMES = frozenset({'node_modules', '__pycache__', '.venv', 'venv',
                              '.mypy_cache', '.pytest_cache', '.tox'})
    # How long after one of our own refreshes to treat index writes as self-
    # induced. Must comfortably exceed DEBOUNCE_MS plus event-delivery latency
    # so the status rewrite's event always lands inside it. The only cost of a
    # generous window is that an external index change in the ~1.5s after a
    # refresh waits for the next event to surface.
    SELF_WRITE_GRACE_US = 1_500_000

    def __init__(self, root, on_change, on_ready=None):
        """on_ready(overflowed) is called on the UI thread once monitoring is
        set up; `overflowed` is True if the tree exceeded MAX_WATCHES."""
        self._root = os.path.abspath(root)
        self._on_change = on_change
        self._on_ready = on_ready
        self._monitors = {}     # dir path -> Gio.FileMonitor
        self._pending = None
        self._stopped = False
        self.overflowed = False
        self._index_path = os.path.join(self._root, '.git', 'index')
        self._self_write_until = 0  # monotonic-us deadline for our own writes
        threading.Thread(target=self._scan, daemon=True).start()

    def note_refreshed(self):
        """Open a grace window during which index writes are treated as our own
        `git status` stat-cache rewrite and skipped. Call right after any of our
        refreshes that ran git status."""
        self._self_write_until = GLib.get_monotonic_time() + self.SELF_WRITE_GRACE_US

    def _ignored(self, path):
        rel = os.path.relpath(path, self._root)
        if rel == os.curdir:
            return False
        if rel.startswith(self.IGNORE_PREFIXES) or rel in self.IGNORE_FILES:
            return True
        return any(part in self.IGNORE_NAMES for part in rel.split(os.sep))

    def _scan(self):
        """Collect directories to watch (off the UI thread), then install the
        monitors on the main loop."""
        dirs = []
        overflowed = False
        for dirpath, dirnames, _ in os.walk(self._root):
            if self._ignored(dirpath):
                dirnames[:] = []
                continue
            dirs.append(dirpath)
            if len(dirs) >= self.MAX_WATCHES:
                overflowed = True
                break  # stop traversing entirely once the cap is reached
        GLib.idle_add(self._install, dirs, overflowed)

    def _install(self, dirs, overflowed):
        if self._stopped:
            return False
        self.overflowed = overflowed
        for path in dirs:
            self._add_one(path)
        if self._on_ready is not None:
            self._on_ready(self.overflowed)
        return False

    def _add_one(self, path):
        if self._stopped or path in self._monitors:
            return
        if len(self._monitors) >= self.MAX_WATCHES:
            self.overflowed = True
            return
        try:
            monitor = Gio.File.new_for_path(path).monitor_directory(
                Gio.FileMonitorFlags.NONE, None)
        except GLib.Error:
            return
        monitor.connect('changed', self._on_event)
        self._monitors[path] = monitor

    def _add_subtree(self, top):
        # A directory appeared at runtime; watch it and its (usually small) set
        # of children, honoring the ignore list and the watch cap.
        for dirpath, dirnames, _ in os.walk(top):
            if self._ignored(dirpath):
                dirnames[:] = []
                continue
            self._add_one(dirpath)
            if len(self._monitors) >= self.MAX_WATCHES:
                break

    def _drop_tree(self, path):
        for p in list(self._monitors):
            if p == path or p.startswith(path + os.sep):
                self._monitors.pop(p).cancel()

    def _on_event(self, _monitor, gfile, _other, event):
        path = gfile.get_path()
        if path and self._ignored(path):
            # Ignored churn (e.g. index.lock) — must skip the refresh too, not
            # just the add/drop bookkeeping, or we'd spin.
            return
        if path == self._index_path and \
                GLib.get_monotonic_time() < self._self_write_until:
            # Our own `git status` rewrote the index stat cache; skip to avoid a
            # watch -> status -> rewrite loop. An external write outside the
            # grace window falls through to schedule a refresh.
            return
        if path:
            if event == Gio.FileMonitorEvent.CREATED and os.path.isdir(path):
                self._add_subtree(path)
            elif event == Gio.FileMonitorEvent.DELETED and path in self._monitors:
                self._drop_tree(path)
        self._schedule()

    def _schedule(self):
        if self._pending is not None:
            GLib.source_remove(self._pending)
        self._pending = GLib.timeout_add(self.DEBOUNCE_MS, self._fire)

    def _fire(self):
        self._pending = None
        self._on_change()
        return False

    def stop(self):
        self._stopped = True
        if self._pending is not None:
            GLib.source_remove(self._pending)
            self._pending = None
        for monitor in self._monitors.values():
            monitor.cancel()
        self._monitors.clear()
