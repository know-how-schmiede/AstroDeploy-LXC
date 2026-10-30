# Teststand vom 30.10.2026

Lokal unter Windows geprüft:

- Bash-Syntax aller drei Starter mit Git Bash: bestanden.
- Python-3.12-Syntax von Orchestrator und Build-Helfer: bestanden.
- Unit-Tests: acht bestanden, drei POSIX-Symlink-Tests übersprungen.
  Geprüft: unveränderter Commit, Buildfehler ohne Aktivierung, Pause,
  normale Extraktion, Stream-Übergabe, Ablehnung gefährlicher Archivpfade/-typen
  sowie sichere Abbrüche bei Downloadfehler und falscher Node-Prüfsumme.

Linux-CI ist angelegt und führt zusätzlich Symlink-Tests für Wiederherstellung
und Cleanup aus. Dieser Workflow wurde hier nicht auf GitHub ausgeführt.
ShellCheck ist lokal nicht installiert; dessen CI-Prüfung steht aus.

Kein Test-LXC ist angeschlossen. Noch nicht live geprüft:

1. Installation/Fortsetzung in Debian 13, öffentliche/private GitHub-Repositories.
2. Erster Build, zweiter Commit, defekter Build und fehlerhafter Healthcheck.
3. Rollback, Reboot, Pause/Resume und parallele Aufrufe unter flock.
4. systemd-Härtung im LXC und effektive Benutzerrechte.
5. Nginx, Certbot samt Erneuerung und externer TLS-Proxy.
6. Node-/Debian-Updates sowie arm64-Betrieb.

Diese Abnahme vor produktivem Einsatz in einem separaten Testcontainer durchführen.
