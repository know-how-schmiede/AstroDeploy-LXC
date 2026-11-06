# Teststand 0.5.1 vom 06.11.2026

Aktuell auf dem Windows-Entwicklungsrechner tatsächlich ausgeführt:

- Python 3.12.15: `py_compile` für `lib/astrodeploy.py` und `lib/build.py` bestanden.
- `unittest discover -s tests`: 63 Tests, 55 bestanden, acht unter Windows
  übersprungen (POSIX-Symlinks bzw. Eigentümer/Gruppen/Modi). Keine Fehler.
- Git Bash: `bash -n` für alle drei Starter bestanden.
- ShellCheck-Aufruf versucht, lokal nicht installiert; Prüfung steht aus.
- `git diff --check`: keine Whitespacefehler.

Neue Tests prüfen explizite Profilmetadaten, exakten Schema-/Typ-/Pfadvertrag,
Größenlimit und doppelte JSON-Schlüssel, fehlende Dateien, Symlinks,
Erstkonfiguration/Secret-Erhalt und Rechte, Node-Bindung/Sandbox,
Profilentfernung, Worker-Startbedingung ohne Versand, nginx mit ACL/TLS-Erhalt,
Rücksicherung nach Syntaxfehler, Artefaktübergabe, Cleanup-Sperre und
Timerwiederherstellung nach fehlgeschlagenem Healthcheck sowie konsistente
SQLite-Sicherung mit noch geöffnetem WAL. Die acht übersprungenen
Tests müssen unter Linux nachgeholt werden. Der vorhandene Linux-CI-Workflow
wurde hier nicht ausgeführt.

0.5.0 prüft zusätzlich das allgemeine Formularpaket ohne Workshop-/Event-Dateien,
getrennte Daten-/Secret-Felder ohne institutionelle SMTP-Werte, Ablehnung von
Hook-/Unit-Injektionen, die profilbezogene Worker-Startbedingung trotz alter
Workshop-Environmentvariablen und die generische Worker-Unit. Der
Website-Formularvertrag ist in [forms.md](forms.md) dokumentiert; eine konkrete
Website-Formularimplementierung wurde in diesem Installer-Repository nicht erstellt.

Kein Setup, kein Containerzugriff und kein Mailversand wurden ausgeführt.
SMTP-Ausfall/Queue-Dauerhaftigkeit, Formular/Kapazität/Abmeldung/Admin/CSV,
effektive Build-/Runtime-Rechte, SQLite-WAL-Backup, Node-Rollback und
nginx-Logverhalten mit echten Token-URLs erfordern die Website und einen
ausdrücklich freigegebenen frischen Debian-13-Test-LXC. Ablauf und Betriebsfreigabe:
[Workshop-Anmeldung](workshop-registration.md) und
[Arbeitsauftrag](arbeitsauftrag-workshop-anmeldung.md). Private Einstellungen
und read-only Deploy-Key erst dort einrichten. Website-Paket muss vorher im
Website-Branch verfügbar sein; echte Testmails nur nach separatem Auftrag.

## Frühere Prüfungen (30.10.2026)

Lokal unter Windows geprüft:

- Bash-Syntax aller drei Starter mit Git Bash: bestanden.
- Python-3.12-Syntax von Orchestrator und Build-Helfer: bestanden.
- Unit-Tests: 35 bestanden, vier POSIX-Symlink-Tests übersprungen.
  Geprüft: unveränderter Commit, Buildfehler ohne Aktivierung, Pause,
  normale Extraktion, Stream-Übergabe, Ablehnung gefährlicher Archivpfade/-typen
  sowie sichere Abbrüche bei Downloadfehler und falscher Node-Prüfsumme.
  Ein Regressionstest prüft das zugängliche Arbeitsverzeichnis für Build-Benutzer.
  Neue Tests prüfen IP-Auswahl, private/öffentliche Repository-URLs, die erlaubte
  Adaptervorbereitung, Abbrüche bei ungeeigneten Projekten und Adapterfehlern,
  Erhalt der ursprünglichen Astro-Version und das Ausblenden von npm-Ausgaben.
  Version 0.2.1 prüft zusätzlich Buildketten mit vorgeschaltetem npm-Check,
  mehrere Aufgaben sowie die Ablehnung mehrdeutiger Folgekommandos.
  Version 0.3.0 prüft statische Ausgabe ohne Adapter/SSR-Konfiguration,
  Ausgabeerkennung, Abschaltung des Node-Dienstes, lokale HTTP-/TLS-Prüfung
  sowie Nginx-Migration mit Erhalt von TLS und Wiederherstellung bei Syntaxfehlern.
- JS-Konfigurationsprüfung mit dem lokal installierten Node: bestanden. Ein
  Testadapter prüft Import der bestehenden Konfiguration, Erhalt von Integrationen
  und Build-Einstellungen sowie die Umstellung auf Server/Standalone.

Bereitgestellte Container-Ausgaben belegen Paketinstallation, erfolgreichen
SSH-Deploy-Key-Zugriff, Nginx-Konfiguration, Node-Download und Git-Checkout.
Der erste Fehler mit geerbtem Arbeitsverzeichnis unter /root ist korrigiert.
Der letzte Versuch stoppte noch am fehlenden Node-Adapter im Website-Projekt.
Die automatische Container-Vorbereitung in 0.2.0 behebt diesen Fall im Code;
ein erfolgreicher vollständiger Wiederholungslauf ist noch nicht belegt.

Der zweite Container-Test verwendete die andere Website mit Buildskript
`npm run check && astro build` und stoppte an der zu engen Skriptprüfung in 0.2.0.
Das Skript wurde anhand des gemeldeten Commits in einer vorhandenen lokalen
Website-Kopie bestätigt. Die Prüfung wurde in 0.2.1 korrigiert; die Website selbst
wurde dabei nicht verändert.

Nachfolgende Serverprotokolle belegen einen laufenden SSR-Dienst, aber auch
`undefined.filter`/`RenderUndefinedEntryError` bei ursprünglich statischen
Routen. Version 0.3.0 führt deshalb den Modus auto und statisches Nginx-Hosting
ein. Der vollständige Umschaltlauf im Container ist noch nicht durchgeführt.

Linux-CI ist angelegt und führt zusätzlich Symlink-Tests für Wiederherstellung
und Cleanup aus. Dieser Workflow wurde hier nicht auf GitHub ausgeführt.
ShellCheck ist lokal nicht installiert; dessen CI-Prüfung steht aus.

Kein Test-LXC ist angeschlossen. Noch nicht live geprüft:

1. Vollständige Neuinstallation/Fortsetzung mit der neuen Container-Vorbereitung,
   echter Adapterinstallation und echtem Astro-Build auf Debian 13.
2. Erster Build, zweiter Commit, defekter Build und fehlerhafter Healthcheck.
3. Rollback, Reboot, Pause/Resume und parallele Aufrufe unter flock.
4. systemd-Härtung im LXC und effektive Benutzerrechte.
5. Nginx, Certbot samt Erneuerung und externer TLS-Proxy.
6. Node-/Debian-Updates sowie arm64-Betrieb.

Diese Abnahme vor produktivem Einsatz in einem separaten Testcontainer durchführen.
