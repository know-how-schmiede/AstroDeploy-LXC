# Rollback

`astroctl rollback` aktiviert das vorherige erfolgreiche Release samt Betriebsart
(statisch oder SSR) und bei SSR dessen Node-Version. Es prüft lokal HTTP 200.
Bei Fehler wird das zuvor laufende Release wieder
gestartet. Die Automatik bleibt dauerhaft pausiert.

Problem in GitHub korrigieren, mit `astroctl deploy` testen, dann
`astroctl resume` ausführen. Manuelle Deployments sind während einer Pause möglich.
Das erste Deployment hat noch keinen Vorgänger. Datenbanken, Uploads und
Debian-Pakete werden nicht zurückgesetzt.

## Workshop-Profil

Dies gilt ab 0.5.0 auch für das allgemeine [Formularprofil](forms.md).
Die passende JSON-Datei, Datenbank und Worker-Startbedingung werden aus dem
Releaseprofil bestimmt, auch bei einem Wechsel zwischen beiden Profilen.

Rollback stoppt zuerst Timer und Worker, stellt Release, Node und Profil-Units zusammen um und startet den Timer erst nach erfolgreichem Healthcheck. Bei fehlgeschlagener Aktivierung wird auch der bisherige Timerzustand wiederhergestellt. Rückwechsel ohne Profil stoppt dessen Jobs, erhält JSON, Secret und SQLite. Datenbank-Restore ist ein separater Vorgang; konsistente Sicherung: [Workshop-Anmeldung](workshop-registration.md).
