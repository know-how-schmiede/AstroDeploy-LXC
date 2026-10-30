---
title: "Astro auf Proxmox: Websites aus GitHub automatisch im Debian-Container bereitstellen"
summary: "AstroDeploy-LXC für Anfänger: Debian-13-Container einrichten, GitHub verbinden und Astro-Websites automatisch bauen und mit Nginx ausliefern – inklusive Deploy-Key, Fehlersuche und Rollback."
contentType: tutorial
level: beginner
topics: [linux, astro]
tags: [proxmox, debian, lxc, github, deployment, nginx, astrodeploy, selfhosting]
status: draft
publishedAt: 2026-10-30
updatedAt: 2026-10-30
featured: false
readingTime: 20
seo:
  title: "Astro auf Proxmox deployen: GitHub und Debian-LXC"
  description: "Schritt für Schritt zur eigenen Astro-Website im Debian-13-LXC: GitHub-Zugriff, automatischer Build, statisches Hosting, SSR und Fehlersuche."
---

<!-- Redaktion: Für die spätere Integration diese Datei nach
src/content/knowledge/astro-deployment-proxmox-debian-lxc-github.md kopieren.
Frontmatter entspricht dem vorhandenen knowledge-Schema der Know-How-Schmiede.
Vor Veröffentlichung status und Datumsfelder prüfen. Keine Kursnummer vergeben:
Der Beitrag ist ein eigenständiges Tutorial für die Themen Linux und Astro. -->

Du hast eine Astro-Website in GitHub gespeichert und möchtest sie auf deinem
eigenen Proxmox-Server betreiben? In diesem Tutorial richten wir dafür einen
Debian-Container ein. **AstroDeploy-LXC** übernimmt anschließend den Abruf aus
GitHub, den Build und die Bereitstellung der fertigen Website.

Auch der Build läuft im Container. Du musst dafür auf deinem PC weder Node.js
installieren noch fertige Website-Dateien von Hand auf den Server kopieren.
Deinen Website-Inhalt pflegst du weiter im GitHub-Projekt.

**Lernziel:** Du kannst eine Astro-Website im eigenen Netzwerk bereitstellen,
Änderungen automatisch übernehmen lassen und typische Probleme selbst eingrenzen.

**Stand dieser Anleitung:** AstroDeploy-LXC 0.3.0, Debian 13 und Node 24 LTS.
Das Projekt wird weiterentwickelt. Beginne mit einem Testcontainer und prüfe vor
einem produktiven Einsatz auch Unterseiten, Backups und gegebenenfalls HTTPS.

## 1. Was passiert bei einem Deployment?

Ein **Deployment** ist die Bereitstellung einer neuen Version deiner Website.
Bei Astro entsteht aus dem Quellcode erst durch einen **Build** die Ausgabe,
die ein Webserver ausliefern kann.

Der Ablauf sieht so aus:

```text
Astro-Projekt in GitHub
        |
        | Container prüft den gewählten Branch
        v
Quellcode im Debian-Container
        |
        | Abhängigkeiten installieren und Website bauen
        v
Neues Release erstellen und aktivieren
        |
        | lokalen HTTP-Aufruf prüfen
        v
Website im Browser erreichbar
```

Ein **Repository**, kurz Repo, enthält deine Projektdateien und deren
Änderungshistorie. Ein **Commit** ist ein gespeicherter Änderungsstand. Ein
**Branch** ist eine Entwicklungslinie; in dieser Anleitung verwenden wir `main`.

Der Container prüft GitHub standardmäßig ungefähr jede Minute. Ein neuer Commit
wird zunächst separat gebaut. Währenddessen bleibt die bisherige Version aktiv.
Bei einem Buildfehler wird sie nicht ersetzt. Schlägt die Prüfung nach der
Aktivierung fehl, versucht der Installer die vorherige Version wiederherzustellen.

Das ist keine Garantie für unterbrechungsfreie Updates. Vor allem beim Neustart
eines Node-Servers kann es eine kurze Unterbrechung geben.

## 2. Statische Website oder SSR: Warum diese Unterscheidung wichtig ist

Astro unterstützt unterschiedliche Arten der Seitenausgabe:

| Betriebsart | Wann entsteht das HTML? | Was läuft im Container? |
| --- | --- | --- |
| Statisch | Beim Build | Nginx liefert fertige HTML-Dateien und andere Dateien aus |
| SSR, also Server-Side Rendering | Bei einer Anfrage | Ein Node-Server erzeugt die Antwort; Nginx leitet die Anfrage weiter |

Ein Blog, eine Wissenssammlung oder eine Unternehmenswebsite kann vollständig
statisch aufgebaut sein. JavaScript im Browser, ein Rechner oder eine Suche
bedeuten nicht automatisch, dass SSR erforderlich ist.

**Wähle im Installer zunächst den Betriebsmodus `auto`.** Dieser behält die
Rendering-Einstellungen deiner Website bei. Eine statische Website bleibt
statisch. Eine vorhandene Node-Standalone-Ausgabe wird als SSR-Anwendung betrieben.

Der Modus `server` ist für eine bewusste Umstellung auf SSR vorgesehen. Dabei
kann der Installer einen fehlenden Node-Adapter in der Build-Kopie ergänzen.
Diese Umstellung passt aber nicht automatisch zu jedem Astro-Projekt.

Ein Beispiel: Statische dynamische Seiten wie `[topic].astro` erhalten ihre Daten
oft über `getStaticPaths()` und `Astro.props`. Wird die Seite ohne passende
Anpassungen auf SSR umgestellt, können diese Daten fehlen. Daraus entstehen
Fehler wie `RenderUndefinedEntryError` oder Zugriffe auf `undefined`.
Die [Astro-Dokumentation zum Routing](https://docs.astro.build/en/guides/routing/#on-demand-dynamic-routes)
erklärt den Unterschied zwischen vorab erzeugten und zur Laufzeit gerenderten Routen.

## 3. Das brauchst du

Für dieses Tutorial benötigst du:

- einen vorhandenen Proxmox-Server und Zugriff auf dessen Weboberfläche;
- einen frischen Debian-13-LXC mit Internetzugriff und systemd;
- eine Astro-Website in einem GitHub-Repository;
- Zugriff auf die Repository-Einstellungen, falls das Website-Repo privat ist;
- einen Browser in demselben Netzwerk wie der Container.

Als Ausgangspunkt für den Container eignen sich **2 CPU-Kerne, 4 GB RAM,
1 GB Swap und 20 bis 30 GB Speicher**. Das sind Richtwerte: Viele Bilder oder
umfangreiche Abhängigkeiten können mehr Ressourcen erfordern. Der Installer
prüft unter anderem, ob mindestens 5 GiB Speicher frei sind.

Verwende einen dedizierten Container für eine Website. Eine bestehende
Nginx-Installation wird beim ersten Setup nicht einfach überschrieben.
Unterstützt werden npm-Projekte mit `package-lock.json`; komplexe Workspaces,
Git LFS und Submodule gehören nicht zum hier beschriebenen Ablauf.

## 4. Den Debian-Container in Proxmox anlegen

Wenn du bereits einen frischen Debian-13-Container hast, kannst du diesen
Abschnitt überspringen.

1. Öffne die Proxmox-Weboberfläche und wähle deinen Server aus.
2. Lade auf einem dafür geeigneten Storage ein Debian-13-Container-Template.
3. Starte den Assistenten **„CT erstellen“** beziehungsweise **„Create CT“**.
4. Vergib einen Namen, beispielsweise `astro-webserver`, und ein sicheres Root-Passwort.
5. Verwende einen **unprivilegierten Container** und das Debian-13-Template.
6. Weise CPU, Arbeitsspeicher und Speicherplatz zu.
7. Verbinde den Container mit deiner LAN-Bridge und richte Netzwerk sowie DNS ein.
8. Starte den Container und öffne dessen **Konsole**.

Die genauen Bezeichnungen hängen von Proxmox-Version und Sprache ab.
Docker wird für AstroDeploy-LXC nicht benötigt.

Eine feste IP-Adresse oder eine DHCP-Reservierung im Router ist sinnvoll.
Sonst kann der Container später eine andere Adresse erhalten, während die
Website-Konfiguration noch die bisherige IP verwendet.

## 5. In der richtigen Konsole arbeiten

Melde dich in der **Konsole des Debian-Containers** als `root` an.
Die folgenden Installationsbefehle gehören nicht in die Shell des Proxmox-Hosts.

Die Container-Konsole funktioniert auch ohne eingerichtetes SSH. Wenn du später
von Windows aus arbeiten möchtest, findest du die Vorbereitung im Beitrag
[Per SSH auf einen Debian-Container zugreifen](/wissen/beitrag/linux-proxmox-ssh-debian-putty/).

Ein Terminal zeigt vor jeder Eingabe einen Prompt, beispielsweise:

```text
root@astro-webserver:~#
```

**Kopiere nur die Befehle aus den Bash-Blöcken, nicht den Prompt.** Mit Enter
führst du den eingegebenen Befehl aus. Bei einer Passwortabfrage bleibt die
Eingabe unter Linux häufig unsichtbar; das ist normal.

## 6. Debian und die Voraussetzungen vorbereiten

Führe im frischen Container aus:

```bash
apt-get update &&
apt-get upgrade &&
apt-get install -y git ca-certificates python3
```

`apt-get update` aktualisiert die Paketlisten. `apt-get upgrade` zeigt verfügbare
Paketupdates an und fragt vor deren Installation nach. Der letzte Befehl
installiert Git, Zertifikate für HTTPS-Verbindungen und Python 3 für den Installer.

Die Verbindung mit `&&` bedeutet: Der nächste Befehl läuft nur, wenn der
vorherige erfolgreich war. Warte, bis der Prompt wieder erscheint.

Node.js und npm musst du nicht zusätzlich global installieren. Der Installer
richtet seine eigene Node-Version unter `/opt/astrodeploy/node` ein.

## 7. Zwei verschiedene GitHub-Repositories auseinanderhalten

Für die Einrichtung sind zwei Repositories wichtig:

| Repository | Zweck |
| --- | --- |
| `know-how-schmiede/AstroDeploy-LXC` | Enthält den Installer und die Verwaltungswerkzeuge |
| Dein Website-Repository | Enthält deine Astro-Seiten, Inhalte und Projektkonfiguration |

Das Setup wird aus dem ersten Repository gestartet. **Im Setup selbst gibst du
die URL deiner Website an.** Würdest du dort erneut das Installer-Repository
eintragen, findet es kein passendes Website-Projekt.

Im Website-Repository sollten mindestens diese Dateien vorhanden sein:

```text
package.json
package-lock.json
src/
```

Eine vorhandene `astro.config.mjs` oder eine andere unterstützte Astro-Konfiguration
wird im Modus `auto` beibehalten. In `package.json` müssen Astro als Abhängigkeit
und ein Buildskript stehen. Übliche Beispiele sind `astro build` und
`npm run check && astro build`. Vorhandene Prüfungen sollen erhalten bleiben.

## 8. Den Installer direkt aus GitHub holen

Führe im Container aus:

```bash
git clone https://github.com/know-how-schmiede/AstroDeploy-LXC.git /root/AstroDeploy-LXC
```

Git lädt das Repository direkt in den Container. Ein manueller ZIP-Download
oder das Kopieren einzelner Dateien von Windows ist nicht nötig. Eine
Internetverbindung wird trotzdem benötigt.

Prüfe vor der Ausführung die Projektbeschreibung und den Stand des Codes.
Danach startest du den Assistenten:

```bash
cd /root/AstroDeploy-LXC && bash bin/setup.sh
```

Für das Klonen eines **öffentlichen** Repositories ist keine GitHub-Anmeldung
erforderlich. Fragt Git bereits hier nach einem Benutzernamen, prüfe die URL
und die öffentliche Erreichbarkeit des Installer-Repositories.

## 9. Die Fragen des Setups beantworten

Der Assistent zeigt zu Beginn die erkannten IPv4-Adressen des Containers.
Bei der Adressfrage wird eine davon als Vorgabe angeboten. **Enter übernimmt
einen Wert in eckigen Klammern**, zum Beispiel `[main]` oder `[auto]`.

Für einen ersten Test im LAN kannst du dich an diesen Einstellungen orientieren:

| Frage | Einstellung für den Einstieg |
| --- | --- |
| Projektname | `website` übernehmen oder einen eigenen Namen vergeben |
| GitHub-URL | Die URL deines Astro-Website-Repositories |
| Repository privat? | Entsprechend der GitHub-Sichtbarkeit `ja` oder `nein` |
| Branch | Meist `main`; muss im Website-Repository existieren |
| Projekt-Unterordner | `.` für die Repository-Wurzel |
| Domain oder Container-IP | Vorgeschlagene IP mit Enter übernehmen |
| Interner Node-Port | `4321` übernehmen; relevant für SSR |
| GitHub automatisch prüfen | `ja` |
| Prüfintervall | `60` Sekunden |
| Healthcheck-Pfad | `/`, wenn die Startseite ohne Anmeldung HTTP 200 liefert |
| HTTPS-Modus | Für den ersten Test im vertrauenswürdigen LAN `http` |
| Betriebsmodus | **`auto`** |

Ein Healthcheck ist ein einfacher Erreichbarkeitstest. Der eingestellte Pfad
muss eine erfolgreiche Antwort liefern. Eine Weiterleitung auf eine Login-Seite
gilt nicht als erfolgreicher Test. Für spezielle Anwendungen kannst du einen
eigenen öffentlich erreichbaren Prüfpfad wie `/health` bereitstellen.

Das Setup fragt außerdem nach optionalen Sicherheitsupdates und einem einmaligen
Debian-Update. Hast du Debian gerade aktualisiert, kannst du den zusätzlichen
einmaligen Update-Schritt überspringen. Auch das Installieren benötigter Pakete
kann jedoch abhängige Pakete aktualisieren.

**Build- und Laufzeitvariablen:** Wenn dein Projekt keine eigenen Umgebungsvariablen
benötigt, musst du die angebotenen Dateien nicht bearbeiten. Benötigte Werte
kannst du im Assistenten mit dem Editor eintragen. Es handelt sich um ein
`NAME=wert`-Format, nicht um ein Shellskript.

Vor den eigentlichen Installationsänderungen erscheint eine Zusammenfassung.
Prüfe besonders Website-Repository, Branch, IP-Adresse und Betriebsmodus.
Bestätige die Einrichtung erst, wenn diese Angaben stimmen.

## 10. Ein privates Website-Repository freigeben

Bei einem privaten Website-Repository stellt der Installer die URL auf SSH um
und erzeugt einen **Deploy-Key**. Dieser Schlüssel erlaubt dem Container,
genau dieses Repository abzurufen.

Der Assistent zeigt den öffentlichen Teil des Schlüssels an und wartet:

1. Öffne dein Website-Repository im Browser und melde dich bei GitHub an.
2. Gehe zu **Settings → Deploy keys → Add deploy key**.
3. Vergib einen Namen, beispielsweise `Astro-Webserver`.
4. Kopiere die vollständige angezeigte Zeile, beginnend mit `ssh-ed25519`, in das Schlüsselfeld.
5. Lass **Allow write access ausgeschaltet** und speichere den Key.
6. Kehre zur Container-Konsole zurück und drücke Enter.

Die Anmeldung erfolgt dabei im Browser. Im Container musst du kein persönliches
GitHub-Passwort eingeben. Der private Schlüssel bleibt im Container und gehört
nicht in GitHub-Dateien, Beiträge oder Screenshots.

Ein nur lesender Schlüssel genügt, weil der Container nichts zurück nach GitHub
schreibt. Nach einem vollständigen Container-Reset entsteht ein neuer Schlüssel;
diesen musst du erneut hinterlegen. Die
[GitHub-Dokumentation zu Deploy-Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
beschreibt dieses Zugriffsmodell.

## 11. Den ersten Build abwarten und die Website prüfen

Der Installer richtet die benötigten Pakete und Dienste ein, holt den gewählten
Commit und baut das Projekt mit npm. Das kann einige Minuten dauern. Die
eigentlichen npm-Ausgaben werden ausgeblendet, weil Projektskripte auch geheime
Umgebungsvariablen ausgeben könnten.

Ein erfolgreicher statischer Build wird sinngemäß so gemeldet:

```text
Deployment erfolgreich: … | statisch über Nginx
Fertig: http://DEINE-CONTAINER-IP
```

`DEINE-CONTAINER-IP` ist hier ein Platzhalter. Verwende im Browser die tatsächliche
Adresse aus der Konsole. Ein Beispiel für ein privates LAN wäre
`http://192.168.1.50/`; diese Beispieladresse musst du nicht übernehmen.

Prüfe anschließend im Container:

```bash
astroctl doctor
```

Öffne im Browser nicht nur die Startseite, sondern auch mehrere Unterseiten:
einen Beitrag, eine Themenübersicht, Bilder und gegebenenfalls interaktive
Funktionen. Der automatische Healthcheck prüft nur den eingestellten Pfad.
Eine funktionierende Startseite beweist nicht, dass alle anderen Seiten funktionieren.

## 12. Den ersten automatischen Update-Lauf ausprobieren

Ändere in deinem Website-Projekt einen gut erkennbaren Text, beispielsweise
eine Überschrift. Speichere die Änderung als Commit und übertrage sie in den
konfigurierten GitHub-Branch. Das geht mit deinem gewohnten Git-Werkzeug oder
für eine einfache Textdatei auch über den GitHub-Webeditor.

Du musst danach im Container keinen Buildbefehl eingeben. Der Timer erkennt
den neuen Commit, baut ein Release und veröffentlicht es nach erfolgreicher Prüfung.
Rechne mit dem Prüfintervall **plus** der benötigten Buildzeit.

Den Zustand siehst du mit:

```bash
astroctl status
```

Falls der Browser noch den alten Text zeigt, lade die Seite ohne Browsercache
neu und prüfe, ob wirklich in den überwachten Branch gepusht wurde.
Ein manueller Versuch ist möglich:

```bash
astroctl deploy
```

Gibt es keinen neuen Stand, erscheint „Keine Änderung; Website ist aktuell“.
Für einen bewussten Neubau desselben Commits verwendest du `astroctl rebuild`.

## 13. Dienste richtig lesen: inactive ist nicht immer ein Fehler

Die Befehle für eine genauere Kontrolle lauten:

```bash
systemctl status nginx --no-pager
systemctl status astro-deploy.timer --no-pager
systemctl status astro-deploy.service --no-pager
```

Nginx sollte laufen. Der aktivierte Timer wartet zwischen den Prüfungen.
`astro-deploy.service` arbeitet dagegen nur während eines Deployment-Laufs.
**`inactive (dead)` zusammen mit `status=0/SUCCESS` ist nach dessen Abschluss normal.**

Bei einer statischen Website ist auch `astro-site` bewusst deaktiviert:
Es wird kein Node-Server für die Auslieferung benötigt. Node bleibt trotzdem
für zukünftige Builds im Container installiert.

## 14. Wenn etwas schiefgeht

### GitHub fragt nach einem Benutzernamen oder meldet „Repository not found“

Prüfe die Repository-Adresse. Öffentliche Repositories lassen sich per HTTPS
ohne Anmeldung lesen. Private Website-Repositories benötigen im beschriebenen
Verfahren SSH und den passenden Deploy-Key. Für die eindeutige Prüfung eines
öffentlichen Repositories kannst du dessen URL in einem Browserfenster ohne
GitHub-Anmeldung öffnen.

### Das Setup meldet einen anderen laufenden Verwaltungsbefehl

Setup und Deployment dürfen nicht gleichzeitig dieselben Dateien verändern.
Ein automatischer Timerlauf kann deshalb kurzzeitig die Verwaltung sperren.
So pausierst du neue Timerläufe, wartest auf den laufenden Vorgang und setzt fort:

```bash
systemctl stop astro-deploy.timer &&
flock /run/astrodeploy.lock true &&
bash /root/AstroDeploy-LXC/bin/setup.sh
```

Die Wartezeit hängt vom laufenden Build ab. Die Sperrdatei nicht löschen und
den Build nicht vorschnell beenden. Nach erfolgreicher Einrichtung wird die
konfigurierte Automatik wieder aktiviert. Brichst du das Setup ab, bleibt der
zuvor gestoppte Timer bis zur bewussten Wiederaufnahme mit `astroctl resume` aus.

### Der Build schlägt fehl

Prüfe zuerst die gemeldete Phase: Installation der Abhängigkeiten, optionale
Adapterinstallation, Projektprüfung oder eigentlicher Build. Häufige Ursachen
sind eine fehlende Lockdatei, unpassende Node-Anforderungen, fehlende Variablen
oder ein Fehler in der Website selbst.

Das Skript installiert Node projektbezogen. Deshalb muss ein manuell als root
eingegebenes `npx` nicht gefunden werden. Installiere nicht vorsorglich eine
zweite globale Node-Version. Die normalen Installer-Befehle benötigen das nicht.

### Manche Seiten liefern HTTP 500

Öffne eine betroffene Seite und lies danach das Serverprotokoll:

```bash
journalctl -u astro-site --since "5 minutes ago" --no-pager -n 100
```

Dieses Protokoll ist für SSR relevant. Bei statischer Auslieferung prüfst du
stattdessen beispielsweise:

```bash
tail -n 100 /var/log/nginx/error.log
```

Bei `RenderUndefinedEntryError` oder fehlenden `Astro.props` nach einer
SSR-Umstellung prüfe den Betriebsmodus. Eine ursprünglich statische Website
sollte zunächst mit ihrer Originalkonfiguration im Modus `auto` gebaut werden.
Verändere nicht vorschnell die funktionierenden Website-Inhalte.

### Eine unterbrochene Einrichtung fortsetzen

Starte denselben Installer erneut:

```bash
cd /root/AstroDeploy-LXC && bash bin/setup.sh
```

Bestätige die angebotene Fortsetzung. Gespeicherte Einstellungen und Schlüssel
bleiben erhalten. Ein Container-Reset ist zur normalen Fehlerbehebung nicht nötig.

## 15. Zur vorherigen Version zurückwechseln

Wenn eine neue Version zwar startet, aber inhaltlich Probleme macht, kannst du
das vorherige erfolgreiche Release aktivieren:

```bash
astroctl rollback
```

Dabei wird die Automatik pausiert. Sonst würde der nächste Timerlauf den
zurückgewiesenen Commit möglicherweise sofort wieder veröffentlichen.
Korrigiere das Problem in GitHub, teste bewusst und aktiviere die Automatik wieder:

```bash
astroctl deploy && astroctl resume
```

Prüfe vor dem Fortsetzen auch die betroffenen Unterseiten. Ein Rollback setzt
keine Datenbank, Uploads oder Debian-Pakete zurück. Beim allerersten Deployment
existiert noch kein vorheriges Release.

## 16. Updates und Backups einplanen

Website-Updates und Systemwartung sind unterschiedliche Aufgaben:

| Befehl | Zweck |
| --- | --- |
| `astroctl update --check` | Debian-Updates und verfügbare Node-LTS-Version anzeigen |
| `astroctl update --system` | Debian-Updates anzeigen und nach Bestätigung installieren |
| `astroctl update --node` | Node innerhalb der vorgesehenen Hauptversion aktualisieren und Website neu bauen |
| `astroctl update --tools` | Installierte Werkzeugversion und Hinweise zum manuellen Update anzeigen |

Ein Push zu GitHub aktualisiert nicht automatisch Debian oder Node.
Paketupdates können Dienste neu starten; plane dafür ein Wartungsfenster ein.
Die Werkzeuge haben noch keinen automatischen Selbstupdatepfad.

Sichere regelmäßig den Container über Proxmox. Wichtig sind außerdem
`/etc/astrodeploy` und gegebenenfalls persistente Anwendungsdaten unter
`/srv/astro/PROJEKT/data`. Ersetze `PROJEKT` durch den im Setup vergebenen Namen.
GitHub enthält den Website-Quellcode, aber nicht automatisch diese lokalen Daten
oder die privaten Zugangsschlüssel. Backups entsprechend geschützt aufbewahren.

## 17. Die Website später öffentlich erreichbar machen

Die LAN-Installation stellt deine Website noch nicht automatisch ins Internet.
Für öffentlichen Zugriff brauchst du eine passende Domain, DNS und eine
bewusst eingerichtete Netzwerkfreigabe oder einen vorhandenen Reverse Proxy.

Der Installer unterstützt direktes Let's Encrypt und einen vorgeschalteten
TLS-Proxy. Für direktes Let's Encrypt müssen die Domain-Einträge stimmen und
Ports 80/443 den Container erreichen. Der Installer richtet keine Routerregeln
ein. Bei einem externen TLS-Proxy darf nur dessen tatsächliche IP beziehungsweise
Netzadresse als vertrauenswürdig eingetragen werden.

Entscheide dich für diesen Weg am besten vor einer neuen Einrichtung. Eine
spätere Änderung von Domain oder HTTPS-Modus ist kein vollständiger automatischer
Rekonfigurationsassistent; JSON, Nginx und gegebenenfalls Zertifikate müssen
zusammenpassen. Die [Installationsdokumentation des Projekts](https://github.com/know-how-schmiede/AstroDeploy-LXC/blob/main/docs/installation.md)
beschreibt die unterstützten Möglichkeiten.

## Deine Abschlusskontrolle

- Die Website ist unter der gewählten Adresse erreichbar.
- Startseite und mehrere unterschiedliche Unterseiten funktionieren.
- `astroctl doctor` meldet erfolgreiche Grundprüfungen.
- Ein Test-Commit im überwachten GitHub-Branch wird automatisch veröffentlicht.
- Statische Websites laufen im Modus `auto` ohne erzwungene SSR-Umstellung.
- Der private Deploy-Key bleibt im Container und hat keinen Schreibzugriff.
- Du kennst den Rollback-Befehl und hast einen Backupplan.

## Weiterführende Quellen

- [AstroDeploy-LXC: Quellcode und aktuelle Anleitung](https://github.com/know-how-schmiede/AstroDeploy-LXC)
- [Astro: On-demand Rendering](https://docs.astro.build/en/guides/on-demand-rendering/)
- [Astro: Dynamische Routen](https://docs.astro.build/en/guides/routing/#dynamic-routes)
- [GitHub: Deploy-Keys verwalten](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
- [Proxmox: Container-Dokumentation](https://pve.proxmox.com/pve-docs/chapter-pct.html)
