# Berner Turmbücher (Daten, Lesungen, Viewer)

Prototyp der [Digital Humanities der Universität Bern](https://www.dh.unibe.ch/) für die Suche in
den Berner Turmbüchern und ihre inhaltliche Erschliessung. Die Turmbücher (Staatsarchiv des Kantons
Bern, B IX 422–509, 16.–18. Jahrhundert) halten Verhöre, Geständnisse und Urteile der Berner
Obrigkeit fest. Sie sind im Projekt [«The Flow»](https://flow-project.net/) aufgenommen und in der
Transkribus-Sammlung 187323 («StABE_Turmbücher_DH_flow», 89 Dokumente, 13 089 Seiten) bearbeitet
worden.

Viewer: <https://dhbern.github.io/turmbuecher-data/> (abgeleitet aus dem der
[St. Galler Missiven](https://github.com/DHBern/sg-missiven-data) und der
[Thuner Missiven](https://github.com/DHBern/thun-missiven-data)).

## Stand (Meilenstein M1, 15.11.2026)

- **Vier Pilotbände** sind eingelesen: B IX 422, 428, 467, 509 (687 Seiten, 675 mit Text,
  76 in Transkribus als Ground Truth markiert).
- **Die Einheit ist vorerst die Seite.** Die Gliederung in Einträge folgt (M3); dann wird der
  Eintrag zur Einheit, mit Datum, Titel (Delikt und Person), Kurzregest und Deliktlabels.
- **Eine Lesung:** der Text, der in Transkribus steht (`transkribus-bestand`). Ausser auf den als
  Ground Truth markierten Seiten ist er unkorrigierte Maschinenlesung. Welches Modell die Seiten
  gelesen hat, ist in Transkribus nicht festgehalten. Weitere Lesungen mit offenen und eigenen
  Modellen folgen (M2).
- **Text und Bild sind Zeile für Zeile verknüpft** (Zeilenumrisse aus Transkribus).
- **Personen, Orte, Organisationen und Daten**, soweit in Transkribus ausgezeichnet, werden
  übernommen (`entities/`): ungeprüft, noch nicht mit Normdaten verknüpft.
- **Bilder:** Der Viewer kann sie über IIIF von `files.transkribus.eu` laden. In der
  veröffentlichten Fassung ist das ausgeschaltet (`site/config.json`, `"images": false`), bis die
  Anzeige mit dem Staatsarchiv geklärt ist. In diesem Repository liegen keine Bilder.

## Inhalt

| Pfad | Inhalt |
|---|---|
| `readings/pages.tsv` | alle Seiten in Signaturfolge: Schlüssel, Band, Seite, Bildgrösse, Status in Transkribus, Zeilen, Zeilen mit Text, Bildkennung (`tk`) |
| `readings/<lesung>.jsonl` | eine Zeile pro Seite: `key`, `text` (eine Zeile pro Textzeile) |
| `readings/lines.jsonl` | Zeilengeometrie pro Seite: Umriss, Text und Regionstyp jeder Zeile |
| `readings/readers.json` | wer jede Lesung ist, mit Vorbehalten |
| `entities/<lesung>.jsonl` | Auszeichnungen als Zeichenbereiche des Seitentexts |
| `ops/ingest_transkribus.py` | holt Metadaten und PAGE-XML aus Transkribus (läuft auf tei; nur lesend; ohne Benutzernamen) |
| `scripts/import_transkribus.py` | macht daraus `readings/` und `entities/` |
| `scripts/build_site.py` | baut `site/data/` für den Viewer |
| `site/` | der Viewer (ohne Build-Schritt); alle Texte in `site/i18n/de.json` |

## Bauen

```
python -m venv .venv && .venv/bin/pip install lxml rapidfuzz
.venv/bin/python scripts/import_transkribus.py <manifest.jsonl> <pagexml-Ordner>
.venv/bin/python scripts/build_site.py
python -m http.server --directory site
```

## Weitere Sprache

Eine Datei `site/i18n/<kürzel>.json` mit denselben Schlüsseln wie `de.json` anlegen und das Kürzel
in `site/config.json` unter `langs` eintragen. Fehlende Schlüssel fallen auf Deutsch zurück.

## Verantwortliche

Herausgegeben von Tobias Hodel, Dominic Weber, Jonas Widmer, Anna Funk und Myrjam Hostettler
(Universität Bern). Mitarbeit im Projekt «The Flow»: Angela Huang, Silke Schwandt, Serena Tolino,
Sefer Korkmaz, Christopher Kuhlmann, Inga Lange, Dana Meyer, Bart Holterman, Mohamed Ilyes
Mechentel, Melvin Wilde, Judith Neubauer, Vivien Popken.

## Lizenz

Daten und Texte: CC BY-SA 4.0 (`LICENSE`).
