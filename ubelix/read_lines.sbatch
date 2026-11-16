#!/bin/bash
# Berner Turmbücher: TrOCR line readers on the Transkribus lines of every page, on preemptable RTX 3090s.
#   sbatch --array=0-7%8 read_lines.sbatch          (2 models x 4 shards)
# Resumable like read_pages.sbatch. Output:
#   /storage/research/wbkolleg_dh_1/tei/turmbuecher-readings/ubelix/<name>/shard-<i>-of-<n>.jsonl
#SBATCH --job-name=turm-lines
#SBATCH --account=gratis
#SBATCH --partition=gpu-invest
#SBATCH --qos=job_gpu_preemptable
#SBATCH --gres=gpu:rtx3090:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --requeue
#SBATCH --output=/scratch/network/users/%u/turmbuecher/logs/%x-%A_%a.out
set -euo pipefail
R=/storage/research/wbkolleg_dh_1
H=$R/Textrecognition_Training/hf_hub
CODE=/rs_scratch/users/$USER/turmbuecher/code
SHARDS=${SHARDS:-4}
i=${SLURM_ARRAY_TASK_ID:-0}
# name|hf repo
MODELS=(
  "trocr-kurrent-xvi-xvii-tklines|dh-unibe/trocr-kurrent-XVI-XVII"
  "trocr-towerbooks-tklines|dh-unibe/trocr-towerbooks"
)
IFS='|' read -r NAME MODEL <<< "${MODELS[$((i / SHARDS))]}"
SHARD=$((i % SHARDS))
OUT=$R/tei/turmbuecher-readings/ubelix/$NAME/shard-$SHARD-of-$SHARDS.jsonl
echo "== $NAME shard $SHARD/$SHARDS on $(hostname) $(date -Is)"
apptainer exec --nv --bind /storage/research:/storage/research --env HF_HOME="$H" --env HF_HUB_OFFLINE=1 \
  "$HOME/ubelix/vlm-train.sif" /opt/vlm-train/bin/python "$CODE/read_lines.py" \
  --root "$R/tei/datasets/turmbuecher-images" --model "$MODEL" --name "$NAME" --out "$OUT" \
  --shard "$SHARD" --shards "$SHARDS" ${LIMIT:+--limit $LIMIT}
echo "== done $(date -Is)"
