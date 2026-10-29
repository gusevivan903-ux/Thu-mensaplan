# 🍽️ Mensa-Ranking THU

Zeigt jeden Tag, welches Essen in der THU-Mensa sich am meisten lohnt – nach **Preis**, **Proteingehalt** und **Nährwerten**. Gewichtung per Schieberegler einstellbar, mit Presets (Gym-Modus, Monatsende, Gesund).

- Standorte: Prittwitzstraße und Oberer Eselsberg
- Daten kommen automatisch vom offiziellen Speiseplan des Studierendenwerks Ulm
- Läuft komplett kostenlos auf GitHub (Actions + Pages), kein eigener Server nötig

## Einrichtung (ca. 10 Minuten, am besten am Laptop)

1. **Repo anlegen:** Auf github.com einloggen → oben rechts **+** → **New repository**
   Name z. B. `thu-mensa`, Sichtbarkeit **Public** (GitHub Pages ist im Gratis-Plan nur für öffentliche Repos), **ohne** README anlegen.

2. **ZIP hochladen:** Im Repo **Add file → Upload files** → `thu-mensa.zip` auswählen (nicht entpacken!) → **Commit changes**.

3. **Pages einschalten:** **Settings → Pages** → bei *Source* **GitHub Actions** auswählen.

4. **Workflow-Datei anlegen:** **Add file → Create new file** → als Dateiname `.github/workflows/mensa.yml` eintippen (die Schrägstriche legen die Ordner automatisch an) → Inhalt von `mensa.yml` reinkopieren → **Commit changes**.
   Dadurch startet automatisch der erste Lauf: Er packt die ZIP aus, holt den Speiseplan und veröffentlicht die Seite. Nach 2–3 Minuten ist sie online unter
   `https://DEIN-GITHUB-NAME.github.io/REPO-NAME/`

Ab dann aktualisiert sich alles automatisch an jedem Werktag morgens und vormittags nochmal.

## 📱 Aufs Handy: Mittags-Push + App-Icon

> Samsungs „Now Brief“ (Morgen-/Mittags-Briefing) nimmt leider keine eigenen Inhalte an – nur Samsungs feste Kategorien und ausgewählte Partner-Apps. Deshalb kommt der Tagessieger stattdessen als **Push-Nachricht um ca. 11:20 Uhr** (Mo–Fr), und die Seite lässt sich als **App auf den Startbildschirm** legen.

### Push-Nachricht einrichten (5 Minuten)

1. **App installieren:** Im Play Store **„ntfy“** installieren (kostenlos, kein Konto nötig).
2. **Geheimen Kanalnamen ausdenken**, z. B. `mensa-ivan-x7k29q`. Wichtig: schwer zu erraten, denn jeder, der den Namen kennt, kann mitlesen.
3. **In ntfy abonnieren:** In der App unten rechts auf **+** tippen, den Kanalnamen eintragen und auf **Abonnieren** tippen.
4. **In GitHub hinterlegen:** Im Repo **Settings → Secrets and variables → Actions → New repository secret**
   Name: `NTFY_TOPIC`, Wert: dein Kanalname. Dann **Add secret**.
5. **Testen:** **Actions → Mensa-Daten holen … → Run workflow** → Haken bei **„Test-Push jetzt sofort aufs Handy schicken“** → **Run workflow**. Nach ca. 1 Minute sollte die Nachricht da sein.

Antippen der Nachricht öffnet das komplette Ranking.

**Tipp für Samsung:** Damit die Nachricht zuverlässig ankommt, in den Handy-Einstellungen **Akku → Hintergrund-Nutzungslimits** prüfen, dass ntfy *nicht* unter „Apps im Tiefschlaf“ steht. In der ntfy-App kannst du den Kanal außerdem auf „Sofortige Zustellung“ stellen.

**Optional anpassen** (Settings → Secrets and variables → Actions → Reiter **Variables** → New repository variable):

| Name | Werte | Standard |
|---|---|---|
| `MENSA_STANDORT` | `prittwitz`, `eselsberg`, `beide` | `prittwitz` |
| `MENSA_PRESET` | `ausgewogen`, `gym`, `pleite`, `gesund` | `ausgewogen` |
| `MENSA_ERNAEHRUNG` | `alle`, `vegetarisch`, `vegan` | `alle` |
| `MENSA_PREISGRUPPE` | `student`, `staff`, `guest` | `student` |

Zur Uhrzeit: GitHub startet geplante Läufe oft 5–30 Minuten verspätet. Die Nachricht kommt also meist zwischen 11:20 und 11:50 Uhr, rechtzeitig zur Mensa-Öffnung um 11:45 Uhr. Kommt ein Lauf erst nach 12 Uhr dran, fällt der Push an dem Tag aus, damit du keine veraltete Nachricht kriegst.

### Seite als App installieren

Die Seite in **Chrome** oder **Samsung Internet** öffnen, dann:
- **Chrome:** ⋮ → **Zum Startbildschirm hinzufügen** → **Installieren**
- **Samsung Internet:** ☰ → **Seite hinzufügen zu** → **Startbildschirm**

Danach startet sie wie eine normale App mit eigenem Icon, ohne Browserleiste, und zeigt offline den letzten geladenen Stand.

## Wenn was nicht stimmt

- **Seite zeigt „Demo-Daten“:** Der Abruf hat noch nicht geklappt. Unter **Actions** den letzten Lauf öffnen und beim Schritt *Speiseplan abrufen* schauen, was da steht.
- **0 Gerichte, keine Preise oder keine Nährwerte:** Dann hat das Studierendenwerk vermutlich das HTML-Format anders als erwartet. Im Lauf unten bei *Artifacts* `debug-html` runterladen und mir (Claude) schicken, dann passe ich den Parser an.
- **Action läuft nicht mehr:** GitHub pausiert Zeitpläne nach 60 Tagen ohne Aktivität im Repo (z. B. Semesterferien). Unter **Actions** einfach wieder aktivieren.

## Bewertung

| Kriterium | Berechnung |
|---|---|
| Preis | günstigstes Gericht des Tages = 100, doppelt so teuer = 50 |
| Protein | meistes Eiweiß des Tages = 100, Rest anteilig |
| Nährwerte | Mittel aus: kcal im Bereich 450–850, gesättigte Fette ≤ 5 g, Zucker ≤ 10 g, Salz ≤ 2 g (jeweils linear abfallend) |
| Gesamt | gewichteter Mittelwert, Gewichte frei einstellbar |

Fehlen die Nährwerte bei einem Gericht, zählen Protein und Nährwerte neutral mit 50 und das Gericht wird markiert.

## Lokal testen

```bash
pip install -r scraper/requirements.txt
python scraper/test_parser.py                                   # Parser-Selbsttest
python scraper/fetch_mensa.py --out docs/data/mensa.json        # echte Daten holen
cd docs && python -m http.server 8000                           # dann http://localhost:8000
```

## Aufbau

```
.github/workflows/mensa.yml   Zeitplan: Daten holen, committen, Seite veröffentlichen, Mittags-Push
scraper/fetch_mensa.py        holt & parst den Speiseplan → docs/data/mensa.json
scraper/notify.py             berechnet den Tagessieger und schickt ihn per ntfy aufs Handy
scraper/test_parser.py        Selbsttest mit scraper/fixtures/sample.html
docs/index.html               die Webseite (eine Datei, kein Framework)
docs/manifest.webmanifest     App-Infos fürs Installieren auf dem Handy
docs/sw.js                    Offline-Cache / Installierbarkeit
docs/icons/                   App-Icons
docs/data/mensa.json          die Daten (anfangs Demo-Daten)
```

Push lokal testen (ohne zu senden): `python scraper/notify.py --dry-run --date 2026-10-19`

Privates Projekt, nicht offiziell vom Studierendenwerk Ulm. Keine Gewähr für Preise und Nährwerte.
