#!/bin/bash
# Berner Turmbücher: page readers (VLM base + LoRA under vLLM) over every page image, on preemptable GPUs.
#   sbatch --array=0-5%4 read_pages.sbatch          (2 models x 3 shards; task i: model i/3, shard i%3)
# Resumable: a preempted or timed-out task is submitted again and skips the pages it has.
# Output on the research share, collected by scripts/collect_readings.py --jsonl:
#   /storage/research/wbkolleg_dh_1/tei/turmbuecher-readings/ubelix/<model>/shard-<i>-of-<n>.jsonl
#SBATCH --job-name=turm-pages
#SBATCH --account=gratis
#SBATCH --partition=gpu-invest
#SBATCH --qos=job_gpu_preemptable
#SBATCH --gres=gpu:h200:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=23:00:00
#SBATCH --requeue
#SBATCH --output=/scratch/network/users/%u/turmbuecher/logs/%x-%A_%a.out
set -euo pipefail
S=/scratch/network/users/$USER
R=/storage/research/wbkolleg_dh_1
H=$R/Textrecognition_Training/hf_hub
CODE=/rs_scratch/users/$USER/turmbuecher/code
SIF=$S/apptainer/vllm-0.29.0.sif
SHARDS=${SHARDS:-3}
i=${SLURM_ARRAY_TASK_ID:-0}
# id|base|adapter|prompt|max_pixels|extra
MODELS=(
  "qwen3.5-4b-german-kurrent-xvi-xix-page-v1|Qwen/Qwen3.5-4B|$(ls -d $H/hub/models--dh-unibe--qwen3.5-4b-german-kurrent-xvi-xix-page-v1/snapshots/*/ | head -1)|transcribe.txt||"
  "olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1|allenai/olmOCR-2-7B-1025|$R/Textrecognition_Training/training_folder/trained/olmocr2-7b-german-kurrent-xvi-xix-blb-page-px4m-native-v1|olmocr2.txt|4194304|--strip-front-matter"
)
IFS='|' read -r ID BASE ADAPTER PROMPT PX EXTRA <<< "${MODELS[$((i / SHARDS))]}"
SHARD=$((i % SHARDS))
OUT=$R/tei/turmbuecher-readings/ubelix/$ID/shard-$SHARD-of-$SHARDS.jsonl
mkdir -p "$(dirname "$OUT")"
echo "== $ID shard $SHARD/$SHARDS on $(hostname) $(date -Is)"
apptainer exec --nv \
  --bind /storage/research:/storage/research --bind /scratch:/scratch --bind /rs_scratch:/rs_scratch \
  --env HF_HOME=$H --env HF_HUB_OFFLINE=1 --env VLLM_NO_USAGE_STATS=1 --env DO_NOT_TRACK=1 \
  "$SIF" python3 "$CODE/recognize.py" \
    --images "$R/tei/datasets/turmbuecher-images/pages" --out "$OUT" --base "$BASE" --adapter "$ADAPTER" \
    --model-id "$ID" --prompt-file "$CODE/prompts/$PROMPT" --shard "$SHARD" --shards "$SHARDS" \
    ${PX:+--max-pixels $PX} $EXTRA --max-num-seqs 32 ${LIMIT:+--limit $LIMIT}
echo "== done $(date -Is)"
