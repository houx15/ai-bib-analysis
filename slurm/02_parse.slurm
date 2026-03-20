#!/bin/bash
#SBATCH --job-name=dblp_parse
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --time=04:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/02_parse.slurm

set -euo pipefail

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 02_parse_dblp.py

echo "=== Parse complete ==="
wc -l /scratch/network/yh6580/ai-bib/dblp/parsed/dblp_papers.csv
