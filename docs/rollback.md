# Rollback

`astroctl rollback` aktiviert das vorherige erfolgreiche Release samt Node-Version
und prüft lokal HTTP 200. Bei Fehler wird das zuvor laufende Release wieder
gestartet. Die Automatik bleibt dauerhaft pausiert.

Problem in GitHub korrigieren, mit `astroctl deploy` testen, dann
`astroctl resume` ausführen. Manuelle Deployments sind während einer Pause möglich.
Das erste Deployment hat noch keinen Vorgänger. Datenbanken, Uploads und
Debian-Pakete werden nicht zurückgesetzt.
