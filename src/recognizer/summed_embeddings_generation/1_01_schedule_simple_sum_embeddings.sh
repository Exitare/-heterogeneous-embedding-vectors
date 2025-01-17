#!/bin/bash

# add range of values to iterate through
cancer_types=$1
amount_of_summed_embeddings=$2
lower_bound=$3
upper_bound=$4

#./src/recognizer/summed_embeddings_generation/1_01_schedule_simple_sum_embeddings.sh "BRCA LUAD STAD BLCA COAD THCA"

# if lower bound not set, set to 2
if [ -z "$lower_bound" ]
then
  echo "Lower bound not set, setting to 3"
  lower_bound=3
fi

# if upper bound not set, set to 30
if [ -z "$upper_bound" ]
then
  echo "Upper bound not set, setting to 30"
  upper_bound=30
fi

# if amount_of_summed_embeddings not set, set to 1000000
if [ -z "$amount_of_summed_embeddings" ]
then
  echo "Amount of summed embeddings not set, setting to 1000000"
  amount_of_summed_embeddings=1000000
fi


echo $cancer_types

# iterate through lower_bound to upper_bound
for walk_distance in $(seq $lower_bound $upper_bound)
do
  for noise_ratio in 0.0 0.1 0.2 0.3 0.4 0.5 0.6
  do
     sbatch ./src/recognizer/summed_embeddings_generation/1_01_create_simple_sum_embeddings.sh $walk_distance $amount_of_summed_embeddings "${cancer_types}" $noise_ratio
  done
done