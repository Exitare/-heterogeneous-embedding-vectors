#!/bin/bash
#SBATCH --nodes=1
#SBATCH --job-name=s_r
#SBATCH --time=9-00:00:00
#SBATCH --partition=exacloud
#SBATCH --qos=long_jobs
#SBATCH --ntasks=1
#SBATCH --mem=128000
#SBATCH --cpus-per-task=4
#SBATCH --output=./output_reports/slurm.%N.%j.out
#SBATCH --error=./error_reports/slurm.%N.%j.err
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=kirchgae@ohsu.edu

walk_distance=$1
run_iteration=$2
amount_of_summed_embeddings=$3
noise_ratio=$4


python3 src/recognizer/2_01_simple_recognizer.py -w "${walk_distance}" -ri "${run_iteration}" -a "${amount_of_summed_embeddings}" -n "${noise_ratio}"