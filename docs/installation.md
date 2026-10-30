# Installation und HTTPS

## Direkt aus GitHub installieren

In Proxmox die Konsole des Debian-13-Containers öffnen und als root anmelden.
Wenn Updates und Python 3 bereits installiert sind, kannst du direkt fortfahren.
Git und ca-certificates bei Bedarf mit `apt-get install -y git ca-certificates`
nachinstallieren.

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

Verwaltete Pfade: /etc/astrodeploy, /var/lib/astrodeploy, /var/lib/astrobuild,
/srv/astro, /opt/astrodeploy/node, /usr/local/lib/astrodeploy,
/usr/local/bin/astroctl, drei systemd-Units und der Nginx-vHost astrodeploy.
Ein automatischer Deinstaller ist nicht enthalten.
