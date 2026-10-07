from __future__ import annotations

import argparse
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib as mpl
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch


mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 14,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "legend.fontsize": 11,
    "axes.linewidth": 0.95,
    "xtick.major.width": 0.9,
    "ytick.major.width": 0.9,
    "xtick.major.size": 4.0,
    "ytick.major.size": 4.0,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

PINK = "#D33682"
TEAL = "#35B9C5"
BLUE = "#3E7BB6"
GREEN = "#2A9D72"
PURPLE = "#7651A3"
YELLOW = "#F2B512"
SALMON = "#DF7B8A"
DARK_GRAY = "#666666"
LIGHT_GRAY = "#BDBDBD"

BLUE_CMAP = LinearSegmentedColormap.from_list(
    "blue", ["#F7F7F7", "#BFDDE5", TEAL, BLUE]
)
GREEN_CMAP = LinearSegmentedColormap.from_list(
    "green", ["#F7F7F7", "#BCE3D1", GREEN, "#176B4C"]
)


def style_axis(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(axis="both", direction="out", width=0.9, length=4)
    ax.grid(False)



FUNCTION_COLS = [f"F{i}" for i in range(1, 7)]
EVIDENCE_COLS = [f"E{i}" for i in range(1, 7)]
VALIDATION_STAGES = ["V0", "V1", "V2", "V3", "V4"]
STATUS_ORDER = ["full-agentic", "agent-adjacent"]
STATUS_LABELS = {
    "full-agentic": "Full-agentic",
    "agent-adjacent": "Agent-adjacent",
}
STATUS_COLORS = {
    "full-agentic": PINK,
    "agent-adjacent": TEAL,
}
STAGE_COLORS = {
    "V0": DARK_GRAY,
    "V1": LIGHT_GRAY,
    "V2": YELLOW,
    "V3": TEAL,
    "V4": PINK,
}
QUALIFIER_ORDER = ["B", "S", "R", "X", "H", "P", "C"]
QUALIFIER_LABELS = {
    "B": "Benchmark",
    "S": "Statistics / uncertainty",
    "R": "Robustness / failure",
    "X": "External / independent",
    "H": "Human / expert",
    "P": "Prospective testing",
    "C": "Closed-loop refinement",
}

# Preserve the original CSV categories. Only display labels are changed.
CATEGORY_LABELS = {
    "computational_pathology_bioimaging": "Computational pathology / bioimaging",
    "cross_domain_bioinformatics": "Cross-domain bioinformatics",
    "drug_discovery": "Drug discovery",
    "epigenomics": "Epigenomics",
    "genomics": "Genomics",
    "proteomics": "Proteomics",
    "transcriptomics": "Transcriptomics",
}




def parse_args():
    parser = argparse.ArgumentParser(
        description="Draw agentic-status sensitivity and exact-category FEV figures."
    )
    parser.add_argument("--input", default="AgenticSystem.csv")
    parser.add_argument("--output-dir", default="reviewer_figures")
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = {
        "record_id", "primary_category", "agentic_status",
        "cumulative_level", "qualifiers", "publication_year",
        *FUNCTION_COLS, *EVIDENCE_COLS,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    text_columns = [
        "record_id", "primary_category", "agentic_status",
        "cumulative_level", "qualifiers",
        *FUNCTION_COLS, *EVIDENCE_COLS,
    ]
    for col in text_columns:
        df[col] = clean_text(df[col])

    if df["record_id"].eq("").any():
        raise ValueError("Blank record_id values found")
    if df["record_id"].duplicated().any():
        duplicates = df.loc[df["record_id"].duplicated(False), "record_id"].tolist()
        raise ValueError(f"Duplicate record IDs: {duplicates[:10]}")

    unexpected_status = sorted(set(df["agentic_status"]) - set(STATUS_ORDER))
    if unexpected_status:
        raise ValueError(f"Unexpected agentic_status values: {unexpected_status}")

    allowed_codes = {"Y", "N", "NR", "U", ""}
    for col in FUNCTION_COLS + EVIDENCE_COLS:
        unexpected = sorted(set(df[col]) - allowed_codes)
        if unexpected:
            raise ValueError(f"Unexpected values in {col}: {unexpected}")

    unexpected_stages = sorted(
        set(df["cumulative_level"]) - set(VALIDATION_STAGES) - {""}
    )
    if unexpected_stages:
        raise ValueError(f"Unexpected Validation levels: {unexpected_stages}")

    unknown_categories = sorted(set(df["primary_category"]) - set(CATEGORY_LABELS))
    if unknown_categories:
        warnings.warn(
            "Unlisted categories will retain raw CSV names: "
            + ", ".join(unknown_categories)
        )
        for category in unknown_categories:
            CATEGORY_LABELS[category] = category

    df["publication_year"] = pd.to_numeric(df["publication_year"], errors="coerce")
    df["function_breadth"] = df[FUNCTION_COLS].eq("Y").sum(axis=1)
    df["evidence_breadth"] = df[EVIDENCE_COLS].eq("Y").sum(axis=1)
    return df


def qualifier_matrix(df: pd.DataFrame) -> pd.DataFrame:
    parsed = df["qualifiers"].apply(
        lambda value: {token.strip() for token in value.split(";") if token.strip()}
    )
    return pd.DataFrame(
        {q: parsed.apply(lambda values, q=q: q in values) for q in QUALIFIER_ORDER},
        index=df.index,
    )


def percent_y(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return pd.Series(
        {column: 100.0 * frame[column].eq("Y").mean() for column in columns},
        dtype=float,
    )


def save_figure(fig, output_base: Path, dpi: int):
    fig.savefig(output_base.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    fig.savefig(output_base.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def add_panel_label(ax, label: str):
    ax.text(
        -0.075, 1.095, label, transform=ax.transAxes,
        ha="left", va="bottom", fontweight="bold",
        clip_on=False,
    )


def annotate_grouped_bars(
    ax,
    containers,
    y_offsets=(2.0, 5.0),
    fontsize=8,
):
    """
    Add percentage labels above grouped bars.

    Different vertical offsets are used for the two groups so labels
    do not overlap when bar heights are similar.
    """

    for group_index, container in enumerate(containers):
        y_offset = y_offsets[group_index]

        for bar in container:
            height = bar.get_height()

            ax.annotate(
                f"{height:.0f}%",
                xy=(
                    bar.get_x() + bar.get_width() / 2,
                    height,
                ),
                xytext=(0, y_offset),
                textcoords="offset points",
                ha="center",
                va="bottom",
                clip_on=False,
            )

def reviewer_sensitivity_figure(
    df: pd.DataFrame,
    outdir: Path,
    dpi: int,
):
    """
    Figure 3:
    Sensitivity analysis comparing full-agentic and
    agent-adjacent system-use-case records.

    Panel order:
        a. Sample composition
        b. Validation-level distribution
        c. Functionality and Evidence breadth
        d. Functionality prevalence
        e. Evidence prevalence
        f. Validation qualifiers
    """

    qmat = qualifier_matrix(df)

    fig, axes = plt.subplots(
        2,
        3,
        figsize=(15.5, 8.4),
    )

    width = 0.34

    status_legend_labels = [
        (
            f"{STATUS_LABELS[status]} "
            f"(n={(df['agentic_status'] == status).sum()})"
        )
        for status in STATUS_ORDER
    ]

    # ==============================================================
    # Panel a: Sample composition
    # ==============================================================

    ax = axes[0, 0]

    counts = (
        df["agentic_status"]
        .value_counts()
        .reindex(STATUS_ORDER)
    )

    bars = ax.bar(
        [
            STATUS_LABELS[status]
            for status in STATUS_ORDER
        ],
        counts.values,
        color=[
            STATUS_COLORS[status]
            for status in STATUS_ORDER
        ],
        edgecolor="white",
        linewidth=0.7,
        width=0.72,
    )

    ax.set_ylabel("Number of records")

    ax.set_ylim(
        0,
        counts.max() * 1.17,
    )

    ax.bar_label(
        bars,
        labels=[
            (
                f"{count}\n"
                f"({100 * count / len(df):.1f}%)"
            )
            for count in counts
        ],
        padding=3,
        fontsize=8,
        fontweight="bold",
    )

    add_panel_label(
        ax,
        "a",
    )

    # ==============================================================
    # Panel b: Validation-level distribution
    # ==============================================================

    ax = axes[0, 1]

    y = np.arange(
        len(STATUS_ORDER)
    )

    left = np.zeros(
        len(STATUS_ORDER)
    )

    stage_rows = []

    for status in STATUS_ORDER:
        subset = df[
            df["agentic_status"] == status
        ]

        stage_counts = (
            subset["cumulative_level"]
            .value_counts()
            .reindex(
                VALIDATION_STAGES,
                fill_value=0,
            )
        )

        stage_rows.append(
            100.0
            * stage_counts
            / len(subset)
        )

    stage_table = pd.DataFrame(
        stage_rows,
        index=STATUS_ORDER,
    )

    for stage in VALIDATION_STAGES:
        values = stage_table[
            stage
        ].values

        ax.barh(
            y,
            values,
            left=left,
            color=STAGE_COLORS[stage],
            label=stage,
            edgecolor="white",
            linewidth=0.7,
            height=0.68,
        )

        for row_index, (
            start,
            value,
        ) in enumerate(
            zip(left, values)
        ):
            if value >= 8:
                ax.text(
                    start + value / 2,
                    row_index,
                    f"{value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                )

        left += values

    ax.set_yticks(
        y,
        [
            STATUS_LABELS[status]
            for status in STATUS_ORDER
        ],
    )

    ax.invert_yaxis()

    ax.set_xlim(
        0,
        100,
    )

    ax.set_xlabel(
        "Records at each validation level (%)"
    )

    ax.xaxis.set_major_formatter(
        mtick.PercentFormatter(
            xmax=100,
            decimals=0,
        )
    )

    # Horizontal legend above the panel.
    ax.legend(
        title="Validation level",
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=len(VALIDATION_STAGES),
        frameon=False,
        borderaxespad=0,
        fontsize=8,
        title_fontsize=9,
        handlelength=1.0,
        columnspacing=0.8,
        labelspacing=0.3,
    )

    add_panel_label(
        ax,
        "b",
    )

    # ==============================================================
    # Panel c: Functionality and Evidence breadth
    # ==============================================================

    ax = axes[0, 2]

    positions = np.array([
        0.00,
        0.75,
        2.10,
        2.85,
    ])

    breadth_data = []
    breadth_colors = []

    for metric in [
        "function_breadth",
        "evidence_breadth",
    ]:
        for status in STATUS_ORDER:
            breadth_data.append(
                df.loc[
                    df["agentic_status"] == status,
                    metric,
                ].values
            )

            breadth_colors.append(
                STATUS_COLORS[status]
            )

    boxplot = ax.boxplot(
        breadth_data,
        positions=positions,
        widths=0.52,
        patch_artist=True,
        showmeans=True,
        meanline=False,
        meanprops={
            "marker": "^",
            "markerfacecolor": "#F2B512",
            "markeredgecolor": "#8A6500",
            "markeredgewidth": 0.8,
            "markersize": 7,
        },
        medianprops={
            "color": "black",
            "linewidth": 1.2,
        },
        boxprops={
            "linewidth": 1.0,
        },
        whiskerprops={
            "linewidth": 1.0,
        },
        capprops={
            "linewidth": 1.0,
        },
        flierprops={
            "marker": "o",
            "markerfacecolor": "white",
            "markeredgecolor": "black",
            "markersize": 5,
            "linestyle": "none",
        },
    )

    for patch, color in zip(
        boxplot["boxes"],
        breadth_colors,
    ):
        patch.set_facecolor(
            color
        )

        patch.set_edgecolor(
            "black"
        )

    ax.set_xticks(
        [0.375, 2.475],
        [
            "Functionality\nbreadth",
            "Evidence\nbreadth",
        ],
    )

    ax.set_xlim(
        -0.55,
        3.40,
    )

    ax.set_ylim(
        -0.2,
        6.4,
    )

    ax.set_ylabel(
        "Breadth score"
    )

    add_panel_label(
        ax,
        "c",
    )

    # ==============================================================
    # Panel d: Functionality prevalence
    # ==============================================================

    ax = axes[1, 0]

    x = np.arange(
        len(FUNCTION_COLS)
    )

    for offset, status in zip(
        [-width / 2, width / 2],
        STATUS_ORDER,
    ):
        subset = df[
            df["agentic_status"] == status
        ]

        values = percent_y(
            subset,
            FUNCTION_COLS,
        )

        ax.bar(
            x + offset,
            values.values,
            width,
            color=STATUS_COLORS[status],
            edgecolor="white",
            linewidth=0.6,
        )

    ax.set_xticks(
        x,
        FUNCTION_COLS,
    )

    ax.set_ylim(
        0,
        105,
    )

    ax.set_ylabel(
        "Systems coded Y (%)"
    )

    ax.yaxis.set_major_formatter(
        mtick.PercentFormatter(
            xmax=100,
            decimals=0,
        )
    )

    add_panel_label(
        ax,
        "d",
    )

    # ==============================================================
    # Panel e: Evidence prevalence
    # ==============================================================

    ax = axes[1, 1]

    x = np.arange(
        len(EVIDENCE_COLS)
    )

    for offset, status in zip(
        [-width / 2, width / 2],
        STATUS_ORDER,
    ):
        subset = df[
            df["agentic_status"] == status
        ]

        values = percent_y(
            subset,
            EVIDENCE_COLS,
        )

        ax.bar(
            x + offset,
            values.values,
            width,
            color=STATUS_COLORS[status],
            edgecolor="white",
            linewidth=0.6,
        )

    ax.set_xticks(
        x,
        EVIDENCE_COLS,
    )

    ax.set_ylim(
        0,
        105,
    )

    ax.set_ylabel(
        "Systems coded Y (%)"
    )

    ax.yaxis.set_major_formatter(
        mtick.PercentFormatter(
            xmax=100,
            decimals=0,
        )
    )

    add_panel_label(
        ax,
        "e",
    )

    # ==============================================================
    # Panel f: Validation qualifiers
    # ==============================================================

    ax = axes[1, 2]

    x = np.arange(
        len(QUALIFIER_ORDER)
    )

    for offset, status in zip(
        [-width / 2, width / 2],
        STATUS_ORDER,
    ):
        idx = df.index[
            df["agentic_status"] == status
        ]

        values = pd.Series({
            qualifier: (
                100.0
                * qmat.loc[
                    idx,
                    qualifier,
                ].mean()
            )
            for qualifier in QUALIFIER_ORDER
        })

        ax.bar(
            x + offset,
            values.values,
            width,
            color=STATUS_COLORS[status],
            edgecolor="white",
            linewidth=0.6,
        )

    ax.set_xticks(
        x,
        QUALIFIER_ORDER,
    )

    ax.set_ylim(
        0,
        105,
    )

    ax.set_ylabel(
        "Records with qualifier (%)"
    )

    ax.yaxis.set_major_formatter(
        mtick.PercentFormatter(
            xmax=100,
            decimals=0,
        )
    )

    add_panel_label(
        ax,
        "f",
    )

    # ==============================================================
    # Shared styling
    # ==============================================================

    for panel_ax in axes.flat:
        style_axis(
            panel_ax
        )

    legend_handles = [
        Patch(
            facecolor=STATUS_COLORS[status],
            edgecolor="none",
        )
        for status in STATUS_ORDER
    ]

    # One shared legend for the agentic-status colors.
    fig.legend(
        legend_handles,
        status_legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=2,
        frameon=False,
        columnspacing=2.0,
        handlelength=1.2,
    )

    # Manual layout avoids overlaps from tight_layout.
    fig.subplots_adjust(
        left=0.07,
        right=0.98,
        bottom=0.13,
        top=0.92,
        wspace=0.62,
        hspace=0.62,
    )

    save_figure(
        fig,
        outdir
        / "figure3_agentic_status_sensitivity",
        dpi,
    )

    return stage_table


def ordered_categories(df: pd.DataFrame) -> list[str]:
    totals = df["primary_category"].value_counts()
    return totals.sort_values(ascending=False).index.tolist()


def category_composition_table(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    return pd.crosstab(df["primary_category"], df["agentic_status"]).reindex(
        index=categories, columns=STATUS_ORDER, fill_value=0
    )


def category_prevalence(df: pd.DataFrame, categories: list[str], columns: list[str], status=None):
    source = df if status is None else df[df["agentic_status"] == status]
    table = pd.DataFrame(index=categories, columns=columns, dtype=float)
    ns = pd.Series(index=categories, dtype=int)
    for category in categories:
        subset = source[source["primary_category"] == category]
        ns.loc[category] = len(subset)
        if len(subset) == 0:
            table.loc[category] = np.nan
        else:
            table.loc[category] = [100.0 * subset[col].eq("Y").mean() for col in columns]
    return table, ns


def validation_by_category(df: pd.DataFrame, categories: list[str], status: str):
    table = pd.DataFrame(index=categories, columns=VALIDATION_STAGES, dtype=float)
    ns = pd.Series(index=categories, dtype=int)
    source = df[df["agentic_status"] == status]
    for category in categories:
        subset = source[source["primary_category"] == category]
        ns.loc[category] = len(subset)
        if len(subset) == 0:
            table.loc[category] = np.nan
        else:
            counts = subset["cumulative_level"].value_counts().reindex(VALIDATION_STAGES, fill_value=0)
            table.loc[category] = 100.0 * counts.values / len(subset)
    return table, ns


def display_category(category: str, n: int) -> str:
    return f"{CATEGORY_LABELS.get(category, category)} (n={n})"


def heatmap(ax, table: pd.DataFrame, row_labels: list[str], cmap: str, label: str):
    masked = np.ma.masked_invalid(table.values.astype(float))
    image = ax.imshow(masked, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(np.arange(table.shape[1]), table.columns)
    ax.set_yticks(np.arange(table.shape[0]), row_labels)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            value = table.iloc[i, j]
            if pd.isna(value):
                ax.text(j, i, "NA", ha="center", va="center", color="0.4")
            else:
                color = "white" if value >= 65 else "black"
                ax.text(j, i, f"{value:.0f}", ha="center", va="center", fontweight="bold", color=color)
    add_panel_label(ax, label)
    return image


def exact_category_figure(
    df: pd.DataFrame,
    outdir: Path,
    dpi: int,
):
    """
    Figure 4:
    Panel a includes all primary categories.
    Panels b-d include categories with at least one full-agentic record.
    """

    categories = ordered_categories(df)
    composition = category_composition_table(df, categories)

    function, n_full_all = category_prevalence(
        df,
        categories,
        FUNCTION_COLS,
        "full-agentic",
    )

    evidence, _ = category_prevalence(
        df,
        categories,
        EVIDENCE_COLS,
        "full-agentic",
    )

    stages, _ = validation_by_category(
        df,
        categories,
        "full-agentic",
    )

    full_categories = [
        category
        for category in categories
        if int(n_full_all.loc[category]) > 0
    ]

    function = function.loc[full_categories].copy()
    evidence = evidence.loc[full_categories].copy()
    stages = stages.loc[full_categories].copy()
    n_full = n_full_all.loc[full_categories].copy()

    short_labels = {
        "drug_discovery": "Drug discovery",
        "transcriptomics": "Transcriptomics",
        "cross_domain_bioinformatics": "Cross-domain",
        "proteomics": "Proteomics",
        "computational_pathology_bioimaging": "Pathology / bioimaging",
        "genomics": "Genomics",
        "epigenomics": "Epigenomics",
    }

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(12.8, 8.0),
        gridspec_kw={
            "width_ratios": [1.05, 1.0],
            "height_ratios": [1.0, 1.0],
        },
    )

    # Panel a: category composition using all records.
    ax = axes[0, 0]

    y_all = np.arange(len(categories))
    left_all = np.zeros(len(categories))

    for status in STATUS_ORDER:
        values = composition[status].values

        ax.barh(
            y_all,
            values,
            left=left_all,
            label=STATUS_LABELS[status],
            color=STATUS_COLORS[status],
            edgecolor="white",
            linewidth=0.7,
            height=0.72,
        )

        for row_index, (start, value) in enumerate(
            zip(left_all, values)
        ):
            if value >= 4:
                ax.text(
                    start + value / 2,
                    row_index,
                    str(int(value)),
                    ha="center",
                    va="center"
                )

        left_all += values

    row_labels_all = [
        (
            f"{short_labels.get(category, category)} "
            f"(n={int(composition.loc[category].sum())})"
        )
        for category in categories
    ]

    ax.set_yticks(
        y_all,
        row_labels_all,
    )

    ax.invert_yaxis()
    ax.set_xlabel("Number of records")

    ax.legend(
        frameon=False,
        loc="lower left",
        bbox_to_anchor=(0.5, 0.0),
        borderaxespad=0,
        handlelength=1.4,
    )

    add_panel_label(ax, "a")

    # Labels shared by panels b-d.
    row_labels_full = [
        (
            f"{short_labels.get(category, category)} "
            f"(n={int(n_full.loc[category])})"
        )
        for category in full_categories
    ]

    # Panel b: functionality profile.
    ax = axes[0, 1]

    heatmap(
        ax,
        function,
        row_labels_full,
        BLUE_CMAP,
        "b",
    )

    ax.set_xlabel("Functionality dimensions")

    # Panel c: evidence profile.
    ax = axes[1, 0]

    heatmap(
        ax,
        evidence,
        row_labels_full,
        GREEN_CMAP,
        "c",
    )

    ax.set_xlabel("Evidence dimensions")

    # Panel d: validation distribution.
    ax = axes[1, 1]

    y_full = np.arange(len(full_categories))
    left_full = np.zeros(len(full_categories))

    for stage in VALIDATION_STAGES:
        values = stages[stage].fillna(0).values

        ax.barh(
            y_full,
            values,
            left=left_full,
            color=STAGE_COLORS[stage],
            label=stage,
            edgecolor="white",
            linewidth=0.7,
            height=0.72,
        )

        for row_index, (start, value) in enumerate(
            zip(left_full, values)
        ):
            if value >= 10:
                ax.text(
                    start + value / 2,
                    row_index,
                    f"{value:.0f}%",
                    ha="center",
                    va="center"
                )

        left_full += values

    ax.set_yticks(
        y_full,
        row_labels_full,
    )

    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Records at each validation level (%)")

    ax.xaxis.set_major_formatter(
        mtick.PercentFormatter()
    )

    ax.legend(
        title="Validation level",
        bbox_to_anchor=(1.01, 1.0),
        loc="upper left",
        frameon=False,
        borderaxespad=0,
        handlelength=1.3,
        labelspacing=0.35,
    )

    add_panel_label(ax, "d")

    for panel_ax in axes.flat:
        style_axis(panel_ax)

    fig.subplots_adjust(
        left=0.20,
        right=0.88,
        bottom=0.09,
        top=0.97,
        wspace=0.95,
        hspace=0.48,
    )

    save_figure(
        fig,
        outdir / "figure4_exact_categories_compact",
        dpi,
    )

    return (
        composition,
        function,
        evidence,
        stages,
        n_full,
    )


def temporal_supplement(
    df: pd.DataFrame,
    outdir: Path,
    dpi: int,
):
    """
    Supplementary descriptive temporal composition.

    The panels describe the composition of the curated sample by
    publication year and do not imply a field-wide temporal trend.
    """

    years = sorted(
        int(year)
        for year in df["publication_year"].dropna().unique()
    )

    grouped = df.dropna(
        subset=["publication_year"]
    ).copy()

    grouped["publication_year"] = (
        grouped["publication_year"]
        .astype(int)
    )

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(14.8, 4.6),
        gridspec_kw={
            "wspace": 0.48,
        },
    )

    # Panel a: number of records by year and agentic status.
    ax = axes[0]

    counts = pd.crosstab(
        grouped["publication_year"],
        grouped["agentic_status"],
    ).reindex(
        index=years,
        columns=STATUS_ORDER,
        fill_value=0,
    )

    x = np.arange(
        len(years)
    )

    width = 0.36

    for offset, status in zip(
        [-width / 2, width / 2],
        STATUS_ORDER,
    ):
        ax.bar(
            x + offset,
            counts[status],
            width,
            label=STATUS_LABELS[status],
            color=STATUS_COLORS[status],
            edgecolor="white",
            linewidth=0.6,
        )

    ax.set_xticks(
        x,
        [str(year) for year in years],
    )

    ax.set_ylabel(
        "Number of records"
    )

    ax.set_xlabel(
        "Publication year"
    )

    ax.legend(
        frameon=False,
        loc="upper left",
    )

    add_panel_label(
        ax,
        "a",
    )

    # Panel b: mean Functionality and Evidence breadth by year.
    ax = axes[1]

    means = (
        grouped
        .groupby("publication_year")[
            [
                "function_breadth",
                "evidence_breadth",
            ]
        ]
        .mean()
        .reindex(years)
    )

    ax.plot(
        years,
        means["function_breadth"],
        marker="o",
        markersize=6,
        linewidth=1.8,
        label="Functionality breadth",
        color="#4C78A8",
    )

    ax.plot(
        years,
        means["evidence_breadth"],
        marker="o",
        markersize=6,
        linewidth=1.8,
        label="Evidence breadth",
        color="#59A14F",
    )

    # Force integer year labels and remove intermediate half-year ticks.
    ax.set_xticks(
        years
    )

    ax.set_xticklabels(
        [str(year) for year in years]
    )

    ax.set_xlim(
        min(years) - 0.15,
        max(years) + 0.15,
    )

    ax.set_ylim(
        0,
        6.2,
    )

    ax.set_xlabel(
        "Publication year"
    )

    ax.set_ylabel(
        "Mean breadth score"
    )

    ax.legend(
        frameon=False,
        loc="upper left",
    )

    add_panel_label(
        ax,
        "b",
    )

    # Panel c: percentage of curated records classified as full-agentic.
    ax = axes[2]

    full_share = (
        grouped
        .groupby("publication_year")[
            "agentic_status"
        ]
        .apply(
            lambda status:
                100.0
                * status.eq("full-agentic").mean()
        )
        .reindex(years)
    )

    ax.plot(
        years,
        full_share,
        marker="o",
        markersize=6,
        linewidth=1.8,
        color=STATUS_COLORS["full-agentic"],
    )

    # Force integer year labels and remove intermediate half-year ticks.
    ax.set_xticks(
        years
    )

    ax.set_xticklabels(
        [str(year) for year in years]
    )

    ax.set_xlim(
        min(years) - 0.15,
        max(years) + 0.15,
    )

    ax.set_ylim(
        0,
        100,
    )

    ax.set_xlabel(
        "Publication year"
    )

    ax.set_ylabel(
        "Full-agentic share"
    )

    ax.yaxis.set_major_formatter(
        mtick.PercentFormatter()
    )

    add_panel_label(
        ax,
        "c",
    )

    for panel_ax in axes.flat:
        style_axis(
            panel_ax
        )

    fig.subplots_adjust(
        left=0.07,
        right=0.98,
        bottom=0.18,
        top=0.93,
        wspace=0.52,
    )

    save_figure(
        fig,
        outdir
        / "figureS_temporal_composition",
        dpi,
    )


def export_tables(df, outdir, stage_by_status, composition, function, evidence, stages, n_full):
    qmat = qualifier_matrix(df)

    # Agentic-status sensitivity tables
    status_rows = []
    for status in STATUS_ORDER:
        subset = df[df["agentic_status"] == status]
        row = {
            "agentic_status": status,
            "n": len(subset),
            "mean_function_breadth": subset["function_breadth"].mean(),
            "mean_evidence_breadth": subset["evidence_breadth"].mean(),
        }
        for col in FUNCTION_COLS + EVIDENCE_COLS:
            row[f"{col}_percent_Y"] = 100.0 * subset[col].eq("Y").mean()
        for stage in VALIDATION_STAGES:
            row[f"{stage}_percent"] = 100.0 * subset["cumulative_level"].eq(stage).mean()
        idx = subset.index
        for q in QUALIFIER_ORDER:
            row[f"qualifier_{q}_percent"] = 100.0 * qmat.loc[idx, q].mean()
        status_rows.append(row)
    pd.DataFrame(status_rows).to_csv(outdir / "agentic_status_sensitivity_summary.csv", index=False)

    stage_by_status.to_csv(outdir / "validation_stage_by_agentic_status.csv")
    composition.to_csv(outdir / "exact_category_by_agentic_status_counts.csv")
    function.to_csv(outdir / "full_agentic_function_by_exact_category.csv")
    evidence.to_csv(outdir / "full_agentic_evidence_by_exact_category.csv")
    stages.to_csv(outdir / "full_agentic_validation_by_exact_category.csv")
    n_full.rename("n_full_agentic").to_csv(outdir / "full_agentic_category_denominators.csv")

    record_level = df[[
        "record_id", "primary_category", "agentic_status", "publication_year",
        "function_breadth", "evidence_breadth", "cumulative_level",
    ]].copy()
    record_level.to_csv(outdir / "record_level_breadth_and_validation.csv", index=False)


def write_summary(df: pd.DataFrame, outdir: Path):
    lines = [
        "Reviewer-focused AgenticSystem analysis",
        f"Total records: {len(df)}",
        "",
        "Agentic status:",
    ]
    for status in STATUS_ORDER:
        n = int(df["agentic_status"].eq(status).sum())
        lines.append(f"  {status}: {n} ({100*n/len(df):.1f}%)")
    lines += ["", "Exact primary categories:"]
    for category, n in df["primary_category"].value_counts().items():
        full = int(((df["primary_category"] == category) & (df["agentic_status"] == "full-agentic")).sum())
        adjacent = int(((df["primary_category"] == category) & (df["agentic_status"] == "agent-adjacent")).sum())
        lines.append(f"  {category}: total={n}, full-agentic={full}, agent-adjacent={adjacent}")
    lines += [
        "",
        "Interpretation notes:",
        "  Percentages are calculated within each displayed subgroup.",
        "  NR and U are not counted as Y in prevalence estimates.",
        "  Exact primary_category values are preserved; no categories are merged.",
        "  Categories with very small denominators should not be interpreted as stable prevalence estimates.",
        "  Publication-year figures describe the curated sample and do not establish field-wide temporal trends.",
    ]
    (outdir / "analysis_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    input_path = Path(args.input)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = load_data(input_path)
    stage_by_status = reviewer_sensitivity_figure(df, outdir, args.dpi)
    composition, function, evidence, stages, n_full = exact_category_figure(df, outdir, args.dpi)
    temporal_supplement(df, outdir, args.dpi)
    export_tables(df, outdir, stage_by_status, composition, function, evidence, stages, n_full)
    write_summary(df, outdir)

    print(f"Analyzed {len(df)} records")
    print(f"Full-agentic: {(df.agentic_status == 'full-agentic').sum()}")
    print(f"Agent-adjacent: {(df.agentic_status == 'agent-adjacent').sum()}")
    print(f"Outputs: {outdir.resolve()}")


if __name__ == "__main__":
    main()
