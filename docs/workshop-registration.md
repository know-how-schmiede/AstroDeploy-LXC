# Optionale Workshop-Anmeldung (0.4.0)

Das Setup fragt ausdrücklich nach der Workshop-Anmeldung. Nur bei Auswahl wird
`runtime_profile: "workshop-registration"` gespeichert. Alte Konfigurationen ohne
dieses Feld behalten ihr Verhalten. Für Technik-MakerLab: Projekt `website`,
Branch `main`, Modus `auto`, vorhandenen Node-Adapter behalten und `/health/`
als Healthcheck wählen. Kein zweiter Webdienst, kein zweiter Updater.

Ab 0.5.0 erfolgt die Auswahl über `keines`, `forms` oder
`workshop-registration`. Diese Seite beschreibt das kompatible Workshop-Profil;
andere Repositories verwenden das [allgemeine Formularprofil](forms.md).

Vor dem LXC-Test muss das Website-Repository
`know-how-schmiede/technik-makerspace-website` den postbuild-Packer enthalten.
Der Build muss den Schema-1-Vertrag aus dem Arbeitsauftrag samt Dateien nach
`dist/server/registration/` schreiben. Der vorhandene unprivilegierte tar-Transfer
übernimmt dieses Verzeichnis; kein Quellcheckout wird zur Laufzeit benötigt.
Unbekannte Verträge, fehlende Dateien, Symlinks, zusätzliche Schlüssel oder
abweichende Jobpfade werden vor dem Releasewechsel abgewiesen.

## Private Einstellungen und Freigabe

`/etc/astrodeploy-runtime` gehört `root:astrorun`, Modus `0750`;
`registration.json` darin hat `0640`. `/etc/astrodeploy` bleibt privat (`0700`).
Build-Benutzer dürfen keiner Runtime-Gruppe angehören. Systemd liest
`/etc/astrodeploy/runtime.env` für beide Dienste; dort wird genau ein
`REGISTRATION_CONFIG=/etc/astrodeploy-runtime/registration.json` eingetragen.
Kommentare, andere Variablen und Dateirechte bleiben erhalten. Fortsetzungszeilen
müssen vor automatischer Bearbeitung aufgelöst werden.

Als root mit `nano /etc/astrodeploy-runtime/registration.json` bearbeiten.
Vorhandene Werte und das dauerhaft generierte Secret bleiben bei Folgedeploys
und Rollbacks erhalten. Die Datenbank liegt unter
`/srv/astro/<Projektname>/data/workshops.sqlite`.

Die Erstkonfiguration setzt `REGISTRATION_ENABLED="false"` und
`REGISTRATION_TEST_MODE="false"`. Technische Einrichtung erteilt keine
Betriebsfreigabe. Folgende Angaben bewusst vervollständigen:

- `REGISTRATION_ORIGIN`: konfigurierte URL, produktiv HTTPS. Domain und Port
  müssen zu Astro `security.allowedDomains` und zum vertrauenswürdigen Proxy
  passen. Der Installer schreibt die Astro-Konfiguration nicht um.
- `REGISTRATION_EMAIL_DOMAINS`, `REGISTRATION_PRIVACY_NOTICE` und
  `REGISTRATION_RETENTION_DAYS`: Betreiberentscheidung; `"0"` bedeutet keine
  automatische Löschung. Keine erfundenen Domains oder Rechtstexte verwenden.
- `REGISTRATION_ADMIN_USER` und `REGISTRATION_ADMIN_PASSWORD_HASH`: gesalzener
  scrypt-Hash über `astroctl registration-admin` mit den vom Website-Werkzeug
  dokumentierten interaktiven Optionen. Das gepackte Werkzeug läuft ausschließlich
  als astrorun, Ausgabe wird nicht durch den Installer aufgezeichnet. Passwort
  niemals als Befehlsargument übergeben. Werkzeug darf die root-eigene JSON-Datei
  nicht schreiben; den erzeugten Hash administrativ eintragen.
- SMTP-Vorbelegung: `141.47.2.1`, Port `25`, Absender
  `MakerLabTechnik@hs-pforzheim.de`, `SMTP_SECURE="false"`,
  `SMTP_REQUIRE_TLS="true"` (STARTTLS). TLS/Relay mit IT prüfen; falls das
  Zertifikat einen DNS-Namen verlangt, den abgestimmten Namen verwenden.
  Zertifikatsprüfung niemals abschalten. Zugangsdaten nur bei Bedarf ergänzen.

Nach Änderungen `systemctl restart astro-site`. `astroctl doctor` zeigt
Prüfpunkte ohne private Werte. Zunächst mit erfundenen Daten und
`REGISTRATION_TEST_MODE="true"` ohne Versand abnehmen. Erst nach Freigabe von
HTTPS, Datenschutz, Domains, Admin-Zugang und SMTP echte Anmeldung aktivieren.
Standardsetup und Diagnose versenden keine Testmail.

## Betrieb, Updates und Rollback

`astro-registration-maintenance.service` ist ein gehärteter oneshot als astrorun.
Der Timer wartet 60 Sekunden nach dem letzten Lauf. Ein Dienst kann nicht
gleichzeitig zweimal laufen; Laufzeitbegrenzung 50 Sekunden. Er nutzt dieselbe
EnvironmentFile wie `astro-site`, das aktive Release als Arbeitsverzeichnis und
die Node-Version aus dessen Metadaten. Schreibbar ist nur das Datenverzeichnis.
Ein Installer-ExecCondition überspringt deaktivierte Anmeldung und lehnt aktivierte
Anmeldung mit HTTP-Origin ab. Worker-Ausgaben werden zum Schutz privater Daten
nicht ins Journal übernommen. Queue-Verarbeitung und Testmodus liegen im gepackten
Website-Worker und müssen separat abgenommen werden.

Unter dem globalen Lock werden Timer und laufender Worker vor dem Wechsel
gestoppt. Nach Webstart und Healthcheck startet der Timer. Bei Fehlern werden
vorheriges Release, Node, Profil-Units und vorheriger aktivierter/gestarteter
Timerzustand hergestellt. Secret und Datenbank werden nicht zurückgerollt.
Bei Profilentfernung (`runtime_profile` aus config.json entfernen, neu deployen)
oder Rollback zu einem Release ohne Profil werden ausschließlich die eigenen
Profil-Units entfernt. Private Dateien und Daten bleiben erhalten. Cleanup
entfernt keine alten Releases, solange der Worker aktiv/aktivierend oder sein
Zustand unklar ist. Website-Pushes verwenden weiterhin den bestehenden Deploytimer.

Innerhalb derselben nginx-Proxy-Location wird für das Profil `access_log off`
gesetzt. Das unterdrückt aus Datenschutzgründen alle Access-Logs dieser Location,
einschließlich `/anmeldung/` und `/verwaltung/`. Keine Geschwister-Locations
umgehen ACLs/Auth. Vorhandene ACLs im Proxyblock und TLS/Certbot im Serverblock
bleiben erhalten. Unbekannte Location-Strukturen werden abgewiesen; vor einem
static-Wechsel angepasste Proxyregeln manuell prüfen. Vor Reload läuft `nginx -t`;
bei Syntaxfehler wird die vorherige Locationdatei wiederhergestellt.

## Diagnose und Sicherung

`astroctl status` und `astroctl doctor` zeigen Profil, Worker-/Timerzustand,
Lesbarkeit als astrorun, Verzeichnisrechte und widersprüchliche Config-Verweise.
Alte `/var/lib/makerlab`-Verweise und unerreichbare JSON-Dateien werden gemeldet.
Ein inaktiver oneshot zwischen zwei Läufen ist normal. `/health/` prüft keine
SMTP-Verbindung; bei deaktivierter Anmeldung liefert die Website HTTP 200, bei
aktivierter Anmeldung prüft sie Konfiguration/SQLite und meldet Fehler mit 503.

`astroctl registration-backup` verwendet vertrauenswürdigen Python-sqlite3-Code
als astrorun. Die SQLite-Backup-API übernimmt auch bestätigte WAL-Inhalte und
schreibt eine neue private `workshops-backup-<ID>.sqlite` im Datenverzeichnis.
Diese Datei administrativ in die geschützte externe Sicherung übernehmen;
Sicherungen enthalten personenbezogene Daten. Nicht nur die aktive SQLite-
Hauptdatei kopieren. Das Website-Backupskript wird niemals als root gestartet.
Wiederherstellung nur bei gestopptem Webdienst und Wartungstimer/Worker, mit
bewusster Behandlung vorhandener WAL-/SHM-Dateien und anschließender Prüfung
von Eigentümer astrorun und Modus `0600`. Restore zuerst im Test-LXC abnehmen.

Noch offen: vollständige Debian-13-LXC-Abnahme einschließlich effektiver Rechte,
Timer, Rollback, nginx/TLS/ACLs, gepackter Website-Module, SQLite-Persistenz,
SMTP-Ausfall, Kapazität, Abmeldung, CSV und Testmodus. Mailversand erfordert
einen separaten Auftrag mit genehmigter Testadresse. Das Setup wird niemals
auf dem Entwicklungsrechner ausgeführt.
