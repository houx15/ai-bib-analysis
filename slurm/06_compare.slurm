#!/bin/bash
#SBATCH --job-name=dblp_vs_openalex
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/06_compare.slurm
# Requires: steps 02 + 03 done, and OpenAlex data accessible

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 06_compare_dblp_openalex.py

echo "=== Compare complete ==="
cat /scratch/network/yh6580/ai-bib/dblp/output/coverage_report.txt
