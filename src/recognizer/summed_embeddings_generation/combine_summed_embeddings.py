import h5py
import numpy as np
from pathlib import Path
from tqdm import tqdm
import logging
from argparse import ArgumentParser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_dataset_shapes(file_path, dataset_names):
    """
    Retrieves the number of rows for each dataset in a given file.
    Assumes that all datasets have the same number of rows.
    """
    with h5py.File(file_path, 'r') as f:
        shapes = {name: f[name].shape for name in dataset_names}
    return shapes


def merge_h5_files(input_files, output_file, dataset_names, chunk_size=10000):
    """
    Merges multiple HDF5 files into a single HDF5 file and adds metadata.

    Parameters:
    - input_files: List of Path objects pointing to input HDF5 files.
    - output_file: Path object for the output HDF5 file.
    - dataset_names: List of dataset names to merge.
    - chunk_size: Number of rows to process at a time.
    """
    logging.info(f"Starting merge of {len(input_files)} files into {output_file}")

    # Determine the shape of each dataset in the output file
    total_sizes = {name: 0 for name in dataset_names}
    max_embedding = 3
    walk_distances = []  # Track walk distances for each row in the merged dataset

    for file_path in input_files:
        with h5py.File(file_path, 'r') as f:
            for name in dataset_names:
                total_sizes[name] += f[name].shape[0]
            # Extract walk distance from the file name
            walk_distance = int(file_path.stem.split("_")[0])  # Assuming the file name format is "<walk>_embeddings.h5"
            num_rows = f[dataset_names[0]].shape[0]
            walk_distances.extend([walk_distance] * num_rows)

    # Initialize the output file with extendable datasets
    with h5py.File(output_file, 'w') as f_out:
        for name in dataset_names:
            # Get shape of the first input file's dataset
            first_file = input_files[0]
            with h5py.File(first_file, 'r') as f_in:
                dataset_shape = f_in[name].shape
                dtype = f_in[name].dtype

            # Define maxshape with None for the first dimension (extendable)
            maxshape = (None,) + dataset_shape[1:]
            f_out.create_dataset(
                name,
                shape=(0,) + dataset_shape[1:],  # Initial shape
                maxshape=maxshape,
                dtype=dtype,
                chunks=True  # Enable chunking for efficient appending
            )

        # Create a new dataset for walk distances
        f_out.create_dataset(
            "WalkDistances",
            shape=(0,),  # Initial shape
            maxshape=(None,),  # Extendable along the first dimension
            dtype=np.int32,
            chunks=True,
        )

        # Iterate over each input file and append data
        for file_path in tqdm(input_files, desc="Merging files"):
            walk_distance = int(file_path.stem.split("_")[0])  # Extract walk distance
            with h5py.File(file_path, 'r') as f_in, h5py.File(output_file, 'a') as f_out:
                for name in dataset_names:
                    data = f_in[name]
                    num_rows = data.shape[0]
                    # Determine how many chunks to process
                    num_chunks = int(np.ceil(num_rows / chunk_size))
                    for i in range(num_chunks):
                        start = i * chunk_size
                        end = min(start + chunk_size, num_rows)
                        chunk_data = data[start:end]

                        # Append the chunk to the output dataset
                        output_dataset = f_out[name]
                        output_dataset.resize(output_dataset.shape[0] + chunk_data.shape[0], axis=0)
                        output_dataset[-chunk_data.shape[0]:] = chunk_data

                # Append the walk distances for this file
                walk_dataset = f_out["WalkDistances"]
                walk_dataset.resize(walk_dataset.shape[0] + num_rows, axis=0)
                walk_dataset[-num_rows:] = walk_distance
                if max_embedding < walk_distance:
                    max_embedding = walk_distance

    with h5py.File(output_file, 'a') as f_out:
        # Add a metadata group with the maximum embedding value
        meta_group = f_out.create_group("meta_information")
        meta_group.attrs["max_embedding"] = max_embedding
        meta_group.attrs["description"] = "Metadata about the combined embeddings"
        meta_group.attrs["num_input_files"] = len(input_files)
        available_keys = list(f_out.keys())

    logging.info(f"Successfully merged files into {output_file}")
    logging.info(f"Metadata added with max_embedding = {max_embedding}")
    logging.info(f"Total embeddings per dataset: {total_sizes}")
    logging.info(f"Output file size: {Path(output_file).stat().st_size / 1e6:.2f} MB")
    logging.info(f"Available Keys: {available_keys}")
    logging.info(f"Max embedding: {max_embedding}")
    logging.info("Merge complete.")


def main():
    parser = ArgumentParser(description='Sum embeddings from different sources')
    parser.add_argument("--amount_of_summed_embeddings", "-a", type=int, default=1000,
                        help="Amount of summed embeddings to generate")
    parser.add_argument("--noise_ratio", "-n", type=float, default=0.0, help="Ratio of random noise vectors to add")
    parser.add_argument("--selected_cancers", "-c", nargs="+", required=False,
                        help="The selected cancer identifiers to sum")
    args = parser.parse_args()

    amount_of_summed_embeddings: int = args.amount_of_summed_embeddings
    noise_ratio: float = args.noise_ratio
    selected_cancers: [] = args.selected_cancers

    if selected_cancers is not None:
        logging.info("Merging multi-cancer embeddings.")
        cancers = "_".join(selected_cancers)
        input_dir = Path("results", "recognizer", "summed_embeddings", "multi", cancers,
                         str(amount_of_summed_embeddings),
                         str(noise_ratio))
        walk_counts = range(3, 16)
    else:
        logging.info("Merging single-cancer embeddings.")
        input_dir = Path("results", "recognizer", "summed_embeddings", "simple", str(amount_of_summed_embeddings),
                         str(noise_ratio))
        walk_counts = range(3, 31)

    # Collect all input files based on walk_counts
    input_files = []
    for walk in walk_counts:
        walk_dir = Path(input_dir, f"{walk}_embeddings.h5")  # Adjust subdirectories as needed
        if walk_dir.exists():
            input_files.append(walk_dir)
        else:
            logging.warning(f"File {walk_dir} does not exist and will be skipped.")

    if not input_files:
        logging.error("No input files found. Exiting.")
        return

    # Define the output file path
    output_file = Path(input_dir, "combined_embeddings.h5")

    if selected_cancers is not None:
        # please add the dataset names for the multi-cancer embeddings
        dataset_names = ["X", "Text", "Image", "RNA", "Mutation"] + selected_cancers
    else:
        # Define the dataset names to merge
        dataset_names = ["X", "Text", "Image", "RNA", "Mutation"]

    # Merge the files
    merge_h5_files(input_files, output_file, dataset_names)


if __name__ == "__main__":
    main()
