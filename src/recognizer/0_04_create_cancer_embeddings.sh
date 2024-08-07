#!/bin/bash
#SBATCH --nodes=1
#SBATCH --job-name=s_vae
#SBATCH --time=9-00:00:00
#SBATCH --partition=exacloud
#SBATCH --qos=long_jobs
#SBATCH --ntasks=1
#SBATCH --mem=64000
#SBATCH --cpus-per-task=32
#SBATCH --output=./output_reports/slurm.%N.%j.out
#SBATCH --error=./error_reports/slurm.%N.%j.err
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=kirchgae@ohsu.edu

# sbatch ./src/embedding_generation/run_vae.sh "BRCA BLCA LAML STAD THCA"

cancer_types=$1

python3 src/recognizer/0_04_create_cancer_embeddings.py -c ${cancer_types}