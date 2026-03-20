#!/bin/bash
#SBATCH --job-name=dblp_parse_filter
#SBATCH --ntasks=1
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --time=05:00:00
#SBATCH --mail-type=end
#SBATCH --mail-user=yh6580@princeton.edu

# Usage: sbatch slurm/02_parse_and_filter.slurm

module purge
module load anaconda3/2023.3
conda activate llm

cd "$SLURM_SUBMIT_DIR"

echo "=== Step 2: Parse DBLP XML ==="
python 02_parse_dblp.py
echo "Papers parsed:"
wc -l /scratch/network/yh6580/ai-bib/dblp/parsed/dblp_papers.csv

echo ""
echo "=== Step 3: Filter AI papers ==="
python 03_filter_ai_papers.py
echo "AI papers found:"
wc -l /scratch/network/yh6580/ai-bib/dblp/parsed/dblp_ai_papers.csv
