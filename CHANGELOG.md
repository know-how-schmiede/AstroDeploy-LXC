# Changelog

## 0.2.0 – 30.10.2026 (unveröffentlicht)

- Projektvorbereitung vollständig im Container: fehlenden Node-Adapter lokal
  ergänzen, zusätzliche SSR-Konfiguration erzeugen und dort bauen.
- Keine Änderungen am GitHub-Website-Repository und kein schreibender Deploy-Key nötig.
- Bestehende Astro-Version beim Ergänzen des Adapters festhalten; strikte Peer-Prüfung.
- Container-IPv4 anzeigen und die Adresse der Standard-Schnittstelle als Vorgabe anbieten.
- Öffentlichen/privaten Website-Zugriff abfragen; private HTTPS-URLs auf SSH umstellen.
- Zugängliches Arbeitsverzeichnis für Build-/Git-Aufrufe auch beim Start aus /root.
- Fehlendes Python nach Rückfrage installieren; verständlichere Build-Fehlerphasen.
- Neustart-Anleitung nach Container-Reset sowie Tests für IP, GitHub-Zugriff und Vorbereitung.

## 0.1.0 – 30.10.2026 (unveröffentlicht)

- Deutsches Setup für Astro SSR im Debian-13-LXC.
- GitHub-Polling, Deploy-Key, getrennte Build-/Runtime-Benutzer.
- Separate Releases, HTTP-Prüfung, automatischer/manueller Rollback.
- Nginx, optional Certbot oder vorhandener TLS-Proxy.
- Debian-/Node-Wartung, Diagnose und Grundtests.
- Werkzeug-Selbstupdate und Linux-Live-Abnahme stehen aus.
- Git-Aufrufe als astrobuild verwenden ein zugängliches Arbeitsverzeichnis,
  auch wenn der Installer aus /root gestartet wird.
