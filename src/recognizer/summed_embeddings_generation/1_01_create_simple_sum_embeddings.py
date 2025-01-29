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
LATENT_SPACE_DIM = 767
CHUNK_SIZE = 100000  # Number of embeddings per chunk

modality_weights = {
    'RNA': 0.25,
    'Text': 0.25,
    'Image': 0.25,
    'Mutation': 0.25
}

modality_choices = list(modality_weights.keys())
modality_probs = list(modality_weights.values())


class EmbeddingBuffer:
    def __init__(self, dataset, num_rows, chunk_size, latent_dim, filter_indices=None):
        self.dataset = dataset
        self.chunk_size = chunk_size
        self.latent_dim = latent_dim
        self.indices = (
            np.array(filter_indices) if filter_indices is not None else np.arange(num_rows)
        )
        self.num_rows = len(self.indices)
        np.random.shuffle(self.indices)
        self.current_chunk = None
        self.current_index = 0
        self.chunk_pointer = 0
        self.total_chunks = int(np.ceil(self.num_rows / self.chunk_size))
        self.field_names = dataset.dtype.names[:latent_dim]

    def load_next_chunk(self):
        """
        Loads the next chunk of embeddings into the buffer, ensuring sorted indices for HDF5 slicing.
        """
        if self.chunk_pointer >= self.total_chunks:
            # Re-shuffle indices only when all chunks have been processed
            np.random.shuffle(self.indices)
            self.chunk_pointer = 0

        # Get the indices for the current chunk
        start = self.chunk_pointer * self.chunk_size
        end = min(start + self.chunk_size, self.num_rows)
        chunk_indices = self.indices[start:end]

        # Sort indices to satisfy HDF5 slicing requirements
        sorted_chunk_indices = np.sort(chunk_indices)

        try:
            rows = self.dataset[sorted_chunk_indices]
            # Access fields directly and stack them
            self.current_chunk = np.stack(
                [rows[name] for name in self.field_names], axis=1
            ).astype(np.float32)
        except Exception as e:
            logging.error(f"Error accessing dataset rows: {e}")
            raise

        self.chunk_pointer += 1
        self.current_index = 0
        logging.debug(
            f"Loaded chunk {self.chunk_pointer}/{self.total_chunks} for dataset '{self.dataset.name}'."
        )

    def get_next_embedding(self):
        if self.current_chunk is None or self.current_index >= self.current_chunk.shape[0]:
            self.load_next_chunk()
        embedding = self.current_chunk[self.current_index]
        self.current_index += 1
        return embedding


def get_total_rows_and_columns(f, group):
    """
    Returns the total number of rows and ensures columns are compatible for summation.
    """
    dataset = f[group]["embeddings"]
    total_rows = dataset.shape[0]
    total_columns = min(len(dataset.dtype), LATENT_SPACE_DIM)  # Limit to LATENT_SPACE_DIM
    return total_rows, total_columns


def add_random_or_real_embedding(buffer, add_noise, latent_dim):
    """
    Adds either random Gaussian noise or a real embedding from the buffer.
    """
    if add_noise:
        return np.random.uniform(-1, 1, size=latent_dim).astype(np.float32)
    else:
        return buffer.get_next_embedding()


def adjust_chunk_size(total_rows, default_size=100000):
    """
    Adjust the chunk size dynamically based on the dataset size.
    """
    return min(total_rows, default_size)


def main():
    # Argument Parsing
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
    noise_ratio: float = args.noise_ratio
    selected_cancers = args.selected_cancers
    load_folder: Path = Path(args.load_path)

    if len(selected_cancers) == 1:
        logging.info("Selected cancers is a single string. Converting...")
        selected_cancers = selected_cancers[0].split(" ")

    cancers = "_".join(selected_cancers)

    logging.info(
        f"Parameters: walk_distance={walk_distance}, amount_of_summed_embeddings={amount_of_summed_embeddings}, noise_ratio={noise_ratio}")

    # Prepare Save Directory
    save_path = Path(SAVE_FOLDER, str(amount_of_summed_embeddings), str(noise_ratio))
    save_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"Save path: {save_path}")

    # Initialize Data Structures
    combined_data = np.zeros((amount_of_summed_embeddings, LATENT_SPACE_DIM), dtype=np.float32)
    labels_data = {label: np.zeros(amount_of_summed_embeddings, dtype=np.int32)
                   for label in ["Text", "Image", "RNA", "Mutation"]}

    with h5py.File(Path(load_folder, f"{cancers}.h5"), 'r') as f:
        # Get total rows and columns for each modality
        rna_total_rows, rna_columns = get_total_rows_and_columns(f, "rna")
        image_total_rows, image_columns = get_total_rows_and_columns(f, "images")
        mutation_total_rows, mutation_columns = get_total_rows_and_columns(f, "mutations")
        annotation_total_rows, annotation_columns = get_total_rows_and_columns(f, "annotations")

        # Ensure all modalities have the same column dimensions
        assert rna_columns == image_columns == mutation_columns == annotation_columns == LATENT_SPACE_DIM, \
            f"All modalities must have exactly {LATENT_SPACE_DIM} usable columns for summation"

        logging.info("All modalities have compatible dimensions.")

        logging.info("Initializing buffers...")
        # Adjust chunk size dynamically for each modality
        buffers = {
            'RNA': EmbeddingBuffer(f['rna']['embeddings'], rna_total_rows, adjust_chunk_size(rna_total_rows), LATENT_SPACE_DIM),
            'Text': EmbeddingBuffer(f['annotations']['embeddings'], annotation_total_rows, adjust_chunk_size(annotation_total_rows), LATENT_SPACE_DIM),
            'Image': EmbeddingBuffer(f['images']['embeddings'], image_total_rows, adjust_chunk_size(image_total_rows), LATENT_SPACE_DIM),
            'Mutation': EmbeddingBuffer(f['mutations']['embeddings'], mutation_total_rows, adjust_chunk_size(mutation_total_rows), LATENT_SPACE_DIM)
        }

        counts = {modality: 0 for modality in modality_choices}

        # Precompute random choices
        precomputed_choices = np.random.choice(
            modality_choices,
            size=(amount_of_summed_embeddings, walk_distance),
            p=modality_probs
        )

        for i in tqdm(range(amount_of_summed_embeddings), desc="Generating Summed Embeddings"):
            combined_sum = np.zeros(LATENT_SPACE_DIM, dtype=np.float32)
            combination_counts = {modality: 0 for modality in modality_choices}

            # Use precomputed random modalities
            random_modalities = precomputed_choices[i]
            unique, sampled_counts = np.unique(random_modalities, return_counts=True)
            modality_counts = dict(zip(unique, sampled_counts))

            # Update global counts
            for modality, count in modality_counts.items():
                counts[modality] += count

            for modality, count in modality_counts.items():
                buffer = buffers[modality]
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
