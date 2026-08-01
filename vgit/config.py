"""Persisted application state: repository list, per-repository credentials,
and UI state (selected repo, drafts, window geometry, splitter positions)."""
import base64
import hashlib
import hmac
import json
import os
import stat

CONFIG_DIR = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'visualgit')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
KEY_FILE = os.path.join(CONFIG_DIR, 'key')


class Config:
    def __init__(self):
        self.data = {'repos': []}
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.isfile(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data = loaded
            except (OSError, ValueError):
                pass
        if not isinstance(self.data.get('repos'), list):
            self.data['repos'] = []
        if not isinstance(self.data.get('state'), dict):
            self.data['state'] = {}
        self._key = None
        self._migrate_plaintext_passwords()

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)

    def repos(self):
        return list(self.data['repos'])

    def get_repo(self, path):
        for repo in self.data['repos']:
            if repo['path'] == path:
                return repo
        return None

    def add_repo(self, path):
        if self.get_repo(path):
            return False
        self.data['repos'].append({'path': path})
        self.save()
        return True

    def set_repo_path(self, path, new_path):
        """Point an existing entry at another folder (e.g. after moving it)."""
        repo = self.get_repo(path)
        if repo is None or self.get_repo(new_path):
            return False
        repo['path'] = new_path
        self.save()
        return True

    def remove_repo(self, path):
        self.data['repos'] = [r for r in self.data['repos'] if r['path'] != path]
        self.save()

    def set_credentials(self, path, username, password):
        repo = self.get_repo(path)
        if repo is not None:
            repo['username'] = username
            repo['password'] = self._encrypt(password) if password else ''
            self.save()

    def credentials(self, path):
        repo = self.get_repo(path) or {}
        return repo.get('username', ''), self._decrypt(repo.get('password', ''))

    # ------------------------------------------------------------- UI state

    def get_state(self, key, default=None):
        return self.data['state'].get(key, default)

    def set_state(self, key, value, save=True):
        self.data['state'][key] = value
        if save:
            self.save()

    # ------------------------------------------------- password obfuscation
    # Keystream cipher (HMAC-SHA256 counter mode) with a random per-value
    # nonce and a machine-local key file. This keeps passwords unreadable in
    # config.json itself; it is not protection against an attacker who can
    # read this user's home directory (the key lives there too).

    def _load_key(self):
        if self._key is None:
            if not os.path.isfile(KEY_FILE):
                with open(KEY_FILE, 'wb') as f:
                    f.write(os.urandom(32))
            os.chmod(KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
            with open(KEY_FILE, 'rb') as f:
                self._key = f.read()
        return self._key

    def _keystream_xor(self, data, nonce):
        key = self._load_key()
        out = bytearray()
        counter = 0
        while len(out) < len(data):
            block = hmac.new(key, nonce + counter.to_bytes(4, 'big'),
                             hashlib.sha256).digest()
            out.extend(block)
            counter += 1
        return bytes(a ^ b for a, b in zip(data, out))

    def _encrypt(self, text):
        nonce = os.urandom(16)
        cipher = self._keystream_xor(text.encode('utf-8'), nonce)
        return 'enc:' + base64.b64encode(nonce + cipher).decode('ascii')

    def _decrypt(self, value):
        if not value.startswith('enc:'):
            return value  # legacy plaintext
        try:
            raw = base64.b64decode(value[4:])
            return self._keystream_xor(raw[16:], raw[:16]).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            return ''

    def _migrate_plaintext_passwords(self):
        changed = False
        for repo in self.data['repos']:
            password = repo.get('password', '')
            if password and not password.startswith('enc:'):
                repo['password'] = self._encrypt(password)
                changed = True
        if changed:
            self.save()
