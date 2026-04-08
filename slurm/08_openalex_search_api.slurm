#!/bin/bash
#SBATCH --job-name=dblp_oa_api
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/08_openalex_search_api.slurm
# Resumable: re-submit to continue from where it left off (checkpoint in
# data/output/dblp_ai_api_matches.csv).

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 08_openalex_search_api.py
