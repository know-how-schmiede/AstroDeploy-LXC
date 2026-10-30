<p align="center"><img src="assets/logo.png" alt="AstroDeploy-LXC" width="112"></p>

# AstroDeploy-LXC

Astro-Websites aus GitHub automatisch im Debian-13-Container auf Proxmox deployen.
Das deutschsprachige Setup richtet Node.js, Nginx und systemd ein. Ein Timer prüft
den gewählten Branch standardmäßig alle 60 Sekunden.

![AstroDeploy-LXC](assets/banner.png)

**Erste Implementierung; noch nicht im Debian-LXC abgenommen.** Syntax und lokale
Unit-Tests wurden geprüft. Die vollständige Installation muss noch im Testcontainer
geprüft werden. Der genaue [Teststand](docs/testing.md) ist dokumentiert.

## 1. Container vorbereiten

Frischen, dedizierten Debian-13-LXC mit systemd verwenden (amd64 oder arm64).
Empfehlung: 2 CPU-Kerne, 4 GB RAM, 1 GB Swap und 20–30 GB Speicher. Feste IP oder
DHCP-Reservierung und Internetzugriff einrichten. Ein unprivilegierter LXC ist
empfohlen. Docker und zusätzliche Container-Berechtigungen sind nicht erforderlich.

In Proxmox den **Container auswählen und dessen Konsole öffnen**. Dort als root
anmelden. Diese Befehle gehören nicht in die Konsole des Proxmox-Hosts:

```bash
apt-get update
apt-get install -y git ca-certificates python3
```

## 2. Website vorbereiten

Unterstützt wird **eine Astro-SSR-Website pro Container**, npm mit eingecheckter
`package-lock.json` und der Node-Adapter im Standalone-Modus. Im lokalen
Website-Projekt ausführen:

```bash
npx astro add node
```

Die Astro-Konfiguration sinngemäß ergänzen; vorhandene Einstellungen beibehalten:

```js
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
});
```

Mit `npm ci && npm run build` lokal prüfen und einschließlich Lockdatei zu GitHub
pushen. Der Build muss `dist/server/entry.mjs` erzeugen.
[Offizielle Astro-Anleitung](https://docs.astro.build/en/guides/integrations-guide/node/).

## 3. Installer starten

Dieses vollständige Repository nach `/root/AstroDeploy-LXC` in den Container
kopieren oder von seiner tatsächlichen GitHub-URL klonen. Es gibt noch keine
festgelegte öffentliche Downloadadresse. Vor Ausführung Code und Version prüfen.
Dann im Container:

```bash
cd /root/AstroDeploy-LXC
bash bin/setup.sh
```

Das Setup fragt Repository, Branch, Unterordner, Domain/IPv4, Port, Healthcheck
und HTTPS ab. Vor Änderungen erscheint eine Zusammenfassung. Für einen ersten
LAN-Test Container-IP und `http` wählen. Healthcheck `/` muss ohne Anmeldung
**HTTP 200** liefern; Redirects gelten nicht als Erfolg. Alternativ einen eigenen
`/health`-Endpunkt anlegen.

Private Repositories: SSH-URL verwenden. Das Setup erzeugt einen Deploy-Key und
erklärt dessen Eintragung bei GitHub. Details: [GitHub-Zugriff](docs/github.md).

Vorhandene Nginx-Installationen werden abgelehnt. Bei einer unterbrochenen eigenen
Einrichtung den Setup-Befehl erneut starten und „fortsetzen“ wählen.

## Verwaltung

Als root im Container ausführen; normale Benutzer verwenden jeweils `sudo`:

| Befehl | Wirkung |
| --- | --- |
| `astroctl status` | Dienste, Commit und letzten Fehler anzeigen |
| `astroctl doctor` | Grundprüfungen für Nginx, GitHub, Rechte, Speicher und HTTP |
| `astroctl deploy` | Änderungen aus GitHub veröffentlichen |
| `astroctl rebuild` | Auch unveränderten Commit erneut bauen |
| `astroctl pause` | Automatik pausieren |
| `astroctl resume` | Automatik aktivieren |
| `astroctl rollback` | Vorherige Version aktivieren und Automatik pausieren |
| `astroctl logs` | Website- und Deployment-Journal anzeigen |
| `astroctl update --check` | Debian-Updates und verfügbare Node-LTS-Version anzeigen |
| `astroctl update --system` | Debian-Updates anzeigen und nach Bestätigung installieren |
| `astroctl update --node` | Innerhalb Node 24 aktualisieren und Website neu bauen |
| `astroctl update --tools` | Werkzeugversion und manuellen Updateweg anzeigen |

Ein Push zum gewählten Branch reicht für automatische Deployments. Während des
Builds läuft die bisherige Website weiter. Der Dienstneustart verursacht eine
kurze Unterbrechung. Bei fehlgeschlagenem Healthcheck wird zurückgewechselt.
Nach Fehlern wartet die Automatik zehn Minuten; manuell kann sofort erneut
versucht werden. Standardmäßig bleiben drei Releases sowie aktive/vorherige Version erhalten.

## Variablen und Daten

- `/etc/astrodeploy/config.json`: root-eigene Einstellungen.
- `/etc/astrodeploy/build.env`: Build-Variablen. Nach Änderung `astroctl rebuild`.
- `/etc/astrodeploy/runtime.env`: Laufzeitvariablen. Nach Änderung
  `systemctl restart astro-site`. HOST, PORT und NODE_ENV verwaltet das Tool.
- `/srv/astro/PROJEKT/data`: persistente Daten. Absoluten Pfad in der Anwendung
  konfigurieren; das Release-Arbeitsverzeichnis ist schreibgeschützt.
- `/srv/astro/PROJEKT/releases`: unveränderliche Releases mit Abhängigkeiten.
- `/var/lib/astrobuild`: privater Git-Zugang und temporäre Builds.

Die Variablendateien können im Setup mit nano bearbeitet werden. Format:
`NAME=wert`, eine Variable pro Zeile, systemd-EnvironmentFile-Syntax, kein `export`
oder Shellcode. `PUBLIC_`-Werte und eingebettete Build-Secrets können im erzeugten
Code sichtbar werden. Geheimnisse möglichst nur zur Laufzeit bereitstellen.

## HTTPS und Grenzen

Let's Encrypt benötigt korrekte DNS-Einträge und erreichbare Ports 80/443.
Certbot übernimmt die Erneuerung; Test: `certbot renew --dry-run`. Bei vorhandenem
TLS-Proxy dessen IP/CIDR angeben. Weitergeleitete Protokollwerte werden nur von
dieser Adresse akzeptiert. [Installation und HTTPS](docs/installation.md).

Node 24 LTS wird getrennt von globalem Node von nodejs.org installiert und mit
SHA-256 aus der offiziellen HTTPS-Quelle geprüft. Das ist keine unabhängige
Signaturprüfung. npm prüft Paket-Engine-Anforderungen strikt. Debian und Node
werden nur durch bewusste Wartung aktualisiert.

Nicht unterstützt: rein statische Builds, mehrere Websites, npm-Workspaces,
Submodule, Git LFS, automatische Datenbankmigrationen und abweichende Buildpfade.
Ein Unterordner muss ein eigenständiges npm-Projekt sein. Alte Node-Versionen
bleiben für Rollbacks erhalten und belegen Speicher. Automatische Werkzeugupdates
sind noch nicht implementiert.

Regelmäßig Container, Konfiguration und Anwendungsdaten sichern. Website-Rollback
setzt weder Datenbanken noch Debian-Pakete zurück. Proxmox-Host und Kernel werden
nicht verwaltet.

Weitere Anleitungen: [Updates](docs/updates.md), [Rollback](docs/rollback.md),
[Fehlersuche](docs/troubleshooting.md), [Teststand](docs/testing.md).
Die ursprünglichen Aufträge liegen unter [doku](doku/CODEX_ARBEITSANLEITUNG.md).
Lizenz und Rechteinhaber müssen vor Veröffentlichung festgelegt werden.
