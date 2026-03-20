#!/bin/bash
#SBATCH --job-name=dblp_filter
#SBATCH --ntasks=1
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --time=01:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/03_filter.slurm

set -euo pipefail

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 03_filter_ai_papers.py

echo "=== Filter complete ==="
wc -l /scratch/network/yh6580/ai-bib/dblp/parsed/dblp_ai_papers.csv
