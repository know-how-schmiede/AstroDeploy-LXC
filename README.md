<p align="center">
  <img src="assets/logo.png" alt="AstroDeploy-LXC Logo: Rakete und gestapelte Container" width="112">
</p>

<h1 align="center">AstroDeploy-LXC</h1>

<p align="center"><strong>Astro-Websites im eigenen LXC betreiben.</strong><br>
Interaktives Setup · GitHub-Deployments · Wartung · Rollback</p>

![AstroDeploy-LXC – Astro SSR deployment for Debian LXC](assets/banner.png)

**AstroDeploy-LXC** soll den Betrieb einer Astro-Website mit Node.js-Serverrendering
in einem Debian-LXC unter Proxmox vereinfachen: Server einrichten, Änderungen aus
GitHub bauen und veröffentlichen sowie die Installation nachvollziehbar warten.

> **Projektstatus: Planung und Implementierungsauftrag.** Dieses Paket enthält die
> Projektbeschreibung, die Codex-Arbeitsanleitung und die Grafiken. Die unten
> beschriebenen Werkzeuge sind der geplante Funktionsumfang. Installations- und
> Verwaltungsbefehle stehen erst nach ihrer Implementierung und Prüfung bereit.
> Der separat entstandene Setup-Prototyp ist keine fertig geprüfte Version dieses
> Projekts.

## Wofür ist das gedacht?

Du entwickelst deine Website lokal, verwaltest den Quellcode in GitHub und möchtest
sie auf deinem eigenen Proxmox-Server betreiben. AstroDeploy-LXC soll den Weg vom
Commit zur erreichbaren Website übernehmen, ohne dass du nach jeder Änderung
manuell SSH, Git und den Build starten musst.

Die erste Version konzentriert sich auf **eine Astro-SSR-Website pro Container**.
Für eine rein statische Website genügt grundsätzlich ein Webserver; ein dauerhaft
laufender Node.js-Server ist dafür nicht erforderlich.

## Geplanter Funktionsumfang

| Bereich | Vorgesehenes Verhalten |
| --- | --- |
| Interaktives Setup | Repository, Branch, Domain, Ports und weitere Einstellungen abfragen |
| Serverbetrieb | Node.js als systemd-Dienst hinter Nginx betreiben |
| GitHub-Deployment | Ausgewählten Branch regelmäßig prüfen und neue Commits veröffentlichen |
| Private Repositories | Zugriff über einen nur lesenden SSH-Deploy-Key |
| Getrennte Builds | Neue Version erstellen, während die bisherige Website weiterläuft |
| Erreichbarkeitsprüfung | Neue Version nach dem Start lokal per HTTP prüfen |
| Rollback | Bei Startfehlern zurückwechseln; manuelles Rollback pausiert die Automatik |
| HTTPS | Optional Let's Encrypt oder Betrieb hinter einem vorhandenen TLS-Proxy |
| Wartung | Website, Debian, Node.js und Deployment-Werkzeuge getrennt aktualisieren |
| Diagnose | Status, Protokolle und Prüfung der Installation über einen Verwaltungsbefehl |

## So soll ein Deployment funktionieren

1. Der systemd-Timer prüft den konfigurierten GitHub-Branch, standardmäßig `main`.
2. Bei einem neuen Stand wird der genaue Commit in einem separaten Verzeichnis gebaut.
3. `npm ci --include=dev` installiert die festgelegten Abhängigkeiten; `npm run build`
   erstellt die Serverausgabe. Beide Schritte laufen ohne Root-Rechte.
4. Ein neues Release wird bereitgestellt und der Node.js-Dienst darauf umgestellt.
5. Die HTTP-Prüfung kontrolliert die Erreichbarkeit. Schlägt sie fehl, wird die
   vorherige Version wieder aktiviert.

Das benötigt ausgehenden Zugriff auf GitHub, aber keinen öffentlich erreichbaren
Webhook. Während des Builds bleibt die alte Version aktiv. Beim Neustart des
Node.js-Dienstes kann eine kurze Unterbrechung auftreten.

## Zielumgebung

| Komponente | Geplante Unterstützung |
| --- | --- |
| Betriebssystem | Debian 13 mit systemd |
| Container | Dedizierter, unprivilegierter Proxmox-LXC mit Nesting |
| Architektur | amd64; arm64 nach entsprechender Prüfung |
| Anwendung | Astro mit `@astrojs/node` im `standalone`-Modus |
| Paketmanager | npm mit eingecheckter `package-lock.json` |
| Serverausgabe | Standardpfad `dist/server/entry.mjs` |
| Netzwerk | Feste IP oder DHCP-Reservierung; passende DNS-Einträge bei Domainbetrieb |

**Empfohlener Einstieg:** 2 CPU-Kerne, 4 GB RAM, 1 GB Swap und 20–30 GB Speicher.
Die benötigten Ressourcen hängen insbesondere von Bildoptimierung, Abhängigkeiten
und Anzahl der aufbewahrten Releases ab.

## Astro-Projekt vorbereiten

Im Website-Projekt eine zur Astro-Version passende Version des Node-Adapters
hinzufügen:

```bash
npx astro add node
```

Die vorhandene Astro-Konfiguration entsprechend ergänzen. Beispiel:

```js
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
});
```

Bestehende Integrationen und Einstellungen beibehalten. `package.json`,
`package-lock.json` und die Konfiguration in GitHub einchecken. Ein erfolgreicher
Build muss die erwartete Serverausgabe erzeugen.

## Entwicklung mit Codex starten

Der vollständige Auftrag steht in
[CODEX_ARBEITSANLEITUNG.md](CODEX_ARBEITSANLEITUNG.md). Lege dieses Paket in ein
lokales Projektverzeichnis und beauftrage Codex:

> Lies CODEX_ARBEITSANLEITUNG.md und setze das beschriebene Projekt vollständig um.
> Erstelle die Setup-, Deployment- und Update-Werkzeuge im Terminal. Prüfe die
> Implementierung und dokumentiere tatsächlich ausgeführte Tests. Bereite das
> GitHub-Repository AstroDeploy-LXC vor. Passe anschließend die README an den
> tatsächlich implementierten Funktionsumfang an.

Nach der Implementierung ist folgender Einstieg vorgesehen:

```bash
# Geplanter Befehl – in diesem Dokumentationspaket noch nicht enthalten:
sudo bash bin/setup.sh
```

Das Setup soll vor Änderungen eine Zusammenfassung anzeigen und wichtige
Einstellungen abfragen. Private Schlüssel und Produktionsgeheimnisse gehören
in den Container und niemals ins Repository.

## Vorgesehene Verwaltung

Diese Befehle sind **Schnittstellenziele für die Implementierung**, noch keine
verfügbaren Programme dieses Pakets:

| Befehl | Zweck |
| --- | --- |
| `sudo astroctl status` | Dienste und letzten Deploymentstatus anzeigen |
| `sudo astroctl doctor` | Installation ohne Änderungen prüfen |
| `sudo astroctl deploy` | GitHub prüfen und gegebenenfalls veröffentlichen |
| `sudo astroctl rebuild` | Auch denselben Commit erneut bauen |
| `sudo astroctl pause` | Automatische Veröffentlichung pausieren |
| `sudo astroctl resume` | Automatik fortsetzen |
| `sudo astroctl rollback` | Vorheriges Release aktivieren und Automatik pausieren |
| `sudo astroctl logs` | Relevante Protokolle anzeigen |
| `sudo astroctl update --check` | Verfügbare Updates prüfen |
| `sudo astroctl update --system` | Debian-Pakete aktualisieren |
| `sudo astroctl update --node` | Node innerhalb der gewählten LTS-Hauptversion aktualisieren |
| `sudo astroctl update --tools` | Deployment-Werkzeuge prüfen bzw. kontrolliert aktualisieren |

## Was wird wann aktualisiert?

| Bestandteil | Vorgesehener Auslöser | Grenze |
| --- | --- | --- |
| Website | Neuer Stand im gewählten GitHub-Branch | Keine eigenmächtigen Änderungen an Abhängigkeiten oder Lockdatei |
| Debian | Bewusster Wartungsbefehl; optional automatische Sicherheitsupdates | Kein automatischer Neustart |
| Node.js | Bewusster Wartungsbefehl mit Neubau und Prüfung | Kein automatischer Wechsel der Hauptversion |
| Deployment-Werkzeuge | Versioniertes, geprüftes Update | Kein ungeprüftes Ausführen von GitHub-main als root |

Ein LXC verwendet den Kernel des Proxmox-Hosts. **Updates des Hosts und seines
Kernels gehören nicht zu diesem Projekt.** Ein Website-Rollback setzt weder
Debian-Pakete noch Datenbankänderungen zurück.

## Daten, Rechte und Backups

- Build und Serverbetrieb sollen unterschiedliche Benutzer verwenden.
- Die Anwendung erhält keinen Zugriff auf den SSH-Deploy-Key oder die Verwaltung.
- Veröffentlichte Releases werden unveränderlich bereitgestellt.
- Uploads, SQLite-Dateien und Sessions benötigen einen persistenten Speicher
  außerhalb der austauschbaren Releases.
- Build-Variablen und Laufzeitvariablen werden getrennt verwaltet. Werte mit
  `PUBLIC_` können im Browser sichtbar werden.
- Regelmäßige Container-Backups sowie Sicherungen der Konfiguration und
  Anwendungsdaten bleiben erforderlich.

## Grenzen der ersten Version

Geplant ist ein überschaubarer Betrieb für eine Website mit npm und Standard-
Buildausgabe. Sonderfälle wie Git LFS, Submodule, komplexe Monorepo-Workspaces,
automatische Datenbankmigrationen oder mehrere Websites benötigen zusätzliche
Unterstützung. Sie dürfen erst nach Implementierung und Tests als unterstützt
ausgewiesen werden.

## Grafiken

| Datei | Verwendung |
| --- | --- |
| [assets/banner.png](assets/banner.png) | Breites Titelbild für die README |
| [assets/logo.png](assets/logo.png) | Projektlogo mit transparentem Hintergrund |
| [assets/IMAGE_PROMPTS.md](assets/IMAGE_PROMPTS.md) | Generierungsbeschreibungen der beiden Grafiken |

Die Grafiken wurden mit Bildgenerierung für dieses Projekt erstellt. Sie sind
keine offiziellen Logos von Astro, Debian oder Proxmox. Eine Projektlizenz und
der Rechteinhaber sind vor der Veröffentlichung noch festzulegen.

## Weiterführende Dokumentation

- [Astro Node-Adapter](https://docs.astro.build/en/guides/integrations-guide/node/)
- [GitHub Deploy-Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
- [GitHub SSH-Fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)

---

**Stand:** 30. Oktober 2026 · Noch nicht auf GitHub veröffentlicht.
