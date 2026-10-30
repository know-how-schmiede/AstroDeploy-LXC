# Codex-Arbeitsanleitung: AstroDeploy-LXC

## Auftrag

Entwickle im Terminal ein GitHub-fähiges Projekt namens **AstroDeploy-LXC**.
Es soll eine Astro-Website mit Node.js-SSR in einem dedizierten Debian-13-LXC
unter Proxmox installieren, aus GitHub automatisch aktualisieren und eine
nachvollziehbare Wartung von Debian, Node.js und den Deployment-Werkzeugen ermöglichen.

Arbeite die Umsetzung bis zu einem geprüften, dokumentierten Ergebnis durch.
Erzeuge die Dateien tatsächlich im Arbeitsverzeichnis. Bleibe nicht bei Vorschlägen
oder Codefragmenten stehen. Lies zuerst vorhandene AGENTS.md und Projektdateien.
Nutze vorhandenen Code, wenn er geeignet ist, und prüfe ihn vor der Übernahme.
Frage nur bei fehlenden Zugangsdaten, unklaren Zielsystemen oder unumkehrbaren
Entscheidungen nach. Routinemäßige Implementierungsentscheidungen triff selbst.

Die Entwicklung erfolgt zunächst im Repository. Führe das Setup nicht versehentlich
auf dem Entwicklungsrechner aus. Systemverändernde Integrationstests nur auf einem
ausdrücklich dafür vorgesehenen Testcontainer durchführen.

## Zielumgebung und Umfang

- Debian 13, systemd, unprivilegierter Proxmox-LXC, Nesting aktiviert.
- amd64 als Pflicht; arm64 unterstützen, soweit Download und Tests es zulassen.
- Eine Website pro Container, zunächst npm mit eingecheckter package-lock.json.
- Astro mit kompatiblem `@astrojs/node`, `mode: 'standalone'`, Standardausgabe
  `dist/server/entry.mjs`; `output: 'server'` oder ausdrücklich unterstützte
  gemischte Ausgabe mit Node-Adapter.
- Nginx als Reverse Proxy; Node lauscht ausschließlich auf Loopback.
- Automatisches Deployment durch systemd-Timer und ausgehenden GitHub-Zugriff.
- Keine eingehende Webhook-Schnittstelle, kein Docker, keine Datenbankpflicht.
- Keine automatische Änderung der Astro-Konfiguration im Website-Repository.
- Keine automatische Datenbankmigration und keine Zusage eines unterbrechungsfreien
  Deployments. Eine kurze Unterbrechung beim Node-Neustart ist akzeptabel.

Empfohlener Start: 2 CPU-Kerne, 4 GB RAM, 1 GB Swap, 20–30 GB Speicher.
Das sind Richtwerte, keine garantierten Mindestanforderungen.

## Vorgesehene Repository-Struktur

```text
AstroDeploy-LXC/
├── README.md
├── AGENTS.md
├── LICENSE
├── CHANGELOG.md
├── .gitignore
├── .github/workflows/checks.yml
├── bin/
│   ├── setup.sh
│   ├── astroctl
│   └── update.sh
├── lib/astrodeploy/
├── templates/
│   ├── systemd/
│   ├── nginx/
│   └── config.example.toml
├── docs/
│   ├── installation.md
│   ├── github.md
│   ├── updates.md
│   ├── rollback.md
│   └── troubleshooting.md
└── tests/
```

Diese Struktur darfst du sinnvoll anpassen. Verwende Bash für kleine Starter und
Python 3.11+ mit Standardbibliothek für komplexe Abläufe, Konfiguration und
Zustandsverwaltung. Keine unnötigen Laufzeitabhängigkeiten. TOML ist möglich;
Systemkonfiguration niemals als ausführbares Shell-Skript sourcen.

## 1. Interaktives Setup

`sudo bash bin/setup.sh` startet eine verständliche deutschsprachige Installation.
Die wichtigsten Werte werden abgefragt, mit Vorgabewerten und Validierung:

1. Projektname und Installationspfad.
2. GitHub-Repository: öffentlich per HTTPS oder privat per SSH-Deploy-Key.
3. Branch, Vorgabe `main`.
4. Optionaler Projekt-Unterordner mit eigener package-lock.json.
5. Domain oder IPv4-Adresse, ohne URL-Schema.
6. Interner Node-Port, Vorgabe 4321; Verfügbarkeit prüfen.
7. Automatisches Deployment ja/nein und Intervall, Vorgabe 60 Sekunden.
8. HTTP-Healthcheck-Pfad, Vorgabe `/health`; auf einen tatsächlich vorhandenen
   öffentlichen Endpunkt hinweisen, alternativ `/`.
9. HTTPS-Modus: direktes Let's Encrypt, vorgeschalteter Reverse Proxy oder nur HTTP.
10. E-Mail bei Let's Encrypt.
11. Unterstützte Node-LTS-Hauptversion; eine aktuell unterstützte und mit dem
    Projekt kompatible Version vorschlagen. Projektanforderungen prüfen.
12. Einmaliges Debian-Update vor Installation, mit sichtbarem Umfang.
13. Optionale automatische Debian-Sicherheitsupdates, standardmäßig ohne Reboot.
14. Build- und Laufzeitvariablen über eine lokale Datei bzw. einen Editor.

Vor Änderungen eine Zusammenfassung anzeigen und innerhalb des laufenden Setups
bestätigen lassen. Passwort- und Geheimniseingaben niemals mitloggen.
GitHub-Tokens dürfen nicht Bestandteil der Repository-URL sein.

Prüfe root-Rechte, Distribution, Architektur, systemd, freien Speicher, Ports,
vorhandene Benutzer, vorhandene Konfigurationen und konkurrierende Dienste.
Keine bestehenden Websites, Node-Installationen oder Nginx-Konfigurationen still
überschreiben. Bei bestehender eigener Installation einen Reparatur-/Fortsetzen-
Modus anbieten. Teilweise fehlgeschlagene Installationen müssen fortsetzbar sein.

Vorhandenen funktionierenden GitHub-SSH-Zugang optional wiederverwenden, andernfalls
einen projektspezifischen Deploy-Key erzeugen. Nur öffentlichen Schlüssel anzeigen.
Der Benutzer trägt ihn als read-only Deploy-Key bei GitHub ein. GitHub-Host-Key
anhand offizieller Fingerprints validieren; kein blindes Vertrauen in ssh-keyscan.

Nginx, Git, Zertifikate und weitere tatsächlich benötigte Debian-Pakete installieren.
Node projektbezogen in einem eigenen Verzeichnis installieren, ohne globale
node/npm-Befehle anderer Anwendungen zu ersetzen. Offizielle Downloadquelle,
Version, Architektur und Prüfsummen nachvollziehbar prüfen. Keine ungeprüfte
`curl | bash`-Installation. Sicherheitsrelevante Quellen aktuell in offiziellen
Dokumentationen verifizieren.

## 2. Rechte, Konfiguration und Verzeichnisse

Trenne mindestens Build-Benutzer, Laufzeitbenutzer und privilegierte Verwaltung.
Repository-Code und npm-Lifecycle-Skripte niemals als root ausführen.
Der Laufzeitbenutzer darf weder SSH-Deploy-Key noch Build-Geheimnisse lesen und
keine Releases oder Verwaltungsdateien verändern.

Beispielaufteilung, bei Bedarf anpassen:

```text
/etc/astrodeploy/              root-eigene Konfiguration, Laufzeitvariablen
/var/lib/astrodeploy/          root-eigener Zustand, Sperren, erfolgreiche Commit-ID
/var/lib/astrobuild/           privater Checkout, SSH-Key, Build-Umgebung
/srv/astro/PROJEKT/releases/   veröffentlichte, unveränderliche Releases
/srv/astro/PROJEKT/current     root-eigener Link auf aktives Release
/srv/astro/PROJEKT/previous    root-eigener Link auf vorheriges Release
/srv/astro/PROJEKT/data/       persistente Anwendungsdaten, nur hier Laufzeitschreibrecht
```

Laufzeit-Secrets außerhalb der Releases halten; restriktive Dateirechte verwenden.
Build-.env nicht ungeprüft in veröffentlichte Releases übernehmen. Benötigte
Produktionsabhängigkeiten müssen dennoch im Release vorhanden sein: Die Node-
Ausgabe ist nicht pauschal eine vollständig unabhängige Einzeldatei.

Für root-seitige Veröffentlichung keine vom Build-Benutzer manipulierbaren
Symlink-Ziele verfolgen. Sichere Übergabe von Build-Ergebnissen, Pfadvalidierung
und Archivextraktion ausdrücklich entwerfen und testen. Keine weitreichende
sudo-Berechtigung für den Build-Benutzer. systemd-Härtung muss im LXC funktionieren.

## 3. Website-Deployment

Ein root-eigener systemd-Oneshot-Dienst orchestriert den Ablauf. Seine zulässigen
Aktionen sind fest implementiert; Projektwerte dürfen nicht als Shellcode wirken.
Der Timer verwendet einen Abstand zum Ende des letzten Laufs, damit keine
überlappenden Builds entstehen. Zusätzlich gemeinsame Sperre für Deployment,
Rollback und Wartung verwenden.

Ablauf:

1. Pausenstatus und Sperre prüfen.
2. Git-Referenz abrufen und exakte Commit-ID bestimmen.
3. Mit zuletzt erfolgreich freigegebenem Commit UND Build-Konfigurationszustand
   vergleichen. Wiederholte Fehlschläge begrenzen bzw. Backoff einsetzen.
4. Exakten Commit in einem frischen Arbeitsverzeichnis bauen.
5. `npm ci --include=dev` und `npm run build` als Build-Benutzer ausführen.
6. Node-Adapter-Ausgabe prüfen. Git-Submodule, Git LFS und Workspace-Sonderfälle
   entweder gezielt unterstützen oder klar mit verständlicher Meldung ablehnen.
7. Ein separates Release mit eindeutiger ID erzeugen. Derselbe Commit muss bei
   geänderten Build-Variablen oder Node-Version erneut gebaut werden können.
8. Build-Artefakte sicher veröffentlichen und den root-eigenen current-Link atomar
   umschalten; eine aktive Version niemals in-place überschreiben.
9. Node-Dienst neu starten, mit begrenzter Gesamtdauer auf lokalen HTTP-Erfolg prüfen.
   Healthchecks dürfen nicht versehentlich eine externe Login-Seite oder einen
   anderen Host als Erfolg werten. Host-Header und erwarteten Status festlegen.
10. Bei Fehler Link zurückschalten, bisherigen Dienst starten und dessen Zustand
    ebenfalls prüfen. Beim ersten Deployment ohne Vorgänger verständlich abbrechen.
11. Erst nach Erfolg den veröffentlichten Zustand speichern und alte Releases
    bereinigen. Aktuelles und vorheriges Release niemals löschen.

Der alte Server läuft während des Builds weiter. Eine kurze Unterbrechung beim
Neustart ist dokumentiert. Fehlgeschlagene Builds zerstören die aktuelle Website
nicht. Aufbewahrung konfigurierbar, Vorgabe drei erfolgreiche Releases.

## 4. Verwaltungsbefehle

Implementiere und dokumentiere mindestens:

```bash
sudo astroctl status
sudo astroctl doctor
sudo astroctl deploy
sudo astroctl rebuild
sudo astroctl pause
sudo astroctl resume
sudo astroctl rollback
sudo astroctl logs
sudo astroctl update --check
sudo astroctl update --system
sudo astroctl update --node
sudo astroctl update --tools
```

`rebuild` erstellt auch beim selben Commit ein neues Release. `rollback` pausiert
automatische Deployments dauerhaft, damit der nächste Timerlauf nicht sofort die
zurückgewiesene Version veröffentlicht. `resume` erklärt dieses Verhalten und
hebt die Pause auf. `doctor` verändert nichts und prüft Dienste, Node-Version,
Repository-Zugriff, Speicher, Nginx, Timer, Dateirechte und letzten Deploymentstatus.
Logs dürfen keine Secrets enthalten.

## 5. Updates: vier getrennte Vorgänge

### Website

Der Deployment-Timer übernimmt Änderungen aus dem ausgewählten Branch. Dabei
kein `npm update`, kein automatisches Astro-Major-Upgrade und kein eigenmächtiges
Ändern der Lockdatei. Anwendungsversionen werden im Website-Repository gepflegt.

### Debian-System

`update.sh --system` bzw. `astroctl update --system` aktualisiert Paketlisten und
zeigt zunächst die vorgesehenen Paketänderungen. Für Routinewartung konservativ
vorgehen; Paketentfernungen und auflösungsbedingte größere Änderungen nicht still
akzeptieren. Ein vollständiges `full-upgrade` bei Bedarf als ausdrücklich gewählten
Modus dokumentieren. apt/dpkg-Sperren berücksichtigen, nicht löschen oder Prozesse
gewaltsam beenden. Dienstneustarts und mögliche Unterbrechungen ankündigen.

Optionale unattended-upgrades auf Debian-Sicherheitsupdates begrenzen. Keine
automatischen Reboots. Konfiguration und Status dokumentieren. Ein LXC teilt den
Kernel des Proxmox-Hosts: Host- und Kernelupdates gehören nicht in diese Skripte.
Ein fehlgeschlagenes Systemupdate lässt sich nicht durch Website-Rollback reparieren.

### Node.js

`--node` sucht zunächst nur Updates innerhalb der konfigurierten LTS-Hauptversion.
Kein automatischer Major-Wechsel. Neue Version parallel installieren, Herkunft und
Prüfsumme prüfen, Website unter dieser Version frisch bauen und lokal testen.
Erst dann Dienst auf neue Node-Version UND das dazu gebaute Release umstellen.
Bei Fehler beides zurücksetzen. Die vorherige Laufzeit bis zur erfolgreichen
Prüfung und zur festgelegten Aufbewahrung behalten. Build- und Laufzeitversion
müssen zusammenpassen, insbesondere bei nativen npm-Modulen.

Node-Updates zunächst manuell auslösen. Ein späterer Update-Timer ist optional und
darf nicht still Teil des automatischen Website-Deployments werden.

### Deployment-Werkzeuge

`--tools` prüft Versionen dieses Repositories. Keine ungeprüfte Ausführung von
GitHub-main als root. Versionierte Releases/Tags und eine nachvollziehbare
Integritäts-/Authentizitätsprüfung verwenden. Beachte: Ein daneben veröffentlichter
Hash allein bestätigt nicht die Identität des Herausgebers. Vor Änderungen Release-
Informationen anzeigen, lokale Konfiguration erhalten, alte Werkzeugversion sichern
und Schemaänderungen versioniert migrieren. Ist ein sicherer Selbstupdatepfad für
Version 1 nicht fertig, nur Updateprüfung und dokumentierte manuelle Installation
implementieren und diese Grenze offen benennen. Kein falscher Erfolg.

## 6. Nginx, HTTPS und Daten

Nginx leitet an den Loopback-Port weiter. Host, Client-IP und Protokoll korrekt
übermitteln. Bei vorgeschaltetem TLS-Proxy nur bekannten Proxy-Adressen vertrauen;
nicht beliebige eingehende X-Forwarded-Proto-Werte übernehmen. Direkter HTTP-Zugriff
darf keine gefälschte HTTPS-Erkennung ermöglichen. Proxy-Kette, Astro-Origin-
Prüfungen, Cookies und Redirects dokumentieren. Nicht pauschal CSRF-Schutz abschalten.

Let's Encrypt nur mit passenden DNS-Einträgen und erreichbaren Ports einrichten.
Erneuerungsdienst und Testbefehl dokumentieren. Keine Firewallregeln oder
Router-Portweiterleitungen automatisch verändern.

Persistente Uploads, SQLite und Sessions separat konfigurieren. Kein automatisches
Schema-Rollback versprechen. Container-Backup und Sicherung der Konfiguration sowie
Anwendungsdaten dokumentieren. Speicherbedarf von node_modules und Releases beachten.

## 7. Qualitätssicherung und Abnahme

Nutze für Bash `bash -n` und ShellCheck, für Python passende Syntax-/Lintprüfungen.
Schreibe gezielte Tests für riskante Verhaltensweisen, nicht nur für Implementierungsdetails:

- Unveränderter Stand löst keinen Build aus; rebuild funktioniert trotzdem.
- Buildfehler lässt die laufende Version unverändert.
- Fehlgeschlagener Start/Healthcheck stellt vorheriges Release und ggf. Node-Version wieder her.
- Rollback pausiert Automatik; parallele Deployment-/Updateaufrufe kollidieren nicht.
- Konfigurationswerte und manipulierte Pfade/Symlinks führen nicht zu Root-Codeausführung.
- Runtime-Benutzer kann Deploy-Key, Build-Secrets und Releases nicht verändern.
- Cleanup erhält aktive und vorherige Version.
- Teilinstallation ist fortsetzbar; bestehende Fremdkonfiguration wird nicht überschrieben.
- Downloadfehler, ungültige Prüfsumme und inkompatible Node-Version brechen sicher ab.

GitHub Actions soll Lint- und Unitprüfungen ausführen; keine echten Deploy-Schlüssel
für Pull Requests benötigen. Untrusted PR-Code niemals auf einem privilegierten
Self-hosted Runner in der Produktivumgebung ausführen.

Auf einem autorisierten frischen Debian-13-Test-LXC einen vollständigen Ablauf
prüfen: Installation, erster Build, zweiter Commit, absichtlich defekter Build,
Rollback, Reboot, Wiederaufnahme und Update. Ist kein Test-LXC verfügbar, Tests
mit Mocks ausführen und ungetestete Integrationsschritte ausdrücklich benennen.
Keine erfolgreichen Live-Tests behaupten, die nicht durchgeführt wurden.

## 8. GitHub-Vorbereitung und Veröffentlichung

Vorgeschlagener Name: **AstroDeploy-LXC**.
Vorgeschlagene Beschreibung: **Interactive Astro SSR deployment and maintenance for Debian LXC containers on Proxmox.**

Alternativen: AstroLXC, AstroServerPilot, Astro-LXC-Deploy. Namensverfügbarkeit
vor Repository-Erstellung prüfen, keine Verfügbarkeit annehmen.

README und Bedienoberfläche zunächst deutsch. README enthält Schnellstart,
Voraussetzungen, Astro-Beispielkonfiguration, private Repositories, Updates,
Rollback, Grenzen und Troubleshooting. AGENTS.md hält Sicherheitsinvarianten,
Architektur und Testbefehle für spätere Codex-Arbeit fest.
Eine MIT-Lizenz mit dem vom Benutzer gewünschten Rechteinhaber vorsehen;
keinen Namen oder Urheberrechtseintrag erfinden.

Vor Git-Commit prüfen: keine .env, Tokens, privaten Schlüssel, persönlichen IPs,
internen URLs, Produktionsdaten oder lokalen Zustandsdateien. .gitignore pflegen.
Kein curl-pipe-bash-Schnellstart. Stattdessen getaggtes Release herunterladen oder
Repository klonen, Code/Version prüfen und dann Setup starten.

Prüfe mit `git status` und `gh auth status`, ob GitHub-Zugang besteht. Bereite ein
lokales Git-Repository und einen sinnvollen ersten Commit vor. Falls der Nutzer die
Veröffentlichung dieses Projekts beauftragt hat und Zielkonto/Sichtbarkeit eindeutig
sind, erstelle das Repository mit GitHub CLI und pushe den geprüften Stand.
Beispiel erst nach Auflösung der Werte verwenden:

```bash
gh repo create OWNER/AstroDeploy-LXC --public --source=. --remote=origin --push
```

Sind Zielkonto, Sichtbarkeit oder Veröffentlichungsauftrag unklar, stelle zuerst
den vollständigen geprüften Stand fertig und kläre nur diese fehlenden Angaben.
Kein vorhandenes Remote umbiegen und keine fremde Historie überschreiben.
Für Version 1 ein Changelog und einen reproduzierbaren Release-Ablauf vorbereiten.

## Erwartete Abschlussmeldung von Codex

Nenne die erzeugten Dateien und den Startbefehl. Berichte knapp über bestandene
Prüfungen, nicht ausgeführte Integrationstests und verbleibende Grenzen. Bei
Veröffentlichung die tatsächliche Repository-URL angeben; sonst klar sagen, dass
der Stand lokal vorbereitet ist. Keine Veröffentlichung oder Installation behaupten,
die nicht stattgefunden hat.
