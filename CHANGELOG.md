# Changelog

## 0.3.0 – 30.10.2026 (unveröffentlicht)

- Vorgabe auto baut mit unveränderter Projektkonfiguration statt pauschal SSR zu erzwingen.
- Statische Websites direkt durch Nginx ausliefern und Node-Runtime deaktivieren.
- SSR und optionale Adaptervorbereitung bleiben als bewusster Modus server verfügbar.
- Nginx-Location mit Backup migrieren, vorhandene TLS-Einstellungen erhalten.
- Release-Betriebsart, Healthchecks und Rollback zwischen statischer/SSR-Ausgabe.
- Behebt die Ursache fehlender getStaticPaths-Props nach erzwungener SSR-Umstellung.

## 0.2.1 – 30.10.2026 (unveröffentlicht)

- Container-Vorbereitung akzeptiert auch `npm run check && astro build`,
  mehrere vorgeschaltete npm-Aufgaben und `astro check && astro build`.
- Bestehende Prüfungen bleiben erhalten; Konfigurationsargumente werden nur an
  den abschließenden Astro-Build übergeben. Mehrdeutige Skripte bleiben ausgeschlossen.
- Regressionstests für die gemeldete zweite Website und unzulässige Folgekommandos.

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

## 0.4.0 – 2026-11-06

- Explizites Workshop-Laufzeitprofil mit strengem Schema-1-Artefaktvertrag.
- Getrennte private JSON-Konfiguration und dauerhaftes Installer-Secret.
- Gehärteter Wartungstimer mit Release-Node und Aktivierungs-/Rollback-Abgleich.
- Datenschutz im vorhandenen nginx-Proxy, Profildiagnose und SQLite-Backup als astrorun.
- Vertrags-, Sandbox-, nginx- und Aktivierungsregressionstests; LXC-Abnahme offen.

## 0.5.0 – 2026-11-06

- Allgemeines optionales Profil `forms` für beliebige Website-Repositories mit
  festem, geprüftem Formular-Artefaktvertrag, ohne Workshop-/Event-Abhängigkeiten.
- Getrennte private Formular-Konfiguration und Datenbank ohne MakerLab-SMTP-Werte.
- Gemeinsamer sicherer Lifecycle, profilbezogene Startbedingung und Verwaltung
  über `forms-admin` / `forms-backup`; Workshop-Vertrag und alte Befehle erhalten.
- Dokumentierter Vertrag für Website-Implementierungen und fünf zusätzliche Tests.

## 0.5.1 – 2026-11-06

- nginx ergänzt X-Forwarded-Host mit öffentlichem Host/Port für Astros
  Herkunftsprüfung und erhält dabei bestehende Proxy-ACLs und TLS.
- Migration alter generierter Proxyblöcke bleibt möglich; abweichende eigene
  Forwarded-Host-Regeln erfordern manuelle Prüfung.
- Drei Regressionstests für Headerergänzung, Konflikte und alte Inlineblöcke.
