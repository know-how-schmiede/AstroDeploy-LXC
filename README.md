<p align="center"><img src="assets/logo.png" alt="AstroDeploy-LXC" width="112"></p>

# AstroDeploy-LXC

Astro-Websites aus GitHub automatisch im Debian-13-Container auf Proxmox deployen.
Das deutschsprachige Setup richtet Node.js, Nginx und systemd ein. Projektvorbereitung
und Build laufen vollständig im Container. Ein Timer prüft den gewählten Branch
standardmäßig alle 60 Sekunden.

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
anmelden. Alle folgenden Befehle gehören in den Debian-Container, nicht auf den
Proxmox-Host.

Für einen frisch zurückgesetzten Container zuerst:

```bash
apt-get update
apt-get install -y git ca-certificates python3
```

Sind diese Pakete bereits installiert, kannst du diesen Schritt überspringen.
Fehlt Python beim Start, bietet der Starter dessen Installation auch selbst an.

## 2. Website-Repository bereithalten

Du brauchst die GitHub-URL deiner Astro-Website und den Branch (meist `main`).
Das Repository muss `astro` in der `package.json`, ein Buildskript `astro build`
und eine eingecheckte `package-lock.json` enthalten. Node/npm auf deinem PC
werden für die Installation nicht benötigt.

Die neue Vorgabe **„Astro automatisch für diesen Container vorbereiten? ja“**
ergänzt einen fehlenden `@astrojs/node`-Adapter ausschließlich in der Build-Kopie.
Eine zusätzliche Konfiguration übernimmt deine bestehenden Einstellungen und
setzt Serverausgabe, Standalone-Adapter und den Standard-Ausgabepfad. Der Build
läuft als `astrobuild`, niemals als root. GitHub bleibt unverändert und der
Deploy-Key benötigt keinen Schreibzugriff.

Die Adapter-Version wird im Setup angezeigt und fest gespeichert. Bereits im
Projekt vorhandene Adapter werden aus dessen Lockdatei verwendet. Die gesperrte
Astro-Version wird beim Ergänzen des Adapters beibehalten. Bei inkompatiblen
Peer-Abhängigkeiten bricht der Build ab, statt Astro eigenständig zu aktualisieren.

Für Projekte mit bereits fertig eingerichteter SSR-Konfiguration oder eigenen
Buildskripten die automatische Vorbereitung mit `nein` ausschalten. Dann muss
das Repository selbst `dist/server/entry.mjs` erzeugen.
Details und Grenzen: [Container-Build](docs/container-build.md).

## 3. Installer starten

Du brauchst keine ZIP-Datei herunterzuladen oder Dateien vom PC zu kopieren.
Hole den Installer direkt aus
[know-how-schmiede/AstroDeploy-LXC](https://github.com/know-how-schmiede/AstroDeploy-LXC)
in den Container. Dafür diese Befehle als root eingeben:

```bash
git clone https://github.com/know-how-schmiede/AstroDeploy-LXC.git /root/AstroDeploy-LXC
```

Danach Code und Version prüfen und das interaktive Setup starten:

```bash
cd /root/AstroDeploy-LXC && bash bin/setup.sh
```

**Repository bereits im Container vorhanden?** Dann nicht erneut klonen.
So bringst du eine unveränderte lokale Kopie auf den aktuellen Stand:

```bash
git -C /root/AstroDeploy-LXC pull --ff-only
```

Anschließend wieder mit `cd /root/AstroDeploy-LXC && bash bin/setup.sh` starten.
Falls Git lokale Änderungen oder einen Konflikt meldet, diese zuerst prüfen;
das Setup erst nach erfolgreicher Aktualisierung starten.

Internet bleibt erforderlich: Git lädt den Installer aus GitHub; das Setup lädt
benötigte Debian-Pakete, Node.js und die Abhängigkeiten deiner Website automatisch.
Ein manueller Download ist nicht nötig. Die im Setup abgefragte GitHub-URL ist
die URL **deines Astro-Website-Projekts**, nicht die URL dieses Installers.

Das Setup fragt Repository, Branch, Unterordner, Domain/IPv4, Port, Healthcheck
und HTTPS ab. Es zeigt die erkannten IPv4-Adressen und schlägt die Adresse der
Standard-Netzwerkschnittstelle vor. Mit Enter übernehmen oder eine Domain eintragen.
Vor Änderungen erscheint eine Zusammenfassung. Für einen ersten LAN-Test
die vorgeschlagene Container-IP und `http` wählen. Healthcheck `/` muss ohne Anmeldung
**HTTP 200** liefern; Redirects gelten nicht als Erfolg. Alternativ einen eigenen
`/health`-Endpunkt anlegen.

Bei der Frage **„Ist dieses Website-Repository privat?“** entsprechend antworten.
Bei `ja` wandelt das Setup auch eine eingegebene HTTPS-URL in eine SSH-URL um,
erzeugt einen Deploy-Key und erklärt dessen Eintragung bei GitHub. Nach einem
Container-Reset ist es ein neuer Key; diesen neu bei GitHub hinterlegen.
Details: [GitHub-Zugriff](docs/github.md).

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
werden nur durch bewusste Wartung aktualisiert. Für einen fehlenden Adapter wird
zusätzlich die im Setup gespeicherte Version aus der offiziellen npm-Registry
installiert. Dafür wird nur die temporäre Build-Kopie angepasst.

Nicht unterstützt: rein statisches Hosting ohne Node, mehrere Websites, npm-Workspaces,
Submodule, Git LFS, automatische Datenbankmigrationen und abweichende Buildpfade.
Der Container-Modus kann eine normale statische Astro-Konfiguration für diesen
Server auf SSR umstellen. Funktionsexporte und mehrere gleichzeitig vorhandene
Astro-Konfigurationsdateien werden dabei nicht unterstützt. Ein Unterordner muss
ein eigenständiges npm-Projekt sein. Alte Node-Versionen
bleiben für Rollbacks erhalten und belegen Speicher. Automatische Werkzeugupdates
sind noch nicht implementiert.

Regelmäßig Container, Konfiguration und Anwendungsdaten sichern. Website-Rollback
setzt weder Datenbanken noch Debian-Pakete zurück. Proxmox-Host und Kernel werden
nicht verwaltet.

Weitere Anleitungen: [Updates](docs/updates.md), [Rollback](docs/rollback.md),
[Fehlersuche](docs/troubleshooting.md), [Teststand](docs/testing.md).
Die ursprünglichen Aufträge liegen unter [doku](doku/CODEX_ARBEITSANLEITUNG.md).
Lizenz und Rechteinhaber müssen vor Veröffentlichung festgelegt werden.
