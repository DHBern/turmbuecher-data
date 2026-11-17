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

## Stand (15.11.2026)

- **Alle 89 Bände** sind eingelesen (13 089 Seiten, 11 010 mit Text, 839 in Transkribus als Ground
  Truth markiert), darunter der Band «Henzi» (in Transkribus «Henzi_duplicated»).
- **Einträge:** Alle 82 Bände mit Text sind maschinell in 8 086 Einträge gegliedert; 7 928 davon
  haben Datum, Titel (Delikt und Person), Kurzregest, Delikte und Ausgang (`scripts/entries.py`,
  offenes Modell Qwen3.8-27B auf dem GPUStack der Universität Bern, Vokabular in
  `taxonomy/delikte.json`, erweiterbar nach `taxonomy/README.md`). Alles ungeprüfte
  Maschinenentwürfe. Sieben Bände (B IX 498–500, 502–505) haben in Transkribus noch keinen Text.
- **Jahre** gelten nur innerhalb der Laufzeit ihres Bandes: für B IX 422–492 laut Archivkatalog des
  Staatsarchivs (`taxonomy/bandjahre.json`), sonst laut Titel oder aus den gelesenen Jahren und den
  Nachbarbänden erschlossen. Ein Jahr, das genau 50 oder 100 Jahre daneben liegt oder sich in der
  Zehnerziffer unterscheidet (nur wenn genau ein Jahr passt), wird berichtigt, ein anderes verworfen.
  Wo gelesenes Jahr und Laufzeit nicht übereinstimmen, trägt der Eintrag einen Vermerk (im Viewer
  und im TEI); `entries/datierung_vermerke.md` listet sie, Band für Band und Eintrag für Eintrag.
- **Karte:** Herkunft der Beschuldigten und genannte Orte, mit Filter nach Zeitraum und Delikt
  (`site/map.js`, Kartengrund swisstopo). 529 Orte sind über die Ortssuche von swisstopo verknüpft
  (`scripts/places.py`, `register/orte.json`), das sind 43 % der Ortsnennungen; verknüpft wird nur,
  wo der ganze Name auf genau einen Schweizer Ort passt. Ältere Namen stehen in
  `taxonomy/ortsnamen.json` und lassen sich dort ergänzen.
- **Register:** Personen, Orte, Delikte (`site/register.js`, `scripts/register.py`). Das
  Personenregister fasst die Nennungen zu 18 086 Namensformen zusammen (keine identifizierten
  Personen). 80 davon tragen Vorschläge aus dem Historischen Lexikon der Schweiz, 38 als
  «wahrscheinlich» (einzige Person des Namens, Vornamen stimmen, zur Zeit am Leben, Bezug zu Bern);
  drei davon sind über Lebensdaten in der Personendatei der Sammlung Schweizerischer Rechtsquellen
  bestätigt. 341 Gemeinden sind über ihre BFS-Nummer mit Wikidata, HLS, GND und GeoNames verbunden.
  Die Normdatentabellen liegen in `register/normdaten/`.
- **TEI:** eine Datei pro Band (`scripts/tei_export.py`, beim Bau nach `site/data/tei/`), gültig
  gegen TEI-All: Einträge mit Text, Zeilenverweisen ins Bild, den Auszeichnungen aus Transkribus
  und der maschinellen Erschliessung (`@resp`, `@cert`); Herausgebende und Mitarbeitende aus
  `taxonomy/verantwortliche.json`. Der Viewer bietet den Download je Band und je Eintrag.
- **Auswertung:** Sankey Zeitraum → Delikt → zusammen genannte Delikte bzw. Ausgang, Delikte über
  die Zeit, Häufigkeit der Delikte (`site/analysis.js`).
- **Nur Maschinenlesung bis 1. Juli 2027:** Die Ground Truth (von Hand geprüfte Transkriptionen
  aus «The Flow» und den Lehrveranstaltungen) wird am 1. Juli 2027 veröffentlicht. Bis dahin wird
  von Transkribus nur Text übernommen, der die unveränderte Ausgabe eines Erkennungsmodells ist
  (Abgleich mit der jüngsten HTR-Fassung jeder Seite in den Sammlungen 89729 und 63705); auf
  Ground-Truth-Seiten und von Hand korrigierten Seiten steht die HTR-Fassung oder nur die Lesung
  der eigenen Modelle (`scripts/vorbehalt.py` → `readings/vorbehalt.tsv`). Seiten, die in 187323
  leer sind, übernehmen die Maschinenlesung der älteren Sammlungen (z. B. B IX 505). Liste der Bände
  mit Ground Truth: [`ground-truth/`](ground-truth/README.md).
- **Lesungen:** der maschinelle Text aus Transkribus (`transkribus-bestand`). Weitere Lesungen mit eigenen Modellen (Qwen3.5-4B Kurrent, TrOCR
  Kurrent) laufen und werden zu einer gemeinsamen Lesung zusammengeführt
  (`scripts/joint_reading.py`): ein Wort ändert sich nur, wo zwei andere Leser übereinstimmen. Ein
  Abgleich mit Ground Truth ist nicht das Ziel.
- **Text und Bild sind Zeile für Zeile verknüpft** (Zeilenumrisse aus Transkribus).
- **Personen, Orte, Organisationen und Daten**, soweit in Transkribus ausgezeichnet, werden
  übernommen (`entities/`): ungeprüft, noch nicht mit Normdaten verknüpft.
- **Bilder:** Der Viewer lädt sie über IIIF von `files.transkribus.eu`. Die Bilder sind gemeinfrei;
  die Vorlagen liegen im Staatsarchiv des Kantons Bern (StABE), B IX 422–509. In diesem Repository
  liegen keine Bilder.

## Inhalt

| Pfad | Inhalt |
|---|---|
| `readings/pages.tsv` | alle Seiten in Signaturfolge: Schlüssel, Band, Seite, Bildgrösse, Status in Transkribus, Zeilen, Zeilen mit Text, Bildkennung (`tk`) |
| `readings/<lesung>.jsonl` | eine Zeile pro Seite: `key`, `text` (eine Zeile pro Textzeile) |
| `readings/lines/<band>.jsonl` | Zeilengeometrie pro Seite: Umriss, Text und Regionstyp jeder Zeile |
| `readings/units.tsv` | die Einheiten des Viewers: Einträge mit ihren Seiten und Zeilenbereichen |
| `entries/` | Eintragsgrenzen (`segments.jsonl`), Antworten des Modells (`extract.jsonl`), die Einträge (`entries.jsonl`) |
| `regests/drafts.jsonl` | Titel und Regest pro Eintrag (Maschinenentwurf) |
| `taxonomy/delikte.json` | Deliktvokabular (vorläufig) |
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

Herausgegeben von Tobias Hodel, Dominic Weber, Jonas Widmer, Anna Funk, Myrjam Hostettler und Christa Schneider
(Universität Bern). Mitarbeit im Projekt «The Flow»: Angela Huang, Silke Schwandt, Serena Tolino,
Sefer Korkmaz, Christopher Kuhlmann, Inga Lange, Dana Meyer, Bart Holterman, Mohamed Ilyes
Mechentel, Melvin Wilde, Judith Neubauer, Vivien Popken.

## Lizenz

Daten und Texte: CC BY-SA 4.0 (`LICENSE`).
