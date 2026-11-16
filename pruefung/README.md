# Prüfung von Hand

Eine feste Stichprobe der maschinellen Arbeit (`stichprobe.json`, gezogen mit `scripts/pruefung.py`,
Zufallszahl 20261116) wird im Viewer unter **#/pruefen** beurteilt:

- **Eintragsgrenzen:** 50 Seiten aus 50 Bänden, über die Reihe verteilt.
- **Delikte und Regesten:** 87 Einträge, bis zu drei je Deliktkategorie, dazu zufällige; geprüft werden
  Delikte, Ausgang, Jahr, Beschuldigte im Titel, Regest und Umfang des Eintrags.
- **Personen im HLS:** alle 38 «wahrscheinlichen» Verknüpfungen und 20 «mögliche».

Die Antworten bleiben im Browser, bis sie mit «Antworten herunterladen» als Datei gespeichert werden.
Diese Dateien gehören nach `pruefung/antworten/`. Auswertung:

```
.venv/bin/python scripts/pruefung_auswerten.py pruefung/antworten/*.json
```

schreibt `pruefung/ergebnis.md`. Mehrere Prüfende können dieselbe Stichprobe beurteilen; doppelt
beurteilte Stücke werden auf Übereinstimmung verglichen.

Wird die Stichprobe neu gezogen (`scripts/pruefung.py`), ändert sich ihr Datum; Antworten zu einer
älteren Stichprobe werden bei der Auswertung übersprungen.
