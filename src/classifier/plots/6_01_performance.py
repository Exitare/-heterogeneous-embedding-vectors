from pathlib import Path
import pandas as pd
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
from click import style

save_folder = Path("figures", "classifier")


def create_grid_plot(df: pd.DataFrame, metric: str):
    # create a grid plot for the accuracy, each unique value of walks should have a separate plot, the hue is cancer
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x="walks", y=metric, hue="cancer", ax=ax,
                order=["3_3", "3_4", "3_5", "4_3", "4_4", "4_5", "5_3", "5_4", "5_5"])
    ax.set_title(f"{metric.upper()} Score")
    ax.set_ylabel(f"{metric.upper()} Score")
    ax.set_xlabel("")

    labels = [item.get_text() for item in ax.get_xticklabels()]
    labels = [f"Distance: {label.split('_')[0]}\n Amount: {label.split('_')[1]}" for label in labels]
    ax.set_xticklabels(labels)
    # adjust legend
    ax.legend(loc='lower center', ncols=7, title="Cancer Type", bbox_to_anchor=(0.5, -0.28))
    plt.tight_layout()
    plt.savefig(Path(save_folder, f"{metric}_score_grid.png"), dpi=300)
    plt.close('all')


def create_hue_performance_plot(df: pd.DataFrame, metric: str):
    # df = df[df["cancer"] == "All"].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x="cancer", y=metric, hue="cancer", ax=ax)
    ax.set_title(f"{metric.upper()} score")
    ax.set_ylabel(f"{metric.upper()} score")
    ax.set_xlabel("Cancer")
    plt.tight_layout()
    plt.savefig(Path(save_folder, f"{metric}_score.png"), dpi=300)
    plt.close('all')


def create_performance_overview_plot(df: pd.DataFrame):
    df = df[df["cancer"] == "All"].copy()
    # df melt
    df = df.melt(id_vars=["cancer"], value_vars=["precision", "recall", "auc"], var_name="metric", value_name="score")
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x="cancer", y="score", hue="metric", ax=ax)
    ax.set_title(f"Overview scores")
    ax.set_ylabel(f"Overview scores")

    ax.set_xlabel("")
    plt.legend(title="Metrics", loc='upper left')
    plt.tight_layout()
    plt.savefig(Path(save_folder, f"overview_scores.png"), dpi=300)
    plt.close('all')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--cancer", "-c", nargs="+", required=True, help="The cancer types to work with.")
    args = parser.parse_args()

    selected_cancers = args.cancer
    cancers = "_".join(selected_cancers)

    save_folder = Path(save_folder, cancers, "performance")

    if not save_folder.exists():
        save_folder.mkdir(parents=True)

    # load all runs from results/classifier/classification
    results = []
    # iterate over all subfolders
    cancer_folder = Path("results", "classifier", "classification", cancers)
    for run in cancer_folder.iterdir():
        if run.is_file():
            continue

        for iteration in run.iterdir():
            if iteration.is_file():
                continue

            print(iteration)
            try:
                df = pd.read_csv(Path(iteration, "results.csv"))
                # load the results from the run
                results.append(df)
            except FileNotFoundError:
                continue

    # concatenate all results
    results = pd.concat(results)
    # create new column walks by combining walk distance and amount_of_walk using an underscore
    results["walks"] = results["walk_distance"].astype(str) + "_" + results["amount_of_walks"].astype(str)
    print(results)

    create_hue_performance_plot(results, "accuracy")
    create_hue_performance_plot(results, "f1")
    create_performance_overview_plot(results)

    create_grid_plot(results, "accuracy")
    create_grid_plot(results, "f1")
