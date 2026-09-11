from __future__ import annotations

import argparse
import json
import re
import textwrap
import unicodedata
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


# Put this script in the project root directory.
ROOT = Path("/home/phpham/Work/BioAgents")
DATA = ROOT / "data"
REPORTS = ROOT / "outputs" / "reports"
FIGURES = ROOT / "outputs" / "figures"

DEFAULT_COMBINED = DATA / "01_combined_source_rows.csv"
DEFAULT_REJECTED = DATA / "02_postcombine_rejected_rows.csv"
DEFAULT_FILTERED = DATA / "02_filtered_candidate_rows.csv"
DEFAULT_DEDUPLICATED = DATA / "03_deduplicated_candidates.csv"
DEFAULT_OUTPUT = FIGURES / "search_preprocessing_flow"
DEFAULT_AUDIT = REPORTS / "search_preprocessing_counts.json"

SOURCE_ORDER = ("PubMed", "Europe PMC", "arXiv")

COLORS = {
    "navy": "#17365D",
    "blue": "#E5EFF8",
    "green": "#E7F3EA",
    "purple": "#EEEAF7",
    "red": "#FBE9E9",
    "gray": "#F3F5F7",
    "next": "#E9F0FA",
    "white": "#FFFFFF",
    "text": "#17212B",
    "muted": "#5D6975",
    "line": "#536273",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.rstrip(".,; )]}>")


def normalize_arxiv(value: Any) -> str:
    match = re.search(
        r"(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?",
        clean(value).lower(),
    )
    return match.group(1) if match else ""


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    try:
        return pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def identifier_key(row: pd.Series) -> str:
    """Reproduce the first deterministic deduplication key."""
    doi = normalize_doi(row.get("doi", ""))
    pmid = clean(row.get("pmid", ""))
    arxiv_id = normalize_arxiv(
        row.get("arxiv_id", "") or row.get("source_id", "")
    )
    title = normalize_title(row.get("title", ""))

    if doi:
        return "DOI:" + doi
    if pmid:
        return "PMID:" + pmid
    if arxiv_id:
        return "ARXIV:" + arxiv_id
    return "TITLE:" + title


def calculate_counts(
    combined_path: Path,
    rejected_path: Path,
    filtered_path: Path,
    deduplicated_path: Path,
) -> dict[str, Any]:
    combined = read_csv(combined_path)
    rejected = read_csv(rejected_path)
    filtered = read_csv(filtered_path)
    deduplicated = read_csv(deduplicated_path)

    if "source" not in combined.columns:
        raise ValueError("The combined file must contain a 'source' column.")
    if "title" not in filtered.columns:
        raise ValueError("The filtered file must contain a 'title' column.")

    source_counts = {
        source: int(combined["source"].eq(source).sum())
        for source in SOURCE_ORDER
    }
    other = int((~combined["source"].isin(SOURCE_ORDER)).sum())
    if other:
        source_counts["Other sources"] = other

    identified = int(len(combined))
    automated_exclusions = int(len(rejected))
    retained = int(len(filtered))
    available_for_screening = int(len(deduplicated))

    if identified != automated_exclusions + retained:
        raise ValueError(
            "Filtering counts do not reconcile: "
            f"{identified:,} != {automated_exclusions:,} + {retained:,}."
        )

    work = filtered.copy()
    work["_identifier_key"] = work.apply(identifier_key, axis=1)
    after_identifier = int(work["_identifier_key"].nunique())

    representative_titles: list[str] = []
    for _, group in work.groupby("_identifier_key", sort=False):
        representative_titles.append(
            max((clean(value) for value in group["title"]), key=len, default="")
        )

    after_title = int(
        pd.Series(representative_titles, dtype=str)
        .map(normalize_title)
        .nunique()
    )

    if after_title != available_for_screening:
        raise ValueError(
            "Calculated deduplication total does not match the saved output: "
            f"{after_title:,} != {available_for_screening:,}."
        )

    identifier_duplicates = retained - after_identifier
    title_duplicates = after_identifier - after_title
    duplicates_removed = retained - available_for_screening

    if duplicates_removed != identifier_duplicates + title_duplicates:
        raise AssertionError("Duplicate-removal counts do not reconcile.")

    return {
        "records_identified": identified,
        "records_by_database": source_counts,
        "records_excluded_by_automation": automated_exclusions,
        "records_retained_for_deduplication": retained,
        "duplicate_records_removed": duplicates_removed,
        "identifier_based_duplicates": identifier_duplicates,
        "title_based_duplicates": title_duplicates,
        "records_available_for_screening": available_for_screening,
        "checks": {
            "filtering": identified == automated_exclusions + retained,
            "deduplication": retained == duplicates_removed + available_for_screening,
        },
        "input_files": {
            "combined": str(combined_path),
            "rejected": str(rejected_path),
            "filtered": str(filtered_path),
            "deduplicated": str(deduplicated_path),
        },
    }


def add_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    fill: str,
    *,
    fontsize: float = 10.0,
    linewidth: float = 1.2,
    linestyle: str = "solid",
    wrap_width: int | None = None,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.010,rounding_size=0.010",
            facecolor=fill,
            edgecolor=COLORS["line"],
            linewidth=linewidth,
            linestyle=linestyle,
            zorder=3,
        )
    )
    if wrap_width is not None:
        wrapped_lines: list[str] = []
        for line in text.splitlines():
            wrapped_lines.extend(
                textwrap.wrap(
                    line,
                    width=wrap_width,
                    break_long_words=False,
                    break_on_hyphens=False,
                ) or [""]
            )
        text = "\n".join(wrapped_lines)

    ax.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=COLORS["text"],
        linespacing=1.28,
        zorder=4,
    )


def add_arrow(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    dashed: bool = False,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=0.9,
            linestyle="dashed" if dashed else "solid",
            color=COLORS["line"],
            shrinkA=5,
            shrinkB=5,
            zorder=1,
        )
    )


def add_branch(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    elbow_x: float,
) -> None:
    x1, y1 = start
    x2, y2 = end
    ax.plot(
        [x1, elbow_x], [y1, y1],
        color=COLORS["line"], linewidth=0.9, zorder=1,
    )
    ax.plot(
        [elbow_x, elbow_x], [y1, y2],
        color=COLORS["line"], linewidth=0.9, zorder=1,
    )
    add_arrow(ax, (elbow_x, y2), (x2, y2))


def draw(counts: dict[str, Any], output: Path) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(12.0, 9.6))
    fig.patch.set_facecolor(COLORS["white"])
    ax.set_facecolor(COLORS["white"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(
        0.5, 0.965,
        "Search and preprocessing flow",
        ha="center", va="center",
        fontsize=16.5, fontweight="bold", color=COLORS["navy"],
    )
    ax.text(
        0.5, 0.935,
        "Automated processing before title and abstract screening",
        ha="center", va="center",
        fontsize=9.8, color=COLORS["muted"],
    )

    main_x, main_w = 0.06, 0.58
    side_x, side_w = 0.69, 0.27
    center_x = main_x + main_w / 2
    elbow_x = 0.665

    source_lines = "\n".join(
        f"{source}: {value:,}"
        for source, value in counts["records_by_database"].items()
    )
    add_box(
        ax, main_x, 0.750, main_w, 0.145,
        "Records identified from databases\n"
        f"n = {counts['records_identified']:,}\n"
        f"{source_lines}",
        COLORS["blue"],
        fontsize=9.4,
        wrap_width=48,
    )

    add_box(
        ax, main_x, 0.555, main_w, 0.095,
        "Records retained for deduplication\n"
        f"n = {counts['records_retained_for_deduplication']:,}",
        COLORS["green"],
        fontsize=9.3,
        wrap_width=44,
    )
    add_box(
        ax, side_x, 0.525, side_w, 0.155,
        "Automated exclusions\n"
        f"n = {counts['records_excluded_by_automation']:,}\n"
        "Search rule not met\n"
        "Retrieval-stage exclusion\n"
        "Missing agent or domain evidence",
        COLORS["red"],
        fontsize=7.8,
        wrap_width=30,
    )

    add_box(
        ax, main_x, 0.350, main_w, 0.105,
        "Records available for screening\n"
        f"n = {counts['records_available_for_screening']:,}",
        COLORS["purple"],
        linewidth=1.7,
        fontsize=9.4,
        wrap_width=42,
    )
    add_box(
        ax, side_x, 0.315, side_w, 0.175,
        "Duplicate records removed\n"
        f"n = {counts['duplicate_records_removed']:,}\n"
        f"Identifier match: {counts['identifier_based_duplicates']:,}\n"
        "DOI, PMID, or arXiv ID\n"
        f"Title match: {counts['title_based_duplicates']:,}",
        COLORS["red"],
        fontsize=7.8,
        wrap_width=30,
    )

    add_box(
        ax, 0.20, 0.125, 0.60, 0.095,
        "Next step\nTitle and abstract screening\n"
        "Apply predefined inclusion and exclusion criteria",
        COLORS["next"],
        fontsize=8.8,
        linewidth=1.25,
        linestyle="dashed",
        wrap_width=58,
    )

    add_arrow(ax, (center_x, 0.750), (center_x, 0.650))
    add_arrow(ax, (center_x, 0.555), (center_x, 0.455))
    add_arrow(ax, (center_x, 0.350), (0.50, 0.220), dashed=True)
    add_branch(ax, (main_x + main_w, 0.603), (side_x, 0.603), elbow_x)
    add_branch(ax, (main_x + main_w, 0.403), (side_x, 0.403), elbow_x)

    ax.text(
        0.5, 0.060,
        (
            f"Count check: {counts['records_identified']:,} - "
            f"{counts['records_excluded_by_automation']:,} - "
            f"{counts['duplicate_records_removed']:,} = "
            f"{counts['records_available_for_screening']:,}"
        ),
        ha="center", va="center",
        fontsize=8.8, color=COLORS["muted"],
    )
    ax.text(
        0.5, 0.032,
        "Counts refer to citation records, not reports or unique studies.",
        ha="center", va="center",
        fontsize=8.4, color=COLORS["muted"],
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for extension in ("pdf", "png"):
        path = output.with_suffix(f".{extension}")
        options: dict[str, Any] = {
            "bbox_inches": "tight",
            "facecolor": COLORS["white"],
            "pad_inches": 0.15,
        }
        if extension == "png":
            options["dpi"] = 600
        fig.savefig(path, **options)
        saved.append(path)
        print(f"Saved: {path}")

    plt.close(fig)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a PRISMA-aligned diagram for automated search and "
            "preprocessing before title/abstract screening."
        )
    )
    parser.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--filtered", type=Path, default=DEFAULT_FILTERED)
    parser.add_argument("--deduplicated", type=Path, default=DEFAULT_DEDUPLICATED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    counts = calculate_counts(
        args.combined,
        args.rejected,
        args.filtered,
        args.deduplicated,
    )

    args.audit_json.parent.mkdir(parents=True, exist_ok=True)
    args.audit_json.write_text(
        json.dumps(counts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved: {args.audit_json}")

    draw(counts, args.output)


if __name__ == "__main__":
    main()
