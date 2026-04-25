#!/bin/bash
#SBATCH --job-name=dblp_country_bulk
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/10a_country_bulk.slurm
# Phase A — bulk OpenAlex .gz scan, NO NETWORK. Mirrors step 06 matching
# and writes country per matched DBLP AI key to dblp_ai_country.csv.
# Resumable via the output CSV (flushes every ~30 min during the run).

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 10a_country_bulk.py
