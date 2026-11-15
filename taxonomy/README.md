# Deliktvokabular erweitern

`delikte.json` ist die einzige Stelle, an der das Vokabular steht. Die Anweisung an das Sprachmodell,
die Titel, die Facetten der Suche und die Auswertung (Sankey, Zeitverlauf, Häufigkeiten) lesen es
von dort; im Code steht keine Kategorie und keine Gruppe.

## Eine Kategorie hinzufügen

1. In `delikte` einen Eintrag ergänzen:

   ```json
   {"id": "wilderei", "label": "Jagd- und Fischfrevel", "gruppe": "Eigentum",
    "hinweis": "unerlaubtes Jagen, Fischen, Holzen", "seit": 2}
   ```

   - `id`: klein, ohne Leerzeichen, bleibt für immer (sie steht in den Daten).
   - `label`: was die Seite zeigt. Darf jederzeit geändert werden.
   - `hinweis`: woran das Modell die Kategorie erkennt, möglichst mit Quellenbegriffen.
   - `gruppe`: eine der `gruppen` oder eine neue (siehe unten).
   - `seit`: die neue Versionsnummer (Schritt 2).
2. `version` um eins erhöhen.
3. Nachlabeln und bauen:

   ```
   python scripts/entries.py relabel
   python scripts/entries.py build
   python scripts/build_site.py
   ```

   `relabel` fragt für jeden Eintrag, der unter einer älteren Version gelabelt wurde, nur die Delikte
   neu ab. Das Modell sieht die bisherige Zuordnung und die seither hinzugekommenen Kategorien und
   soll nichts anderes ändern. Datum, Personen und Regest bleiben, wie sie sind. Die neuen Labels
   stehen in `entries/labels.jsonl`; `build` nimmt je Eintrag das neueste. Einträge ohne Delikt
   (Register, Notizen) werden nicht angefasst.

Im Test (15.11.2026, B IX 467, eine Probekategorie) änderten sich so 12 von 143 Einträgen. Fragt man
die Delikte dagegen ohne die bisherige Zuordnung neu ab, ändern sich 60 von 143: Das Modell
entscheidet bei Grenzfällen nicht jedes Mal gleich. Deshalb ändert `relabel` so wenig wie möglich.

## Eine Gruppe hinzufügen

In `gruppen` ergänzen: `{"id": "Wirtschaft", "farbe": "#6250d6"}`. Die Reihenfolge der Liste ist die
Reihenfolge in Legende und Diagrammen. Eine Gruppe, die nur an einer Kategorie genannt ist, erscheint
ebenfalls, in Grau. Mehr als acht Gruppen lassen sich farblich nicht mehr sicher unterscheiden; dann
besser Kategorien einer bestehenden Gruppe zuordnen.

## Umbenennen, zusammenlegen

- **Nur die Bezeichnung ändern:** `label` ändern, fertig.
- **Kennung ändern oder zwei Kategorien zusammenlegen:** die alte Kennung unter `alias` der bleibenden
  Kategorie eintragen (`"alias": ["alte_id"]`). Bestehende Einträge werden beim Bauen umgeschrieben;
  ein Nachlabeln ist dafür nicht nötig.
- **Eine Kategorie teilen:** die neuen Kategorien anlegen (mit `seit`), Version erhöhen, `relabel`.

## Was fehlt?

```
python scripts/entries.py vorschlaege
```

schreibt `entries/vorschlaege.tsv`: die Einträge, die das Modell unter «Sonstiges» oder «Unklar»
abgelegt hat, gruppiert nach der Bezeichnung, die es für die fehlende Kategorie vorschlägt
(`delikt_vorschlag`), mit dem Wortlaut der Quelle. Häufige Vorschläge sind Kandidaten für die nächste
Kategorie. Einträge, die vor dem 15.11.2026 erschlossen wurden, tragen noch keinen Vorschlag.

## Verfahren und Sanktionen

`verfahren` und `sanktionen` sind auf dieselbe Weise Listen in `delikte.json`. Ein Nachlabeln gibt es
für sie noch nicht; nach einer Erweiterung müssen die betroffenen Einträge neu erschlossen werden.
