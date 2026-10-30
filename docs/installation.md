# Installation und HTTPS

Die Schritte in der README in der Konsole des Debian-Containers ausführen.
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
