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
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

VERSION = '0.2.1'
ETC = Path('/etc/astrodeploy')
STATE = Path('/var/lib/astrodeploy')
BUILD = Path('/var/lib/astrobuild')
BASE = Path('/srv/astro')
TOOLS = Path('/usr/local/lib/astrodeploy')
NODE = Path('/opt/astrodeploy/node')
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


def healthy(c):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        conn = http.client.HTTPConnection('127.0.0.1', c['port'], timeout=2)
        try:
            conn.request('GET', c['health'], headers={'Host': c['host']})
            if conn.getresponse().status == 200 and subprocess.run(
                    ['systemctl', 'is-active', '--quiet', 'astro-site'], check=False).returncode == 0:
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
    link(current, release)
    try:
        run(['systemctl', 'restart', 'astro-site'])
        if not healthy(c):
            raise RuntimeError('Healthcheck erwartet HTTP 200 am konfigurierten Pfad.')
    except BaseException:
        if old:
            link(current, old)
            run(['systemctl', 'restart', 'astro-site'])
            if not healthy(c):
                raise RuntimeError('Auch die wiederhergestellte Version ist nicht erreichbar!') from None
        else:
            current.unlink(missing_ok=True)
            run(['systemctl', 'stop', 'astro-site'])
        raise
    if old and old != release:
        link(base / 'previous', old)


def cleanup(c):
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
        preparation = [c['adapter_version']] if c.get('container_prepare') else []
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
                'entry': 'Build erzeugt kein dist/server/entry.mjs. Prerender- und Ausgabeeinstellungen prüfen.',
            }
            code = (error.stdout or '').strip().removeprefix('ASTRODEPLOY_ERROR:')
            raise RuntimeError(messages.get(code, 'Container-Build fehlgeschlagen. systemd-Status und docs/troubleshooting.md prüfen.')) from None
        with tempfile.TemporaryFile() as archive:
            build_command(['tar', '-C', str(project), '-cf', '-', 'dist', 'node_modules', 'package.json', 'package-lock.json'],
                          stdout=archive, stderr=subprocess.DEVNULL, timeout=300)
            archive.seek(0)
            safe_extract(archive, release)
        if not (release / 'dist/server/entry.mjs').is_file():
            raise RuntimeError('dist/server/entry.mjs fehlt. Astro-Node-Adapter mit standalone konfigurieren.')
        save_json(release / 'release.json', {'commit': commit, 'node': str(node), 'fingerprint': fingerprint,
                                            'tools': VERSION, 'container_prepare': c.get('container_prepare', False),
                                            'adapter_version': c.get('adapter_version')})
        # Runtime needs read access to metadata, but never write access.
        os.chmod(release / 'release.json', 0o644)
        (release / 'start').write_text('#!/bin/sh\nexec ' + str(node / 'bin/node') + ' ./dist/server/entry.mjs\n')
        os.chmod(release / 'start', 0o755)
        activate(c, release)
        cleanup(c)
        print('Deployment erfolgreich: ' + commit[:12])
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
    proto = '$scheme'
    extra = ''
    if c['tls'] == 'proxy':
        network = str(ipaddress.ip_network(c['proxy'], strict=False))
        extra = f'''geo $astro_trusted {{ default 0; {network} 1; }}
map "$astro_trusted:$http_x_forwarded_proto" $astro_proto {{ default $scheme; "1:https" https; "1:http" http; }}
'''
        proto = '$astro_proto'
    save('/etc/nginx/sites-available/astrodeploy', extra + f'''server {{
    listen 80;
    server_name {c['host']};
    location / {{
        proxy_pass http://127.0.0.1:{c['port']};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto {proto};
    }}
}}
''', 0o644)
    link(Path('/etc/nginx/sites-enabled/astrodeploy'), Path('/etc/nginx/sites-available/astrodeploy'))
    run(['nginx', '-t'])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', 'astro-site', 'nginx'])
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
        print('\nContainer-Modus: fehlenden Node-Adapter hier installieren und eine zusätzliche\n'
              'Server-Konfiguration verwenden. GitHub bleibt unverändert; kein Schreibzugriff nötig.\n'
              'Unterstützt "astro build", auch nach "npm run check &&", und objektbasierte Astro-Konfigurationen.')
        c['container_prepare'] = yes('Astro automatisch für diesen Container vorbereiten?', True)
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


def system_update():
    print('Debian-Updates können Dienste neu starten und die Website kurz unterbrechen.')
    run(['apt-get', '-s', '--no-remove', 'upgrade'])
    if yes('Die angezeigten Paketupdates installieren?'):
        run(['apt-get', '-o', 'DPkg::Lock::Timeout=120', '--no-remove', 'upgrade'])


def main():
    if os.name != 'posix' or os.geteuid() != 0:
        raise RuntimeError('Bitte als root im Debian-13-Container ausführen.')
    os.umask(0o022)
    args = sys.argv[1:]
    command = args[0] if args else 'help'
    if command == 'help':
        print('astroctl: status | doctor | deploy | rebuild | pause | resume | rollback | logs\n'
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
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # Never include command output or env contents in persistent error state.
        print(f'Abbruch: {error}\nHinweise: astroctl status / docs/troubleshooting.md', file=sys.stderr)
        sys.exit(1)
