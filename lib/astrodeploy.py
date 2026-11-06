#!/usr/bin/python3
"""AstroDeploy: root orchestration; all repository code runs as astrobuild."""
import contextlib
import hashlib
import http.client
import ipaddress
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import shutil
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

VERSION = '0.5.1'
RUNTIME = Path('/etc/astrodeploy-runtime')
SYSTEMD = Path('/etc/systemd/system')
PROFILE_ID = 'workshop-registration'
JOB = 'astro-registration-maintenance'
PACKAGE = 'dist/server/registration/'
PROFILE = {
    'schemaVersion': 1, 'id': PROFILE_ID,
    'config': {'template': PACKAGE + 'deploy/registration.config.example.json',
               'filename': 'registration.json', 'environmentVariable': 'REGISTRATION_CONFIG',
               'dataFileFields': {'REGISTRATION_DB': 'workshops.sqlite'}},
    'jobs': [{'id': 'registration-maintenance',
              'entry': PACKAGE + 'scripts/registration-maintenance.mjs', 'intervalSeconds': 60}],
    'tools': {'admin': PACKAGE + 'scripts/registration-admin.mjs',
              'backup': PACKAGE + 'deploy/backup-registration-db.mjs'},
}
REGISTRATION_FIELDS = (
    'REGISTRATION_ENABLED REGISTRATION_TEST_MODE REGISTRATION_ORIGIN REGISTRATION_SECRET '
    'REGISTRATION_EMAIL_DOMAINS REGISTRATION_PRIVACY_NOTICE REGISTRATION_RETENTION_DAYS '
    'REGISTRATION_ADMIN_USER REGISTRATION_ADMIN_PASSWORD_HASH REGISTRATION_DB '
    'SMTP_HOST SMTP_PORT SMTP_FROM SMTP_SECURE SMTP_REQUIRE_TLS SMTP_USER SMTP_PASSWORD'
).split()
FORMS_ID = 'forms'
FORMS_PACKAGE = 'dist/server/forms/'
FORMS_PROFILE = {
    'schemaVersion': 1, 'id': FORMS_ID,
    'config': {'template': FORMS_PACKAGE + 'forms.config.example.json',
               'filename': 'forms.json', 'environmentVariable': 'FORMS_CONFIG',
               'dataFileFields': {'FORMS_DB': 'forms.sqlite'}},
    'jobs': [{'id': 'forms-maintenance', 'entry': FORMS_PACKAGE + 'maintenance.mjs',
              'intervalSeconds': 60}],
    'tools': {'admin': FORMS_PACKAGE + 'admin.mjs', 'backup': FORMS_PACKAGE + 'backup.mjs'},
}
PROFILES = {PROFILE_ID: PROFILE, FORMS_ID: FORMS_PROFILE}


def profile_spec(profile_id):
    if not isinstance(profile_id, str) or profile_id not in PROFILES:
        raise ValueError('Unbekanntes Laufzeitprofil.')
    return PROFILES[profile_id]


def profile_prefix(profile):
    return 'FORMS' if profile['id'] == FORMS_ID else 'REGISTRATION'


def profile_fields(profile):
    prefix = profile_prefix(profile)
    return [name.replace('REGISTRATION_', prefix + '_') for name in REGISTRATION_FIELDS]


def initial_runtime_config(c, release, profile):
    value = limited_json(regular_release_file(release, profile['config']['template']))
    prefix = profile_prefix(profile)
    dbfield, filename = next(iter(profile['config']['dataFileFields'].items()))
    value.update({prefix + '_ENABLED': 'false', prefix + '_TEST_MODE': 'false',
                  prefix + '_SECRET': secrets.token_urlsafe(48),
                  prefix + '_ORIGIN': ('http' if c['tls'] == 'http' else 'https') + '://' + c['host'],
                  dbfield: str(BASE / c['name'] / 'data' / filename),
                  'SMTP_SECURE': 'false', 'SMTP_REQUIRE_TLS': 'true'})
    if profile['id'] == PROFILE_ID:
        value.update(SMTP_HOST='141.47.2.1', SMTP_PORT='25', SMTP_FROM='MakerLabTechnik@hs-pforzheim.de')
    else:
        # Generic installations must never inherit another operator's mail relay.
        for key in ('SMTP_HOST', 'SMTP_PORT', 'SMTP_FROM', 'SMTP_USER', 'SMTP_PASSWORD'):
            value[key] = ''
    return value
ETC = Path('/etc/astrodeploy')
STATE = Path('/var/lib/astrodeploy')
BUILD = Path('/var/lib/astrobuild')
BASE = Path('/srv/astro')
TOOLS = Path('/usr/local/lib/astrodeploy')
NODE = Path('/opt/astrodeploy/node')
NGINX_LOCATION = Path('/etc/nginx/astrodeploy-location.conf')
NGINX_SITE = Path('/etc/nginx/sites-available/astrodeploy')
GH_KEY = 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl\n'


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def save(path, value, mode=0o600):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    # Parent directories are root-owned; never use this for build-owned paths.
    with open(tmp, 'w', encoding='utf-8') as stream:
        stream.write(value)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def save_json(path, value):
    save(path, json.dumps(value, indent=2) + '\n')


def ask(label, default='', validate=lambda v: bool(v)):
    while True:
        value = input(f'{label}' + (f' [{default}]' if default else '') + ': ').strip() or default
        if validate(value):
            return value
        print('Ungültige Eingabe. Bitte erneut versuchen.')


def yes(label, default=False):
    return ask(label + ' (ja/nein)', 'ja' if default else 'nein',
               lambda v: v in ('ja', 'nein')) == 'ja'


def valid_repo(value):
    return bool(re.fullmatch(r'(https://github\.com/|git@github\.com:)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', value))


def valid_host(value):
    return bool(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', value))


def valid_subdir(value):
    return value == '.' or bool(re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*', value)) and '..' not in PurePosixPath(value).parts


def container_ips():
    """Prefer addresses on the default interface; no external connection needed."""
    try:
        addresses = json.loads(run(['ip', '-j', '-4', 'address', 'show', 'scope', 'global'],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, timeout=5).stdout)
        try:
            routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'default'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, timeout=5).stdout)
            preferred = {route.get('dev') for route in routes}
        except (OSError, ValueError, subprocess.SubprocessError):
            preferred = set()
        result = []
        for interface in sorted(addresses, key=lambda item: item.get('ifname') not in preferred):
            for address in interface.get('addr_info', []):
                try:
                    ip = ipaddress.IPv4Address(address.get('local', ''))
                except ipaddress.AddressValueError:
                    continue
                if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast):
                    if str(ip) not in result:
                        result.append(str(ip))
        return result
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def repository_prompt():
    repo = ask('GitHub-URL deiner ASTRO-WEBSITE (nicht des Installers)', validate=valid_repo)
    private = yes('Ist dieses Website-Repository privat?', repo.startswith('git@'))
    slug = re.sub(r'^(https://github\.com/|git@github\.com:)', '', repo)
    return ('git@github.com:' if private else 'https://github.com/') + slug


def adapter_version():
    metadata = json.loads(download('https://registry.npmjs.org/@astrojs%2fnode/latest'))
    version = metadata['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('Die npm-Registry liefert keine gültige stabile Adapter-Version.')
    return version


def validate(c):
    if c.get('runtime_profile') not in (None, PROFILE_ID, FORMS_ID):
        raise ValueError('Unbekanntes runtime_profile.')
    if not (re.fullmatch(r'[a-z][a-z0-9-]{0,30}', c['name']) and valid_repo(c['repo'])
            and valid_host(c['host']) and valid_subdir(c['subdir'])
            and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', c['branch'])
            and '..' not in c['branch'] and 1024 <= c['port'] <= 65535
            and 30 <= c['interval'] <= 86400 and c['node_major'] == 24
            and re.fullmatch(r'/[A-Za-z0-9_./~%-]*', c['health'])
            and c['tls'] in ('http', 'letsencrypt', 'proxy')
            and 2 <= c['keep'] <= 20):
        raise ValueError('Ungültige Konfiguration in /etc/astrodeploy/config.json')
    if c['tls'] == 'proxy':
        ipaddress.ip_network(c['proxy'], strict=False)
    if c.get('render_mode', 'server') not in ('auto', 'server'):
        raise ValueError('render_mode muss auto oder server sein.')
    if not isinstance(c.get('container_prepare', False), bool):
        raise ValueError('container_prepare muss true oder false sein.')
    if c.get('container_prepare') and not re.fullmatch(r'\d+\.\d+\.\d+', c.get('adapter_version', '')):
        raise ValueError('Für den Container-Modus wird eine feste adapter_version benötigt.')
    return c


def config():
    return validate(json.loads((ETC / 'config.json').read_text()))


@contextlib.contextmanager
def lock():
    import fcntl
    with open('/run/astrodeploy.lock', 'w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Ein anderer Verwaltungsbefehl läuft bereits.') from None
        yield


def build_command(args, node=None, **kwargs):
    # The installer is usually started in /root, which astrobuild cannot traverse.
    # Git inspects cwd even for remote-only commands such as ls-remote.
    kwargs.setdefault('cwd', BUILD)
    env = ['HOME=' + str(BUILD), 'PATH=' + (str(node / 'bin') + ':' if node else '') + '/usr/bin:/bin',
           'GIT_TERMINAL_PROMPT=0',
           'GIT_SSH_COMMAND=ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes '
           '-o UserKnownHostsFile=/var/lib/astrobuild/.ssh/known_hosts '
           '-o IdentitiesOnly=yes -i /var/lib/astrobuild/.ssh/deploy']
    return run(['runuser', '-u', 'astrobuild', '--', 'env', '-i', *env, *args], **kwargs)


def git(c, *args, capture=False):
    result = build_command(['git', '-c', 'core.hooksPath=/dev/null', *args],
                           stdout=subprocess.PIPE if capture else None, text=True, timeout=300)
    return result.stdout.strip() if capture else None


def download(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def install_node(major):
    arch = {'x86_64': 'x64', 'aarch64': 'arm64'}[os.uname().machine]
    releases = json.loads(download('https://nodejs.org/dist/index.json'))
    release = next(x for x in releases if x['version'].startswith(f'v{major}.') and x['lts'])
    version = release['version']
    destination = NODE / version
    if (destination / 'bin/node').is_file():
        return destination
    name = f'node-{version}-linux-{arch}.tar.xz'
    url = f'https://nodejs.org/dist/{version}/'
    sums = download(url + 'SHASUMS256.txt').decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
    print(f'Installiere Node {version} ({arch}) von nodejs.org; SHA-256 wird geprüft.')
    archive = download(url + name)
    if hashlib.sha256(archive).hexdigest() != expected:
        raise RuntimeError('Node-Prüfsumme stimmt nicht überein!')
    NODE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=NODE) as tmp:
        path = Path(tmp) / name
        path.write_bytes(archive)
        with tarfile.open(path) as tar:
            tar.extractall(Path(tmp) / 'unpack', filter='data')
        os.rename(Path(tmp) / 'unpack' / f'node-{version}-linux-{arch}', destination)
    return destination



def archive_build(project, archive):
    # npm can install hardlinked files. Emit regular files while keeping symlinks
    # intact; safe_extract deliberately rejects hardlink archive entries.
    build_command(['tar', '--hard-dereference', '-C', str(project), '-cf', '-',
                   'dist', 'node_modules', 'package.json', 'package-lock.json'],
                  stdout=archive, stderr=subprocess.DEVNULL, timeout=300)


def safe_extract(archive, target):
    """Untrusted build tar: no devices, hardlinks, traversal or symlink parents."""
    with (tarfile.open(fileobj=archive) if hasattr(archive, 'read') else tarfile.open(archive)) as tar:
        members = tar.getmembers()
        names = set()
        symlinks = set()
        for member in members:
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or member.name in names:
                raise ValueError('Unsicherer Archivpfad')
            names.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError('Nicht unterstützter Archivtyp')
            if member.issym():
                symlinks.add(p)
                resolved = posixpath.normpath(str(p.parent / member.linkname))
                if member.linkname.startswith('/') or resolved == '..' or resolved.startswith('../'):
                    raise ValueError('Symlink verlässt das Release')
        for member in members:
            if any(parent in symlinks for parent in PurePosixPath(member.name).parents):
                raise ValueError('Symlink als Archiv-Elternpfad')
        target.mkdir(mode=0o755)
        for member in members:
            dest = target / member.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                dest.mkdir(exist_ok=True)
            elif member.isfile():
                with tar.extractfile(member) as source, open(dest, 'xb') as sink:
                    shutil.copyfileobj(source, sink)
                os.chmod(dest, 0o755 if member.mode & 0o111 else 0o644)
        for member in members:
            if member.issym():
                os.symlink(member.linkname, target / member.name)
        for member in members:
            try:
                if not (target / member.name).resolve().is_relative_to(target.resolve()):
                    raise ValueError('Verketteter Symlink verlässt das Release')
            except RuntimeError:
                raise ValueError('Zyklischer Symlink im Release') from None


def link(path, target):
    temp = path.with_name(path.name + '.new')
    temp.unlink(missing_ok=True)
    temp.symlink_to(target)
    os.replace(temp, path)


def release_type(release):
    metadata = release / 'release.json'
    return json.loads(metadata.read_text()).get('kind', 'server') if metadata.exists() else 'server'


def regular_release_file(release, relative):
    # No symlinks, including internal links, anywhere in a profile path.
    if not isinstance(relative, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', relative):
        raise ValueError('Ungültiger Profilpfad.')
    parts = PurePosixPath(relative).parts
    if any(p in ('.', '..') for p in parts):
        raise ValueError('Ungültiger Profilpfad.')
    path = release
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlink im Profilpfad.')
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Profildatei fehlt oder ist nicht regulär.')
    return path


def limited_json(path):
    if path.stat().st_size > 32768:
        raise ValueError('Profil-JSON ist zu groß.')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Doppelter JSON-Schlüssel im Profil.')
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('Ungültiges Profil-JSON.') from None


def checked_profile(release, kind, profile_id=PROFILE_ID):
    expected = profile_spec(profile_id)
    package = FORMS_PACKAGE if profile_id == FORMS_ID else PACKAGE
    value = limited_json(regular_release_file(release, package + 'profile.json'))
    # Serialized comparison also rejects bool/float where integer 1/60 is required.
    if json.dumps(value, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('Laufzeitprofil: ausschließlich der gewählte bekannte Schema-1-Vertrag wird unterstützt.')
    if kind != 'server':
        raise ValueError('Formular-/Workshop-Profil benötigt Node-Serverausgabe.')
    extra = [
                     *(PACKAGE + 'src/server/' + name for name in
                       ('registration-config.mjs', 'registrations.mjs', 'registration-mail.mjs')),
                     PACKAGE + 'src/content/events.json'] if profile_id == PROFILE_ID else []
    for relative in [expected['config']['template'], expected['jobs'][0]['entry'],
                     *expected['tools'].values(), *extra]:
        regular_release_file(release, relative)
    template = limited_json(release / expected['config']['template'])
    if not isinstance(template, dict) or set(template) != set(profile_fields(expected)) or any(
            not isinstance(v, str) or len(v) > 8192 or any(ord(ch) < 32 for ch in v)
            for v in template.values()):
        raise ValueError('Profil-Konfigurationsvorlage: bekannte String-Felder erforderlich.')
    return value


def release_profile(release):
    path = release / 'release.json'
    metadata = json.loads(path.read_text()) if path.exists() else {}
    value = metadata.get('runtime_profile')
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('Ungültige Profilmetadaten im Release.')
    checked = checked_profile(release, metadata.get('kind'), value.get('id'))
    if value != checked:
        raise ValueError('Ungültige Profilmetadaten im Release.')
    return checked


def prepare_registration(c, release):
    profile = release_profile(release)
    if not profile:
        return
    import grp
    gid = grp.getgrnam('astrorun').gr_gid
    if RUNTIME.is_symlink():
        raise ValueError('Unsicheres Runtime-Verzeichnis.')
    RUNTIME.mkdir(mode=0o750, exist_ok=True)
    os.chown(RUNTIME, 0, gid)
    os.chmod(RUNTIME, 0o750)
    path = RUNTIME / profile['config']['filename']
    if path.is_symlink():
        raise ValueError('Unsichere Runtime-Konfiguration.')
    if not path.exists():
        value = initial_runtime_config(c, release, profile)
        save_json(path, value)
    if not path.is_file():
        raise ValueError('Runtime-Konfiguration ist keine reguläre Datei.')
    os.chown(path, 0, gid)
    os.chmod(path, 0o640)
    env = ETC / 'runtime.env'
    content = env.read_text(encoding='utf-8')
    # EnvironmentFile supports continuations: refuse ambiguous edits rather than
    # accidentally adding our assignment inside another variable's value.
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith(('#', ';')):
            continue
        quote, escaped = None, False
        for char in line:
            if escaped:
                escaped = False
            elif char == '\\' and quote != "'":
                escaped = True
            elif char == quote:
                quote = None
            elif char in ('"', "'") and quote is None:
                quote = char
        if escaped or quote:
            raise ValueError('runtime.env: Mehrzeilige Werte vor Profileinrichtung auflösen.')
    variable = profile['config']['environmentVariable']
    lines = [line for line in content.splitlines(keepends=True)
             if not re.match(r'^\s*' + re.escape(variable) + r'\s*=', line)]
    new = ''.join(lines).rstrip('\n') + '\n' + variable + '=' + str(path) + '\n'
    if new != content:
        save(env, new, stat.S_IMODE(env.stat().st_mode))


def job_state():
    if not (SYSTEMD / (JOB + '.service')).exists():
        return None
    def query(action):
        return subprocess.run(['systemctl', action, '--quiet', JOB + '.timer'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
    return (query('is-enabled'), query('is-active'))


def stop_registration():
    if (SYSTEMD / (JOB + '.service')).exists():
        # A failed stop aborts activation/cleanup. Never remove a running job's release.
        run(['systemctl', 'stop', JOB + '.timer'])
        run(['systemctl', 'stop', JOB + '.service'])


def configure_registration(c, release):
    profile = release_profile(release)
    service = SYSTEMD / (JOB + '.service')
    timer = SYSTEMD / (JOB + '.timer')
    if not profile:
        if service.exists():
            run(['systemctl', 'disable', '--now', JOB + '.timer'])
            service.unlink()
            timer.unlink(missing_ok=True)
            run(['systemctl', 'daemon-reload'])
        return
    node = json.loads((release / 'release.json').read_text())['node']
    if not re.fullmatch(re.escape(str(NODE)) + r'/v24\.\d+\.\d+', node):
        raise ValueError('Ungültige Release-Node-Version.')
    base = BASE / c['name']
    save(service, f'''[Unit]
Description=Astro Formular Wartung
After=network.target
[Service]
Type=oneshot
User=astrorun
Group=astrorun
WorkingDirectory={base}/current
ExecStart={node}/bin/node {profile['jobs'][0]['entry']}
EnvironmentFile=/etc/astrodeploy/runtime.env
ExecCondition=/usr/bin/python3 /usr/local/lib/astrodeploy/astrodeploy.py registration-enabled {profile['id']}
TimeoutStartSec=50s
TimeoutStopSec=20s
KillMode=control-group
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths={base}/data
InaccessiblePaths=/var/lib/astrobuild /var/lib/astrodeploy
StandardOutput=null
StandardError=null
''', 0o644)
    save(timer, '''[Unit]
Description=Astro Formular Wartungstimer
[Timer]
OnBootSec=60s
OnUnitInactiveSec=60s
Unit=astro-registration-maintenance.service
[Install]
WantedBy=timers.target
''', 0o644)
    run(['systemctl', 'daemon-reload'])


def start_registration(release, state=None):
    if release_profile(release):
        if state is None or state[0]:
            run(['systemctl', 'enable', JOB + '.timer'])
        else:
            run(['systemctl', 'disable', JOB + '.timer'])
        if state is None or state[1]:
            run(['systemctl', 'start', JOB + '.timer'])


def classify_release(release, mode):
    if (release / 'dist/server/entry.mjs').is_file():
        return 'server'
    if mode == 'auto' and (release / 'dist').is_dir() and any(p.is_file() for p in (release / 'dist').rglob('*')):
        return 'static'
    raise RuntimeError('Keine passende Buildausgabe in dist. Für SSR wird dist/server/entry.mjs benötigt.')


def proxy_location(c, forwarded_host=True):
    proto = '$astro_proto' if c['tls'] == 'proxy' else '$scheme'
    host = '        proxy_set_header X-Forwarded-Host $http_host;\n' if forwarded_host else ''
    return f'''    location / {{
        proxy_pass http://127.0.0.1:{c['port']};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
{host}        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto {proto};
    }}'''


def location_content(c, kind):
    if kind == 'server':
        return proxy_location(c) + '\n'
    return f'''root {BASE / c['name']}/current/dist;
index index.html;
error_page 404 /404.html;
location / {{
    try_files $uri $uri/ $uri.html =404;
}}
'''


def migrate_nginx(c):
    """Replace only our known location block, preserving Certbot's TLS settings."""
    site = NGINX_SITE
    text = site.read_text()
    include = '    include /etc/nginx/astrodeploy-location.conf;'
    if include in text:
        return
    candidates = [proxy_location(c), proxy_location(c, forwarded_host=False)]
    matches = [block for block in candidates if text.count(block) == 1]
    if len(matches) != 1:
        raise RuntimeError('Eigene Nginx-Konfiguration wurde verändert. Automatische Migration abgebrochen; '
                           'siehe docs/static-hosting.md.')
    old = matches[0]
    backup = STATE / 'nginx-before-0.3.conf'
    if not backup.exists():
        save(backup, text)
    save(NGINX_LOCATION, old + '\n', 0o644)
    save(site, text.replace(old, include), 0o644)
    try:
        run(['nginx', '-t'])
    except Exception:
        save(site, text, 0o644)
        raise


def configure_runtime(c, kind):
    migrate_nginx(c)
    original = NGINX_LOCATION.read_text() if NGINX_LOCATION.exists() else None
    desired = location_content(c, kind)
    profile = release_profile(BASE / c['name'] / 'current')
    privacy = '        access_log off; # astrodeploy registration privacy\n'
    # Keep existing ACL/auth directives inside the very same proxy location.
    if original and kind == 'server' and original != desired:
        clean = original.replace(privacy, '')
        if (clean.count('location / {') != 1 or clean.count('location ') != 1
                or clean.count('proxy_pass ') != 1
                or f'proxy_pass http://127.0.0.1:{c["port"]};' not in clean):
            raise RuntimeError('Unbekannte Nginx-Location; manuelle Prüfung erforderlich.')
        desired = clean
    elif original and kind == 'static' and original.replace(privacy, '') not in (
            location_content(c, 'static'), location_content(c, 'server'),
            proxy_location(c, forwarded_host=False) + '\n'):
        raise RuntimeError('Angepasste Nginx-Location vor static-Wechsel manuell prüfen.')
    if kind == 'server':
        # Overwrite client-supplied forwarded host at this proxy boundary. Keep
        # the public port; Astro must allow this host in security.allowedDomains.
        header = 'proxy_set_header X-Forwarded-Host $http_host;'
        existing = re.findall(r'proxy_set_header\s+X-Forwarded-Host\s+[^;]*;', desired, re.I)
        if existing and existing != [header]:
            raise RuntimeError('Eigener X-Forwarded-Host-Header: Nginx-Konfiguration manuell prüfen.')
        if not existing:
            desired = desired.replace('location / {\n', 'location / {\n        ' + header + '\n', 1)
    if profile:
        desired = desired.replace('location / {\n', 'location / {\n' + privacy, 1)
    save(NGINX_LOCATION, desired, 0o644)
    try:
        run(['nginx', '-t'])
    except BaseException:
        if original is not None:
            save(NGINX_LOCATION, original, 0o644)
        raise
    if kind == 'server':
        run(['systemctl', 'enable', 'astro-site'])
        run(['systemctl', 'restart', 'astro-site'])
    run(['systemctl', 'reload', 'nginx'])
    if kind == 'static':
        run(['systemctl', 'disable', '--now', 'astro-site'])


def healthy(c):
    kind = release_type(BASE / c['name'] / 'current')
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        conn = http.client.HTTPConnection('127.0.0.1', c['port'] if kind == 'server' else 80, timeout=2)
        try:
            conn.request('GET', c['health'], headers={'Host': c['host']})
            status = conn.getresponse().status
            if kind == 'static' and c['tls'] == 'letsencrypt' and status in (301, 302, 307, 308):
                conn.close()
                # Probe the same path locally over TLS; never follow arbitrary redirects.
                conn = http.client.HTTPConnection('127.0.0.1', 443, timeout=2)
                raw = socket.create_connection(('127.0.0.1', 443), timeout=2)
                conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=c['host'])
                conn.request('GET', c['health'], headers={'Host': c['host']})
                status = conn.getresponse().status
            if status == 200 and subprocess.run(
                    ['systemctl', 'is-active', '--quiet', 'astro-site' if kind == 'server' else 'nginx'], check=False).returncode == 0:
                return True
        except OSError:
            pass
        finally:
            conn.close()
        time.sleep(1)
    return False


def activate(c, release):
    base = BASE / c['name']
    current = base / 'current'
    old = current.resolve() if current.exists() else None
    profile = release_profile(release)
    if profile:
        prepare_registration(c, release)
    state = job_state()
    stop_registration()
    try:
        link(current, release)
        configure_registration(c, release)
        configure_runtime(c, release_type(release))
        if not healthy(c):
            raise RuntimeError('Healthcheck erwartet HTTP 200 am konfigurierten Pfad.')
        start_registration(release)
    except BaseException:
        stop_registration()
        if old:
            link(current, old)
            configure_registration(c, old)
            configure_runtime(c, release_type(old))
            if not healthy(c):
                raise RuntimeError('Auch die wiederhergestellte Version ist nicht erreichbar!') from None
            start_registration(old, state)
        else:
            current.unlink(missing_ok=True)
            # New profile units must not survive an unsuccessful first activation.
            if (SYSTEMD / (JOB + '.service')).exists():
                run(['systemctl', 'disable', '--now', JOB + '.timer'])
                for suffix in ('.timer', '.service'):
                    (SYSTEMD / (JOB + suffix)).unlink(missing_ok=True)
                run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'stop', 'astro-site'])
            save(NGINX_LOCATION, proxy_location(c) + '\n', 0o644)
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        raise
    if old and old != release:
        link(base / 'previous', old)


def cleanup(c):
    if (SYSTEMD / (JOB + '.service')).exists():
        result = subprocess.run(['systemctl', 'is-active', JOB + '.service'],
                                capture_output=True, text=True, check=False)
        if result.stdout.strip() not in ('inactive', 'failed'):
            return
    base = BASE / c['name']
    protected = {(base / name).resolve() for name in ('current', 'previous')}
    releases = sorted((base / 'releases').iterdir(), key=lambda p: p.name, reverse=True)
    for release in releases[c['keep']:]:
        if release.resolve() not in protected and not release.is_symlink():
            shutil.rmtree(release)


def deploy(c, force=False, automatic=False, node=None):
    if automatic and (STATE / 'paused').exists():
        print('Automatik pausiert.')
        return
    failure = STATE / 'failure.json'
    if automatic and failure.exists() and time.time() - json.loads(failure.read_text())['time'] < 600:
        print('Warte nach Fehler zehn Minuten bis zum nächsten Versuch.')
        return
    try:
        _deploy(c, force, node)
        failure.unlink(missing_ok=True)
    except Exception:
        save_json(failure, {'time': time.time(), 'status': 'fehlgeschlagen; astroctl logs prüfen'})
        raise


def _deploy(c, force, node):
    base = BASE / c['name']
    repo = BUILD / 'repository.git'
    if not repo.exists():
        git(c, 'init', '--bare', '--initial-branch=source', str(repo))
    git(c, '--git-dir', str(repo), 'fetch', '--no-tags', '--depth=1', c['repo'], '+refs/heads/' + c['branch'] + ':refs/heads/source')
    commit = git(c, '--git-dir', str(repo), 'rev-parse', 'refs/heads/source', capture=True)
    if not re.fullmatch(r'[0-9a-f]{40,64}', commit):
        raise RuntimeError('Git liefert keine gültige Commit-ID.')
    current = base / 'current'
    if node is None:
        node = Path(json.loads((current / 'release.json').read_text())['node']) if current.exists() else install_node(c['node_major'])
    fingerprint = hashlib.sha256(commit.encode() + str(node).encode() +
                                 (ETC / 'build.env').read_bytes() + json.dumps(c, sort_keys=True).encode()
                                 + VERSION.encode()).hexdigest()
    if current.exists() and not force and json.loads((current / 'release.json').read_text())['fingerprint'] == fingerprint:
        print('Keine Änderung; Website ist aktuell.')
        return
    work = BUILD / ('work-' + uuid.uuid4().hex)
    release = base / 'releases' / (time.strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:8])
    unit = 'astro-build-' + uuid.uuid4().hex
    try:
        build_command(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-checkout', '--no-hardlinks', str(repo), str(work)])
        build_command(['git', '-C', str(work), '-c', 'core.hooksPath=/dev/null', 'checkout', '--detach', commit])
        # Check project metadata as the unprivileged user too.
        project = work / c['subdir']
        mode = c.get('render_mode', 'server')
        preparation = [c['adapter_version'] if c.get('container_prepare') and mode == 'server' else '-', mode]
        try:
            build_command(['/usr/bin/python3', str(TOOLS / 'build.py'), 'check', str(work), c['subdir'], *preparation], timeout=60)
        except subprocess.CalledProcessError:
            raise RuntimeError('Projektprüfung fehlgeschlagen. Die Meldung darüber und docs/container-build.md beachten.') from None
        # systemd tracks all lifecycle children and kills leftovers after completion.
        print('Installiere npm-Abhängigkeiten und baue die Website (maximal 30 Minuten).\n'
              'Build-Ausgaben werden zum Schutz von Geheimnissen ausgeblendet.', flush=True)
        build_args = ['systemd-run', '--quiet', '--wait', '--collect', '--pipe', '--unit=' + unit,
             '-p', 'User=astrobuild', '-p', 'Group=astrobuild', '-p', 'KillMode=control-group',
             '-p', 'RuntimeMaxSec=1800', '-p', 'TimeoutStopSec=15', '-p', 'UMask=0077',
             '-p', 'NoNewPrivileges=yes', '-p', 'ProtectSystem=strict', '-p', 'ProtectHome=yes',
             '-p', 'PrivateTmp=yes', '-p', 'ReadWritePaths=' + str(BUILD),
             '-p', 'EnvironmentFile=' + str(ETC / 'build.env'),
             '-p', 'Environment=HOME=' + str(BUILD),
             '-p', 'Environment=PATH=' + str(node / 'bin') + ':/usr/bin:/bin',
             '-p', 'WorkingDirectory=' + str(project),
             '/usr/bin/python3', str(TOOLS / 'build.py'), 'build', *preparation]
        try:
            run(build_args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=1900)
        except subprocess.CalledProcessError as error:
            messages = {
                'dependencies': 'npm ci fehlgeschlagen. Lockdatei, Node-Anforderungen und Registry-Zugriff prüfen.',
                'adapter': 'Node-Adapter konnte nicht installiert werden. Adapter-Version und Astro-Peer-Abhängigkeiten prüfen.',
                'config': 'Automatische Server-Konfiguration nicht möglich. Siehe docs/container-build.md.',
                'build': 'Astro-Build fehlgeschlagen. Projekt und Build-Variablen prüfen.',
                'entry': 'Passende Buildausgabe in dist fehlt. Für SSR wird dist/server/entry.mjs benötigt; Ausgabeeinstellungen prüfen.',
            }
            code = (error.stdout or '').strip().removeprefix('ASTRODEPLOY_ERROR:')
            raise RuntimeError(messages.get(code, 'Container-Build fehlgeschlagen. systemd-Status und docs/troubleshooting.md prüfen.')) from None
        with tempfile.TemporaryFile() as archive:
            archive_build(project, archive)
            archive.seek(0)
            safe_extract(archive, release)
        kind = classify_release(release, mode)
        profile = checked_profile(release, kind, c['runtime_profile']) if c.get('runtime_profile') else None
        if kind == 'static':
            if (release / 'node_modules').is_symlink():
                (release / 'node_modules').unlink()
            else:
                shutil.rmtree(release / 'node_modules')
        save_json(release / 'release.json', {'commit': commit, 'node': str(node), 'fingerprint': fingerprint,
                                            'tools': VERSION, 'kind': kind,
                                            'runtime_profile': profile,
                                            'container_prepare': c.get('container_prepare', False) and mode == 'server',
                                            'adapter_version': c.get('adapter_version')})
        # Runtime needs read access to metadata, but never write access.
        os.chmod(release / 'release.json', 0o644)
        if kind == 'server':
            (release / 'start').write_text('#!/bin/sh\nexec ' + str(node / 'bin/node') + ' ./dist/server/entry.mjs\n')
            os.chmod(release / 'start', 0o755)
        activate(c, release)
        cleanup(c)
        print('Deployment erfolgreich: ' + commit[:12] + ' | ' + ('statisch über Nginx' if kind == 'static' else 'SSR über Node'))
    finally:
        subprocess.run(['systemctl', 'stop', unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        # Never recursively traverse build-owned paths as root.
        build_command(['rm', '-rf', '--', str(work)], timeout=60)
        protected = {(base / name).resolve() for name in ('current', 'previous')}
        if release.exists() and release.resolve() not in protected:
            shutil.rmtree(release)


def units(c):
    base = BASE / c['name']
    save('/etc/systemd/system/astro-site.service', f'''[Unit]
Description=Astro Website
After=network.target
[Service]
User=astrorun
Group=astrorun
WorkingDirectory={base}/current
ExecStart={base}/current/start
EnvironmentFile=/etc/astrodeploy/runtime.env
Environment=HOST=127.0.0.1 PORT={c['port']} NODE_ENV=production
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths={base}/data
InaccessiblePaths=/var/lib/astrobuild /var/lib/astrodeploy
[Install]
WantedBy=multi-user.target
''', 0o644)
    save('/etc/systemd/system/astro-deploy.service', '''[Unit]
Description=GitHub Astro Deployment
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/astroctl deploy --automatic
TimeoutStartSec=45min
UMask=0077
''', 0o644)
    save('/etc/systemd/system/astro-deploy.timer', f'''[Unit]
Description=GitHub regelmäßig prüfen
[Timer]
OnBootSec=2min
OnUnitInactiveSec={c['interval']}s
RandomizedDelaySec=5s
[Install]
WantedBy=timers.target
''', 0o644)
    extra = ''
    if c['tls'] == 'proxy':
        network = str(ipaddress.ip_network(c['proxy'], strict=False))
        extra = f'''geo $astro_trusted {{ default 0; {network} 1; }}
map "$astro_trusted:$http_x_forwarded_proto" $astro_proto {{ default $scheme; "1:https" https; "1:http" http; }}
'''
    save(NGINX_LOCATION, proxy_location(c) + '\n', 0o644)
    save('/etc/nginx/sites-available/astrodeploy', extra + f'''server {{
    listen 80;
    server_name {c['host']};
    include /etc/nginx/astrodeploy-location.conf;
}}
''', 0o644)
    link(Path('/etc/nginx/sites-enabled/astrodeploy'), Path('/etc/nginx/sites-available/astrodeploy'))
    run(['nginx', '-t'])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', 'nginx'])
    run(['systemctl', 'restart', 'nginx'])


def setup():
    osinfo = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if osinfo.get('ID', '').strip('"') != 'debian' or osinfo.get('VERSION_ID', '').strip('"') != '13':
        raise RuntimeError('Dieses Setup benötigt Debian 13 im Zielcontainer.')
    if not Path('/run/systemd/system').exists() or os.uname().machine not in ('x86_64', 'aarch64'):
        raise RuntimeError('systemd und amd64/arm64 werden benötigt.')
    ips = container_ips()
    print('\nAstroDeploy ' + VERSION + ' – Einrichtung direkt im Debian-Container')
    print('Erkannte Container-IPv4: ' + (', '.join(ips) if ips else 'keine; Domain/IPv4 bitte selbst eingeben'))
    if shutil.disk_usage('/').free < 5 * 1024**3:
        raise RuntimeError('Bitte mindestens 5 GiB freien Speicher bereitstellen.')
    if (ETC / 'config.json').exists():
        c = config()
        print('Vorhandene Installation gefunden. Konfiguration und Secrets bleiben erhalten.')
        if not yes('Fehlende Einrichtung fortsetzen und erstes Deployment erneut versuchen?'):
            return
        if 'render_mode' not in c:
            print('Bisher wurde SSR erzwungen. auto behält die Original-Konfiguration bei und erkennt statische Ausgabe.')
            c['render_mode'] = ask('Betriebsmodus: auto (empfohlen) oder server (SSR erzwingen)', 'auto', lambda v: v in ('auto', 'server'))
            save_json(ETC / 'config.json', c)
    else:
        for user in ('astrobuild', 'astrorun'):
            import pwd
            try:
                pwd.getpwnam(user)
            except KeyError:
                continue
            raise RuntimeError('Benutzer existiert bereits: ' + user)
        for path in (ETC, STATE, BUILD, BASE, TOOLS, NODE.parent,
                     Path('/etc/nginx/sites-available/astrodeploy'), Path('/usr/local/bin/astroctl'),
                     Path('/etc/systemd/system/astro-site.service'),
                     Path('/etc/systemd/system/astro-deploy.service'),
                     Path('/etc/systemd/system/astro-deploy.timer')):
            if path.exists():
                raise RuntimeError('Vorhandener Pfad wird nicht überschrieben: ' + str(path))
        if Path('/etc/nginx').exists():
            raise RuntimeError('Nginx ist bereits konfiguriert. Bitte einen frischen dedizierten Container verwenden.')
        for port in (80, 443):
            with socket.socket() as sock:
                sock.bind(('0.0.0.0', port))
        print('\nAstroDeploy – eine Astro-SSR-Website auf Debian 13 einrichten.\n'
              'Benötigt: Astro-Repository mit package-lock.json. Der Build läuft hier im Container.\n'
              'Es werden Pakete, zwei Benutzer, Nginx und systemd-Dienste eingerichtet.\n')
        c = {'name': ask('Projektname (Kleinbuchstaben)', 'website', lambda v: bool(re.fullmatch(r'[a-z][a-z0-9-]{0,30}', v))),
             'repo': repository_prompt(),
             'branch': ask('Branch', 'main', lambda v: bool(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', v)) and '..' not in v),
             'subdir': ask('Projekt-Unterordner (. = Repository-Wurzel)', '.', valid_subdir),
             'host': ask('Domain oder Container-IPv4 (ohne http://)', ips[0] if ips else '', valid_host),
             'port': int(ask('Interner Node-Port', '4321', lambda v: v.isdigit() and 1024 <= int(v) <= 65535)),
             'automatic': yes('GitHub automatisch prüfen?', True),
             'interval': int(ask('Prüfintervall in Sekunden', '60', lambda v: v.isdigit() and 30 <= int(v) <= 86400)),
             'health': ask('Healthcheck-Pfad (muss ohne Anmeldung HTTP 200 liefern)', '/', lambda v: bool(re.fullmatch(r'/[A-Za-z0-9_./~%-]*', v))),
             'tls': ask('HTTPS: letsencrypt, proxy oder http (HTTP nur im vertrauenswürdigen Netz)', 'http', lambda v: v in ('http', 'proxy', 'letsencrypt')),
             'node_major': 24, 'keep': 3, 'proxy': '', 'email': ''}
        selection = ask('Optionales Laufzeitprofil: keines, forms (allgemeine Formulare), workshop-registration',
                        'keines', lambda v: v in ('keines', FORMS_ID, PROFILE_ID))
        if selection != 'keines':
            if RUNTIME.exists() or RUNTIME.is_symlink() or any(
                    (SYSTEMD / (JOB + suffix)).exists() for suffix in ('.service', '.timer')):
                raise RuntimeError('Vorhandene Formular-Pfade werden nicht übernommen; frischen Container verwenden.')
            c['runtime_profile'] = selection
            c['health'] = ask('Formular-Healthcheck-Pfad', '/health/',
                              lambda v: bool(re.fullmatch(r'/[A-Za-z0-9_./~%-]*', v)))
        c['render_mode'] = ask('Betriebsmodus: auto (Original-Konfiguration) oder server (SSR erzwingen)',
                               'auto', lambda v: v in ('auto', 'server'))
        print('\nauto behält die Rendering-Einstellungen des Projekts bei. Statische Websites liefert Nginx direkt aus.\n'
              'Im Modus server kann die folgende Vorbereitung SSR erzwingen; für bestehende statische Projekte auto wählen.')
        print('\nSSR-Vorbereitung: fehlenden Node-Adapter hier installieren und eine zusätzliche\n'
              'Server-Konfiguration verwenden. GitHub bleibt unverändert; kein Schreibzugriff nötig.\n'
              'Unterstützt "astro build", auch nach "npm run check &&", und objektbasierte Astro-Konfigurationen.')
        c['container_prepare'] = c['render_mode'] == 'server' and yes('SSR automatisch für diesen Container vorbereiten?', True)
        if c['container_prepare']:
            c['adapter_version'] = ask('Feste Node-Adapter-Version für Projekte ohne Adapter', adapter_version(),
                                       lambda v: bool(re.fullmatch(r'\d+\.\d+\.\d+', v)))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', c['port']))
        if c['tls'] == 'proxy':
            c['proxy'] = ask('IP/CIDR des vertrauenswürdigen TLS-Proxys')
            ipaddress.ip_network(c['proxy'], strict=False)
        if c['tls'] == 'letsencrypt':
            c['email'] = ask('E-Mail für Let’s Encrypt', validate=lambda v: bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', v)))
        c['security_updates'] = yes('Automatische Debian-Sicherheitsupdates ohne automatischen Neustart?')
        c['system_update'] = yes('Vor Installation Debian-Paketupdates anzeigen und optional installieren?')
        validate(c)
        print('\nZusammenfassung:\n' + json.dumps(c, indent=2, ensure_ascii=False))
        print(f"Website: {BASE / c['name']} | Node 24 LTS | HTTP-Port 80 | drei Releases aufbewahren")
        if not yes('Diese Einrichtung jetzt durchführen?'):
            return
        ETC.mkdir(mode=0o700)
        save_json(ETC / 'config.json', c)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    run(['apt-get', 'update'])
    if c['system_update']:
        system_update()
    run(['apt-get', '-o', 'DPkg::Lock::Timeout=120', 'install', '-y', 'nginx', 'git', 'ca-certificates',
         'openssh-client', 'xz-utils', 'build-essential', 'python3', 'curl'])
    import pwd
    for user, home in (('astrobuild', BUILD), ('astrorun', Path('/nonexistent'))):
        try:
            pwd.getpwnam(user)
        except KeyError:
            run(['useradd', '--system', '--user-group', '--home-dir', str(home), '--shell', '/usr/sbin/nologin', user])
    BUILD.mkdir(mode=0o700, parents=True, exist_ok=True)
    run(['chown', 'astrobuild:astrobuild', str(BUILD)])
    base = BASE / c['name']
    (base / 'releases').mkdir(mode=0o755, parents=True, exist_ok=True)
    (base / 'data').mkdir(mode=0o700, exist_ok=True)
    run(['chown', 'astrorun:astrorun', str(base / 'data')])
    TOOLS.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent
    for name in ('astrodeploy.py', 'build.py'):
        if source != TOOLS:
            shutil.copyfile(source / name, TOOLS / name)
        os.chmod(TOOLS / name, 0o644)
    if source != TOOLS:
        shutil.copyfile(source.parent / 'bin/astroctl', '/usr/local/bin/astroctl')
    os.chmod('/usr/local/bin/astroctl', 0o755)
    for name in ('build.env', 'runtime.env'):
        path = ETC / name
        if not path.exists():
            save(path, '# KEY=value; systemd EnvironmentFile-Syntax, kein Shellcode.\n')
        print(f'{path}: optionale Umgebungsvariablen (PUBLIC_ ist öffentlich!).')
        if yes('Jetzt mit nano bearbeiten?'):
            run(['apt-get', 'install', '-y', 'nano'])
            run(['nano', str(path)])
    build_command(['mkdir', '-p', str(BUILD / '.ssh')])
    build_command(['chmod', '700', str(BUILD / '.ssh')])
    # Writing host keys as the owning user avoids following a build-controlled link as root.
    build_command(['tee', str(BUILD / '.ssh/known_hosts')], input=GH_KEY, text=True, stdout=subprocess.DEVNULL)
    if c['repo'].startswith('git@'):
        if not (BUILD / '.ssh/deploy').exists():
            build_command(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(BUILD / '.ssh/deploy')])
        print('\nIn GitHub: Repository → Settings → Deploy keys → Add deploy key.\n'
              'Diesen öffentlichen Schlüssel eintragen; Schreibzugriff NICHT aktivieren:')
        build_command(['cat', str(BUILD / '.ssh/deploy.pub')])
        input('Nach dem Speichern bei GitHub Enter drücken … ')
    try:
        git(c, 'ls-remote', '--exit-code', c['repo'], 'refs/heads/' + c['branch'], capture=True)
    except subprocess.CalledProcessError:
        raise RuntimeError('GitHub-Zugriff fehlgeschlagen. URL, Branch und Deploy-Key prüfen. '
                           'Private Repositories benötigen die SSH-URL git@github.com:NAME/REPO.git; '
                           'Details: docs/github.md. Konfiguration bleibt für Fortsetzung erhalten.') from None
    if c['security_updates']:
        run(['apt-get', 'install', '-y', 'unattended-upgrades'])
        save('/etc/apt/apt.conf.d/52astrodeploy', '''#clear Unattended-Upgrade::Origins-Pattern;
Unattended-Upgrade::Origins-Pattern { "origin=Debian,codename=trixie-security,label=Debian-Security"; };
Unattended-Upgrade::Automatic-Reboot "false";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
''', 0o644)
    if not (STATE / 'configured').exists():
        units(c)
        save(STATE / 'configured', 'yes\n')
    deploy(c)
    if c['tls'] == 'letsencrypt':
        print('DNS muss auf diesen Server zeigen; Ports 80/443 müssen erreichbar sein.\n'
              'Mit Fortsetzen akzeptierst du die Let’s-Encrypt-Nutzungsbedingungen.')
        if not yes('Zertifikat jetzt anfordern?'):
            raise RuntimeError('HTTPS noch offen. Setup erneut starten, um fortzusetzen.')
        run(['apt-get', 'install', '-y', 'certbot', 'python3-certbot-nginx'])
        run(['certbot', '--nginx', '--non-interactive', '--agree-tos', '--redirect',
             '--email', c['email'], '-d', c['host']])
        run(['systemctl', 'enable', '--now', 'certbot.timer'])
    if c['automatic']:
        run(['systemctl', 'enable', '--now', 'astro-deploy.timer'])
    print(f"\nFertig: {'http' if c['tls'] == 'http' else 'https'}://{c['host']}\n"
          'Verwaltung: astroctl status | astroctl logs | astroctl doctor')
    print('Änderungen in GitHub werden nach erfolgreichem Build automatisch veröffentlicht.'
          if c['automatic'] else 'Manuelles Deployment: astroctl deploy')
    if c.get('runtime_profile'):
        registration_guidance(c)


def system_update():
    print('Debian-Updates können Dienste neu starten und die Website kurz unterbrechen.')
    run(['apt-get', '-s', '--no-remove', 'upgrade'])
    if yes('Die angezeigten Paketupdates installieren?'):
        run(['apt-get', '-o', 'DPkg::Lock::Timeout=120', '--no-remove', 'upgrade'])


def registration_guidance(c, profile=None):
    profile = profile or profile_spec(c.get('runtime_profile', PROFILE_ID))
    prefix = profile_prefix(profile)
    print('Formularprofil ' + profile['id'] + ': Freigabe über private Konfiguration prüfen.\n'
          'Private Einstellungen: nano ' + str(RUNTIME / profile['config']['filename']) + '\n'
          'Offen: E-Mail-Domains, Datenschutzhinweis, Aufbewahrung, Admin-Zugang und SMTP/TLS mit IT abstimmen.\n'
          + prefix + '_ORIGIN mit URL und Astro security.allowedDomains abgleichen; Domain/Port prüfen.\n'
          'HTTPS für Anmeldung und Verwaltungszugang erforderlich. Zertifikatsprüfung nicht abschalten.\n'
          'Admin-Werkzeug: astroctl forms-admin [Argumente laut Website-Dokumentation]\n'
          'SQLite-Sicherung: astroctl forms-backup\n'
          'Nach Konfigurationsänderungen: systemctl restart astro-site')
    if c['tls'] == 'http':
        print('Betriebsfreigabe offen: aktuell HTTP; keine echten Anmeldungen freischalten.')


def registration_diagnostics(c):
    print('Gewähltes Runtime-Profil: ' + (c.get('runtime_profile') or 'keines'))
    current = BASE / c['name'] / 'current'
    active = release_profile(current) if current.exists() else None
    print('Aktives Formularprofil: ' + (active['id'] + ' (Schema 1)' if active else 'keines'))
    if not c.get('runtime_profile') and not active:
        return
    for suffix in ('.service', '.timer'):
        result = subprocess.run(['systemctl', 'is-active', JOB + suffix], capture_output=True,
                                text=True, check=False)
        print(JOB + suffix + ': ' + ('aktiv' if result.returncode == 0 else 'inaktiv'))
    env = (ETC / 'runtime.env').read_text()
    if '/var/lib/makerlab' in env:
        raise RuntimeError('Veralteter Runtime-Verweis auf /var/lib/makerlab; runtime.env prüfen.')
    profile = active or profile_spec(c['runtime_profile'])
    path = RUNTIME / profile['config']['filename']
    readable = subprocess.run(['runuser', '-u', 'astrorun', '--', 'test', '-r', str(path)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if readable.returncode:
        raise RuntimeError('Profil-Konfiguration für astrorun nicht lesbar; Elternverzeichnis 0750 und Datei 0640 prüfen.')
    import grp
    import pwd
    gid = grp.getgrnam('astrorun').gr_gid
    for target, mode in ((RUNTIME, 0o750), (path, 0o640)):
        info = target.lstat()
        if target.is_symlink() or info.st_uid != 0 or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
            raise RuntimeError('Unsichere Profil-Konfigurationsrechte: ' + str(target))
    data = BASE / c['name'] / 'data'
    info = data.lstat()
    if data.is_symlink() or info.st_uid != pwd.getpwnam('astrorun').pw_uid or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('Profil-Datenverzeichnis muss astrorun gehören und Modus 0700 haben.')
    value = limited_json(path)
    dbfield, filename = next(iter(profile['config']['dataFileFields'].items()))
    if value.get(dbfield) != str(data / filename):
        raise RuntimeError(dbfield + ' verweist nicht auf das Projekt-Datenverzeichnis; Altpfad prüfen.')
    variable = profile['config']['environmentVariable']
    expected = variable + '=' + str(path)
    assignments = [line.strip() for line in env.splitlines() if re.match(r'^\s*' + re.escape(variable) + r'\s*=', line)]
    if assignments != [expected]:
        raise RuntimeError(variable + ' in runtime.env fehlt oder ist widersprüchlich.')
    print('Profil-Konfiguration lesbar; Datenrechte geprüft. Keine privaten Werte ausgegeben.')
    registration_guidance(c, profile)


def registration_tool(c, args):
    current = BASE / c['name'] / 'current'
    profile = release_profile(current)
    if not profile:
        raise RuntimeError('Kein aktives Formularprofil.')
    registration_diagnostics(c)
    if args[0] in ('registration-admin', 'forms-admin'):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError('Admin-Werkzeug nur interaktiv im Terminal ausführen.')
        node = json.loads((current / 'release.json').read_text())['node']
        # No secrets in argv, no inherited root environment, no output capture.
        run(['runuser', '-u', 'astrorun', '--', 'env', '-i', 'PATH=/usr/bin:/bin',
             profile['config']['environmentVariable'] + '=' + str(RUNTIME / profile['config']['filename']),
             node + '/bin/node', str(current / profile['tools']['admin']), *args[1:]], cwd=current)
    else:
        if len(args) != 1:
            raise ValueError('registration-backup akzeptiert keine Argumente.')
        data = BASE / c['name'] / 'data'
        dbfile = next(iter(profile['config']['dataFileFields'].values()))
        destination = data / (Path(dbfile).stem + '-backup-' + uuid.uuid4().hex + '.sqlite')
        # Trusted installer code, executed without root privileges. SQLite backup
        # includes committed WAL contents; never copy just the main DB file.
        code = '''import os, sqlite3, sys
os.umask(0o077)
source = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
partial = sys.argv[2] + '.partial'
fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.close(fd)
try:
    with sqlite3.connect(partial) as target:
        source.backup(target)
    target.close()
    os.replace(partial, sys.argv[2])
finally:
    source.close()
'''
        try:
            run(['runuser', '-u', 'astrorun', '--', '/usr/bin/python3', '-c', code,
                 str(data / dbfile), str(destination)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError('SQLite-Sicherung fehlgeschlagen; Datenbank und Datenrechte prüfen.') from None
        print('Konsistente private Sicherung: ' + str(destination))


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise RuntimeError('Bitte als root im Debian-13-Container ausführen.')
    os.umask(0o022)
    args = sys.argv[1:]
    command = args[0] if args else 'help'
    if command == 'help':
        print('astroctl: status | doctor | deploy | rebuild | pause | resume | rollback | logs\n'
              '          forms-admin | forms-backup (auch registration-admin / registration-backup)\n'
              '          update --check | --system | --node | --tools')
        return
    with lock():
        if command == 'setup':
            setup()
            return
        c = config()
        if command in ('deploy', 'rebuild'):
            deploy(c, force=command == 'rebuild', automatic='--automatic' in args)
        elif command == 'pause':
            save(STATE / 'paused', 'yes\n')
            print('Automatik pausiert; manuelles Deployment bleibt möglich.')
        elif command == 'resume':
            (STATE / 'paused').unlink(missing_ok=True)
            run(['systemctl', 'enable', '--now', 'astro-deploy.timer'])
            print('Automatik aktiv. Der nächste Lauf kann einen manuell zurückgerollten Stand ersetzen.')
        elif command == 'rollback':
            previous = BASE / c['name'] / 'previous'
            if not previous.exists():
                raise RuntimeError('Kein vorheriges Release vorhanden.')
            save(STATE / 'paused', 'yes\n')
            activate(c, previous.resolve())
            print('Vorherige Version aktiv. Automatik bleibt pausiert bis astroctl resume.')
        elif command == 'logs':
            print('Build-Ausgaben werden zum Schutz von Secrets nicht gespeichert. Anwendung kann selbst Secrets loggen.')
            run(['journalctl', '-u', 'astro-site', '-u', 'astro-deploy', '-n', '100', '--no-pager'])
        elif command in ('status', 'doctor'):
            print('AstroDeploy ' + VERSION + (' | PAUSIERT' if (STATE / 'paused').exists() else ' | nicht pausiert'))
            for name in ('astro-site', 'nginx', 'astro-deploy.timer'):
                subprocess.run(['systemctl', '--no-pager', 'status', name], check=False)
            current = BASE / c['name'] / 'current'
            print((current / 'release.json').read_text() if current.exists() else 'Noch kein aktives Release.')
            if (STATE / 'failure.json').exists():
                print((STATE / 'failure.json').read_text())
            registration_diagnostics(c)
            if command == 'doctor':
                run(['nginx', '-t'])
                git(c, 'ls-remote', '--exit-code', c['repo'], 'refs/heads/' + c['branch'], capture=True)
                print('Freier Speicher (GiB):', round(shutil.disk_usage(BASE).free / 1024**3, 1))
                for path in (ETC, STATE, TOOLS, BASE / c['name'] / 'releases'):
                    info = path.stat()
                    if info.st_uid != 0 or info.st_mode & 0o022:
                        raise RuntimeError('Unsichere Rechte: ' + str(path))
                if not healthy(c):
                    raise RuntimeError('Website liefert lokal kein HTTP 200.')
                print('Grundprüfungen erfolgreich.')
        elif command in ('registration-admin', 'registration-backup', 'forms-admin', 'forms-backup'):
            registration_tool(c, args)
        elif command == 'update' and len(args) == 2:
            if args[1] == '--system':
                run(['apt-get', 'update'])
                system_update()
            elif args[1] == '--node':
                deploy(c, force=True, node=install_node(c['node_major']))
            elif args[1] == '--check':
                run(['apt-get', 'update'])
                run(['apt-get', '-s', '--no-remove', 'upgrade'])
                releases = json.loads(download('https://nodejs.org/dist/index.json'))
                print('Verfügbare Node-LTS-Version:', next(x['version'] for x in releases if x['version'].startswith('v24.') and x['lts']))
            elif args[1] == '--tools':
                print('Installierte Werkzeugversion: ' + VERSION + '\nKein automatisches Selbstupdate. '
                      'Geprüftes Repository sichern und neue Werkzeugdateien nach Codeprüfung manuell installieren; siehe docs/updates.md.')
            else:
                raise ValueError('Unbekannte Updateoption')
        else:
            raise ValueError('Unbekannter Befehl. Hilfe: astroctl help')


if __name__ == '__main__':
    if sys.argv[1:2] == ['registration-enabled']:
        # Runs as astrorun inside the job sandbox. Do not expose parsed values.
        try:
            profile = profile_spec(sys.argv[2] if len(sys.argv) == 3 else PROFILE_ID)
            prefix = profile_prefix(profile)
            value = limited_json(Path(os.environ[profile['config']['environmentVariable']]))
            enabled = value.get(prefix + '_ENABLED') == 'true'
            if enabled and not value.get(prefix + '_ORIGIN', '').startswith('https://'):
                sys.exit(2)
            sys.exit(0 if enabled else 1)
        except (KeyError, ValueError, OSError):
            sys.exit(2)
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # Never include command output or env contents in persistent error state.
        print(f'Abbruch: {error}\nHinweise: astroctl status / docs/troubleshooting.md', file=sys.stderr)
        sys.exit(1)
