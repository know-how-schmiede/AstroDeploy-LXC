# AstroDeploy-LXC

Eine Astro-SSR-Website pro dediziertem Debian-13-LXC. Deutsche Bedienoberfläche.

## Sicherheitsinvarianten

- Root orchestriert. Repository-Code/npm ausschließlich als astrobuild ausführen.
- Runtime als astrorun. Keine sudo-Rechte für Build oder Runtime.
- JSON-Konfiguration niemals als Shellcode behandeln; kein shell=True.
- /var/lib/astrobuild ist nicht vertrauenswürdig: Root darf darin keine
  rekursiven Kopier-/Löschoperationen oder Schreibzugriffe durchführen.
- Artefakte über unprivilegiertes tar und strikt geprüfte Extraktion übergeben.
- Releases und Verwaltung bleiben root-eigen, Runtime schreibt nur ins Datenverzeichnis.
- Buildfehler ändern current nicht; Startfehler stellen vorheriges Release wieder her.
- Node-Version ist Teil des Releases. Rollback wechselt beide zusammen.
- Globales flock serialisiert Setup und Verwaltungsaktionen.
- Keine Secrets oder Build-Ausgaben ins Journal oder ins Repository schreiben.
- Optionaler Container-Modus darf nur die Build-Kopie verändern. Kein Git-Push,
  kein Schreibzugriff für Deploy-Keys. Vorhandene Konfiguration importieren,
  keine Textersetzungen in der Originaldatei. Astro-Version niemals automatisch erhöhen.
- Neue Configfelder sind optional für alte Installationen; automatische
  Container-Vorbereitung erfordert eine feste Adapter-Version und explizite Setup-Auswahl.
- Setup niemals auf dem Entwicklungsrechner ausführen. Integrationstests nur
  im ausdrücklich autorisierten Test-LXC durchführen.

## Tests

```sh
bash -n bin/setup.sh
bash -n bin/astroctl
bash -n bin/update.sh
shellcheck bin/setup.sh bin/astroctl bin/update.sh
python3 -m py_compile lib/astrodeploy.py lib/build.py
python3 -m unittest discover -s tests -v
```

Symlink-Tests brauchen Linux. Offene Abnahme: docs/testing.md.
