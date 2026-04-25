#!/bin/bash
#SBATCH --job-name=dblp_country_api
#SBATCH --ntasks=1
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --time=12:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/10b_country_api.slurm
# Phase B — live OpenAlex API top-up by openalex_id (filter pool, free
# 10k/day with API key). Tops up country for 08a doi_api + 08b strong
# matches that 10a couldn't see in the bulk snapshot. Resumable.
#
# REQUIRES OUTBOUND NETWORK on the executing node — submit on whichever
# queue allowed 08a/08b to reach api.openalex.org.

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"
python 10b_country_api.py
