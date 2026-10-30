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
        with patch.object(app, 'BASE', self.root), patch.object(app, 'configure_runtime'), patch.object(app, 'run'), patch.object(app, 'healthy', side_effect=[False, True]):
            app.link(self.base / 'current', old)
            with self.assertRaises(RuntimeError):
                app.activate(self.c, new)
            self.assertEqual((self.base / 'current').resolve(), old)

    @unittest.skipIf(os.name == 'nt', 'Benötigt POSIX-Symlinks; Linux-CI führt diesen Test aus')
    def test_initial_failure_leaves_no_active_release(self):
        new = self.release('new')
        with patch.object(app, 'BASE', self.root), patch.object(app, 'configure_runtime'), patch.object(app, 'save'), patch.object(app, 'run'), patch.object(app, 'healthy', return_value=False):
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
        self.c['repo'] = 'https://github.com/test/test'
        self.c['branch'] = 'main'
        fingerprint = app.hashlib.sha256(commit.encode() + str(node).encode() + json.dumps(self.c, sort_keys=True).encode() + app.VERSION.encode()).hexdigest()
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


class BuildUserTests(unittest.TestCase):
    def test_commands_do_not_inherit_root_working_directory(self):
        with patch.object(app, 'run') as run:
            app.build_command(['git', 'ls-remote', 'https://github.com/example/site.git'])
        self.assertEqual(run.call_args.kwargs['cwd'], app.BUILD)


class SetupTests(unittest.TestCase):
    def test_default_interface_ip_first_and_invalid_addresses_filtered(self):
        from types import SimpleNamespace
        addresses = [
            {'ifname': 'other', 'addr_info': [{'local': '192.0.2.20'}]},
            {'ifname': 'eth0', 'addr_info': [{'local': '127.0.0.1'}, {'local': '192.0.2.10'},
                                          {'local': '169.254.1.2'}, {'local': 'invalid'}]},
        ]
        results = [SimpleNamespace(stdout=json.dumps(addresses)),
                   SimpleNamespace(stdout=json.dumps([{'dev': 'eth0'}]))]
        with patch.object(app, 'run', side_effect=results):
            self.assertEqual(app.container_ips(), ['192.0.2.10', '192.0.2.20'])

    def test_ip_detection_without_ip_command_is_optional(self):
        with patch.object(app, 'run', side_effect=FileNotFoundError):
            self.assertEqual(app.container_ips(), [])

    def test_private_https_repository_is_converted_to_ssh(self):
        with patch.object(app, 'ask', return_value='https://github.com/example/site.git'), patch.object(app, 'yes', return_value=True):
            self.assertEqual(app.repository_prompt(), 'git@github.com:example/site.git')

    def test_public_repository_uses_https(self):
        with patch.object(app, 'ask', return_value='git@github.com:example/site.git'), patch.object(app, 'yes', return_value=False):
            self.assertEqual(app.repository_prompt(), 'https://github.com/example/site.git')


class RenderingTests(unittest.TestCase):
    def test_static_runtime_disables_node_and_reloads_nginx(self):
        c = {'name': 'test', 'port': 4321, 'tls': 'http'}
        with patch.object(app, 'migrate_nginx'), patch.object(app, 'save'), patch.object(app, 'run') as run:
            app.configure_runtime(c, 'static')
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(['systemctl', 'disable', '--now', 'astro-site'], commands)
        self.assertIn(['systemctl', 'reload', 'nginx'], commands)
        self.assertNotIn(['systemctl', 'restart', 'astro-site'], commands)

    def test_static_healthcheck_uses_local_nginx_and_configured_host(self):
        from types import SimpleNamespace
        c = {'name': 'test', 'port': 4321, 'tls': 'http', 'host': 'example.invalid', 'health': '/wissen/'}
        with patch.object(app, 'release_type', return_value='static'), patch.object(app.http.client, 'HTTPConnection') as http, patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            http.return_value.getresponse.return_value.status = 200
            self.assertTrue(app.healthy(c))
        http.assert_called_once_with('127.0.0.1', 80, timeout=2)
        http.return_value.request.assert_called_once_with('GET', '/wissen/', headers={'Host': 'example.invalid'})

    def test_static_tls_probe_stays_local_and_validates_hostname(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        first, second = MagicMock(), MagicMock()
        first.getresponse.return_value.status = 301
        second.getresponse.return_value.status = 200
        c = {'name': 'test', 'port': 4321, 'tls': 'letsencrypt', 'host': 'example.invalid', 'health': '/'}
        with patch.object(app, 'release_type', return_value='static'), patch.object(app.http.client, 'HTTPConnection', side_effect=[first, second]), patch.object(app.socket, 'create_connection') as connect, patch.object(app.ssl, 'create_default_context') as context, patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            self.assertTrue(app.healthy(c))
        connect.assert_called_once_with(('127.0.0.1', 443), timeout=2)
        context.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='example.invalid')
        second.request.assert_called_once_with('GET', '/', headers={'Host': 'example.invalid'})

    @unittest.skipIf(os.name == 'nt', 'Benötigt POSIX-Symlinks')
    def test_failed_static_activation_restores_server_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / 'test'
            old, new = base / 'old', base / 'new'
            old.mkdir(parents=True)
            new.mkdir()
            (old / 'release.json').write_text('{"kind":"server"}')
            (new / 'release.json').write_text('{"kind":"static"}')
            app.link(base / 'current', old)
            with patch.object(app, 'BASE', root), patch.object(app, 'configure_runtime') as configure, patch.object(app, 'healthy', side_effect=[False, True]):
                with self.assertRaises(RuntimeError):
                    app.activate({'name': 'test'}, new)
                self.assertEqual([call.args[1] for call in configure.call_args_list], ['static', 'server'])
                self.assertEqual((base / 'current').resolve(), old)

    def test_static_output_accepted_only_in_auto_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp)
            (release / 'dist').mkdir()
            (release / 'dist/index.html').write_text('static content')
            self.assertEqual(app.classify_release(release, 'auto'), 'static')
            with self.assertRaises(RuntimeError):
                app.classify_release(release, 'server')

    def test_server_output_detected_and_legacy_release_stays_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            release = Path(tmp)
            (release / 'dist/server').mkdir(parents=True)
            (release / 'dist/server/entry.mjs').touch()
            self.assertEqual(app.classify_release(release, 'auto'), 'server')
            self.assertEqual(app.release_type(release), 'server')

    def test_nginx_migration_preserves_tls_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            site = base / 'site.conf'
            c = {'port': 4321, 'tls': 'letsencrypt'}
            original = 'server {\nlisten 443 ssl;\nssl_certificate /existing/cert.pem;\n' + app.proxy_location(c) + '\n}'
            site.write_text(original)
            with patch.object(app, 'NGINX_SITE', site), patch.object(app, 'NGINX_LOCATION', base / 'location.conf'), patch.object(app, 'STATE', base), patch.object(app, 'run'):
                app.migrate_nginx(c)
                app.migrate_nginx(c)
            self.assertIn('ssl_certificate /existing/cert.pem;', site.read_text())
            self.assertIn('include /etc/nginx/astrodeploy-location.conf;', site.read_text())
            self.assertEqual((base / 'nginx-before-0.3.conf').read_text(), original)

    def test_unknown_nginx_config_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / 'site.conf'
            site.write_text('custom configuration')
            with patch.object(app, 'NGINX_SITE', site):
                with self.assertRaises(RuntimeError):
                    app.migrate_nginx({'port': 4321, 'tls': 'http'})
            self.assertEqual(site.read_text(), 'custom configuration')

    def test_failed_nginx_migration_restores_original_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            site = base / 'site.conf'
            c = {'port': 4321, 'tls': 'http'}
            original = 'server {\n' + app.proxy_location(c) + '\n}'
            site.write_text(original)
            with patch.object(app, 'NGINX_SITE', site), patch.object(app, 'NGINX_LOCATION', base / 'location.conf'), patch.object(app, 'STATE', base), patch.object(app, 'run', side_effect=RuntimeError('nginx syntax')):
                with self.assertRaises(RuntimeError):
                    app.migrate_nginx(c)
            self.assertEqual(site.read_text(), original)


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
