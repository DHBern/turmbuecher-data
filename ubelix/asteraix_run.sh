#!/usr/bin/env bash
# Berner Turmbücher: all four readers on asteraix's two A40s (when UBELIX's GPU queue is full).
#   card 0: Qwen3.5 Kurrent page → TrOCR Turmbücher (lines) → TrOCR Kurrent XVI-XVII (lines)
#   card 1: olmOCR Kurrent + BLB (page)
# LIMIT=3 for a smoke test. Resumable: every reader skips the pages it has.
set -uo pipefail
H=/mnt/wbkolleg_dh_1/Textrecognition_Training/hf_hub
IMG=/mnt/wbkolleg_dh_1/tei/datasets/turmbuecher-images
OUT=/mnt/wbkolleg_dh_1/tei/turmbuecher-readings/asteraix
CODE=$HOME/turmbuecher-read
PY=$HOME/.venvs/vllm/bin/python
export PATH=$HOME/.venvs/vllm/bin:$PATH   # vLLM builds kernels with ninja from the venv
export HF_HOME=$H HF_HUB_OFFLINE=1 VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
L=${LIMIT:+--limit $LIMIT}
QWEN=$(ls -d $H/hub/models--dh-unibe--qwen3.5-4b-german-kurrent-xvi-xix-page-v1/snapshots/*/ | head -1)
card0() {
  CUDA_VISIBLE_DEVICES=0 $PY $CODE/recognize.py --images $IMG/pages --out $OUT/qwen3.5-4b-german-kurrent-xvi-xix-page-v1/shard-0-of-1.jsonl \
    --base Qwen/Qwen3.5-4B --adapter "$QWEN" --model-id qwen3.5-4b-german-kurrent-xvi-xix-page-v1 \
    --prompt-file $CODE/prompts/transcribe.txt --max-num-seqs 32 $L
  for m in "trocr-towerbooks-tklines|dh-unibe/trocr-towerbooks" "trocr-kurrent-xvi-xvii-tklines|dh-unibe/trocr-kurrent-XVI-XVII"; do
    IFS='|' read -r NAME MODEL <<< "$m"
    CUDA_VISIBLE_DEVICES=0 $PY $CODE/read_lines.py --root $IMG --model $MODEL --name $NAME --out $OUT/$NAME/shard-0-of-1.jsonl $L
  done
}
card1() {
  CUDA_VISIBLE_DEVICES=1 $PY $CODE/recognize.py --images $IMG/pages --out $OUT/olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1/shard-0-of-1.jsonl \
    --base allenai/olmOCR-2-7B-1025 --adapter /mnt/wbkolleg_dh_1/Textrecognition_Training/training_folder/trained/olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1 \
    --model-id olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1 --prompt-file $CODE/prompts/olmocr2.txt \
    --max-pixels 4194304 --strip-front-matter --max-num-seqs 16 $L
}
echo "== start $(date -Is) ${LIMIT:+(limit $LIMIT)}"
card0 > $CODE/card0.log 2>&1 &
card1 > $CODE/card1.log 2>&1 &
wait
echo "== done $(date -Is)"
