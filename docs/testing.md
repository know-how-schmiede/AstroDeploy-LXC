# Teststand vom 30.10.2026

Lokal unter Windows geprüft:

- Bash-Syntax aller drei Starter mit Git Bash: bestanden.
- Python-3.12-Syntax von Orchestrator und Build-Helfer: bestanden.
- Unit-Tests: 23 bestanden, drei POSIX-Symlink-Tests übersprungen.
  Geprüft: unveränderter Commit, Buildfehler ohne Aktivierung, Pause,
  normale Extraktion, Stream-Übergabe, Ablehnung gefährlicher Archivpfade/-typen
  sowie sichere Abbrüche bei Downloadfehler und falscher Node-Prüfsumme.
  Ein Regressionstest prüft das zugängliche Arbeitsverzeichnis für Build-Benutzer.
  Neue Tests prüfen IP-Auswahl, private/öffentliche Repository-URLs, die erlaubte
  Adaptervorbereitung, Abbrüche bei ungeeigneten Projekten und Adapterfehlern,
  Erhalt der ursprünglichen Astro-Version und das Ausblenden von npm-Ausgaben.
- JS-Konfigurationsprüfung mit dem lokal installierten Node: bestanden. Ein
  Testadapter prüft Import der bestehenden Konfiguration, Erhalt von Integrationen
  und Build-Einstellungen sowie die Umstellung auf Server/Standalone.

Bereitgestellte Container-Ausgaben belegen Paketinstallation, erfolgreichen
SSH-Deploy-Key-Zugriff, Nginx-Konfiguration, Node-Download und Git-Checkout.
Der erste Fehler mit geerbtem Arbeitsverzeichnis unter /root ist korrigiert.
Der letzte Versuch stoppte noch am fehlenden Node-Adapter im Website-Projekt.
Die automatische Container-Vorbereitung in 0.2.0 behebt diesen Fall im Code;
ein erfolgreicher vollständiger Wiederholungslauf ist noch nicht belegt.

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
