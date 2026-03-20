#!/bin/bash
#SBATCH --job-name=dblp_download
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/01_download.slurm

set -euo pipefail

RAW_DIR="/scratch/network/yh6580/ai-bib/dblp/raw"

cd "$SLURM_SUBMIT_DIR"
bash 01_download_dblp.sh "$RAW_DIR"
