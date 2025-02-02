
# upper bound is the maximum walk distance
upper_bound=$1
amount_of_summed_embeddings=$2


# if upper bound not set, set to 10
if [ -z "$upper_bound" ]
then
  echo "Upper bound not set, setting to 10"
  upper_bound=10
fi

# if summed embeddings count not set, set to 1000000
if [ -z "$amount_of_summed_embeddings" ]
then
  echo "Amount of summed embeddings count not set, setting to 1000000"
  amount_of_summed_embeddings=1000000
  exit 1
fi




for walk_distance in $(seq 3 $upper_bound)
do
  for noise in 0.1 0.2 0.3 0.4 0.5 0.6
  do
    # run it 30 times
    for iteration in $(seq 1 15)
    do
      sbatch ./src/recognizer/models/2_01_run_simple_recognizer.sh $walk_distance $iteration $amount_of_summed_embeddings $noise
    done
  done
done