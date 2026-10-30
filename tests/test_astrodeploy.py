import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('astrodeploy', Path(__file__).parents[1] / 'lib/astrodeploy.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.c = {'name': 'test', 'keep': 3}
        self.base = self.root / 'test'
        (self.base / 'releases').mkdir(parents=True)

    def release(self, name):
        path = self.base / 'releases' / name
        path.mkdir()
        return path

    @unittest.skipIf(os.name == 'nt', 'Benötigt POSIX-Symlinks; Linux-CI führt diesen Test aus')
    def test_failed_start_restores_old_version(self):
        old, new = self.release('old'), self.release('new')
        with patch.object(app, 'BASE', self.root), patch.object(app, 'run'), patch.object(app, 'healthy', side_effect=[False, True]):
            app.link(self.base / 'current', old)
            with self.assertRaises(RuntimeError):
                app.activate(self.c, new)
            self.assertEqual((self.base / 'current').resolve(), old)

    @unittest.skipIf(os.name == 'nt', 'Benötigt POSIX-Symlinks; Linux-CI führt diesen Test aus')
    def test_initial_failure_leaves_no_active_release(self):
        new = self.release('new')
        with patch.object(app, 'BASE', self.root), patch.object(app, 'run'), patch.object(app, 'healthy', return_value=False):
            with self.assertRaises(RuntimeError):
                app.activate(self.c, new)
            self.assertFalse((self.base / 'current').exists())

    @unittest.skipIf(os.name == 'nt', 'Benötigt POSIX-Symlinks; Linux-CI führt diesen Test aus')
    def test_cleanup_preserves_current_and_previous(self):
        releases = [self.release(str(i)) for i in range(7)]
        with patch.object(app, 'BASE', self.root):
            app.link(self.base / 'current', releases[0])
            app.link(self.base / 'previous', releases[1])
            app.cleanup(self.c)
        self.assertTrue(releases[0].exists())
        self.assertTrue(releases[1].exists())
        self.assertFalse(releases[2].exists())

    def test_unchanged_commit_skips_build(self):
        current = self.base / 'current'
        current.mkdir()
        etc = self.root / 'etc'
        etc.mkdir()
        (etc / 'build.env').write_bytes(b'')
        node = Path('/opt/astrodeploy/node/v24.0.0')
        commit = 'a' * 40
        fingerprint = app.hashlib.sha256(commit.encode() + str(node).encode() + b'' + json.dumps(self.c, sort_keys=True).encode()).hexdigest()
        (current / 'release.json').write_text(json.dumps({'fingerprint': fingerprint}))
        self.c['repo'] = 'https://github.com/test/test'
        self.c['branch'] = 'main'
        # Recalculate after adding repository configuration.
        fingerprint = app.hashlib.sha256(commit.encode() + str(node).encode() + json.dumps(self.c, sort_keys=True).encode()).hexdigest()
        (current / 'release.json').write_text(json.dumps({'fingerprint': fingerprint}))
        with patch.object(app, 'BASE', self.root), patch.object(app, 'ETC', etc), patch.object(app, 'git', return_value=commit), patch.object(app, 'build_command') as build:
            app._deploy(self.c, False, node)
            build.assert_not_called()

    def test_build_failure_never_activates(self):
        current = self.base / 'current'
        current.mkdir()
        etc = self.root / 'etc'
        etc.mkdir()
        (etc / 'build.env').write_bytes(b'')
        self.c.update(repo='https://github.com/test/test', branch='main', subdir='.')
        with patch.object(app, 'BASE', self.root), patch.object(app, 'ETC', etc), patch.object(app, 'git', return_value='a' * 40), patch.object(app, 'build_command'), patch.object(app, 'run', side_effect=RuntimeError('build failed')), patch.object(app.subprocess, 'run'), patch.object(app, 'activate') as activate:
            with self.assertRaises(RuntimeError):
                app._deploy(self.c, True, Path('/opt/node'))
            activate.assert_not_called()
            self.assertEqual((self.base / 'current').resolve(), current)

    def test_paused_automatic_deploy_does_nothing(self):
        (self.root / 'paused').touch()
        with patch.object(app, 'STATE', self.root), patch.object(app, '_deploy') as deploy:
            app.deploy(self.c, automatic=True)
            deploy.assert_not_called()


class ArchiveTests(unittest.TestCase):
    def archive(self, entries):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            for name, kind, target in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = target
                tar.addfile(info)
        stream.seek(0)
        return stream

    def test_unsafe_archives_rejected(self):
        cases = [
            [('../escape', tarfile.REGTYPE, '')],
            [('/escape', tarfile.REGTYPE, '')],
            [('file', tarfile.LNKTYPE, '/etc/passwd')],
            [('link', tarfile.SYMTYPE, '../../etc')],
            [('dir', tarfile.SYMTYPE, 'other'), ('dir/file', tarfile.REGTYPE, '')],
            [('device', tarfile.CHRTYPE, '')],
        ]
        for entries in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'bad.tar'
                path.write_bytes(self.archive(entries).getvalue())
                with self.assertRaises(ValueError):
                    app.safe_extract(path, Path(tmp) / 'release')

    def test_normal_files_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ok.tar'
            path.write_bytes(self.archive([('dist', tarfile.DIRTYPE, ''), ('dist/file', tarfile.REGTYPE, '')]).getvalue())
            target = Path(tmp) / 'release'
            app.safe_extract(path, target)
            self.assertTrue((target / 'dist/file').is_file())

    def test_stream_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            stream = self.archive([('dist/file', tarfile.REGTYPE, '')])
            app.safe_extract(stream, Path(tmp) / 'release')
            self.assertTrue((Path(tmp) / 'release/dist/file').is_file())


class NodeTests(unittest.TestCase):
    def test_wrong_checksum_never_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_name = 'node-v24.1.0-linux-x64.tar.xz'
            downloads = [json.dumps([{'version': 'v24.1.0', 'lts': 'Krypton'}]).encode(),
                         ('0' * 64 + '  ' + archive_name).encode(), b'corrupt archive']
            from types import SimpleNamespace
            with patch.object(app.os, 'uname', create=True, return_value=SimpleNamespace(machine='x86_64')), patch.object(app, 'NODE', Path(tmp)), patch.object(app, 'download', side_effect=downloads):
                with self.assertRaisesRegex(RuntimeError, 'Prüfsumme'):
                    app.install_node(24)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_download_failure_never_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace
            with patch.object(app.os, 'uname', create=True, return_value=SimpleNamespace(machine='x86_64')), patch.object(app, 'NODE', Path(tmp)), patch.object(app, 'download', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    app.install_node(24)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
