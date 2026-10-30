# Fehlersuche

Zuerst `astroctl status`, `astroctl doctor` und `astroctl logs` aufrufen.

| Problem | Prüfung |
| --- | --- |
| Permission denied (publickey) | Deploy-Key im richtigen GitHub-Repository hinterlegt? |
| Branch nicht gefunden | Branchname einschließlich Groß-/Kleinschreibung prüfen |
| Buildfehler | Lokal mit Node 24 npm ci --include=dev --engine-strict und npm run build ausführen |
| entry.mjs fehlt | Astro-Node-Adapter mit standalone und output server konfigurieren |
| Healthcheckfehler | Pfad muss ohne Login/Redirect HTTP 200 liefern; Domain und Host prüfen |
| 502 | systemctl status astro-site und journalctl -u astro-site -n 100 |
| Keine automatischen Updates | Pause, Timerstatus, neuen Commit und zehnminütige Fehlerpause prüfen |
| Zertifikat fehlt | DNS, IPv6, Ports 80/443 und Router prüfen; Setup fortsetzen |
| Speicher voll | df -h; Container vergrößern, aktive/vorherige Releases behalten |

Build-Ausgaben werden zum Schutz von Secrets nicht gespeichert oder ins Journal
geschrieben. Zur Diagnose denselben Commit lokal mit Node 24 und ungefährlichen
Testvariablen bauen. Die Website selbst kann Geheimnisse loggen; ihre eigene
Protokollierung entsprechend gestalten.

Uploads, SQLite und Sessions explizit nach /srv/astro/PROJEKT/data konfigurieren.
Das Tool erzeugt keine automatischen Symlinks für Anwendungsdaten.
doctor prüft grundlegende Rechte, aber keine vollständigen ACLs oder öffentliche
Erreichbarkeit und ersetzt kein Sicherheitsaudit.
