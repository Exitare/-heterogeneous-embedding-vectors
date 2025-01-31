import h5py
import numpy as np
from tqdm import tqdm
from pathlib import Path
from argparse import ArgumentParser
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
SAVE_FOLDER = Path("results", "recognizer", "summed_embeddings", "simple")
LATENT_SPACE_DIM = 768
CHUNK_SIZE = 10  # Number of embeddings per chunk

modality_weights = {
    'RNA': 0.25,
    'Text': 0.25,
    'Image': 0.25,
    'Mutation': 0.25
}

modality_choices = list(modality_weights.keys())
modality_probs = list(modality_weights.values())


def get_total_rows_and_columns(f, group):
    """
    Returns the total number of rows and ensures columns are compatible for summation.
    """
    dataset = f[group]["embeddings"]
    total_rows = dataset.shape[0]
    total_columns = dataset.shape[1]
    return total_rows, total_columns


def add_random_or_real_embedding(buffer, add_noise, latent_dim):
    """
    Adds either random Gaussian noise or a real embedding from the buffer.
    """
    if add_noise:
        return np.random.uniform(-1, 1, size=latent_dim).astype(np.float32)
    else:
        random_index = np.random.randint(0, buffer.shape[0])  # Select a random row
        return buffer[random_index]


def main():
    used_image_ids: int = 0
    image_chunk = 0  # Track image indices
    parser = ArgumentParser(description='Sum embeddings from different sources')
    parser.add_argument("--walk_distance", "-w", type=int, help="Number of embeddings to sum", required=True)
    parser.add_argument("--amount_of_summed_embeddings", "-a", type=int, default=1000,
                        help="Amount of summed embeddings to generate")
    parser.add_argument("--noise_ratio", "-n", type=float, default=0.0, help="Ratio of random noise vectors to add")
    parser.add_argument("--selected_cancers", "-c", nargs="+", required=True, help="The cancer types to work with.")
    parser.add_argument("--load_path", "-l", type=str, default="results/embeddings",
                        help="Path to the embeddings folder")
    args = parser.parse_args()

    amount_of_summed_embeddings: int = args.amount_of_summed_embeddings
    walk_distance: int = args.walk_distance
    selected_cancers: [] = args.selected_cancers

    if len(selected_cancers) == 1:
        logging.info("Selected cancers is a single string. Converting...")
        selected_cancers = selected_cancers[0].split(" ")

    noise_ratio: float = args.noise_ratio
    load_folder: Path = Path(args.load_path)

    logging.info(f"Noise ratio: {noise_ratio}")
    logging.info(f"Walk distance: {walk_distance}")
    logging.info(f"Amount of summed embeddings: {amount_of_summed_embeddings}")
    logging.info(f"Selected cancers: {selected_cancers}")
    logging.info(f"Loading embeddings from {load_folder}")
    logging.info(f"Load folder: {load_folder}")

    if len(selected_cancers) == 1:
        logging.info("Selected cancers is a single string. Converting...")
        selected_cancers = selected_cancers[0].split(" ")

    cancers: str = "_".join(selected_cancers)
    save_path: Path = Path(SAVE_FOLDER, str(amount_of_summed_embeddings), str(noise_ratio))
    save_path.mkdir(parents=True, exist_ok=True)

    combined_data = np.zeros((amount_of_summed_embeddings, LATENT_SPACE_DIM), dtype=np.float32)
    labels_data = {label: np.zeros(amount_of_summed_embeddings, dtype=np.int32)
                   for label in ["Text", "Image", "RNA", "Mutation"]}

    counts = {modality: 0 for modality in modality_choices}

    # Precompute random choices
    precomputed_choices = np.random.choice(
        modality_choices,
        size=(amount_of_summed_embeddings, walk_distance),
        p=modality_probs
    )

    with h5py.File(Path(load_folder, f"{cancers}.h5"), 'r') as f:
        detected_chunk_size = f["rna"]["embeddings"].chunks[0]
        logging.info(f"Detected chunk size: {detected_chunk_size}")

        # Get total rows and columns for each modality
        rna_total_rows, rna_columns = get_total_rows_and_columns(f, "rna")
        image_total_rows, image_columns = get_total_rows_and_columns(f, "images")
        mutation_total_rows, mutation_columns = get_total_rows_and_columns(f, "mutations")
        annotation_total_rows, annotation_columns = get_total_rows_and_columns(f, "annotations")

        logging.info(f"RNA: {rna_total_rows} rows, {rna_columns} columns")
        logging.info(f"Image: {image_total_rows} rows, {image_columns} columns")
        logging.info(f"Mutation: {mutation_total_rows} rows, {mutation_columns} columns")
        logging.info(f"Annotation: {annotation_total_rows} rows, {annotation_columns} columns")

        # Ensure all modalities have the same column dimensions
        assert rna_columns == image_columns == mutation_columns == annotation_columns == LATENT_SPACE_DIM, \
            f"All modalities must have exactly {LATENT_SPACE_DIM} usable columns for summation"

        logging.info("All modalities have compatible dimensions.")

        # Read text, image and rna data into memory
        text_data = f["annotations"]["embeddings"][:]
        mutation_data = f["mutations"]["embeddings"][:]
        rna_data = f["rna"]["embeddings"][:]
        # Load the first image chunk
        image_data = f["images"]["embeddings"][:]

        data: {} = {
            "Text": text_data,
            "Mutation": mutation_data,
            "RNA": rna_data,
            "Image": image_data
        }

        for i in tqdm(range(amount_of_summed_embeddings), desc="Generating Summed Embeddings"):
            combined_sum = np.zeros(LATENT_SPACE_DIM, dtype=np.float32)
            combination_counts = {modality: 0 for modality in modality_choices}

            # Use precomputed random modalities
            random_modalities = precomputed_choices[i]
            unique, sampled_counts = np.unique(random_modalities, return_counts=True)
            modality_counts = dict(zip(unique, sampled_counts))

            for modality, count in modality_counts.items():
                counts[modality] += count

            for modality, count in modality_counts.items():
                buffer = data[modality]
                for _ in range(count):
                    add_noise = np.random.random() < noise_ratio
                    embedding = add_random_or_real_embedding(buffer, add_noise, LATENT_SPACE_DIM)
                    combined_sum += embedding

                    if not add_noise:
                        combination_counts[modality] += 1

            combined_data[i] = combined_sum
            for label, count in combination_counts.items():
                labels_data[label][i] = count

        # Save the data to an HDF5 file with compression for efficiency
        output_file = Path(save_path, f"{walk_distance}_embeddings.h5")
        with h5py.File(output_file, "w") as f_out:
            # Save combined embeddings
            f_out.create_dataset("X", data=combined_data, compression="gzip")
            # Save labels
            for label, data in labels_data.items():
                f_out.create_dataset(label, data=data, compression="gzip")

        logging.info(f"Saved HDF5 file to {output_file}")


if __name__ == '__main__':
    main()
