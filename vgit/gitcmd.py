"""All git interaction, via the git CLI (one subprocess per operation)."""
import os
import subprocess

SEP = '\x1f'

# Which git executable to invoke. Defaults to 'git' (found on PATH); can be
# pointed at an explicit path via set_git_binary() when git is elsewhere.
_GIT_BINARY = 'git'


def set_git_binary(path):
    global _GIT_BINARY
    _GIT_BINARY = path or 'git'


def git_binary():
    return _GIT_BINARY


def git_binary_works(path):
    """True if `path` runs and reports itself as git."""
    try:
        proc = subprocess.run([path, '--version'], capture_output=True, text=True)
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.startswith('git version')


def git_available():
    """True if the currently configured git binary is runnable."""
    return git_binary_works(_GIT_BINARY)


class GitError(Exception):
    pass


class Git:
    def __init__(self, path, cred_provider=None, askpass=None):
        self.path = path
        self.cred_provider = cred_provider
        self.askpass = askpass

    def _run(self, *args, auth=False, env=None, check=True, ok_codes=(0,)):
        environ = os.environ.copy()
        # Force English messages: error handling matches on git's output
        # (e.g. 'no upstream', 'tell me who you are').
        environ['LC_ALL'] = 'C'
        if auth:
            environ['GIT_TERMINAL_PROMPT'] = '0'
            creds = self.cred_provider() if self.cred_provider else None
            if creds and creds[0] and self.askpass:
                environ['GIT_ASKPASS'] = self.askpass
                environ['VGIT_USERNAME'] = creds[0]
                environ['VGIT_PASSWORD'] = creds[1] or ''
        if env:
            environ.update(env)
        try:
            proc = subprocess.run([_GIT_BINARY, '-C', self.path] + list(args),
                                  capture_output=True, text=True, env=environ)
        except OSError as exc:
            # e.g. the git binary is missing/misconfigured — surface it the
            # same way as any other git failure so callers can show a toast.
            raise GitError('Could not run git (%s): %s' % (_GIT_BINARY, exc))
        if check and proc.returncode not in ok_codes:
            message = proc.stderr.strip() or proc.stdout.strip() or \
                'git %s failed (exit %d)' % (args[0], proc.returncode)
            raise GitError(message)
        return proc

    @staticmethod
    def is_repo(path):
        try:
            proc = subprocess.run([_GIT_BINARY, '-C', path, 'rev-parse',
                                   '--is-inside-work-tree'],
                                  capture_output=True, text=True)
        except OSError:
            return False
        return proc.returncode == 0 and proc.stdout.strip() == 'true'

    # ------------------------------------------------------------- queries

    def current_branch(self):
        proc = self._run('symbolic-ref', '--short', 'HEAD', check=False)
        if proc.returncode == 0:
            return proc.stdout.strip()
        proc = self._run('rev-parse', '--short', 'HEAD', check=False)
        if proc.returncode == 0:
            return '(detached: %s)' % proc.stdout.strip()
        return '(no commits)'

    def branches(self):
        proc = self._run('branch', '--format=%(refname:short)', check=False)
        if proc.returncode != 0:
            return []
        return [l for l in proc.stdout.splitlines() if l and not l.startswith('(')]

    def ahead_counts(self):
        """Map local branch -> number of committed-but-unpushed commits.

        When a branch has a configured upstream, use git's ahead count against
        it. Otherwise, if the repo has any remote, count commits on the branch
        that aren't on any remote-tracking branch. Repos with no remote at all
        (nowhere to push) and branches in sync are omitted."""
        proc = self._run('for-each-ref',
                         '--format=%(refname:short)\t%(upstream)\t'
                         '%(upstream:track,nobracket)', 'refs/heads', check=False)
        if proc.returncode != 0:
            return {}
        has_remotes = bool(self._run('remote', check=False).stdout.split())
        counts = {}
        for line in proc.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) != 3:
                continue
            name, upstream, track = parts
            if upstream:
                for part in track.split(','):
                    part = part.strip()
                    if part.startswith('ahead '):
                        try:
                            counts[name] = int(part[6:])
                        except ValueError:
                            pass
            elif has_remotes:
                count = self._count_unpushed(name)
                if count:
                    counts[name] = count
        return counts

    def _count_unpushed(self, branch):
        """Commits on `branch` not reachable from any remote-tracking ref."""
        proc = self._run('rev-list', '--count', branch, '--not', '--remotes',
                         check=False)
        if proc.returncode != 0:
            return 0
        try:
            return int(proc.stdout.strip())
        except ValueError:
            return 0

    def remote_branches(self):
        """Remote-tracking branches (e.g. 'origin/main'), without HEAD pointers."""
        proc = self._run('branch', '-r', '--format=%(refname:short)', check=False)
        if proc.returncode != 0:
            return []
        return [l for l in proc.stdout.splitlines()
                if '/' in l and not l.endswith('/HEAD')]

    @staticmethod
    def _state_label(x, y):
        if x == '?':
            return 'Untracked'
        if 'U' in (x, y) or (x, y) in (('A', 'A'), ('D', 'D')):
            return 'Conflict'
        if x != ' ' and y == ' ':
            return {'A': 'Added', 'M': 'Staged', 'D': 'Deleted, staged',
                    'R': 'Renamed', 'C': 'Copied'}.get(x, 'Staged')
        if x == ' ':
            return {'M': 'Modified', 'D': 'Deleted', 'T': 'Type changed'}.get(y, y)
        return 'Staged + ' + {'M': 'Modified', 'D': 'Deleted'}.get(y, y)

    def status(self):
        # -uall: list untracked files individually instead of collapsing
        # an untracked directory into a single 'dir/' entry.
        # -z: NUL-separated, unquoted output — plain parsing would receive
        # C-quoted escapes for any path with non-ASCII/special characters.
        proc = self._run('status', '--porcelain', '-z', '-uall')
        entries = []
        tokens = proc.stdout.split('\0')
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if len(token) < 4 or token[2] != ' ':
                continue
            x, y, path = token[0], token[1], token[3:]
            if x in 'RC' or y in 'RC':
                index += 1  # the following token is the rename origin path
            entries.append({
                'path': path,
                'name': os.path.basename(path),
                'dir': os.path.dirname(path),
                'state': self._state_label(x, y),
                'untracked': x == '?',
                'staged': x not in (' ', '?'),
                'unstaged': y not in (' ', '?') or x == '?',
            })
        entries.sort(key=lambda e: (e['dir'], e['name']))
        return entries

    def has_staged(self):
        proc = self._run('diff', '--cached', '--quiet', check=False)
        if proc.returncode not in (0, 1):
            raise GitError(proc.stderr.strip() or 'Failed to inspect the index.')
        return proc.returncode == 1

    def diff_file(self, path, staged=False, untracked=False):
        if untracked:
            proc = self._run('diff', '--no-index', '--', '/dev/null', path,
                             check=True, ok_codes=(0, 1))
            return proc.stdout
        args = ['diff']
        if staged:
            args.append('--cached')
        args += ['--', path]
        return self._run(*args).stdout

    def log(self, limit=300):
        fmt = SEP.join(['%H', '%h', '%an', '%ae', '%ad', '%D', '%s'])
        # --all + HEAD: keep the full history visible (every branch, remote
        # and tag) even when HEAD is detached on an older commit.
        proc = self._run('log', '-n', str(limit), '--all', 'HEAD',
                         '--topo-order', '--date=format:%Y-%m-%d %H:%M',
                         '--pretty=format:' + fmt, check=False)
        if proc.returncode != 0:
            return []
        commits = []
        for line in proc.stdout.splitlines():
            parts = line.split(SEP)
            if len(parts) != 7:
                continue
            commits.append(dict(zip(
                ('hash', 'short', 'author', 'email', 'date', 'refs', 'subject'), parts)))
        return commits

    def messages(self, limit=50):
        proc = self._run('log', '-z', '-n', str(limit), '--format=%B', check=False)
        if proc.returncode != 0:
            return []
        return [m.strip() for m in proc.stdout.split('\x00') if m.strip()]

    def commit_info(self, commit):
        proc = self._run('show', '-s', '--format=%an' + SEP + '%ae' + SEP + '%B', commit)
        name, email, body = proc.stdout.split(SEP, 2)
        return name, email, body.strip()

    def identity(self):
        """Effective user.name / user.email for this repo ('' when unset)."""
        name = self._run('config', 'user.name', check=False).stdout.strip()
        email = self._run('config', 'user.email', check=False).stdout.strip()
        return name, email

    def set_identity(self, name, email):
        """Write identity into this repository's .git/config."""
        self._run('config', 'user.name', name)
        self._run('config', 'user.email', email)

    def head_hash(self):
        proc = self._run('rev-parse', 'HEAD', check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    # ------------------------------------------------------------- actions

    def stage(self, path):
        self._run('add', '--', path)

    def unstage(self, path):
        # reset (unlike restore --staged) also works on a branch with no
        # commits yet, and never touches the working tree file.
        self._run('reset', '-q', '--', path)

    def add_to_gitignore(self, rel_paths):
        """Append anchored patterns for the given repo-relative paths to the
        repo's root .gitignore, skipping any already present. Returns the list
        of patterns actually added."""
        gitignore = os.path.join(self.path, '.gitignore')
        lines = []
        if os.path.isfile(gitignore):
            with open(gitignore, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
        existing = {line.strip() for line in lines}
        added = []
        for rel in rel_paths:
            # Leading '/' anchors to the repo root (so it matches this exact
            # file, not same-named files elsewhere) and neutralises any
            # leading '#'/'!' that would otherwise be special in .gitignore.
            pattern = '/' + rel.replace(os.sep, '/')
            if pattern in existing or rel in existing:
                continue
            existing.add(pattern)
            added.append(pattern)
        if added:
            with open(gitignore, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines + added) + '\n')
        return added

    def discard(self, path):
        """Revert a tracked file (index and working tree) back to HEAD."""
        self._run('restore', '--source=HEAD', '--staged', '--worktree', '--', path)

    def commit(self, message):
        self._run('commit', '-m', message)

    def pull(self):
        self._run('pull', auth=True, env={'GIT_EDITOR': 'true'})

    def _push_remote(self):
        """Remote to push to: the branch's configured remote, else the only
        remote, else 'origin' when several exist."""
        branch = self._run('symbolic-ref', '--short', 'HEAD', check=False).stdout.strip()
        if branch:
            remote = self._run('config', 'branch.%s.remote' % branch,
                               check=False).stdout.strip()
            if remote:
                return remote
        remotes = self._run('remote', check=False).stdout.split()
        if not remotes:
            raise GitError('No remote is configured for this repository.')
        if 'origin' in remotes:
            return 'origin'
        return remotes[0]

    def push(self):
        proc = self._run('push', auth=True, check=False)
        if proc.returncode != 0:
            err = proc.stderr or ''
            if 'no upstream' in err or 'set-upstream' in err:
                self._run('push', '--set-upstream', self._push_remote(), 'HEAD',
                          auth=True)
            else:
                raise GitError(err.strip() or 'git push failed')

    def merge(self, branch):
        self._run('merge', '--no-edit', branch, env={'GIT_EDITOR': 'true'})

    def checkout(self, ref):
        self._run('checkout', ref)

    def checkout_remote(self, remote_ref):
        """Check out a remote branch, creating a local tracking branch if needed."""
        local = remote_ref.partition('/')[2] or remote_ref
        if local in self.branches():
            self._run('checkout', local)
        else:
            self._run('checkout', '-b', local, '--track', remote_ref)

    def reword(self, commit, message, author_name, author_email):
        """Rewrite message/author of any commit. Returns True if history
        beyond HEAD was rewritten (rebase used)."""
        full = self._run('rev-parse', commit).stdout.strip()
        author = '%s <%s>' % (author_name, author_email)
        if full == self.head_hash():
            self._run('commit', '--amend', '--allow-empty', '-m', message,
                      '--author', author, env={'GIT_EDITOR': 'true'})
            return False
        has_parent = self._run('rev-parse', '--verify', '--quiet', full + '^',
                               check=False).returncode == 0
        base = [full + '^'] if has_parent else ['--root']
        # --rebase-merges: keep merge commits above the edited one (a plain
        # rebase -i silently linearizes them). The first 'pick' in the todo
        # is the edited commit — the sed range 0,/…/ targets only that line.
        quiet_env = {'GIT_SEQUENCE_EDITOR': "sed -i '0,/^pick /s/^pick /edit /'",
                     'GIT_EDITOR': 'true'}
        try:
            self._run('rebase', '-i', '--rebase-merges', *base, env=quiet_env)
            self._run('commit', '--amend', '--allow-empty', '-m', message,
                      '--author', author, env={'GIT_EDITOR': 'true'})
            self._run('rebase', '--continue', env={'GIT_EDITOR': 'true'})
        except GitError:
            self._run('rebase', '--abort', check=False)
            raise
        return True
