#!/bin/bash
#SBATCH --nodes=1
#SBATCH --job-name=s_e_g
#SBATCH --time=9-00:00:00
#SBATCH --partition=exacloud
#SBATCH --qos=long_jobs
#SBATCH --ntasks=1
#SBATCH --mem=64000
#SBATCH --cpus-per-task=4
#SBATCH --output=./output_reports/slurm.%N.%j.out
#SBATCH --error=./error_reports/slurm.%N.%j.err
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=kirchgae@ohsu.edu

walk_distance=$1
amount_of_summed_embeddings=$2
cancer_types=$3
noise_ratio=$4

python3 src/recognizer/1_01_create_simple_sum_embeddings.py -a "${amount_of_summed_embeddings}" -w "${walk_distance}" -c ${cancer_types} -n "${noise_ratio}"