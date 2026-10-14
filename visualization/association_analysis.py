from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from scipy.stats import chi2_contingency, kruskal, spearmanr

# Journal-style defaults
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 12,
    "axes.titlesize": 12,
    "axes.labelsize": 12,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
    "axes.linewidth": 0.9,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.facecolor": "white",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

FUNCTION_COLS = [f"F{i}" for i in range(1, 7)]
EVIDENCE_COLS = [f"E{i}" for i in range(1, 7)]
STAGES = ["V0", "V1", "V2", "V3", "V4"]
STAGE_TO_ORDINAL = {stage: i for i, stage in enumerate(STAGES)}
STAGE_COLORS = {
    "V0": "#5F6368",
    "V1": "#B8BCC2",
    "V2": "#F5B514",
    "V3": "#35B6C4",
    "V4": "#D33682",
}
DOMAIN_LABELS = {
    "drug_discovery": "Drug discovery",
    "transcriptomics": "Transcriptomics",
    "cross_domain_bioinformatics": "Cross-domain",
    "proteomics": "Proteomics",
    "computational_pathology_bioimaging": "Pathology/bioimaging",
    "genomics": "Genomics",
    "epigenomics": "Epigenomics",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create polished exploratory FEV association figures and statistical tables."
    )
    parser.add_argument("--input", default="data/HumanVerification/AgenticSystem.csv")
    parser.add_argument("--output-dir", default="visualization/association_outputs")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument(
        "--exclude-duplicates",
        action="store_true",
        help="Exclude rows with a non-empty duplicate_of value.",
    )
    return parser.parse_args()


def read_csv_flexible(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error


def clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def prepare_data(path: Path, exclude_duplicates: bool) -> pd.DataFrame:
    df = read_csv_flexible(path)
    required = {
        "record_id",
        "publication_year",
        "primary_category",
        "cumulative_level",
        *FUNCTION_COLS,
        *EVIDENCE_COLS,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    text_cols = [
        "record_id",
        "primary_category",
        "cumulative_level",
        *FUNCTION_COLS,
        *EVIDENCE_COLS,
    ]
    for col in text_cols:
        df[col] = clean_text(df[col])

    if exclude_duplicates and "duplicate_of" in df.columns:
        duplicate_marker = clean_text(df["duplicate_of"])
        df = df.loc[duplicate_marker.eq("")].copy()

    allowed_codes = {"Y", "N", "NR", "U", ""}
    for col in FUNCTION_COLS + EVIDENCE_COLS:
        unexpected = sorted(set(df[col]) - allowed_codes)
        if unexpected:
            raise ValueError(f"Unexpected values in {col}: {unexpected}")

    unexpected_stages = sorted(set(df["cumulative_level"]) - set(STAGES))
    if unexpected_stages:
        raise ValueError(f"Unexpected cumulative levels: {unexpected_stages}")

    df["publication_year"] = pd.to_numeric(df["publication_year"], errors="coerce")
    df["F_breadth"] = df[FUNCTION_COLS].eq("Y").sum(axis=1)
    df["E_breadth"] = df[EVIDENCE_COLS].eq("Y").sum(axis=1)
    df["V_ordinal"] = df["cumulative_level"].map(STAGE_TO_ORDINAL)
    df["domain_label"] = df["primary_category"].map(DOMAIN_LABELS).fillna(
        df["primary_category"].str.replace("_", " ").str.title()
    )
    df["artifact_status"] = derive_artifact_status(df)
    return df.reset_index(drop=True)


def derive_artifact_status(df: pd.DataFrame) -> pd.Series:
    """Conservative text-coded proxy, not an open-source license audit."""
    if "source_code_review" not in df.columns:
        return pd.Series("Not coded", index=df.index)

    review = clean_text(df["source_code_review"]).str.lower()
    positive = review.str.contains(
        r"official repository (?:was )?reviewed|"
        r"official attributable repository inspected|"
        r"attributable repository reviewed|"
        r"public source supports replay|"
        r"source package|executable source|"
        r"implementation package is available",
        regex=True,
    )
    negative = review.str.contains(
        r"no attributable|not located|readme documentation only|"
        r"no executable source|no official public implementation|"
        r"not established|insufficient",
        regex=True,
    )
    return pd.Series(
        np.select(
            [positive & ~negative, negative],
            ["Reviewed public artifact", "Not established"],
            default="Not coded",
        ),
        index=df.index,
    )


def style_axis(ax, grid_axis="y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#555555")
    ax.spines["bottom"].set_color("#555555")
    ax.tick_params(direction="out", color="#555555")
    if grid_axis:
        ax.grid(axis=grid_axis, color="#E7E9EC", linewidth=0.75, zorder=0)


def add_panel_label(ax, label: str) -> None:
    ax.text(
        -0.10,
        1.04,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=13,
        fontweight="bold",
        clip_on=False,
    )


def format_p(p_value: float) -> str:
    if not np.isfinite(p_value):
        return "NA"
    return "<0.001" if p_value < 0.001 else f"={p_value:.3f}"


def add_stat_box(ax, text: str, location="upper left") -> None:
    positions = {
    "upper left": (0.025, 0.965, "left"),
    "upper right": (0.975, 0.965, "right"),
    "lower center": (0.460, 0.1, "center"),
    "lower left": (0.1, 0.17, "left"),
    }
    x, y, horizontal_alignment = positions[location]
    ax.text(
        x,
        y,
        text,
        transform=ax.transAxes,
        ha=horizontal_alignment,
        va="top",
        bbox={
            "boxstyle": "round,pad=0.24",
            "facecolor": "white",
            "edgecolor": "#D9DDE2",
            "linewidth": 0.6,
            "alpha": 0.96,
        },
        zorder=20,
    )


def bootstrap_spearman(x, y, rng, n_boot=5000):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    statistic, p_value = spearmanr(x, y)
    boot = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(x), len(x))
        if np.unique(x[idx]).size < 2 or np.unique(y[idx]).size < 2:
            continue
        boot.append(spearmanr(x[idx], y[idx]).statistic)
    low, high = np.percentile(boot, [2.5, 97.5]) if boot else (np.nan, np.nan)
    return statistic, p_value, low, high


def cramers_v(table):
    table = np.asarray(table)
    table = table[table.sum(axis=1) > 0]
    table = table[:, table.sum(axis=0) > 0]
    if table.shape[0] < 2 or table.shape[1] < 2:
        return np.nan, np.nan, 0, np.nan, np.empty((0, 0))

    chi2, p_value, dof, expected = chi2_contingency(table)
    n = table.sum()
    rows, cols = table.shape
    phi2 = chi2 / n
    phi2_corrected = max(0, phi2 - ((cols - 1) * (rows - 1)) / max(n - 1, 1))
    rows_corrected = rows - ((rows - 1) ** 2) / max(n - 1, 1)
    cols_corrected = cols - ((cols - 1) ** 2) / max(n - 1, 1)
    denominator = min(rows_corrected - 1, cols_corrected - 1)
    effect = np.sqrt(phi2_corrected / denominator) if denominator > 0 else np.nan
    return chi2, p_value, dof, effect, expected


def stage_legend_handles():
    return [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=STAGE_COLORS[stage],
            markeredgecolor="white",
            markersize=8,
            label=stage,
        )
        for stage in STAGES
    ]


def plot_breadth_bubbles(ax, df):
    counts = (
        df.groupby(["F_breadth", "E_breadth", "cumulative_level"], observed=True)
        .size()
        .reset_index(name="n")
    )
    for stage in STAGES:
        part = counts.loc[counts["cumulative_level"].eq(stage)]
        if part.empty:
            continue
        ax.scatter(
            part["F_breadth"],
            part["E_breadth"],
            s=24 + 12 * part["n"],
            c=STAGE_COLORS[stage],
            alpha=0.74,
            edgecolors="white",
            linewidths=0.65,
            zorder=3,
        )

    rho, p_value = spearmanr(df["F_breadth"], df["E_breadth"])
    add_stat_box(ax, rf"Spearman $\rho$={rho:.2f}; $P${format_p(p_value)}", "lower center")
    ax.set_xlim(-0.4, 6.4)
    ax.set_ylim(-0.4, 6.4)
    ax.set_xticks(range(7))
    ax.set_yticks(range(7))
    ax.set_xlabel("Functionality breadth (0-6)")
    ax.set_ylabel("Evidence breadth (0-6)")
    style_axis(ax, grid_axis="both")
    add_panel_label(ax, "a")


def draw_boxplot(ax, groups, positions, colors, rng, offset, width=0.30):
    valid = [(pos, group, color) for pos, group, color in zip(positions, groups, colors) if len(group)]
    if not valid:
        return
    valid_positions, valid_groups, valid_colors = zip(*valid)
    box = ax.boxplot(
        valid_groups,
        positions=np.asarray(valid_positions) + offset,
        widths=width,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#222222", "linewidth": 1.35},
        whiskerprops={"color": "#555555", "linewidth": 0.9},
        capprops={"color": "#555555", "linewidth": 0.9},
        boxprops={"edgecolor": "#555555", "linewidth": 0.9},
    )
    for patch, color in zip(box["boxes"], valid_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.86)
    for pos, group in zip(valid_positions, valid_groups):
        jitter = rng.normal(pos + offset, 0.035, len(group))
        ax.scatter(jitter, group, s=9, c="#30343A", alpha=0.22, edgecolors="none", zorder=4)


def plot_breadth_by_stage(ax, df, rng):
    positions = np.arange(len(STAGES))
    f_groups = [df.loc[df["cumulative_level"].eq(stage), "F_breadth"].to_numpy() for stage in STAGES]
    e_groups = [df.loc[df["cumulative_level"].eq(stage), "E_breadth"].to_numpy() for stage in STAGES]
    draw_boxplot(ax, f_groups, positions, ["#5276A7"] * len(STAGES), rng, -0.18)
    draw_boxplot(ax, e_groups, positions, ["#69B8A9"] * len(STAGES), rng, 0.18)

    rho_f, p_f = spearmanr(df["F_breadth"], df["V_ordinal"])
    rho_e, p_e = spearmanr(df["E_breadth"], df["V_ordinal"])
    stat_text = (
        rf"F breadth: $\rho$={rho_f:.2f}, $P${format_p(p_f)}"
        "\n"
        rf"E breadth: $\rho$={rho_e:.2f}, $P${format_p(p_e)}"
    )
    add_stat_box(ax, stat_text, location="lower left")
    ax.set_xticks(positions, STAGES)
    ax.set_xlim(-0.60, len(STAGES) - 0.40)
    ax.set_ylim(-0.4, 6.4)
    ax.set_ylabel("Breadth (0-6)")
    ax.legend(
        handles=[
            Line2D([0], [0], color="#5276A7", lw=8, label="Functionality breadth"),
            Line2D([0], [0], color="#69B8A9", lw=8, label="Evidence breadth"),
        ],
        loc="lower right",
        frameon=False,
    )
    style_axis(ax)
    add_panel_label(ax, "b")
    return kruskal(*[g for g in f_groups if len(g)]), kruskal(*[g for g in e_groups if len(g)])


def plot_domain_composition(ax, df):
    counts = df["domain_label"].value_counts()
    domains = counts.index.tolist()
    table = pd.crosstab(df["domain_label"], df["cumulative_level"]).reindex(
        index=domains, columns=STAGES, fill_value=0
    )
    percentages = table.div(table.sum(axis=1), axis=0) * 100
    y = np.arange(len(domains))
    left = np.zeros(len(domains))
    for stage in STAGES:
        values = percentages[stage].to_numpy()
        ax.barh(y, values, left=left, color=STAGE_COLORS[stage], height=0.66, label=stage)
        left += values

    labels = [f"{domain}  (n={int(counts[domain])})" for domain in domains]
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter())
    ax.set_xlabel("Records within domain")
    chi2, p_value, dof, effect, expected = cramers_v(table.to_numpy())
    add_stat_box(ax, rf"Cramér's $V$={effect:.2f}; $P${format_p(p_value)}")
    style_axis(ax, grid_axis="x")
    add_panel_label(ax, "c")
    return table, (chi2, p_value, dof, effect, expected)


def plot_year_composition(ax, df):
    years = sorted(df["publication_year"].dropna().astype(int).unique())
    table = pd.crosstab(df["publication_year"].astype("Int64"), df["cumulative_level"]).reindex(
        index=years, columns=STAGES, fill_value=0
    )
    percentages = table.div(table.sum(axis=1), axis=0) * 100
    x = np.arange(len(years))
    bottom = np.zeros(len(years))
    for stage in STAGES:
        values = percentages[stage].to_numpy()
        ax.bar(x, values, bottom=bottom, color=STAGE_COLORS[stage], width=0.68)
        bottom += values

    year_counts = df["publication_year"].value_counts()
    labels = [f"{year}\n(n={int(year_counts[year])})" for year in years]
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter())
    ax.set_ylabel("Records within publication year")
    rho, p_value = spearmanr(df["publication_year"], df["V_ordinal"], nan_policy="omit")
    add_stat_box(
        ax,
        rf"Year vs Validation: $\rho$={rho:.2f}; $P${format_p(p_value)}",
        location="lower center",
    )
    style_axis(ax)
    add_panel_label(ax, "d")
    return table


def create_main_figure(df, outdir, dpi, seed):
    rng = np.random.default_rng(seed)
    fig = plt.figure(figsize=(16, 9))
    grid = fig.add_gridspec(
        2,
        2,
        left=0.175,
        right=0.980,
        top=0.885,
        bottom=0.165,
        hspace=0.38,
        wspace=0.31,
    )

    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 0])
    ax_d = fig.add_subplot(grid[1, 1])

    plot_breadth_bubbles(ax_a, df)
    kw_f, kw_e = plot_breadth_by_stage(ax_b, df, rng)
    domain_table, domain_result = plot_domain_composition(ax_c, df)
    year_table = plot_year_composition(ax_d, df)

    fig.legend(
        handles=stage_legend_handles(),
        labels=STAGES,
        title="Validation stage",
        loc="lower center",
        bbox_to_anchor=(0.57, 0.055),
        ncol=5,
        frameon=False,
        handletextpad=0.35,
        columnspacing=1.25,
    )

    for extension in ("png", "pdf", "svg"):
        fig.savefig(outdir / f"exploratory_associations.{extension}", dpi=dpi)
    plt.close(fig)
    return kw_f, kw_e, domain_table, domain_result, year_table


def create_artifact_figure_if_informative(df, outdir, dpi):
    coded = df.loc[~df["artifact_status"].eq("Not coded")].copy()
    groups = coded["artifact_status"].value_counts()
    if len(groups) < 2 or groups.min() < 5:
        return None

    order = [x for x in ["Reviewed public artifact", "Not established"] if x in groups.index]
    table = pd.crosstab(coded["artifact_status"], coded["cumulative_level"]).reindex(
        index=order, columns=STAGES, fill_value=0
    )
    percentages = table.div(table.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    fig.subplots_adjust(left=0.14, right=0.96, top=0.84, bottom=0.22)
    x = np.arange(len(order))
    bottom = np.zeros(len(order))
    for stage in STAGES:
        values = percentages[stage].to_numpy()
        ax.bar(x, values, bottom=bottom, color=STAGE_COLORS[stage], width=0.58, label=stage)
        bottom += values

    chi2, p_value, dof, effect, expected = cramers_v(table.to_numpy())
    labels = [f"{label}\n(n={int(groups[label])})" for label in order]
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter())
    ax.set_ylabel("Records within artifact-status group")
    add_stat_box(ax, rf"Cramér's $V$={effect:.2f}; $P${format_p(p_value)}")
    ax.legend(title="Validation", ncol=5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    style_axis(ax)
    fig.text(
        0.14,
        0.035,
        "Artifact status is a conservative text-coded proxy from source_code_review, not an open-source license audit.",
        color="#555555",
    )
    for extension in ("png", "pdf", "svg"):
        fig.savefig(outdir / f"artifact_validation_association.{extension}", dpi=dpi)
    plt.close(fig)
    return table, (chi2, p_value, dof, effect, expected)


def export_statistics(df, outdir, seed, kw_f, kw_e, domain_result, artifact_result):
    rng = np.random.default_rng(seed)
    rows = []
    pairs = [
        ("Functionality breadth vs Evidence breadth", "F_breadth", "E_breadth"),
        ("Functionality breadth vs Validation stage", "F_breadth", "V_ordinal"),
        ("Evidence breadth vs Validation stage", "E_breadth", "V_ordinal"),
        ("Publication year vs Functionality breadth", "publication_year", "F_breadth"),
        ("Publication year vs Evidence breadth", "publication_year", "E_breadth"),
        ("Publication year vs Validation stage", "publication_year", "V_ordinal"),
    ]
    for label, x_col, y_col in pairs:
        subset = df[[x_col, y_col]].dropna()
        effect, p_value, low, high = bootstrap_spearman(subset[x_col], subset[y_col], rng)
        rows.append({
            "association": label,
            "n": len(subset),
            "method": "Spearman rank correlation",
            "effect_name": "rho",
            "effect_size": effect,
            "ci_95_low": low,
            "ci_95_high": high,
            "p_value": p_value,
        })

    rows.extend([
        {
            "association": "Functionality breadth across Validation stages",
            "n": len(df),
            "method": "Kruskal-Wallis",
            "effect_name": "H",
            "effect_size": kw_f.statistic,
            "ci_95_low": np.nan,
            "ci_95_high": np.nan,
            "p_value": kw_f.pvalue,
        },
        {
            "association": "Evidence breadth across Validation stages",
            "n": len(df),
            "method": "Kruskal-Wallis",
            "effect_name": "H",
            "effect_size": kw_e.statistic,
            "ci_95_low": np.nan,
            "ci_95_high": np.nan,
            "p_value": kw_e.pvalue,
        },
    ])

    chi2, p_value, dof, effect, expected = domain_result
    rows.append({
        "association": "Domain vs Validation stage",
        "n": len(df),
        "method": "Chi-square; bias-corrected Cramer's V",
        "effect_name": "Cramer's V",
        "effect_size": effect,
        "ci_95_low": np.nan,
        "ci_95_high": np.nan,
        "p_value": p_value,
    })
    if expected.size and np.any(expected < 5):
        warnings.warn(
            "Domain vs Validation stage: some expected cells are below 5; interpret the asymptotic P value cautiously."
        )

    if artifact_result is not None:
        chi2, p_value, dof, effect, expected = artifact_result
        rows.append({
            "association": "Artifact-status proxy vs Validation stage",
            "n": int((df["artifact_status"] != "Not coded").sum()),
            "method": "Chi-square; bias-corrected Cramer's V",
            "effect_name": "Cramer's V",
            "effect_size": effect,
            "ci_95_low": np.nan,
            "ci_95_high": np.nan,
            "p_value": p_value,
        })

    pd.DataFrame(rows).to_csv(outdir / "exploratory_association_statistics.csv", index=False)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = prepare_data(input_path, args.exclude_duplicates)
    kw_f, kw_e, domain_table, domain_result, year_table = create_main_figure(
        df, outdir, args.dpi, args.seed
    )
    artifact_output = create_artifact_figure_if_informative(df, outdir, args.dpi)
    artifact_table = artifact_output[0] if artifact_output is not None else None
    artifact_result = artifact_output[1] if artifact_output is not None else None

    domain_table.to_csv(outdir / "domain_by_validation_counts.csv")
    year_table.to_csv(outdir / "year_by_validation_counts.csv")
    if artifact_table is not None:
        artifact_table.to_csv(outdir / "artifact_proxy_by_validation_counts.csv")

    export_statistics(
        df,
        outdir,
        args.seed,
        kw_f,
        kw_e,
        domain_result,
        artifact_result,
    )

    print(f"Analyzed {len(df)} records")
    print(f"Main figure: {outdir / 'exploratory_associations.png'}")
    if artifact_output is None:
        print("Artifact figure skipped because at least two adequately sized coded groups were not available.")
    print(f"Outputs written to {outdir.resolve()}")


if __name__ == "__main__":
    main()
