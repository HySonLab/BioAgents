from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path("/home/phpham/Work/BioAgents")
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"

DEFAULT_COMBINED = DATA / "01_combined_source_rows.csv"
DEFAULT_REJECTED = DATA / "02_postcombine_rejected_rows.csv"
DEFAULT_FILTERED = DATA / "02_filtered_candidate_rows.csv"
DEFAULT_DEDUPLICATED = DATA / "03_deduplicated_candidates.csv"
DEFAULT_OUTPUT = OUTPUTS / "figures" / "literature_search_flow"
DEFAULT_COUNTS = OUTPUTS / "reports" / "literature_search_counts.json"

SOURCE_ORDER = ("PubMed", "Europe PMC", "arXiv")

COLORS = {
    "navy": "#17365D",
    "blue": "#E7F0F8",
    "green": "#E8F3EC",
    "gold": "#FFF3DA",
    "purple": "#EEEAF7",
    "red": "#FBE9E9",
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


def norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_doi(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.rstrip(".,; )]}>")


def norm_arxiv(value: Any) -> str:
    match = re.search(
        r"(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?",
        clean(value).lower(),
    )
    return match.group(1) if match else ""


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    try:
        return pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
        ).fillna("")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def dedup_key(row: pd.Series) -> str:
    doi = norm_doi(row.get("doi", ""))
    pmid = clean(row.get("pmid", ""))
    arxiv_id = norm_arxiv(
        row.get("arxiv_id", "") or row.get("source_id", "")
    )
    title = norm_text(row.get("title", ""))

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

    source_rows = {
        source: int(combined["source"].eq(source).sum())
        for source in SOURCE_ORDER
    }
    unknown_sources = int(
        (~combined["source"].isin(SOURCE_ORDER)).sum()
    )
    if unknown_sources:
        source_rows["Other"] = unknown_sources

    if len(combined) != len(rejected) + len(filtered):
        raise ValueError(
            "Filtering counts do not balance: "
            f"{len(combined):,} != {len(rejected):,} + {len(filtered):,}."
        )

    work = filtered.copy()
    work["_dedup_key"] = work.apply(dedup_key, axis=1)
    identifier_groups = int(work["_dedup_key"].nunique())

    representative_titles = []
    for _, group in work.groupby("_dedup_key", sort=False):
        representative_titles.append(
            max((clean(value) for value in group["title"]), key=len, default="")
        )

    title_groups = int(
        pd.Series(representative_titles, dtype=str).map(norm_text).nunique()
    )

    if title_groups != len(deduplicated):
        raise ValueError(
            "Deduplication count does not match the saved output: "
            f"calculated {title_groups:,}, saved {len(deduplicated):,}."
        )

    counts = {
        "source_rows": source_rows,
        "retrieved": int(len(combined)),
        "excluded": int(len(rejected)),
        "eligible": int(len(filtered)),
        "identifier_matches": int(len(filtered) - identifier_groups),
        "identifier_groups": identifier_groups,
        "title_matches": int(identifier_groups - title_groups),
        "screening_set": int(len(deduplicated)),
        "total_consolidated": int(len(filtered) - len(deduplicated)),
    }

    if counts["retrieved"] != counts["excluded"] + counts["eligible"]:
        raise AssertionError("Retrieval arithmetic failed.")
    if counts["eligible"] != (
        counts["identifier_matches"] + counts["identifier_groups"]
    ):
        raise AssertionError("Identifier arithmetic failed.")
    if counts["identifier_groups"] != (
        counts["title_matches"] + counts["screening_set"]
    ):
        raise AssertionError("Title arithmetic failed.")

    return counts


def add_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    count: int,
    fill: str,
    *,
    details: list[str] | None = None,
    linewidth: float = 1.25,
) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.012",
            facecolor=fill,
            edgecolor=COLORS["line"],
            linewidth=linewidth,
            zorder=3,
        )
    )

    lines = [title, f"n = {count:,}"]
    if details:
        lines.extend(details)

    ax.text(
        x + width / 2,
        y + height / 2,
        "\n".join(lines),
        ha="center",
        va="center",
        fontsize=10.2,
        color=COLORS["text"],
        linespacing=1.35,
        zorder=4,
    )


def arrow(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.35,
            color=COLORS["line"],
            shrinkA=2,
            shrinkB=2,
            zorder=2,
        )
    )


def branch(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    elbow_x: float,
) -> None:
    x1, y1 = start
    x2, y2 = end
    ax.plot([x1, elbow_x], [y1, y1], color=COLORS["line"], lw=1.25, zorder=1)
    ax.plot([elbow_x, elbow_x], [y1, y2], color=COLORS["line"], lw=1.25, zorder=1)
    arrow(ax, (elbow_x, y2), (x2, y2))


def draw(counts: dict[str, Any], output: Path) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )

    fig, ax = plt.subplots(figsize=(10.5, 10.0))
    fig.patch.set_facecolor(COLORS["white"])
    ax.set_facecolor(COLORS["white"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(
        0.5,
        0.955,
        "Literature search flow",
        ha="center",
        va="center",
        fontsize=18,
        fontweight="bold",
        color=COLORS["navy"],
    )
    ax.text(
        0.5,
        0.922,
        "Automated retrieval, filtering, and consolidation",
        ha="center",
        va="center",
        fontsize=10.5,
        color=COLORS["muted"],
    )

    main_x, main_w = 0.11, 0.56
    side_x, side_w = 0.73, 0.21
    center = main_x + main_w / 2
    elbow = 0.70

    source_details = [
        f"{source}: {value:,}"
        for source, value in counts["source_rows"].items()
    ]
    add_box(
        ax,
        main_x,
        0.740,
        main_w,
        0.140,
        "Records retrieved",
        counts["retrieved"],
        COLORS["blue"],
        details=source_details,
    )

    add_box(
        ax,
        main_x,
        0.545,
        main_w,
        0.090,
        "Eligible records",
        counts["eligible"],
        COLORS["green"],
    )
    add_box(
        ax,
        side_x,
        0.545,
        side_w,
        0.090,
        "Excluded",
        counts["excluded"],
        COLORS["red"],
    )

    add_box(
        ax,
        main_x,
        0.350,
        main_w,
        0.090,
        "Identifier groups",
        counts["identifier_groups"],
        COLORS["gold"],
        details=["DOI, PMID, arXiv ID, or title"],
    )
    add_box(
        ax,
        side_x,
        0.350,
        side_w,
        0.090,
        "Matches merged",
        counts["identifier_matches"],
        COLORS["red"],
    )

    add_box(
        ax,
        main_x,
        0.155,
        main_w,
        0.100,
        "Screening set",
        counts["screening_set"],
        COLORS["purple"],
        details=["After exact title matching"],
        linewidth=1.8,
    )
    add_box(
        ax,
        side_x,
        0.155,
        side_w,
        0.090,
        "Title matches",
        counts["title_matches"],
        COLORS["red"],
    )

    arrow(ax, (center, 0.740), (center, 0.635))
    arrow(ax, (center, 0.545), (center, 0.440))
    arrow(ax, (center, 0.350), (center, 0.255))

    branch(ax, (main_x + main_w, 0.590), (side_x, 0.590), elbow)
    branch(ax, (main_x + main_w, 0.395), (side_x, 0.395), elbow)
    branch(ax, (main_x + main_w, 0.205), (side_x, 0.200), elbow)

    ax.text(
        0.5,
        0.070,
        (
            f"Check: {counts['retrieved']:,} - {counts['excluded']:,} - "
            f"{counts['total_consolidated']:,} = {counts['screening_set']:,}"
        ),
        ha="center",
        va="center",
        fontsize=9.2,
        color=COLORS["muted"],
    )
    ax.text(
        0.5,
        0.040,
        "Manual title/abstract screening begins after this stage.",
        ha="center",
        va="center",
        fontsize=8.7,
        color=COLORS["muted"],
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
        description="Build and draw a concise literature-search flow diagram."
    )
    parser.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--filtered", type=Path, default=DEFAULT_FILTERED)
    parser.add_argument("--deduplicated", type=Path, default=DEFAULT_DEDUPLICATED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--counts", type=Path, default=DEFAULT_COUNTS)
    args = parser.parse_args()

    counts = calculate_counts(
        args.combined,
        args.rejected,
        args.filtered,
        args.deduplicated,
    )

    args.counts.parent.mkdir(parents=True, exist_ok=True)
    args.counts.write_text(
        json.dumps(counts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved: {args.counts}")

    draw(counts, args.output)


if __name__ == "__main__":
    main()