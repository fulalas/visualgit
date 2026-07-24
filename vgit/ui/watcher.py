"""Recursively watch a repository folder and fire a debounced callback when
anything changes on disk — working-tree edits and git-state changes (commits,
checkouts) alike, since .git is watched too.

GIO's file monitors use inotify where available and transparently fall back to
their own polling on filesystems that don't (e.g. NFS), so this works
everywhere without a fixed timer.
"""
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib


class FolderWatcher:
    MAX_WATCHES = 4000          # bound inotify usage on huge trees
    DEBOUNCE_MS = 400           # collapse bursts of events into one refresh
    # Noisy/large git internals whose churn needs no UI refresh; the parts that
    # matter (HEAD, index, refs, logs) live directly under .git and are watched.
    IGNORE = (os.path.join('.git', 'objects'), os.path.join('.git', 'lfs'))

    def __init__(self, root, on_change):
        self._root = os.path.abspath(root)
        self._on_change = on_change
        self._monitors = {}     # dir path -> Gio.FileMonitor
        self._pending = None
        self.overflowed = False
        self._add_tree(self._root)

    def _ignored(self, path):
        rel = os.path.relpath(path, self._root)
        return any(rel == ig or rel.startswith(ig + os.sep) for ig in self.IGNORE)

    def _add_tree(self, top):
        for dirpath, dirnames, _ in os.walk(top):
            if self._ignored(dirpath):
                dirnames[:] = []
                continue
            self._add_one(dirpath)
            if len(self._monitors) >= self.MAX_WATCHES:
                self.overflowed = True
                dirnames[:] = []  # stop descending once the cap is hit

    def _add_one(self, path):
        if path in self._monitors:
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

    def _drop_tree(self, path):
        for p in list(self._monitors):
            if p == path or p.startswith(path + os.sep):
                self._monitors.pop(p).cancel()

    def _on_event(self, _monitor, gfile, _other, event):
        path = gfile.get_path()
        if path and not self._ignored(path):
            if event == Gio.FileMonitorEvent.CREATED and os.path.isdir(path):
                self._add_tree(path)          # start watching a new subtree
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
        if self._pending is not None:
            GLib.source_remove(self._pending)
            self._pending = None
        for monitor in self._monitors.values():
            monitor.cancel()
        self._monitors.clear()
