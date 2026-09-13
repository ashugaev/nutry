import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.update_from_remote import sync


class RemoteUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / 'remote.git'
        self.writer = self.root / 'writer'
        self.host = self.root / 'host'
        self.git(self.root, 'init', '--bare', str(self.remote))
        self.git(self.root, 'clone', str(self.remote), str(self.writer))
        self.git(self.writer, 'checkout', '-b', 'main')
        self.commit('bot.py', 'initial')
        self.git(self.root, 'clone', '-b', 'main', str(self.remote), str(self.host))

    def git(self, cwd, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c',
            'user.email=test@example.invalid', *args], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self, name, value):
        (self.writer / name).write_text(value)
        self.git(self.writer, 'add', name)
        self.git(self.writer, 'commit', '-m', 'test update')
        self.git(self.writer, 'push', 'origin', 'main')

    def test_remote_main_update_and_repeat(self):
        self.commit('bot.py', 'merged change')
        self.assertEqual(sync(self.host), 'updated')
        self.assertEqual((self.host / 'bot.py').read_text(), 'merged change')
        self.assertEqual(sync(self.host), 'unchanged')

    def test_dirty_or_other_branch_is_preserved(self):
        (self.host / 'bot.py').write_text('local work')
        self.assertIn('local changes', sync(self.host))
        self.git(self.host, 'checkout', '-b', 'feature')
        self.assertIn('not main', sync(self.host))

    def test_dependency_update_requires_planned_upgrade(self):
        self.commit('requirements.txt', 'changed-package')
        self.assertTrue(sync(self.host).startswith('blocked:'))
        self.assertFalse((self.host / 'requirements.txt').exists())

    def test_divergence_never_overwrites_local_commits(self):
        (self.host / 'local.txt').write_text('keep')
        self.git(self.host, 'add', 'local.txt')
        self.git(self.host, 'commit', '-m', 'local change')
        self.commit('remote.txt', 'remote change')
        with self.assertRaises(subprocess.CalledProcessError):
            sync(self.host)
        self.assertEqual((self.host / 'local.txt').read_text(), 'keep')
