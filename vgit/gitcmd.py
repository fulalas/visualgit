import os
import stat
import subprocess
import tempfile

SEP = '\x1f'

# Handed to git via GIT_ASKPASS; the values come from environment variables
# set only for that git subprocess.
_ASKPASS_SCRIPT = """#!/bin/sh
case "$1" in
    [Uu]sername*) printf '%s\\n' "$VGIT_USERNAME" ;;
    *) printf '%s\\n' "$VGIT_PASSWORD" ;;
esac
"""


def _write_askpass():
    fd, path = tempfile.mkstemp(prefix='vgit-askpass-', suffix='.sh')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(_ASKPASS_SCRIPT)
    except OSError:
        os.unlink(path)
        raise
    os.chmod(path, stat.S_IRWXU)
    return path

_GIT_BINARY = 'git'


def set_git_binary(path):
    global _GIT_BINARY
    _GIT_BINARY = path or 'git'


def git_binary():
    return _GIT_BINARY


def git_binary_works(path):
    try:
        proc = subprocess.run([path, '--version'], capture_output=True, text=True)
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.startswith('git version')


def git_available():
    return git_binary_works(_GIT_BINARY)


def _file_type(path):
    # A dotfile like `.gitignore` must come out with no extension, which is
    # what splitext already does.
    return os.path.splitext(os.path.basename(path))[1].lstrip('.').lower()


class GitError(Exception):
    pass


class Git:
    def __init__(self, path, cred_provider=None):
        self.path = path
        self.cred_provider = cred_provider

    def _run(self, *args, auth=False, env=None, check=True, ok_codes=(0,)):
        environ = os.environ.copy()
        # Force English messages: error handling matches on git's output
        # (e.g. 'no upstream', 'tell me who you are').
        environ['LC_ALL'] = 'C'
        askpass_file = None
        if auth:
            environ['GIT_TERMINAL_PROMPT'] = '0'
            creds = self.cred_provider() if self.cred_provider else None
            if creds and creds[0]:
                askpass_file = _write_askpass()
                environ['GIT_ASKPASS'] = askpass_file
                environ['VGIT_USERNAME'] = creds[0]
                environ['VGIT_PASSWORD'] = creds[1] or ''
        if env:
            environ.update(env)
        try:
            proc = subprocess.run([_GIT_BINARY, '-C', self.path] + list(args),
                                  capture_output=True, text=True, env=environ)
        except OSError as exc:
            raise GitError('Could not run git (%s): %s' % (_GIT_BINARY, exc))
        finally:
            if askpass_file:
                try:
                    os.unlink(askpass_file)
                except OSError:
                    pass
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

    def _branch_name(self):
        proc = self._run('symbolic-ref', '--short', 'HEAD', check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ''

    def current_branch(self):
        branch = self._branch_name()
        if branch:
            return branch
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
        proc = self._run('for-each-ref',
                         '--format=%(refname:short)\t%(upstream)\t'
                         '%(upstream:track,nobracket)', 'refs/heads', check=False)
        if proc.returncode != 0:
            return {}
        has_remotes = bool(self.remotes())
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
        proc = self._run('rev-list', '--count', branch, '--not', '--remotes',
                         check=False)
        if proc.returncode != 0:
            return 0
        try:
            return int(proc.stdout.strip())
        except ValueError:
            return 0

    def remote_branches(self):
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
        # -z: NUL-separated, unquoted output — plain parsing would receive
        # C-quoted escapes for any path with non-ASCII/special characters.
        # -uall lists untracked files individually, but a nested repository
        # still comes back as a single 'dir/' entry.
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
            # The trailing slash of a folder entry makes basename() empty, so
            # it is stripped; the name keeps one to mark the entry as a folder.
            named = path.rstrip('/')
            is_dir = named != path
            entries.append({
                'path': path,
                'name': os.path.basename(named) + ('/' if is_dir else ''),
                'type': '' if is_dir else _file_type(path),
                'dir': os.path.dirname(named),
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

    _COMMIT_STATES = {'A': 'Added', 'M': 'Modified', 'D': 'Deleted',
                      'R': 'Renamed', 'C': 'Copied', 'T': 'Type changed'}

    def commit_files(self, commit):
        # -m --first-parent: a plain `git show` emits nothing for a merge.
        proc = self._run('show', '--format=', '--name-status', '-M', '-m',
                         '--first-parent', '-z', commit, check=False)
        if proc.returncode != 0:
            return []
        tokens = proc.stdout.split('\0')
        entries = []
        index = 0
        while index < len(tokens):
            status = tokens[index]
            index += 1
            if not status:
                continue
            code = status[0]
            if code in ('R', 'C'):
                path = tokens[index + 1] if index + 1 < len(tokens) else ''
                index += 2  # origin path, then new path
            else:
                path = tokens[index] if index < len(tokens) else ''
                index += 1
            if not path:
                continue
            entries.append({
                'path': path,
                'name': os.path.basename(path),
                'dir': os.path.dirname(path),
                'state': self._COMMIT_STATES.get(code, code),
            })
        entries.sort(key=lambda e: (e['dir'], e['name']))
        return entries

    def commit_file_diff(self, commit, path):
        return self._run('show', '--format=', '-M', '-m', '--first-parent',
                         commit, '--', path, check=False).stdout

    def log(self, limit=300):
        fmt = SEP.join(['%H', '%h', '%an', '%ae', '%ad', '%D', '%s'])
        # --all + HEAD: keep the full history visible (every branch, remote
        # and tag) even when HEAD is detached on an older commit.
        proc = self._run('log', '-n', str(limit), '--all', 'HEAD',
                         '--topo-order', '--date=format:%Y-%m-%d %H:%M',
                         '--pretty=format:' + fmt, check=False)
        if proc.returncode != 0:
            return []
        prefixes = tuple(r + '/' for r in self.remotes())
        commits = []
        for line in proc.stdout.splitlines():
            parts = line.split(SEP)
            if len(parts) != 7:
                continue
            info = dict(zip(
                ('hash', 'short', 'author', 'email', 'date', 'refs', 'subject'), parts))
            info['refs'] = self._remote_refs(info['refs'], prefixes)
            commits.append(info)
        return commits

    @staticmethod
    def _remote_refs(refs, prefixes):
        if not prefixes:
            return ''
        kept = [r for r in (t.strip() for t in refs.split(','))
                if r.startswith(prefixes) and not r.endswith('/HEAD')]
        return ', '.join(kept)

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
        name = self._run('config', 'user.name', check=False).stdout.strip()
        email = self._run('config', 'user.email', check=False).stdout.strip()
        return name, email

    def set_identity(self, name, email):
        self._run('config', 'user.name', name)
        self._run('config', 'user.email', email)

    def head_hash(self):
        proc = self._run('rev-parse', 'HEAD', check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None

    def stage(self, path):
        self._run('add', '--', path)

    def unstage(self, path):
        # reset (unlike restore --staged) also works on a branch with no
        # commits yet, and never touches the working tree file.
        self._run('reset', '-q', '--', path)

    def rm_cached(self, path):
        self._run('rm', '--cached', '--', path)

    def add_to_gitignore(self, rel_paths):
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
        self._run('restore', '--source=HEAD', '--staged', '--worktree', '--', path)

    def commit(self, message):
        self._run('commit', '-m', message)

    def pull(self):
        branch = self._branch_name()
        upstream = ''
        if branch:
            upstream = self._run('config', 'branch.%s.remote' % branch,
                                 check=False).stdout.strip()
        if branch and not upstream:
            # No upstream configured, so a plain pull would fetch but refuse
            # to merge. Pull the same-named branch from the effective remote,
            # then adopt it as upstream so the next pull is a plain one.
            remote = self._push_remote()
            self._run('pull', '--no-edit', remote, branch, auth=True)
            self._run('branch', '--set-upstream-to=%s/%s' % (remote, branch),
                      check=False)
        else:
            self._run('pull', '--no-edit', auth=True)

    def remotes(self):
        proc = self._run('remote', check=False)
        return proc.stdout.split() if proc.returncode == 0 else []

    def get_remote_url(self, name='origin'):
        proc = self._run('remote', 'get-url', name, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ''

    def set_remote(self, name, url):
        if name in self.remotes():
            self._run('remote', 'set-url', name, url)
        else:
            self._run('remote', 'add', name, url)

    def _push_remote(self):
        branch = self._branch_name()
        if branch:
            remote = self._run('config', 'branch.%s.remote' % branch,
                               check=False).stdout.strip()
            if remote:
                return remote
        remotes = self.remotes()
        if not remotes:
            raise GitError('No remote is configured for this repository.')
        if 'origin' in remotes:
            return 'origin'
        return remotes[0]

    def effective_remote(self):
        try:
            return self._push_remote()
        except GitError:
            return 'origin'

    def remote_needs_password(self):
        # HTTP(S) is the only transport the stored credentials apply to.
        url = self.get_remote_url(self.effective_remote())
        return url.startswith('http://') or url.startswith('https://')

    def remove_remote(self, name):
        self._run('remote', 'remove', name)

    def push(self):
        proc = self._run('push', auth=True, check=False)
        if proc.returncode != 0:
            err = proc.stderr or ''
            if 'no upstream' in err or 'set-upstream' in err:
                self._run('push', '--set-upstream', self._push_remote(), 'HEAD',
                          auth=True)
            else:
                raise GitError(err.strip() or 'git push failed')

    def delete_local_branch(self, name):
        # -D so an unmerged branch still deletes; the UI confirms first.
        self._run('branch', '-D', name)

    def delete_remote_branch(self, remote_ref):
        remote, _, short = remote_ref.partition('/')
        self._run('push', remote, '--delete', short, auth=True)

    def create_branch(self, name):
        self._run('checkout', '-b', name)

    def merge(self, branch):
        self._run('merge', '--no-edit', branch, env={'GIT_EDITOR': 'true'})

    def checkout(self, ref):
        self._run('checkout', ref)

    def checkout_remote(self, remote_ref):
        local = remote_ref.partition('/')[2] or remote_ref
        if local in self.branches():
            self._run('checkout', local)
        else:
            self._run('checkout', '-b', local, '--track', remote_ref)

    def reword(self, commit, message, author_name, author_email):
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
