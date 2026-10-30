# Fehlersuche

Zuerst `astroctl status`, `astroctl doctor` und `astroctl logs` aufrufen.

| Problem | Prüfung |
| --- | --- |
| Permission denied (publickey) | Deploy-Key im richtigen GitHub-Repository hinterlegt? |
| failed to stat /root/AstroDeploy-LXC: Permission denied | Installer-Kopie mit git pull --ff-only aktualisieren und bash bin/setup.sh erneut starten; Fortsetzen bestätigen. Rechte von /root nicht lockern. |
| Branch nicht gefunden | Branchname einschließlich Groß-/Kleinschreibung prüfen |
| Buildfehler | Lokal mit Node 24 npm ci --include=dev --engine-strict und npm run build ausführen |
| Node-Adapter fehlt | Automatische Container-Vorbereitung im Setup einschalten; siehe container-build.md |
| Container-Vorbereitung benötigt das npm-Buildskript "astro build" | Auf Installer 0.2.1 aktualisieren; dieser unterstützt auch npm run check && astro build. Anschließend Setup fortsetzen, ohne Container-Reset. |
| Adapter-Installation fehlgeschlagen | Feste Adapter-Version muss zu Astro passen; npm erzwingt keine inkompatiblen Peer-Abhängigkeiten |
| entry.mjs fehlt | Container-Vorbereitung prüfen; andernfalls Astro-Node-Adapter mit standalone und output server konfigurieren |
| Healthcheckfehler | Pfad muss ohne Login/Redirect HTTP 200 liefern; Domain und Host prüfen |
| 502 | systemctl status astro-site und journalctl -u astro-site -n 100 |
| HTTP 500 mit undefined filter oder RenderUndefinedEntryError nach SSR-Vorbereitung | Statisches Projekt wurde auf SSR umgestellt. Auf 0.3.0 aktualisieren, Setup fortsetzen und auto wählen; siehe static-hosting.md |
| astro-site ist inactive/disabled | Bei statischen Releases beabsichtigt: Nginx liefert die Dateien direkt aus |
| Keine automatischen Updates | Pause, Timerstatus, neuen Commit und zehnminütige Fehlerpause prüfen |
| Zertifikat fehlt | DNS, IPv6, Ports 80/443 und Router prüfen; Setup fortsetzen |
| Speicher voll | df -h; Container vergrößern, aktive/vorherige Releases behalten |

Build-Ausgaben werden zum Schutz von Secrets nicht gespeichert oder ins Journal
geschrieben. Fehlermeldungen nennen die Phase. Eine weitere Diagnose kann im
Container in einer separaten Build-Kopie als astrobuild mit der Node-Version
unter /opt/astrodeploy/node erfolgen; kein npm/npx als root ausführen.
Die Website selbst kann Geheimnisse loggen; ihre eigene
Protokollierung entsprechend gestalten.

Uploads, SQLite und Sessions explizit nach /srv/astro/PROJEKT/data konfigurieren.
Das Tool erzeugt keine automatischen Symlinks für Anwendungsdaten.
doctor prüft grundlegende Rechte, aber keine vollständigen ACLs oder öffentliche
Erreichbarkeit und ersetzt kein Sicherheitsaudit.
