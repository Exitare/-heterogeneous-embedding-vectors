import pandas as pd
from argparse import ArgumentParser
from pathlib import Path
from tqdm import tqdm
import numpy as np
import random
import networkx as nx
from node2vec import Node2Vec
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt

results_folder = Path("results", "graph_embeddings")
embeddings_size = 768




# Function to sum embeddings from the random walk and return individual embeddings and additional info
def sum_embeddings_from_walk(graph, walk):
    individual_embeddings = [graph.nodes[node]['embedding'] for node in walk]
    additional_info = [graph.nodes[node]['additional_info'] for node in walk]
    aggregated_embedding = np.sum(individual_embeddings, axis=0)
    return aggregated_embedding, individual_embeddings, additional_info


def random_sum_embeddings(embeddings, max_count):
    # Randomly choose embeddings up to max_count
    n = random.randint(1, max_count)  # Ensure at least one is selected
    chosen_indices = random.sample(range(len(embeddings)), n)
    chosen_embeddings = embeddings.iloc[chosen_indices]
    summed_embeddings = chosen_embeddings.sum(axis=0)
    return summed_embeddings, n


if __name__ == '__main__':

    parser = ArgumentParser()
    parser.add_argument("--cancer", "-c", nargs='+', required=True, help="The cancer type to work with.")
    parser.add_argument("--iterations", "-i", type=int, required=False, help="Number of iterations to run.",
                        default=1000)
    parser.add_argument("--walks", "-w", type=int, required=False, help="Number of walks to perform.", default=1000)
    args = parser.parse_args()

    selected_cancers = args.cancer
    iterations = args.iterations
    cancers = "_".join(selected_cancers)
    num_walks = args.walks

    results_folder = Path(results_folder, cancers, "graph_generation")

    if not results_folder.exists():
        results_folder.mkdir(parents=True)

    loaded_cancer_embeddings = {}
    for cancer in selected_cancers:
        loaded_cancer_embeddings[cancer] = pd.read_csv(
            Path("results", "embeddings", "cancer", f"{cancer.lower()}_embeddings.csv"), nrows=100)

    # Load the embeddings from CSV files
    image_embeddings = pd.read_csv(Path("results", "embeddings", 'image_embeddings.csv'), nrows=100)
    sentence_embeddings = pd.read_csv(Path("results", "embeddings", 'sentence_embeddings.csv'), nrows=100)

    combined_data = []

    for _ in tqdm(range(iterations)):
        # Determine random order for processing embeddings
        embeddings_list = [(sentence_embeddings, 'Text'), (image_embeddings, 'Image')]
        for cancer_type, cancer_embedding in loaded_cancer_embeddings.items():
            embeddings_list.append((cancer_embedding, cancer_type))

        random.shuffle(embeddings_list)

        combined_sum = pd.Series(np.zeros_like(embeddings_list[0][0].iloc[0]), index=embeddings_list[0][0].columns)
        # remaining embeddings should be a number between 2 and 10
        remaining_embeddings = random.randint(2, 10)
        combination_counts = {}
        selected_cancer_type = None

        for embeddings, name in embeddings_list:
            if remaining_embeddings > 0:
                if name in loaded_cancer_embeddings.keys():
                    # If a specific cancer type was selected, continue using that type
                    if selected_cancer_type is None:
                        selected_cancer_type = name
                    elif name != selected_cancer_type:
                        combination_counts[name] = 0
                        continue

                current_sum, count = random_sum_embeddings(embeddings, remaining_embeddings)
                combined_sum += current_sum
                remaining_embeddings -= count
                combination_counts[name] = count
            else:
                combination_counts[name] = 0

        # Ensure there is at least one embedding selected in total (avoid all-zero entries)
        if all(v == 0 for v in combination_counts.values()):
            embeddings, name = random.choice(embeddings_list)
            current_sum, count = random_sum_embeddings(embeddings, 1)  # Force at least one selection
            combined_sum += current_sum
            combination_counts[name] = count

        # Sort the combination counts by the keys
        combination_counts = dict(sorted(combination_counts.items()))

        # Combine combined_sum and the combination_counts which are Image, Text and the cancer types
        combined_data.append(
            list(combined_sum) + [combination_counts.get('Image', 0), combination_counts.get('Text', 0)] + [
                combination_counts.get(cancer_type, 0) for cancer_type in loaded_cancer_embeddings.keys()])

        # Save the data to CSV
    column_names = list(embeddings_list[0][0].columns) + ['Image', 'Text'] + [
        cancer_type for cancer_type in loaded_cancer_embeddings.keys()]

    combined_df = pd.DataFrame(combined_data, columns=column_names)
    # create another column called RNA which is the sum of the cancer types in the dataset, defined by the loaded_cancer_embeddings
    combined_df["RNA"] = combined_df[[cancer_type for cancer_type in loaded_cancer_embeddings.keys()]].sum(axis=1)
    # save combined_df to a csv file
    combined_df.to_csv(Path(results_folder, "combined_embeddings.csv"), index=False)

    # Separate the embeddings and the additional columns
    embeddings = combined_df.iloc[:, :embeddings_size].values
    additional_columns = combined_df.iloc[:, embeddings_size:]
    print(additional_columns)

    # Create the graph and add nodes with embeddings
    G = nx.Graph()
    node_to_index = {}
    for idx, row in combined_df.iterrows():
        node_id = idx  # or some unique identifier if available
        embedding = row[:embeddings_size].values
        additional_info = row[embeddings_size:].values

        # Determine cancer type
        if row['BRCA'] > 0:
            cancer_type = 'BRCA'
        elif row['LAML'] > 0:
            cancer_type = 'LAML'
        else:
            cancer_type = 'Unknown'

        # Add node with attributes
        G.add_node(node_id, embedding=embedding, additional_info=additional_info, cancer_type=cancer_type)
        node_to_index[node_id] = idx

    # Compute similarity matrix and add edges
    similarity_matrix = np.corrcoef(embeddings)
    similarity_threshold = 0.8

    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            if similarity_matrix[i, j] > similarity_threshold:
                G.add_edge(i, j, weight=similarity_matrix[i, j])

    print(G)

    # Step 2: Configure Node2Vec
    node2vec = Node2Vec(G, dimensions=64, walk_length=30, num_walks=200, p=1, q=1)

    # Step 3: Generate walks and train the model
    model = node2vec.fit(window=10, min_count=1, batch_words=4)

    # Step 4: Get embeddings
    embeddings = {str(node): model.wv[str(node)] for node in G.nodes()}

    # Get embeddings
    embeddings_dict = {str(node): model.wv[str(node)] for node in G.nodes()}
    # Extract embeddings and cancer types for t-SNE
    embeddings_matrix = np.array(list(embeddings_dict.values()))
    cancer_labels = [G.nodes[node]['cancer_type'] for node in G.nodes()]

    # t-SNE for dimensionality reduction
    tsne = TSNE(n_components=2, random_state=42)
    embeddings_2d = tsne.fit_transform(embeddings_matrix)

    # Color coding
    unique_labels = list(set(cancer_labels))
    label_to_color = {label: idx for idx, label in enumerate(unique_labels)}
    colors = [label_to_color[label] for label in cancer_labels]

    # Plot with color-coding
    plt.figure(figsize=(12, 10))
    for label in unique_labels:
        indices = [i for i, l in enumerate(cancer_labels) if l == label]
        plt.scatter(embeddings_2d[indices, 0], embeddings_2d[indices, 1], label=label, alpha=0.7)

    plt.legend()
    plt.title('Node Embeddings Visualized with t-SNE and Color-Coded by Cancer Type')
    plt.xlabel('t-SNE Component 1')
    plt.ylabel('t-SNE Component 2')
    plt.show()