# Arbeitsauftrag: optionale Workshop-Anmeldung in AstroDeploy-LXC

## Auftrag und Ausgangslage

Erweitere **dieses Installer-Projekt AstroDeploy-LXC** um ein ausdrücklich wählbares Laufzeitprofil für die Technik-MakerLab-Website. Ziel ist eine frische Installation im zurückgesetzten Debian-13-LXC. Der Auftraggeber hat am 06.11.2026 bestätigt: Es existieren noch keine echten Workshop-Anmeldungen, IP-/SMTP-Einstellungen sind vorhanden, ein neuer Deploy-Key darf erstellt werden. Keine Datenmigration und kein zweites Deploymentverfahren einführen.

Diese Anweisung wurde anhand des Installer-Stands `db75cabf64a70d265bcbb8bde018f9e577c1b7ee` erstellt. Vor Umsetzung aktuellen Stand und AGENTS.md lesen, vorhandene Änderungen erhalten. Der Auftrag betrifft Erweiterung und Tests des Installers; keinen Container auf dem Entwicklungsrechner einrichten oder zurücksetzen und ohne separaten Auftrag keine echten E-Mails versenden. Noch keine Implementierung dieser Erweiterung behaupten.

Die Website ist ein separates Repository: `know-how-schmiede/technik-makerspace-website`, Branch `main`. Sie enthält Astro 7 mit Node-Adapter, statische Inhaltsseiten und dynamische Workshopseiten. Die Website-Dateien dieses Arbeitsauftrags müssen vor dem LXC-Test in ihrem Branch verfügbar sein.

## Vorhandenes weiterverwenden

- `lib/astrodeploy.py` erkennt bereits `dist/server/entry.mjs`, richtet `astro-site.service` ein und erzeugt nginx-Proxy auf `127.0.0.1:4321`.
- Node 24, Versionsbindung an den Release, `current`/`previous`, Rollback, Build-Sandbox und sicheres tar-Handling existieren bereits.
- Git/Build als **astrobuild**, Website und neue Jobs als **astrorun**. Root bleibt Orchestrator und führt niemals Website-/npm-Code aus.
- Im Modus **auto** Originalkonfiguration beibehalten. Website besitzt den Adapter bereits; keine erzwungene Serverumstellung, kein automatisches Astro-Upgrade und kein pauschales Nachinstallieren des neuesten Adapters.
- `/etc/astrodeploy/runtime.env` ist für Laufzeitvariablen vorhanden. Das dauerhafte, für astrorun schreibbare Datenverzeichnis ist `/srv/astro/<Projekt>/data`.
- Der heutige Artefaktumfang `dist`, `node_modules`, `package.json`, `package-lock.json` reicht aus. Kein allgemeines Kopieren des Quellrepositories und keine Erweiterung auf beliebige private Dateien nötig.

Keinen zweiten Webdienst `makerlab.service`, keinen zweiten Node-Port und keinen parallelen Website-Installer einführen. Das frühere `deploy/update-lxc.sh` der Website ist stillgelegt.

## Neuer Artefaktvertrag der Website

`npm run build` führt im postbuild `scripts/package-registration-runtime.mjs` aus. Das vollständige Zusatzpaket liegt danach unter `dist/server/registration/` und wird vom bestehenden tar-Mechanismus bereits erfasst. Es enthält:

```text
dist/server/registration/
  profile.json
  scripts/registration-maintenance.mjs
  scripts/registration-admin.mjs
  src/server/registration-config.mjs
  src/server/registrations.mjs
  src/server/registration-mail.mjs
  src/content/events.json
  deploy/registration.config.example.json
  deploy/backup-registration-db.mjs
```

Die Module nutzen `node:sqlite` und die mitgelieferte npm-Abhängigkeit Nodemailer. Die relative Struktur ist absichtlich erhalten, sodass kein Quellcheckout zur Laufzeit benötigt wird. Private JSON-Konfiguration, SQLite, `.env` und Deploy-Schlüssel sind **nicht** enthalten.

Die Website liefert unter `profile.json` diesen Vertrag; es ist eine vorbereitete Schnittstelle, im Installer noch nicht implementiert:

```json
{
  "schemaVersion": 1,
  "id": "workshop-registration",
  "config": {
    "template": "dist/server/registration/deploy/registration.config.example.json",
    "filename": "registration.json",
    "environmentVariable": "REGISTRATION_CONFIG",
    "dataFileFields": { "REGISTRATION_DB": "workshops.sqlite" }
  },
  "jobs": [{
    "id": "registration-maintenance",
    "entry": "dist/server/registration/scripts/registration-maintenance.mjs",
    "intervalSeconds": 60
  }],
  "tools": {
    "admin": "dist/server/registration/scripts/registration-admin.mjs",
    "backup": "dist/server/registration/deploy/backup-registration-db.mjs"
  }
}
```

Für die erste Version ausschließlich Schema 1 und dieses bekannte Profil unterstützen. Kein allgemeiner Root-Hook-/Shellskript-Baukasten. Paketmetadaten stammen aus einem unprivilegierten Build und sind untrusted: Größe begrenzen, Typen/Schlüssel/IDs/Pfade strikt validieren, absolute Pfade, `..`, Symlink-Ausbrüche, fehlende Dateien, neue Zeilen, `%`-/Shell-/systemd-Injektionen ablehnen. Nur reguläre Dateien innerhalb des sicher extrahierten Releases zulassen. Die beschriebenen Befehle werden als einzelne Argumente ausgeführt, niemals `shell=True` oder als JSON-Shellcode.

## Gewünschte Erweiterungen

### 1. Explizite Auswahl und Abwärtskompatibilität

Im Setup optional fragen: „Workshop-Anmeldung mit Konfigurationsdatei und Wartungstimer einrichten?“ Keine automatische Aktivierung nur aufgrund einer Repo-Datei. Die Profileinstellung in der root-eigenen Installer-Konfiguration speichern. Bei alten Installationen ohne neues Feld bleibt das bisherige Verhalten erhalten. Ohne gewähltes Profil keine neuen Dateien, Dienste, Fragen oder geänderten Berechtigungen für andere Websites.

Nach dem Build das gewählte Profil im geprüften Release validieren und dessen aktivierte Version/Job-Metadaten in `release.json` speichern. Ein fehlendes oder ungültiges ausgewähltes Profil muss vor Änderung von `current` mit verständlicher Fehlermeldung abbrechen. Automatische Redeploys dürfen keine interaktiven Fragen stellen.

### 2. Private Laufzeitkonfiguration

Die neue Datei wird unter **`/etc/astrodeploy-runtime/registration.json`** abgelegt. Eigenes Verzeichnis `root:astrorun`, `0750`, Datei `root:astrorun`, `0640`. Wichtig: `/etc/astrodeploy` ist im heutigen Installer `0700`; eine JSON-Datei darin wäre für astrorun trotz `0640` nicht erreichbar. Dieses bisherige private Verwaltungsverzeichnis **nicht pauschal öffnen**, sondern das neue getrennte Verzeichnis verwenden.

In `/etc/astrodeploy/runtime.env` die Zeile `REGISTRATION_CONFIG=/etc/astrodeploy-runtime/registration.json` ergänzen. Andere Variablen, Kommentare und Rechte erhalten, keine doppelten widersprüchlichen Einträge. Beide Runtime-Dienste erhalten diese EnvironmentFile. Der Build darf weder diese Datei noch JSON-Secrets lesen.

Erstmalig die leere Vorlage aus dem geprüften Release als **Daten** einlesen, bekannte Felder übernehmen, ein Secret mit der vertrauenswürdigen Installer-Implementierung generieren und `REGISTRATION_DB` auf `/srv/astro/<tatsächlicher Projektname>/data/workshops.sqlite` setzen. Zum Secret-Erzeugen keinen Repository-Code als root ausführen. Bestehende Konfiguration einschließlich Secret bei Updates/Fortsetzung/Rollback unverändert erhalten. Niemals private Werte ins Journal oder auf Übersichtsseiten ausgeben.

Vorlage und String-Felder:

- `REGISTRATION_ENABLED="false"`: technische Einrichtung allein öffnet keine Anmeldungen.
- `REGISTRATION_TEST_MODE="false"`: echte Aktivierung erst nach bewusster Betriebsfreigabe; auf Wunsch Testmodus `"true"` ohne Versand.
- `REGISTRATION_ORIGIN`: tatsächliche konfigurierte URL, produktiv HTTPS. Die Website muss diese Domain auch in ihrer Build-Konfiguration `security.allowedDomains` zulassen; abweichende Domain/Port als klaren Prüfpunkt melden, nicht heimlich Astro umschreiben.
- `REGISTRATION_SECRET`: mindestens 32 zufällige Zeichen, dauerhaft erhalten.
- `REGISTRATION_EMAIL_DOMAINS`: vom Betreiber festzulegen; keine Endungen erfinden.
- `REGISTRATION_PRIVACY_NOTICE`: fachlich abzustimmen, kein generischer Rechtstext.
- `REGISTRATION_RETENTION_DAYS`: vom Betreiber festzulegen; `"0"` bedeutet keine automatische Löschung.
- `REGISTRATION_ADMIN_USER`, `REGISTRATION_ADMIN_PASSWORD_HASH`: Verwaltungszugang mit gesalzenem scrypt-Hash.
- Bestätigte SMTP-Vorbelegung: `SMTP_HOST="141.47.2.1"`, `SMTP_PORT="25"`, `SMTP_FROM="MakerLabTechnik@hs-pforzheim.de"`. TLS/Relay sind noch zu prüfen; `SMTP_SECURE="false"`, `SMTP_REQUIRE_TLS="true"` bedeutet STARTTLS, nicht ungeprüft verschlüsselte Verbindung. Zertifikatsprüfung nicht abschalten. Bei Zertifikat für einen DNS-Namen muss dieser nach IT-Abstimmung statt der IP konfiguriert werden.
- `SMTP_USER`, `SMTP_PASSWORD` nur bei Bedarf, niemals in Git.

Es muss nach Setup einen klaren Weg geben, die Datei zu bearbeiten und die verbleibenden Angaben zu sehen, ohne Secrets auszugeben. Für Admin-Passwort/Hash das gepackte Werkzeug nur als **astrorun** und interaktiv ausführen; dessen Ausgabe nicht ins Deploymentjournal übernehmen. Keine echten Testmails während einer Standardinstallation versenden.

### 3. Wartungsdienst und Timer

Einen Installer-verwalteten oneshot-Dienst, z. B. `astro-registration-maintenance.service`, und zugehörigen Timer im Abstand von 60 Sekunden ergänzen. Ein einziger Job bedient Mailwarteschlange und Aufbewahrungsfrist.

- Benutzer/Gruppe `astrorun`, keine Root-Rechte und kein npm zur Laufzeit.
- `WorkingDirectory=/srv/astro/<Projekt>/current`.
- Node-Binary aus dem **aktiven Release** verwenden, nicht `/usr/bin/node` und keinen neuen globalen Node installieren. Das muss auch nach Node-Update und Rollback stimmen.
- Einstieg `dist/server/registration/scripts/registration-maintenance.mjs`.
- Dieselbe `/etc/astrodeploy/runtime.env` wie der Webdienst.
- Sandbox wie Runtime: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `UMask=0077`, Schreibrecht ausschließlich auf das persistente Datenverzeichnis. Keine Freigabe des Build-Verzeichnisses oder der Root-Konfigurationen.
- Sinnvolle Zeitbegrenzung; laufender Job darf nicht parallel noch einmal gestartet werden. Im deaktivierten Profil beziehungsweise bei deaktivierter Anmeldung darf keine Mail versendet werden. Der Worker beendet sich dann mit einem knappen Hinweis.
- Die Website speichert Mailaufträge transaktional mit der Anmeldung und wiederholt Fehler. SMTP-Ausfall darf die gespeicherte Anmeldung nicht verlieren. Es gilt mindestens einmal, keine Zusage exakt einmal.

Der Installer erzeugt die Unit aus geprüftem eigenen Code. Keine systemd-Unit aus dem Website-Repo unkontrolliert installieren.

### 4. Aktivierung, Rollback und Aufräumen

Aktivierungsablauf mit dem bestehenden globalen Lock abstimmen: laufenden Job und Timer geordnet stoppen, Release wechseln, Units auf Release-Node/Profil abgleichen, Webdienst starten und Healthcheck prüfen; erst anschließend Timer starten. Das alte Release darf während noch laufender Jobs nicht entfernt werden.

Bei Fehlern den vorherigen Release **einschließlich** Node-Version, Profilmetadaten, Job-Units und Timerzustand wiederherstellen. Datenbank/Secret nicht durch Release-Rollback überschreiben. Rückwechsel zu einem Release ohne Profil oder zu einer statischen Website stoppt den Profiltimer, erhält aber private Konfiguration/Daten. Keine fremden Dienste pauschal anhalten. Das optionale Profil verändert das bestehende auto-/static-Verhalten nicht.

### 5. nginx, TLS und Datenschutz

Der bestehende Proxy von nginx zu `astro-site.service` bleibt erhalten. Es wird kein zweiter Webdienst und kein zweiter Proxy auf Port 4321 benötigt.

Für `/anmeldung/` und `/verwaltung/` dürfen keine Abmeldetoken, Zugangsdaten oder personenbezogenen Querywerte im Access-Log landen. Das gezielt in der vorhandenen Proxykonfiguration lösen, beispielsweise durch validierte bedingte Log-Unterdrückung im vorhandenen Location-/http-Kontext. Keine neuen Geschwister-Locations einführen, die bisherige `allow`/`deny`-/Auth-Regeln von `location /` umgehen. Vorhandene TLS-/Certbot-/Proxy-/Netz-/VPN-Regeln vollständig erhalten. `nginx -t` vor Reload, Rücksicherung bei Syntaxfehlern.

HTTP-/TLS-Proxy-Modus des Installers weiterverwenden. HTTPS für echte Anmeldung und Basic-Auth sicherstellen. Keine Zertifikate oder Hochschul-Netzregeln erfinden. Weitergeleitete Host-/Protokollwerte müssen zum vorhandenen vertrauenswürdigen Proxy-Modell und Astros Herkunftsprüfung passen.

### 6. Status, Diagnose und Sicherung

`astroctl status`/`doctor` um gewähltes Profil, Worker-/Timerstatus, Konfigurationslesbarkeit als astrorun und Datenverzeichnisrechte ergänzen. Keine Passwörter, Secret, Empfänger, Datenbankinhalte oder Abmeldetoken ausgeben. Prüfen, dass ein veralteter Runtime-Verweis auf `/var/lib/makerlab` oder eine nicht durchquerbare Konfigurationsdatei verständlich gemeldet wird.

Die Website bietet `/health/`: HTTP 200 bei gültigem Serverbetrieb und deaktivierter Anmeldung; bei aktivierter Anmeldung prüft sie zusätzlich Konfiguration und SQLite, bei Fehler HTTP 503. Kein SMTP-Test und keine personenbezogenen Inhalte. Diesen Endpunkt im Setup für dieses Profil vorschlagen. Healthcheck eines anderen bestehenden Projekts nicht pauschal ersetzen.

Konsistente SQLite-Sicherung einschließlich WAL erklären und optional in die bestehenden Verwaltungsbefehle integrieren. Root darf dafür nur vertrauenswürdigen eigenen Installer-Code verwenden, beispielsweise Python sqlite3-Backup. Das Website-Backupwerkzeug niemals als root starten; alternativ als astrorun in einen geschützten Unterordner von `data` sichern und administrativ übernehmen. Kein blindes Kopieren nur der aktiven Hauptdatei.

## Tests und Abnahme

Die in AGENTS.md vorgeschriebenen Prüfungen ausführen. Neue Unit-Tests mindestens für:

1. Bestehende Konfiguration ohne Profil bleibt unverändert nutzbar, statische Websites erhalten keine Jobs.
2. Profilwahl ist explizit; fehlende/ungültige Version/Typen/Pfade/Dateien/IDs, Symlink-Ausbrüche und Unit-Injektionen werden abgewiesen.
3. Erstkonfiguration erhält korrektes Secret und tatsächlichen Projekt-Datenpfad; Updates überschreiben keine privaten Werte.
4. Elternverzeichnis-/Dateirechte erlauben astrorun das Lesen der JSON-Datei, astrobuild dagegen nicht. `/etc/astrodeploy` bleibt privat.
5. Runtime und Worker verwenden identischen Config-Verweis sowie Node des jeweiligen Releases, auch nach Rollback.
6. Build- oder Aktivierungsfehler verändern keine Daten; fehlgeschlagener Healthcheck stellt auch Timer/Jobzustand wieder her.
7. Profilentfernung/static-Wechsel stoppt Job/Timer ohne Löschen von Daten. Aktive Worker verhindern vorzeitiges Release-Cleanup.
8. nginx-Anpassung erhält bestehende ACLs/TLS; Token-URLs erscheinen nicht im Access-Log.
9. Unprivilegiertes Buildarchiv enthält das Laufzeitpaket unverändert; kein zusätzlicher Quellcheckout nötig und keine privaten Dateien im Artefakt.
10. SMTP-Ausfall oder deaktivierte Anmeldung erzeugt keinen Datenverlust/ungewollten Versand; Logs enthalten keine Secrets.

Danach in einem **ausdrücklich freigegebenen frischen Debian-13-Test-LXC** prüfen:

- Installer per bestehendem GitHub-Weg laden, privates Website-Repo mit neuem read-only Deploy-Key anbinden.
- Projekt `website`, Modus `auto`, bereits vorhandenen Adapter beibehalten, Profil auswählen, Healthcheck `/health/`.
- Erster Build und timerbasierter Folgedeploy; Tests mit erfundenen Daten und `REGISTRATION_TEST_MODE="true"`.
- Formular, DB-Persistenz über Redeploy/Neustart, Kapazitätsgrenze, Abmeldung, Zugriffsschutz/CSV und gepackter Worker.
- Absichtlich defekter Build und fehlgeschlagener Start mit vollständiger Rücksicherung.
- Mailversand erst nach separatem Auftrag an eine genehmigte Testadresse; echte Anmeldungen erst nach fertigen Domains/Datenschutz/TLS/SMTP.

README, Installations-, GitHub-, Variablen-, Update-, Rollback-, Troubleshooting- und Testdokumentation im Installer-Projekt entsprechend aktualisieren. Konkrete Version und wirklich ausgeführte Tests melden. Noch offene Linux-/LXC-Abnahmen ausdrücklich nennen.

## Fertig-Kriterium

Ein frischer LXC lässt sich mit **einem** AstroDeploy-LXC-Setup installieren. Danach genügt ein Website-Push für weitere Releases. Ein Betreiber kann die vorhandene SMTP-Konfiguration ergänzen, Datenschutz/Domains festlegen und die Anmeldung bewusst freischalten. Es gibt keinen separaten Website-Updater, keinen konkurrierenden Webdienst und keine private Konfiguration in Git oder `dist`.
