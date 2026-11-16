# Lesungen auf UBELIX

Die weiteren Lesungen aller Bände entstehen auf dem Hochleistungsrechner der Universität Bern
(UBELIX), auf kostenlosen, unterbrechbaren GPUs (`job_gpu_preemptable`). Die Skripte liegen auf
UBELIX unter `/rs_scratch/users/<user>/turmbuecher/code/` (Kopie hier).

| Leser | Art | Skript |
|---|---|---|
| `qwen3.5-4b-german-kurrent-xvi-xix-page-v1` | eigenes Seitenmodell (Kurrent 16.–19. Jh.), wie auf den Pilotbänden | `read_pages.sbatch` (vLLM, `recognize.py`) |
| `olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1` | eigenes Seitenmodell (olmOCR-2 mit LoRA, Kurrent + BLB) | `read_pages.sbatch` |
| `trocr-kurrent-xvi-xvii-tklines` | eigenes Zeilenmodell (TrOCR Kurrent 16./17. Jh.) auf den Transkribus-Zeilen | `read_lines.sbatch` (`read_lines.py`) |
| `trocr-towerbooks-tklines` | eigenes Zeilenmodell, trainiert auf den Turmbüchern (`dh-unibe/trocr-towerbooks`), auf den Transkribus-Zeilen | `read_lines.sbatch` |

Eingabe sind die Seitenbilder, wie der IIIF-Server von Transkribus sie ausliefert (aufrecht,
höchstens 3000 px; `ops/fetch_images.py`), und die PAGE-XML der Sammlung, beides auf der
Forschungsfreigabe unter `tei/datasets/turmbuecher-images/`. Die Zeilenleser lesen genau die
Zeilen von Transkribus; ihre Zeile *i* ist darum Zeile *i* des Transkribus-Texts.

Ausgabe: `tei/turmbuecher-readings/ubelix/<leser>/shard-<i>-of-<n>.jsonl`, eingesammelt mit

```
python scripts/collect_readings.py --jsonl <kopie der Ordner>
python scripts/joint_reading.py
```

Alle Skripte setzen fort, wo sie unterbrochen wurden: Eine unterbrochene Aufgabe wird einfach
noch einmal eingereicht.

## Danach: die Bände ohne Transkribus-Text erschliessen

Die Erschliessung liest jede Seite in der ersten Lesung, die sie hat: zuerst der Text aus
Transkribus, sonst die zusammengeführte Lesung (`--reader transkribus-bestand,joint`, die
Vorgabe). Auf Seiten ohne Transkribus-Text ruht die zusammengeführte Lesung auf dem
Turmbücher-TrOCR, dessen Zeilen genau die Zeilen von Transkribus sind. Nach dem Einsammeln:

```
python scripts/joint_reading.py
python scripts/entries.py segment      # nur Seiten, die noch keine Grenzen haben
python scripts/entries.py extract
python scripts/entries.py build
python scripts/register.py
python scripts/build_site.py
```

Bereits erschlossene Einträge bleiben, wie sie sind.
