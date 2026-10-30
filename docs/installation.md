# Installation und HTTPS

## Direkt aus GitHub installieren

In Proxmox die Konsole des frisch zurückgesetzten Debian-13-Containers öffnen
und als root anmelden. Einmalig die Voraussetzungen installieren:

```bash
apt-get update
apt-get install -y git ca-certificates python3
```

Sind diese bereits installiert, direkt mit Git fortfahren. Der Starter kann
fehlendes Python alternativ nach Rückfrage selbst installieren.

Ohne manuellen ZIP-Download oder Kopieren vom PC:

```bash
git clone https://github.com/know-how-schmiede/AstroDeploy-LXC.git /root/AstroDeploy-LXC
```

Code und Version prüfen, danach das Setup starten:

```bash
cd /root/AstroDeploy-LXC && bash bin/setup.sh
```

Ist das Repository schon im Container vorhanden, statt erneutem Klonen
`git -C /root/AstroDeploy-LXC pull --ff-only` verwenden. Erst nach erfolgreicher
Aktualisierung das Setup starten. Lokale Änderungen werden dabei nicht verworfen.

Die weiteren Eingaben erklärt die [README](../README.md). Im Setup die GitHub-URL
deiner **Astro-Website** eingeben; das Installer-Repository ist ein anderes Projekt.
Die Installation braucht Internet und lädt Pakete automatisch herunter.

## Die Eingaben beim Neustart

1. Das Setup zeigt die erkannten Container-IPv4-Adressen.
2. Website-Repository eingeben; bei privaten Projekten „privat“ bestätigen.
   Die URL wird dann automatisch für SSH vorbereitet.
3. Branch und Projekt-Unterordner auswählen, meist `main` und `.`.
4. Vorgeschlagene Container-IP mit Enter übernehmen, oder eine Domain eingeben.
5. Für einen ersten LAN-Test HTTP und Healthcheck `/` wählen.
6. Betriebsmodus `auto` übernehmen. Die ursprüngliche Rendering-Konfiguration
   bleibt erhalten; statische Websites werden direkt mit Nginx ausgeliefert.
   Nur für eine bewusste SSR-Umstellung `server` und die optionale Vorbereitung wählen.
7. Zusammenfassung bestätigen. Bei privatem Repository den neu erzeugten
   öffentlichen Deploy-Key in GitHub hinterlegen, ohne Schreibzugriff.
8. Build und HTTP-Prüfung abwarten, anschließend die angezeigte Website öffnen
   und `astroctl doctor` im Container ausführen. Auch mehrere Unterseiten testen;
   der automatische Healthcheck prüft nur den eingestellten Pfad.

Nach einem Container-Reset ist der Deploy-Key neu. Ein Schlüssel der vorherigen
Installation reicht dann nicht; den neu angezeigten öffentlichen Key eintragen.
Die IP wird automatisch erkannt, aber nicht fest konfiguriert. Bei DHCP eine
Reservierung im Router setzen. Mehrere IPs werden angezeigt; prüfen, welche aus
deinem LAN erreichbar ist. Ohne erkannte IPv4 kann eine Domain manuell eingegeben werden.

Nur Repository-Code einsetzen, dem du vertraust: npm-Skripte haben Netzwerkzugriff
und können Build-Variablen sowie den read-only Deploy-Key dieses Projekts lesen.
Der Installer ist keine Sandbox für fremde Projekte.

## HTTPS-Modi

`http`: erster Test im vertrauenswürdigen LAN. Für produktive Anmeldungen HTTPS verwenden.

`letsencrypt`: Domain mit passenden A-/gegebenenfalls AAAA-Einträgen auf den Server
richten. Router/Firewall müssen Ports 80/443 zum Container durchlassen. Das Tool
ändert keine Router- oder Firewallregeln. Die Zustimmung zu den ACME-Bedingungen
wird im Setup abgefragt. Certbot richtet HTTPS und seinen Erneuerungstimer ein.
Danach `certbot renew --dry-run` prüfen.

`proxy`: HTTPS endet auf einem vorhandenen Proxy. Domain und dessen tatsächliche
IP/CIDR eintragen, nicht pauschal das gesamte LAN. Der Proxy muss Host und
X-Forwarded-Proto korrekt übermitteln. Nginx ersetzt eingehende Client-IP-Header.
Mehrstufige Proxy-Ketten benötigen eine eigene geprüfte Konfiguration.
Astro-Origin-/CSRF-Prüfungen nicht pauschal deaktivieren.

## Fortsetzen

Nach Abbruch dasselbe Setup erneut starten. Konfiguration und Secrets bleiben
erhalten. Bereits eingerichtete Nginx-/systemd-Dateien werden bei Fortsetzung
nicht neu erzeugt, damit Certbot-Anpassungen erhalten bleiben. Dies ist kein
allgemeiner Reparatur- oder Rekonfigurationsmodus. Änderungen an Domain/Port
erfordern abgestimmte Änderungen von JSON, Units und Nginx.

Der frühere Fehler beim Start aus /root ist behoben: Git-/Build-Aufrufe verwenden
nun /var/lib/astrobuild als zugängliches Arbeitsverzeichnis. Der normale Einstieg
`bash bin/setup.sh` funktioniert damit auch unter /root. Der Umweg über /tmp ist unnötig.

Verwaltete Pfade: /etc/astrodeploy, /var/lib/astrodeploy, /var/lib/astrobuild,
/srv/astro, /opt/astrodeploy/node, /usr/local/lib/astrodeploy,
/usr/local/bin/astroctl, drei systemd-Units und der Nginx-vHost astrodeploy.
Ein automatischer Deinstaller ist nicht enthalten.
