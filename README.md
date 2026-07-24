# VisualGit

A simple, intentionally minimal git GUI client (GTK3 + Python). All git
operations shell out to the system `git`.

## Run

```
python3 main.py
```

Requires: Python 3, PyGObject (GTK 3), git.

If `git` is not on your `PATH`, VisualGit asks for the folder containing the
git program on startup and remembers it (saved as `git_binary` in the config).

## Layout

- **Repositories** (top left) — registered repos; right-click for
  *Set credentials…* / *Remove repository*.
- **Branches** (bottom left) — *Local Branches* plus one group per remote
  (e.g. *origin*). Right-click any non-current branch for *Checkout* /
  *Merge from*; double-click also checks out. Checking out a remote branch
  creates a local tracking branch if one doesn't exist yet.
- **Files** (top center) — working tree / index status. Double-click opens
  the file in its default application; right-click for *Open file*,
  *Reveal in file manager*, and *Stage* / *Unstage*.
- **Commit** (top right) — commit message field and Commit button.
- **Changes** (middle) — unified diff of the selected file.
- **Journal** (bottom) — commit log; right-click a commit for
  *Copy commit hash*, *Edit message and author…* (HEAD is amended, older
  commits are reworded via rebase — hashes change), and
  *Checkout this commit* (detached HEAD).

## Toolbar

- **Add** — register a local repository (asks only for a path).
- **Pull** / **Push** — run against the current repo, using the per-repo
  credentials if set (via `GIT_ASKPASS`).

## Shortcuts (app-wide)

- **Ctrl+Enter** — commit. Empty message or empty stage → bottom popover
  message, nothing happens.
- **Alt+PageUp** — commit whatever is staged (using the current message),
  then push. Nothing staged or empty message → popover message, nothing
  happens.
- **Ctrl+Up / Ctrl+Down** (in the commit field) — walk back / forward
  through previous commit messages; your unsent draft is restored when you
  navigate back past the newest one.

Commits are only possible when something is staged.

## Persisted state

Saved to `~/.config/visualgit/config.json` on exit (and when switching
repos): selected repository, per-repository commit message drafts, window
size / position / maximized state, and all splitter positions. Passwords
are stored encrypted (HMAC-SHA256 keystream, per-value nonce) with a
machine-local key in `~/.config/visualgit/key` — this keeps them
unreadable in the config file itself, but is not protection against
someone with access to this user account.

All notifications are temporary popovers at the bottom of the window —
never modal dialogs.
