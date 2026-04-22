#!/bin/bash
#SBATCH --job-name=dblp_oa_doi
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/08a_openalex_doi.slurm
# Phase 1: DOI-lookup stage. Cheap (OpenAlex filter pool, 10k/day free).
# Resumable — re-submit to continue from the checkpoint in
# data/output/dblp_ai_doi_matches.csv.

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 08a_openalex_doi.py
