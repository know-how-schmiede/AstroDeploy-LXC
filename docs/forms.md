# Allgemeine Formulare ab 0.5.0

Das optionale Profil `forms` ist für beliebige Astro-Website-Repositories
verfügbar. Es stellt den sicheren Laufzeitbetrieb bereit. Die Website implementiert
Formulare, Endpunkte, Validierung, Schutz vor Missbrauch, Datenschutz, Speicherung,
Mailwarteschlange und gegebenenfalls eine Verwaltung. Ein Installer kann diese
fachlichen Funktionen nicht aus beliebigen HTML-Formularen ableiten.

Im Setup `forms` ausdrücklich auswählen, Modus `auto` und einen geeigneten
Healthcheck verwenden (Vorschlag `/health/`). Eine vorhandene Installation kann
`"runtime_profile": "forms"` in `/etc/astrodeploy/config.json` ergänzen und mit
`astroctl rebuild` ein neues Release bauen. Das setzt das unten beschriebene
Website-Paket voraus. Ohne Profil bleiben statische und SSR-Websites unverändert.
Statische Seiten können weiterhin externe Formulardienste nutzen; für lokal
verarbeitete Formulare muss die Website Node-Serverausgabe bereitstellen.
Der Installer stellt statische Projekte nicht automatisch auf SSR um.

## Vertrag für Website-Repositories

Der Build packt das folgende Paket unter `dist/server/forms/`. Interne Module
und zusätzliche Inhaltsdateien können darin liegen; alle Imports müssen aus dem
Release und dessen node_modules auflösbar sein. Kein Runtime-Quellcheckout.
Keine private JSON-Datei, SQLite-Datenbank, .env oder Schlüssel ins Paket schreiben.

`profile.json` muss exakt diesen bekannten Schema-1-Vertrag enthalten:

```json
{
  "schemaVersion": 1,
  "id": "forms",
  "config": {
    "template": "dist/server/forms/forms.config.example.json",
    "filename": "forms.json",
    "environmentVariable": "FORMS_CONFIG",
    "dataFileFields": { "FORMS_DB": "forms.sqlite" }
  },
  "jobs": [{
    "id": "forms-maintenance",
    "entry": "dist/server/forms/maintenance.mjs",
    "intervalSeconds": 60
  }],
  "tools": {
    "admin": "dist/server/forms/admin.mjs",
    "backup": "dist/server/forms/backup.mjs"
  }
}
```

Die genannten Dateien sind reguläre Dateien ohne Symlink-Eltern. IDs, Pfade,
Intervall, Typen und Schlüssel werden strikt geprüft. Es gibt keine frei wählbaren
Root-Hooks oder systemd-Units aus dem Repository. Schema 1 liefert eine gemeinsame
SQLite-Datei und einen Wartungsjob für beliebig viele Formulare einer Website.
Eine eigene fachliche Tabellenstruktur bleibt der Website überlassen.

`forms.config.example.json` enthält exakt folgende String-Felder:

```json
{
  "FORMS_ENABLED": "false",
  "FORMS_TEST_MODE": "false",
  "FORMS_ORIGIN": "",
  "FORMS_SECRET": "",
  "FORMS_EMAIL_DOMAINS": "",
  "FORMS_PRIVACY_NOTICE": "",
  "FORMS_RETENTION_DAYS": "0",
  "FORMS_ADMIN_USER": "",
  "FORMS_ADMIN_PASSWORD_HASH": "",
  "FORMS_DB": "",
  "SMTP_HOST": "",
  "SMTP_PORT": "",
  "SMTP_FROM": "",
  "SMTP_SECURE": "false",
  "SMTP_REQUIRE_TLS": "true",
  "SMTP_USER": "",
  "SMTP_PASSWORD": ""
}
```

Die Website liest den privaten JSON-Pfad aus `FORMS_CONFIG`. Sie muss diese
Felder berücksichtigen: deaktiviert keine Annahme/kein Versand; Testmodus ohne
Versand; Herkunft prüfen; Domainbeschränkung, Aufbewahrung und Datenschutzhinweis
fachlich umsetzen. Verwaltungszugänge benötigen einen gesalzenen scrypt-Hash und
HTTPS. Mailaufträge mit den Formulardaten transaktional speichern und bei
SMTP-Ausfall später wiederholen (mindestens einmal, keine Exakt-einmal-Zusage).
Ausgaben dürfen keine Geheimnisse, Empfänger oder personenbezogenen Werte enthalten.
`maintenance.mjs` verarbeitet Queue/Aufbewahrung; `admin.mjs` stellt interaktive
Verwaltungsfunktionen bereit. `backup.mjs` gehört zum Paketvertrag, wird vom
Installer aber nicht ausgeführt: dessen Backup nutzt eigenen Python-sqlite3-Code.

## Betrieb

- Private Datei: `/etc/astrodeploy-runtime/forms.json`, `root:astrorun`, `0640`;
  Verzeichnis `0750`. `/etc/astrodeploy` bleibt `0700`.
- `FORMS_CONFIG=/etc/astrodeploy-runtime/forms.json` in der gemeinsamen
  runtime.env. Kein Zugriff für astrobuild.
- Datenbank: `/srv/astro/<Projekt>/data/forms.sqlite`. Secret wird durch den
  Installer erzeugt. Vorhandene private Werte werden bei Updates erhalten.
- Anmeldung/Verarbeitung zunächst deaktiviert; SMTP-Host, Port und Absender
  bleiben leer. Keine Hochschul-/MakerLab-Werte werden übernommen. SMTP und
  STARTTLS mit dem eigenen Betreiber abstimmen, Zertifikatsprüfung beibehalten.
- `astroctl forms-admin` startet das gepackte Werkzeug interaktiv als astrorun.
  Keine Passwörter als Argumente übergeben. Hash administrativ in JSON eintragen.
- `astroctl forms-backup` sichert die profilzugehörige SQLite-Datei einschließlich
  bestätigter WAL-Inhalte. Sicherungen im Datenverzeichnis privat extern sichern.
- `astroctl status` und `doctor` prüfen aktives Profil und passende Config-/Datenpfade.

Beide Profile nutzen denselben Installer-Wartungsdienst mit historischem Namen
`astro-registration-maintenance`, dieselbe Sandbox und dieselbe Aktivierungs- und
Rollbacklogik. Pro Website ist genau ein Profil ausgewählt. Der Worker verwendet
den Release-Node und einen explizit profilbezogenen Starttest; eine alte
REGISTRATION_CONFIG kann das Formularprofil nicht aktivieren. Wechsel zwischen
Profilen migriert keine fachlichen Daten und übernimmt keine privaten Werte des
anderen Profils. Alte Konfiguration/Daten bleiben für einen Rollback erhalten.

Für das Profil werden Access-Logs in der vorhandenen nginx-Proxy-Location
unterdrückt; ACLs und TLS bleiben erhalten. Alle Formulare benötigen geprüfte
Herkunfts-/Proxywerte und einen passenden Healthcheck. Details zu Sandbox,
Sicherung und Rollback: [Laufzeitbetrieb](workshop-registration.md).

## Kompatibilität und Abnahme

`workshop-registration` behält seinen ursprünglichen Vertrag, seine privaten
Pfade und die bestätigten Workshop-SMTP-Vorgaben. Allgemeine Formulare erfordern
keine events.json, Workshopmodule oder MakerLab-Repo-URL. Bestehende
`registration-admin`/`registration-backup` bleiben als Befehlsnamen verfügbar;
beide Befehlsnamenspaare bedienen das aktive Profil.

Vor Produktivbetrieb das Website-Paket und die komplette Formularverarbeitung
im ausdrücklich freigegebenen Debian-13-Test-LXC abnehmen: effektive Rechte,
Testmodus, SMTP-Ausfall, SQLite-Persistenz, Kapazitäts-/Validierungsregeln,
Missbrauchsschutz, Backup und Rollback. Kein Setup auf dem Entwicklungsrechner
und kein Mailversand ohne gesonderten Auftrag.
