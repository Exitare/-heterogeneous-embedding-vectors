import h5py
import numpy as np
from tqdm import tqdm
from pathlib import Path
from argparse import ArgumentParser
import logging
import random
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration Constants
SAVE_FOLDER = Path("results", "recognizer", "summed_embeddings", "multi")
LOAD_FILE = Path("embedding_data.h5")
LATENT_SPACE_DIM = 767
CHUNK_SIZE = 10000  # Number of embeddings per chunk


class EmbeddingBuffer:
    """
    A buffer to manage chunks of embeddings for a given modality.
    Handles both structured and unstructured datasets.
    """

    def __init__(
            self,
            dataset: h5py.Dataset,
            num_rows: int,
            chunk_size: int,
            latent_dim: int,
            filter_indices: Optional[List[int]] = None,
    ):
        self.dataset = dataset
        self.chunk_size = chunk_size
        self.latent_dim = latent_dim

        if filter_indices is not None:
            self.indices = np.array(filter_indices)
            self.num_rows = len(self.indices)
        else:
            self.indices = np.arange(num_rows)
            self.num_rows = num_rows

        np.random.shuffle(self.indices)
        self.current_chunk = None
        self.current_index = 0
        self.chunk_pointer = 0
        self.total_chunks = int(np.ceil(self.num_rows / self.chunk_size))

        # Determine if the dataset is structured
        if self.dataset.dtype.names:
            self.structured = True
            self.field_names = self.dataset.dtype.names[:self.latent_dim]
            logging.info(f"Dataset '{self.dataset.name}' is structured.")
        else:
            self.structured = False
            logging.info(f"Dataset '{self.dataset.name}' is unstructured.")

    def load_next_chunk(self):
        """
        Loads the next chunk of embeddings into the buffer.
        """
        if self.chunk_pointer >= self.total_chunks:
            # Re-shuffle indices when all chunks have been used
            np.random.shuffle(self.indices)
            self.chunk_pointer = 0

        start = self.chunk_pointer * self.chunk_size
        end = min(start + self.chunk_size, self.num_rows)
        chunk_indices = self.indices[start:end]

        # Sort chunk_indices to satisfy h5py's requirement for increasing order
        sorted_chunk_indices = np.sort(chunk_indices)

        try:
            rows = self.dataset[sorted_chunk_indices]
        except Exception as e:
            logging.error(f"Error accessing dataset rows: {e}")
            raise

        if self.structured:
            try:
                # Extract and stack fields across all rows
                self.current_chunk = np.stack(
                    [rows[field] for field in self.field_names], axis=1
                ).astype(np.float32)
            except IndexError as e:
                logging.error(f"Structured indexing error: {e}")
                logging.error(f"Available fields: {self.dataset.dtype.names}")
                raise
            except Exception as e:
                logging.error(f"Error processing structured dataset: {e}")
                raise
        else:
            try:
                # Assume rows are 2D numeric arrays; slice columns up to latent_dim
                self.current_chunk = rows[:, : self.latent_dim].astype(np.float32)
            except IndexError as e:
                logging.error(f"Unstructured slicing error: {e}")
                raise
            except Exception as e:
                logging.error(f"Error processing unstructured dataset: {e}")
                raise

        self.chunk_pointer += 1
        self.current_index = 0
        logging.debug(
            f"Loaded chunk {self.chunk_pointer}/{self.total_chunks} for dataset '{self.dataset.name}'."
        )

    def get_next_embedding(self) -> np.ndarray:
        """
        Retrieves the next embedding from the current chunk.
        Loads a new chunk if the current one is exhausted.
        """
        if self.current_chunk is None or self.current_index >= self.current_chunk.shape[0]:
            self.load_next_chunk()

        embedding = self.current_chunk[self.current_index]
        self.current_index += 1
        return embedding


def get_total_rows_and_columns(f: h5py.File, group: str) -> (int, int):
    """
    Returns the total number of rows and ensures columns are compatible for summation.
    """
    dataset = f[group]["embeddings"]
    total_rows = dataset.shape[0]
    if dataset.dtype.names:
        total_columns = len(dataset.dtype.names)  # Number of fields
    else:
        total_columns = dataset.shape[1] if len(dataset.shape) > 1 else 1
    total_columns = min(total_columns, LATENT_SPACE_DIM)
    return total_rows, total_columns


def filter_rows_by_cancer(dataset: h5py.Dataset, cancer_type: str) -> List[int]:
    """
    Filters rows by cancer type within the given dataset.
    Assumes there is a 'cancer' field in the dataset.
    """
    if 'cancer' not in dataset.dtype.names:
        logging.error(f"'cancer' field not found in dataset '{dataset.name}'.")
        raise KeyError("'cancer' field not found in dataset.")

    # Use vectorized operations for filtering
    cancer_bytes = dataset['cancer']
    # Decode all at once
    cancer_str = np.array([c.decode("utf-8") for c in cancer_bytes])
    indices = np.where(cancer_str == cancer_type)[0]
    return indices.tolist()


def generate_noise(embedding_length: int, scale: float = 0.1) -> np.ndarray:
    """
    Generates Gaussian noise.
    """
    return np.random.normal(loc=0, scale=scale, size=embedding_length).astype(np.float32)


def main():
    # Argument Parsing
    parser = ArgumentParser(
        description='Sum embeddings from different sources with performance improvements'
    )
    parser.add_argument(
        "--walk_distance",
        "-w",
        type=int,
        help="Number of embeddings to sum",
        required=True,
    )
    parser.add_argument(
        "--amount_of_summed_embeddings",
        "-a",
        type=int,
        default=200000,
        help="Amount of summed embeddings to generate",
    )
    parser.add_argument(
        "--selected_cancers",
        "-c",
        nargs="+",
        required=True,
        help="The selected cancer identifiers to sum",
    )
    parser.add_argument(
        "--noise_ratio",
        "-n",
        type=float,
        default=0.0,
        help="Ratio of random noise vectors to add",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug mode",
    )
    args = parser.parse_args()

    amount_of_summed_embeddings = args.amount_of_summed_embeddings
    walk_distance = args.walk_distance
    noise_ratio = args.noise_ratio
    selected_cancers = args.selected_cancers
    cancers = "_".join(selected_cancers)
    debug = args.debug

    # Set logging level based on debug flag
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug(f"Selected cancers: {selected_cancers}")
        logging.debug(f"Walk distance: {walk_distance}")
        logging.debug(f"Amount of summed embeddings: {amount_of_summed_embeddings}")
        logging.debug(f"Noise ratio: {noise_ratio}")

    # Prepare Save Directory
    save_path = SAVE_FOLDER / cancers / str(amount_of_summed_embeddings) / str(noise_ratio)
    save_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"Save path: {save_path}")

    # Initialize data structures
    combined_data = np.zeros((amount_of_summed_embeddings, LATENT_SPACE_DIM), dtype=np.float32)
    labels = ["Text", "Image", "Mutation", "RNA"] + selected_cancers
    labels_data = {label: np.zeros(amount_of_summed_embeddings, dtype=np.int32) for label in labels}

    modality_choices_general = ["Text", "Image", "Mutation"]

    with h5py.File(LOAD_FILE, 'r') as f:
        # Validate selected cancers and get their indices
        cancer_indices = {}
        rna_dataset = f['rna']['embeddings']
        for cancer in selected_cancers:
            indices = filter_rows_by_cancer(rna_dataset, cancer)
            if len(indices) == 0:
                logging.warning(f"No rows found for cancer type '{cancer}'. Skipping.")
            else:
                cancer_indices[cancer] = indices
                logging.info(f"Found {len(indices)} rows for cancer type '{cancer}'.")

        if not cancer_indices:
            logging.error("No valid cancer types found. Exiting.")
            raise ValueError("No valid cancer types found. Exiting.")

        # Get total rows and columns for other modalities
        annotation_total_rows, annotation_columns = get_total_rows_and_columns(f, "annotations")
        image_total_rows, image_columns = get_total_rows_and_columns(f, "images")
        mutation_total_rows, mutation_columns = get_total_rows_and_columns(f, "mutations")

        # Ensure all modalities have compatible dimensions
        if not (annotation_columns == image_columns == mutation_columns == LATENT_SPACE_DIM):
            logging.error(f"All modalities must have exactly {LATENT_SPACE_DIM} usable columns for summation")
            raise ValueError(f"All modalities must have exactly {LATENT_SPACE_DIM} usable columns for summation")

        logging.info("All modalities have compatible dimensions.")

        # Initialize buffers for each modality
        buffers = {
            'Text': EmbeddingBuffer(f['annotations']['embeddings'], annotation_total_rows, CHUNK_SIZE,
                                    LATENT_SPACE_DIM),
            'Image': EmbeddingBuffer(f['images']['embeddings'], image_total_rows, CHUNK_SIZE, LATENT_SPACE_DIM),
            'Mutation': EmbeddingBuffer(f['mutations']['embeddings'], mutation_total_rows, CHUNK_SIZE,
                                        LATENT_SPACE_DIM),
        }

        # Initialize buffers for each selected cancer's RNA
        for cancer, indices in cancer_indices.items():
            buffers[cancer] = EmbeddingBuffer(
                dataset=f['rna']['embeddings'],
                num_rows=len(indices),
                chunk_size=CHUNK_SIZE,
                latent_dim=LATENT_SPACE_DIM,
                filter_indices=indices
            )

        # Pre-load the first chunk for each buffer
        for buffer in buffers.values():
            buffer.load_next_chunk()

        selected_cancer_list = []

        # Generate summed embeddings
        for i in tqdm(range(amount_of_summed_embeddings), desc="Generating Summed Embeddings"):
            combined_sum = np.zeros(LATENT_SPACE_DIM, dtype=np.float32)

            # Select a cancer type randomly for this summed embedding
            selected_cancer = random.choice(selected_cancers)
            selected_cancer_list.append(selected_cancer)

            # Define modality choices for this summed embedding
            modality_choices = modality_choices_general + [selected_cancer]
            random_modalities = np.random.choice(modality_choices, size=walk_distance)
            unique, counts = np.unique(random_modalities, return_counts=True)
            modality_counts = dict(zip(unique, counts))

            for modality, count in modality_counts.items():
                buffer = buffers[modality]
                for _ in range(count):
                    if random.random() < noise_ratio:
                        # Add noise vector
                        noise_vector = generate_noise(LATENT_SPACE_DIM)
                        combined_sum += noise_vector
                        continue

                    try:
                        embedding = buffer.get_next_embedding()
                        combined_sum += embedding
                        labels_data[modality][i] += 1

                        # If the modality is the selected cancer, increment RNA label
                        if modality == selected_cancer:
                            labels_data["RNA"][i] += 1
                    except IndexError as e:
                        logging.error(f"IndexError when accessing embedding: {e}")
                        continue
                    except Exception as e:
                        logging.error(f"Unexpected error when accessing embedding: {e}")
                        continue

            combined_data[i] = combined_sum

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
