# Statische Astro-Websites und SSR

## Warum funktionierende Unterseiten im Container HTTP 500 lieferten

Die bisherige SSR-Vorbereitung setzte pauschal `output: 'server'`. Statische
dynamische Seiten wie `[topic].astro` erhalten aber beim Build ihre Daten über
`getStaticPaths()` und `Astro.props`. Werden sie stattdessen erst bei einer
Anfrage gerendert, fehlen diese Daten. Das erklärt die gemeldeten Fehler
`Cannot read properties of undefined (reading 'filter')` und
`RenderUndefinedEntryError`. Die funktionierende Website muss dafür nicht
umgeschrieben werden; ihre Rendering-Einstellungen müssen erhalten bleiben.

## Empfohlener Modus auto

Ab 0.3.0 ist `auto` die Setup-Vorgabe. Original-Konfiguration und ursprüngliches
`npm run build` bleiben erhalten. Kein Adapter wird ergänzt und kein SSR erzwungen.

- `dist/server/entry.mjs` vorhanden: Node-Standalone-Dienst hinter Nginx.
- Sonstige statische Ausgabe in `dist`: direkte Auslieferung durch Nginx;
  der Node-Dienst wird deaktiviert. Node wird weiterhin für den Build verwendet.
- Keine passende Ausgabe: Deployment abbrechen, bisherige Version erhalten.

Bei SSR muss das Projekt im Modus auto bereits einen passenden Node-Adapter
enthalten. Andere Serveradapter werden nicht automatisch unterstützt. Für eine
bewusste Umstellung auf Node-SSR gibt es weiterhin den Modus `server`.

Ein Release speichert seine Betriebsart. Rollback zwischen statischer und
SSR-Ausgabe stellt auch Nginx-/Dienstbetrieb wieder her. Statische Releases
enthalten keine node_modules; für erneute Builds wird wieder npm ci ausgeführt.
Die HTTP-Prüfung statischer Websites läuft lokal über Nginx mit dem konfigurierten
Host-Header. Bei direktem Let's Encrypt prüft sie nach HTTP-Redirect lokal TLS mit
Zertifikatsprüfung und demselben Host/Pfad, ohne externe Redirectziele aufzurufen.

## Bestehenden Testcontainer aktualisieren

Zuerst den neuen lokalen Installer-Stand nach GitHub hochladen. Im Container:

```bash
cd /root/AstroDeploy-LXC && git pull --ff-only && bash bin/setup.sh
```

Fortsetzung bestätigen und bei der neuen Modusfrage `auto` wählen. Ein neuer
Build wird durch die Werkzeugversion ausgelöst, auch ohne neuen Website-Commit.
Ein Container-Reset und ein neuer Deploy-Key sind nicht erforderlich.

Die bekannte bisherige Nginx-Proxy-Location wird durch ein umschaltbares Include
ersetzt. Vorherige Datei: `/var/lib/astrodeploy/nginx-before-0.3.conf`.
TLS-Einstellungen von Certbot bleiben erhalten. Bei unbekannten manuellen
Änderungen wird die Migration abgelehnt; nicht blind die gesamte Nginx-Datei
ersetzen. Die eigene Location dann fachkundig auf
`include /etc/nginx/astrodeploy-location.conf;` umstellen und mit `nginx -t` prüfen.

Danach `astroctl doctor` ausführen und die zuvor betroffenen Unterseiten öffnen.
Bei statischem Hosting ist `astro-site` absichtlich inactive/disabled;
`nginx` und bei aktivierter Automatik `astro-deploy.timer` müssen laufen.
Der Healthcheck prüft nur den konfigurierten Pfad, nicht alle Unterseiten.
