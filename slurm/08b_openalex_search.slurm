#!/bin/bash
#SBATCH --job-name=dblp_oa_search
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/08b_openalex_search.slurm
# Phase 2: search-API stage. PAID — counts against OpenAlex search quota
# ($1 / 1,000 calls; 1,000/day free tier). Run only after step 08a is done
# and billing is configured if the search residual is large.
# Resumable via data/output/dblp_ai_search_matches.csv.

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 08b_openalex_search.py
