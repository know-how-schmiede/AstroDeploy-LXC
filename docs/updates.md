# Updates

Website: Commit mit Lockdatei pushen. Der Timer baut mit npm ci und npm run build;
er aktualisiert keine Abhängigkeitsversionen eigenständig.

Debian: `astroctl update --check`, danach `astroctl update --system`. Ein Probelauf
zeigt Änderungen vor der Bestätigung. Kein full-upgrade oder automatische
Paketentfernungen. Dienste können neu starten. apt-Sperren nicht löschen.
Optionale Sicherheitsupdates beschränken sich auf trixie-security, ohne Reboot.
Konfiguration: /etc/apt/apt.conf.d/52astrodeploy. Prüfung:
`unattended-upgrade --dry-run --debug`. Proxmox-Host separat warten.

Node: `astroctl update --node` installiert die neueste Node-24-LTS-Version
parallel, prüft die offizielle SHA-256-Summe und baut neu. Das Release enthält
die dazugehörige Node-Version; Startfehler wechseln beide gemeinsam zurück.
Alte Node-Verzeichnisse werden nicht automatisch gelöscht. Kein Major-Wechsel.

Werkzeuge: `astroctl update --tools` zeigt nur die installierte Version und
den manuellen Weg. Eine veröffentlichte Release-Quelle und authentifizierte
Updateautomatik fehlen noch. Geprüfte neue Version herunterladen, Container
sichern, Tests ausführen und beide Python-Dateien nach /usr/local/lib/astrodeploy
sowie den Starter nach /usr/local/bin/astroctl übernehmen. Root-Eigentum,
Python-Modus 644, Starter 755. Vorherige Dateien sichern. Schema-/Unitänderungen
brauchen eine versionsspezifische Migration. Kein ungeprüftes main als root ausführen.
