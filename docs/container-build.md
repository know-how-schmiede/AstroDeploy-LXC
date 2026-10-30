# Projektvorbereitung und Build im Container

Seit Version 0.2.0 kann ein Astro-Projekt ohne Node-Adapter direkt aus GitHub im
Container vorbereitet und gebaut werden. Ein PC mit Node/npm ist nicht nötig.
Im Setup „Astro automatisch für diesen Container vorbereiten?“ mit `ja` beantworten.

## Ablauf

1. Exakten GitHub-Commit als astrobuild in ein frisches Verzeichnis auschecken.
2. Astro, Buildskript und Lockdatei prüfen. Ein fremdes Framework wird nicht konvertiert.
3. `npm ci --include=dev --engine-strict` mit der projektbezogenen Node-Version ausführen.
4. Falls der Adapter fehlt: die im Setup festgelegte `@astrojs/node`-Version
   ergänzen. Dabei wird die bereits installierte Astro-Version exakt festgehalten;
   npm prüft Engines und Peer-Abhängigkeiten strikt. Kein automatisches Astro-Upgrade.
5. `.astrodeploy.config.mjs` nur in der Build-Kopie erzeugen. Sie importiert die
   vorhandene Konfiguration und übernimmt deren Einstellungen/Integrationen.
   Sie setzt `output: 'server'`, den Node-Adapter auf `standalone`, `outDir` auf
   `dist` und die Standardpfade `server`, `client`, `entry.mjs`.
6. `npm run build -- --config .astrodeploy.config.mjs` ausführen.
7. Ausgabe prüfen, Release veröffentlichen, Dienst starten und lokal HTTP 200 prüfen.

Npm-Lifecycle-Skripte, Konfigurationsimporte und Build laufen ausschließlich als
astrobuild. Das bestehende Release läuft währenddessen weiter.

GitHub-Dateien werden nicht verändert, committet oder gepusht. Ein read-only
Deploy-Key reicht. Bei jedem neuen Commit wird dieselbe Vorbereitung erneut
angewendet. Ein vorhandener Adapter wird aus der ursprünglichen Projekt-Lockdatei
installiert und nicht durch die Setup-Version ersetzt.

Die ursprünglichen Abhängigkeiten werden zunächst mit npm ci installiert. Beim
Ergänzen eines fehlenden Adapters löst npm dessen zusätzliche Abhängigkeiten auf;
die daraus entstandene Lockdatei wird im Release mit aufbewahrt. Deren transitive
Versionen können bei späteren Neubauten anders ausfallen. Für vollständig vom
Website-Repository festgelegte Abhängigkeiten den Adapter dort einschließlich
Lockdatei pflegen und die automatische Vorbereitung ausschalten.

## Voraussetzungen und Grenzen

- Astro ist bereits eine Abhängigkeit und eine gültige package-lock.json ist vorhanden.
- Für automatische Vorbereitung muss das Buildskript mit `astro build` enden.
  Davor sind eine oder mehrere Aufgaben `npm run NAME &&` sowie `astro check &&`
  erlaubt, z. B. `npm run check && astro build`. Diese Prüfungen werden weiterhin
  ausgeführt. Das Tool führt das ursprüngliche npm-Buildskript aus und hängt die
  Konfigurationsargumente an den abschließenden Astro-Aufruf an.
  Nachfolgende Befehle, eigene Astro-Flags, Pipes und andere Shell-Konstruktionen
  bleiben ausgeschlossen, damit die Konfigurationsargumente eindeutig ankommen.
  Vor-/Nachbereitung über npm-prebuild/postbuild läuft weiterhin unter dem Build-Benutzer.
- Keine oder genau eine astro.config.mjs/js/ts/mts/cjs/cts mit objektbasiertem Export.
  Bestehende `.astrodeploy.config.mjs` wird nicht überschrieben.
- Funktionen als Konfigurationsexport, eigene Adapter und Spezial-Buildskripte:
  fertige SSR-Konfiguration im Projekt verwenden und die Vorbereitung ausschalten.
- Routenspezifisches `prerender` wird nicht geändert. Andere Dateiausgaben und
  dynamisches Schreiben ins Release werden nicht unterstützt.
- Neueste stabile Adapter-Version wird als Vorschlag aus registry.npmjs.org
  ermittelt. Bei älterem Astro gegebenenfalls eine kompatible feste Version wählen.
  Inkompatibilität führt zum Abbruch, nicht zu einem erzwungenen Upgrade.

Build-Ausgaben werden wegen möglicher Geheimnisse ausgeblendet. Bei Fehlern
meldet die Verwaltung die Phase: Abhängigkeiten, Adapter, Konfiguration oder Build.
Es wird kein globales Node/npm installiert; manuelle npx-Befehle als root sind unnötig.

Quellen: [Astro-Node-Adapter](https://docs.astro.build/en/guides/integrations-guide/node/)
und [Astro --config](https://docs.astro.build/en/reference/cli-reference/#--config).
