"""Installer contract tests; website mail/SQLite behavior needs the separate LXC acceptance."""
import copy
import io
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_astrodeploy import app


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.release = self.root / 'release'
        self.release.mkdir()
        self.etc = self.root / 'etc'
        self.etc.mkdir()
        self.env = self.etc / 'runtime.env'
        self.env.write_text('# comment\nOTHER=value\nREGISTRATION_CONFIG=old\nREGISTRATION_CONFIG=other\n')
        self.runtime = self.root / 'private'
        self.systemd = self.root / 'units'
        self.systemd.mkdir()
        self.c = {'name': 'actual-project', 'tls': 'proxy', 'host': 'workshop.example', 'port': 4321}
        self.manifest = copy.deepcopy(app.PROFILE)
        paths = [app.PACKAGE + 'profile.json', app.PROFILE['config']['template'],
                 app.PROFILE['jobs'][0]['entry'], *app.PROFILE['tools'].values(),
                 *(app.PACKAGE + 'src/server/' + f for f in
                   ('registration-config.mjs', 'registrations.mjs', 'registration-mail.mjs')),
                 app.PACKAGE + 'src/content/events.json']
        for relative in paths:
            path = self.release / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        self.profile_path = self.release / (app.PACKAGE + 'profile.json')
        self.profile_path.write_text(json.dumps(self.manifest))
        (self.release / app.PROFILE['config']['template']).write_text(json.dumps(dict.fromkeys(app.REGISTRATION_FIELDS, '')))
        self.metadata(self.release, self.manifest)

    def metadata(self, release, profile, node='/opt/astrodeploy/node/v24.12.0', kind='server'):
        (release / 'release.json').write_text(json.dumps({'kind': kind, 'node': node, 'runtime_profile': profile}))

    def test_contract_and_legacy_opt_in(self):
        self.assertEqual(app.checked_profile(self.release, 'server'), self.manifest)
        self.metadata(self.release, None, kind='static')
        self.assertIsNone(app.release_profile(self.release))
        with patch.object(app, 'SYSTEMD', self.systemd), patch.object(app, 'run') as run:
            app.configure_registration(self.c, self.release)
            run.assert_not_called()
        with self.assertRaises(ValueError):
            app.checked_profile(self.release, 'static')

    def test_old_installer_config_stays_unchanged(self):
        c = dict(name='legacy', repo='https://github.com/example/site', host='example.org',
                 subdir='.', branch='main', port=4321, interval=60, node_major=24,
                 health='/', tls='http', keep=3)
        before = copy.deepcopy(c)
        self.assertIs(app.validate(c), c)
        self.assertEqual(c, before)
        c['runtime_profile'] = 'untrusted'
        with self.assertRaises(ValueError):
            app.validate(c)

    def test_invalid_selected_profile_never_changes_runtime(self):
        self.profile_path.unlink()
        with patch.object(app, 'BASE', self.root), patch.object(app, 'link') as link, \
                patch.object(app, 'prepare_registration') as prepare, patch.object(app, 'stop_registration') as stop:
            with self.assertRaises(ValueError):
                app.activate(self.c, self.release)
            link.assert_not_called()
            prepare.assert_not_called()
            stop.assert_not_called()

    def test_backup_uses_sqlite_api_and_includes_live_wal(self):
        data = self.root / self.c['name'] / 'data'
        data.mkdir(parents=True)
        source = sqlite3.connect(data / 'workshops.sqlite')
        self.addCleanup(source.close)
        source.execute('pragma journal_mode=wal')
        source.execute('create table registrations (id integer)')
        source.execute('insert into registrations values (42)')
        source.commit()
        commands = []
        def execute(args, **kwargs):
            commands.append(args)
            # Run only the installer-owned sqlite code with the local interpreter.
            return subprocess.run([sys.executable, *args[5:]], check=True, **kwargs)
        with patch.object(app, 'BASE', self.root), patch.object(app, 'release_profile', return_value=self.manifest), \
                patch.object(app, 'registration_diagnostics'), patch.object(app, 'run', side_effect=execute):
            app.registration_tool(self.c, ['registration-backup'])
        self.assertEqual(commands[0][:5], ['runuser', '-u', 'astrorun', '--', '/usr/bin/python3'])
        backups = list(data.glob('workshops-backup-*.sqlite'))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as backup:
            self.assertEqual(backup.execute('select id from registrations').fetchall(), [(42,)])
        backup.close()
        self.assertEqual(list(data.glob('*.partial')), [])

    def test_bad_contracts_rejected(self):
        cases = []
        for version in (True, 1.0, 2, '1', None):
            value = copy.deepcopy(self.manifest)
            value['schemaVersion'] = version
            cases.append(value)
        for entry in ('/etc/passwd', '../bad', app.PACKAGE + 'missing.mjs', '%n', 'x\nUser=root', '$(id)'):
            value = copy.deepcopy(self.manifest)
            value['jobs'][0]['entry'] = entry
            cases.append(value)
        for key, value in (('id', 'other'), ('jobs', {}), ('tools', []), ('extra', True)):
            changed = copy.deepcopy(self.manifest)
            changed[key] = value
            cases.append(changed)
        for value in cases:
            with self.subTest(value=value):
                self.profile_path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    app.checked_profile(self.release, 'server')

    def test_missing_file_duplicate_keys_and_size_limit(self):
        self.profile_path.write_text('{"id":"x","id":"y"}')
        with self.assertRaises(ValueError):
            app.checked_profile(self.release, 'server')
        self.profile_path.write_text(' ' * 32769)
        with self.assertRaises(ValueError):
            app.checked_profile(self.release, 'server')
        self.profile_path.write_text(json.dumps(self.manifest))
        (self.release / app.PROFILE['tools']['admin']).unlink()
        with self.assertRaises(ValueError):
            app.checked_profile(self.release, 'server')

    @unittest.skipIf(os.name == 'nt', 'Requires POSIX symlinks')
    def test_symlinks_even_within_release_rejected(self):
        path = self.release / app.PROFILE['tools']['admin']
        path.unlink()
        path.symlink_to(self.profile_path)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            app.checked_profile(self.release, 'server')

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership and groups')
    def test_private_initialization_and_preservation(self):
        import grp
        with patch.object(app, 'RUNTIME', self.runtime), patch.object(app, 'ETC', self.etc), \
                patch.object(app, 'BASE', self.root), patch.object(app.os, 'chown') as chown, \
                patch.object(grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=123)):
            app.prepare_registration(self.c, self.release)
            path = self.runtime / 'registration.json'
            value = json.loads(path.read_text())
            self.assertGreaterEqual(len(value['REGISTRATION_SECRET']), 32)
            self.assertEqual(value['REGISTRATION_ENABLED'], 'false')
            self.assertEqual(value['REGISTRATION_DB'], str(self.root / 'actual-project/data/workshops.sqlite'))
            self.assertEqual(value['REGISTRATION_ORIGIN'], 'https://workshop.example')
            self.assertEqual(value['SMTP_REQUIRE_TLS'], 'true')
            value['SMTP_PASSWORD'] = 'private'
            path.write_text(json.dumps(value))
            before = path.read_bytes()
            app.prepare_registration(self.c, self.release)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o750)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            chown.assert_any_call(self.runtime, 0, 123)
            self.assertEqual(self.env.read_text(), '# comment\nOTHER=value\nREGISTRATION_CONFIG=' + str(path) + '\n')

    def test_units_use_release_node_and_sandbox(self):
        base = str(Path('/srv/astro') / self.c['name'])
        with patch.object(app, 'SYSTEMD', self.systemd), patch.object(app, 'BASE', Path('/srv/astro')), \
                patch.object(app, 'NODE', '/opt/astrodeploy/node'), patch.object(app, 'run'):
            app.configure_registration(self.c, self.release)
            service = (self.systemd / (app.JOB + '.service')).read_text()
            for expected in ('User=astrorun', 'Group=astrorun', 'ProtectSystem=strict', 'NoNewPrivileges=yes',
                             'WorkingDirectory=' + base + '/current',
                             'ExecStart=/opt/astrodeploy/node/v24.12.0/bin/node ' + app.PROFILE['jobs'][0]['entry'],
                             'EnvironmentFile=/etc/astrodeploy/runtime.env', 'UMask=0077',
                             'ReadWritePaths=' + base + '/data', 'ExecCondition='):
                self.assertIn(expected, service)
            self.metadata(self.release, self.manifest, node='/opt/astrodeploy/node/v24.10.0')
            app.configure_registration(self.c, self.release)
            self.assertIn('v24.10.0/bin/node', (self.systemd / (app.JOB + '.service')).read_text())
            self.metadata(self.release, None, kind='static')
            app.configure_registration(self.c, self.release)
            self.assertFalse((self.systemd / (app.JOB + '.service')).exists())

    def test_worker_guard_disabled_and_http_never_runs_node(self):
        path = self.root / 'config.json'
        for enabled, origin, expected in [('false', 'https://site', 1), ('true', 'http://site', 2), ('true', 'https://site', 0)]:
            path.write_text(json.dumps({'REGISTRATION_ENABLED': enabled, 'REGISTRATION_ORIGIN': origin}))
            result = subprocess.run([sys.executable, str(Path(app.__file__)), 'registration-enabled'],
                                    env={**os.environ, 'REGISTRATION_CONFIG': str(path)}, capture_output=True)
            self.assertEqual(result.returncode, expected)
            self.assertEqual(result.stdout + result.stderr, b'')

    def test_nginx_keeps_acl_tls_and_suppresses_access_log(self):
        site = self.root / 'nginx-site'
        location = self.root / 'nginx-location'
        site.write_text('server {\nlisten 443 ssl;\nssl_certificate /cert;\n    include /etc/nginx/astrodeploy-location.conf;\n}')
        original = app.proxy_location(self.c).replace('location / {', 'location / {\n        allow 10.0.0.0/8;\n        deny all;\n        auth_basic "Private";') + '\n'
        location.write_text(original)
        with patch.object(app, 'NGINX_SITE', site), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'release_profile', return_value=self.manifest), patch.object(app, 'run'):
            app.configure_runtime(self.c, 'server')
            app.configure_runtime(self.c, 'server')
        self.assertEqual(location.read_text().count('access_log off;'), 1)
        self.assertIn('allow 10.0.0.0/8;', location.read_text())
        self.assertIn('deny all;', location.read_text())
        self.assertEqual(location.read_text().count('location '), 1)
        self.assertIn('ssl_certificate /cert;', site.read_text())
        with patch.object(app, 'NGINX_SITE', site), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'release_profile', return_value=None), patch.object(app, 'run'):
            app.configure_runtime(self.c, 'server')
        self.assertEqual(location.read_text(), original)

    def test_nginx_failed_validation_restores_file(self):
        location = self.root / 'nginx-location'
        original = app.proxy_location(self.c) + '\n'
        location.write_text(original)
        with patch.object(app, 'migrate_nginx'), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'release_profile', return_value=self.manifest), \
                patch.object(app, 'run', side_effect=RuntimeError('invalid')):
            with self.assertRaises(RuntimeError):
                app.configure_runtime(self.c, 'server')
        self.assertEqual(location.read_text(), original)

    def test_legacy_proxy_gains_forwarded_host_without_losing_acl(self):
        location = self.root / 'nginx-location'
        original = app.proxy_location(self.c, forwarded_host=False).replace(
            'location / {', 'location / {\n        deny 192.0.2.1;') + '\n'
        location.write_text(original)
        with patch.object(app, 'migrate_nginx'), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'release_profile', return_value=self.manifest), patch.object(app, 'run'):
            app.configure_runtime(self.c, 'server')
            app.configure_runtime(self.c, 'server')
        content = location.read_text()
        self.assertEqual(content.count('proxy_set_header X-Forwarded-Host $http_host;'), 1)
        self.assertIn('deny 192.0.2.1;', content)
        self.assertIn('access_log off;', content)

    def test_conflicting_forwarded_host_is_not_overwritten(self):
        location = self.root / 'nginx-location'
        original = app.proxy_location(self.c).replace('X-Forwarded-Host $http_host', 'X-Forwarded-Host custom.example')
        location.write_text(original)
        with patch.object(app, 'migrate_nginx'), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'release_profile', return_value=self.manifest), patch.object(app, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'X-Forwarded-Host'):
                app.configure_runtime(self.c, 'server')
            run.assert_not_called()
        self.assertEqual(location.read_text(), original)

    def test_original_inline_proxy_migrates_with_tls_preserved(self):
        site = self.root / 'site'
        location = self.root / 'nginx-location'
        site.write_text('server {\nlisten 443 ssl;\nssl_certificate /existing;\n' +
                        app.proxy_location(self.c, forwarded_host=False) + '\n}')
        with patch.object(app, 'NGINX_SITE', site), patch.object(app, 'NGINX_LOCATION', location), \
                patch.object(app, 'STATE', self.root), patch.object(app, 'run'):
            app.migrate_nginx(self.c)
        self.assertIn('ssl_certificate /existing;', site.read_text())
        self.assertIn('include /etc/nginx/astrodeploy-location.conf;', site.read_text())

    def test_profile_package_survives_existing_artifact_handoff(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            tar.add(self.release / 'dist', arcname='dist')
        stream.seek(0)
        target = self.root / 'extracted'
        app.safe_extract(stream, target)
        self.assertEqual(app.checked_profile(target, 'server'), self.manifest)
        self.assertFalse((target / 'registration.json').exists())

    def test_cleanup_defers_while_worker_activating(self):
        (self.systemd / (app.JOB + '.service')).touch()
        with patch.object(app, 'SYSTEMD', self.systemd), patch.object(app.subprocess, 'run',
                return_value=SimpleNamespace(stdout='activating\n')), patch.object(app.shutil, 'rmtree') as remove:
            app.cleanup(self.c)
            remove.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'Requires POSIX symlinks')
    def test_failed_health_restores_job_node_and_timer_state(self):
        base = self.root / self.c['name']
        base.mkdir()
        old = base / 'old'
        old.mkdir()
        self.metadata(old, None)
        app.link(base / 'current', old)
        with patch.object(app, 'BASE', self.root), patch.object(app, 'prepare_registration'), \
                patch.object(app, 'job_state', return_value=(False, False)), \
                patch.object(app, 'stop_registration') as stop, \
                patch.object(app, 'configure_registration') as configure, \
                patch.object(app, 'configure_runtime'), patch.object(app, 'start_registration') as start, \
                patch.object(app, 'healthy', side_effect=[False, True]):
            with self.assertRaises(RuntimeError):
                app.activate(self.c, self.release)
            self.assertEqual((base / 'current').resolve(), old)
            self.assertEqual([call.args[1] for call in configure.call_args_list], [self.release, old])
            start.assert_called_once_with(old, (False, False))
            self.assertEqual(stop.call_count, 2)


class GeneralFormsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = copy.deepcopy(app.FORMS_PROFILE)
        for relative in [app.FORMS_PACKAGE + 'profile.json', self.profile['config']['template'],
                         self.profile['jobs'][0]['entry'], *self.profile['tools'].values()]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        (self.root / (app.FORMS_PACKAGE + 'profile.json')).write_text(json.dumps(self.profile))
        self.template = self.root / self.profile['config']['template']
        self.template.write_text(json.dumps(dict.fromkeys(app.profile_fields(self.profile), '')))
        (self.root / 'release.json').write_text(json.dumps({
            'kind': 'server', 'node': '/opt/astrodeploy/node/v24.12.0', 'runtime_profile': self.profile}))

    def test_generic_contract_needs_no_workshop_modules_or_events(self):
        self.assertEqual(app.checked_profile(self.root, 'server', app.FORMS_ID), self.profile)
        self.assertEqual(app.release_profile(self.root), self.profile)
        self.assertFalse((self.root / app.PACKAGE).exists())
        with self.assertRaises(ValueError):
            app.checked_profile(self.root, 'static', app.FORMS_ID)
        with self.assertRaises(ValueError):
            app.checked_profile(self.root, 'server', 'arbitrary-hook')

    def test_generic_initial_config_has_own_data_secret_and_no_institution_smtp(self):
        c = {'name': 'contact-site', 'host': 'contact.example.org', 'tls': 'proxy'}
        template = json.loads(self.template.read_text())
        template.update(SMTP_HOST='untrusted-relay', SMTP_USER='preloaded-user')
        self.template.write_text(json.dumps(template))
        value = app.initial_runtime_config(c, self.root, self.profile)
        self.assertEqual(value['FORMS_ORIGIN'], 'https://contact.example.org')
        self.assertEqual(value['FORMS_DB'], str(app.BASE / 'contact-site/data/forms.sqlite'))
        self.assertEqual(value['FORMS_ENABLED'], 'false')
        self.assertGreaterEqual(len(value['FORMS_SECRET']), 32)
        for key in ('SMTP_HOST', 'SMTP_PORT', 'SMTP_FROM', 'SMTP_USER', 'SMTP_PASSWORD'):
            self.assertEqual(value[key], '')
        self.assertFalse(any(key.startswith('REGISTRATION_') for key in value))

    def test_generic_contract_rejects_hooks_injections_and_unknown_fields(self):
        path = self.root / (app.FORMS_PACKAGE + 'profile.json')
        for entry in ('/etc/passwd', '../worker.mjs', 'worker.mjs\nUser=root', '%n', '$(id)'):
            value = copy.deepcopy(self.profile)
            value['jobs'][0]['entry'] = entry
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                app.checked_profile(self.root, 'server', app.FORMS_ID)
        path.write_text(json.dumps(self.profile))
        template = json.loads(self.template.read_text())
        template['EXEC_ROOT'] = 'arbitrary'
        self.template.write_text(json.dumps(template))
        with self.assertRaises(ValueError):
            app.checked_profile(self.root, 'server', app.FORMS_ID)

    def test_generic_service_guard_uses_selected_profile_even_with_legacy_env(self):
        path = self.root / 'private.json'
        legacy = self.root / 'legacy.json'
        legacy.write_text(json.dumps({'REGISTRATION_ENABLED': 'true', 'REGISTRATION_ORIGIN': 'https://old'}))
        for enabled, expected in [('false', 1), ('true', 0)]:
            path.write_text(json.dumps({'FORMS_ENABLED': enabled, 'FORMS_ORIGIN': 'https://contact.example.org'}))
            result = subprocess.run([sys.executable, str(Path(app.__file__)), 'registration-enabled', 'forms'],
                                    env={**os.environ, 'FORMS_CONFIG': str(path), 'REGISTRATION_CONFIG': str(legacy)},
                                    capture_output=True)
            self.assertEqual(result.returncode, expected)
            self.assertEqual(result.stdout + result.stderr, b'')

    def test_generic_units_use_generic_entry_and_explicit_guard(self):
        units = self.root / 'units'
        units.mkdir()
        with patch.object(app, 'SYSTEMD', units), patch.object(app, 'NODE', '/opt/astrodeploy/node'), \
                patch.object(app, 'run'):
            app.configure_registration({'name': 'contact-site'}, self.root)
        service = (units / (app.JOB + '.service')).read_text()
        self.assertIn('registration-enabled forms\n', service)
        self.assertIn('/bin/node dist/server/forms/maintenance.mjs', service)
        self.assertNotIn('registration-maintenance.mjs', service)


if __name__ == '__main__':
    unittest.main()
