# VisualGit

A simple, intentionally minimal git GUI client (GTK3 + Python). All git
operations shell out to the system `git`.

<img width="1396" height="1249" alt="visualGit" src="https://github.com/user-attachments/assets/a0b655ed-2889-4296-9979-26ed7b1f159a" />

## Run

```
python3 main.py
```

Requires: Python 3, PyGObject (GTK 3), git.

If `git` is not on your `PATH`, VisualGit asks for the folder containing the
git program on startup and remembers it (saved as `git_binary` in the config).

## Build (Linux only)

`./build.sh` produces a single-file `./visualgit` (Linux x86_64) via
PyInstaller (build artifacts live in `build/`, safe to delete). CPython, the
GTK libraries and all of the app's own icons are bundled — the binary never
relies on a system icon theme. Runtime needs only `git` on `PATH`.

## Layout

- **Repositories** (top left) — registered repos; the active one is shown in
  bold with a ▸ marker. Right-click for *Set remote…*, *Set credentials…*,
  *Set identity…*, *Edit path…* (point an entry at a moved folder) and
  *Remove*.
- **Branches** (bottom left) — *Local Branches* plus one group per remote
  (e.g. *origin*). Each local branch shows an orange `(N)` with the number of
  committed-but-unpushed commits. Right-click any non-current branch for
  *Checkout* / *Merge from* / *Delete*; double-click also checks out. Checking
  out a remote branch creates a local tracking branch if one doesn't exist yet.
- **Files** (top center) — working tree / index status, with a colored state
  icon per file and untracked files listed individually. Auto-refreshes when
  the folder changes on disk. Multiple files can be selected; double-click
  opens a file in its default application, and clicking empty space clears the
  selection. Right-click for *Open file* / *Reveal in file manager* (single
  file only), *Stage* / *Unstage*, *Discard*, *Delete file*, *Stop tracking*
  (`git rm --cached`, keeps the file on disk), and (for untracked files)
  *Add to .gitignore*. Right-click on empty space offers *Reveal in file
  manager* for the repository folder.
- **Commit** (top right) — commit message field and Commit button.
- **Changes** (middle) — unified diff of the selected file.
- **Journal** (bottom) — commit log across all branches (Hash / Refs /
  Subject / Author / Date columns), with the current commit (HEAD) shown in
  bold. Double-click a commit to open a window with its changed files and
  diffs. Right-click for *Copy commit hash*, *Edit message and author…* (HEAD
  is amended, older commits are reworded via rebase — hashes change), and
  *Checkout this commit* (detached HEAD).

## Toolbar

- **Add** — register a local repository (asks only for a path).
- **Pull** / **Push** — run against the current repo, using the per-repo
  credentials if set (via `GIT_ASKPASS`).

## Shortcuts (app-wide)

- **Ctrl+Enter** — commit.
- **Alt+PageUp** — commit staged changes (if any), then push.
- **Alt+PageDown** — pull.
- **Ctrl+Up / Ctrl+Down** — walk back/forward through previous commit
  messages.
- **Ctrl+Q** — quit.

Commits are only possible when something is staged.

## Persisted state

Saved to `~/.config/visualgit/config.json` on exit (and when switching
repos): selected repository, per-repository commit message drafts, window
size / position / maximized state, splitter positions, file-list column
widths, and the git binary path (if set manually). Passwords are stored
encrypted (HMAC-SHA256 keystream, per-value nonce) with a
machine-local key in `~/.config/visualgit/key` — this keeps them
unreadable in the config file itself, but is not protection against
someone with access to this user account.
