# VisualGit

Simple git GUI client. Python 3 + GTK 3 (PyGObject); all git operations
shell out to the system `git` CLI. Run with `python3 main.py`.

## Versioning (do this on EVERY change)

1. The version lives in `vgit/version.txt` (single line, e.g. `0.1`).
2. **Bump it on every change** — semver-style: patch for fixes (`0.1.1`),
   minor for features (`0.2`).
3. The version is surfaced in the app as the window title:
   `VisualGit - [version]` (read via `vgit.__version__` — no other place
   needs editing).

## Structure

- `main.py` — entry point
- `vgit/gitcmd.py` — ALL git subprocess logic lives here, nowhere else
- `vgit/config.py` — persisted repos, credentials (encrypted), UI state
  (`~/.config/visualgit/`)
- `vgit/ui/window.py` — layout, global shortcuts, action wiring
- `vgit/ui/*_panel.py` — one file per panel; `dialogs.py`, `toast.py`,
  `toolbar.py`, `panel.py` (shared helpers)

## Conventions

- Notifications are non-modal bottom popovers (`toast.show_message`),
  never modal dialogs. Modals only for input (credentials, identity,
  edit commit) and delete confirmation.
- Commits require staged changes; guard actions and show a toast instead
  of failing silently.
- Every user-changeable thing (selected repo, drafts, geometry, splitter
  positions, column widths) persists via `Config.get_state`/`set_state` —
  keep new UI state in there too.
- Stay on GTK 3.
- Test non-UI logic against a scratch repo in /tmp; compile-check with
  `python3 -m py_compile`.
