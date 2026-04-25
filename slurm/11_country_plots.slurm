#!/bin/bash
#SBATCH --job-name=dblp_country_plots
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=00:30:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/11_country_plots.slurm
# Reads data/output/dblp_ai_country.csv (step 10) and writes two PDFs
# plus data/output/country_counts.csv.

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 11_country_plots.py
