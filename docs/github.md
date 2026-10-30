# GitHub-Zugriff

Öffentlich: `https://github.com/NAME/REPO.git` ohne Token angeben.
Privat: `git@github.com:NAME/REPO.git` verwenden.
Das Setup fragt nach der Sichtbarkeit und wandelt bei „privat“ eine HTTPS-URL
automatisch in die passende SSH-URL um. Eine GitHub-Anmeldung im Container ist
nicht erforderlich; den Deploy-Key einmalig im GitHub-Browser eintragen.

1. Den vom Setup angezeigten öffentlichen Schlüssel kopieren.
2. In GitHub Website-Repository → Settings → Deploy keys → Add deploy key öffnen.
3. Namen vergeben und Schlüssel einfügen.
4. **Allow write access deaktiviert lassen**, speichern.
5. In der Container-Konsole Enter drücken.

Nach einem Container-Reset muss der neu erzeugte Key hinterlegt werden. Auch mit
automatischer Projektvorbereitung im Container genügt read-only: Es werden keine
Änderungen nach GitHub gepusht.

Der private Schlüssel bleibt unter /var/lib/astrobuild/.ssh/deploy. Nicht in
Chats, Screenshots oder ins Repository kopieren. Persönliche SSH-Schlüssel
werden nicht übernommen. Niemals Tokens in Repository-URLs eintragen.

Der fest hinterlegte GitHub-Ed25519-Hostkey stammt aus der
[offiziellen Fingerprint-Dokumentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints),
geprüft am 30.10.2026. Es gibt kein ungeprüftes ssh-keyscan. Bei einer Rotation
erst GitHubs offizielle Meldung prüfen, dann den hinterlegten Key aktualisieren.

Keine Webhooks nötig. Ausgehend müssen GitHub-SSH (Port 22) bzw. HTTPS sowie
npm-Registry und nodejs.org erreichbar sein.
