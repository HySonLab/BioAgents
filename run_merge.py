from pathlib import Path
import re
import pandas as pd

# Folder containing the domain CSV files and Manually_Identified.csv
BASE_DIR = Path("data/by_category_HUMAN")
MANUAL_FILE = BASE_DIR / "Manually_Identified.csv"
OUTPUT_DIR = BASE_DIR / "merge"

DOMAIN_COLUMN = "primary_category"
TITLE_COLUMN = "title"
SUMMARY_FILE_NAME = "merge_summary.csv"
COUNT_FILE_NAME = "article_counts.csv"


def normalize_domain(value: object) -> str:
    """Normalize a domain value so that it safely matches a CSV filename."""
    text = str(value).strip().lower()
    text = re.sub(r"[\s\-/]+", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "", text)
    return re.sub(r"_+", "_", text).strip("_")


def normalized_title(series: pd.Series) -> pd.Series:
    """Create a normalized key for case-insensitive title deduplication."""
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.casefold()
    )


def count_articles_in_merged_files() -> pd.DataFrame:
    """Count the number of article rows in every merged domain CSV file."""
    records = []

    excluded_files = {SUMMARY_FILE_NAME, COUNT_FILE_NAME}
    for csv_file in sorted(OUTPUT_DIR.glob("*.csv")):
        if csv_file.name in excluded_files:
            continue

        data = pd.read_csv(csv_file, encoding="utf-8-sig")
        records.append(
            {
                "domain": csv_file.stem,
                "article_count": len(data),
                "file_name": csv_file.name,
            }
        )

    counts = pd.DataFrame(records)
    if not counts.empty:
        counts = counts.sort_values(
            ["article_count", "domain"], ascending=[False, True]
        ).reset_index(drop=True)

    counts.to_csv(
        OUTPUT_DIR / COUNT_FILE_NAME,
        index=False,
        encoding="utf-8-sig",
    )
    return counts


def main() -> None:
    if not MANUAL_FILE.exists():
        raise FileNotFoundError(f"File not found: {MANUAL_FILE}")

    manual = pd.read_csv(MANUAL_FILE, encoding="utf-8-sig")
    manual.columns = manual.columns.astype(str).str.strip()

    required = {TITLE_COLUMN, DOMAIN_COLUMN}
    missing = required.difference(manual.columns)
    if missing:
        raise ValueError(
            f"{MANUAL_FILE.name} is missing required columns: "
            f"{', '.join(sorted(missing))}. "
            f"Available columns: {', '.join(manual.columns)}"
        )

    manual = manual.dropna(subset=[TITLE_COLUMN, DOMAIN_COLUMN]).copy()
    manual[TITLE_COLUMN] = manual[TITLE_COLUMN].astype(str).str.strip()
    manual[DOMAIN_COLUMN] = manual[DOMAIN_COLUMN].map(normalize_domain)
    manual = manual[(manual[TITLE_COLUMN] != "") & (manual[DOMAIN_COLUMN] != "")]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []

    for domain, manual_domain in manual.groupby(DOMAIN_COLUMN, sort=True):
        source_file = BASE_DIR / f"{domain}.csv"
        output_file = OUTPUT_DIR / f"{domain}.csv"

        if source_file.exists():
            original = pd.read_csv(source_file, encoding="utf-8-sig")
            original.columns = original.columns.astype(str).str.strip()
        else:
            original = pd.DataFrame()

        combined = pd.concat([original, manual_domain], ignore_index=True, sort=False)

        if TITLE_COLUMN not in combined.columns:
            raise ValueError(
                f"File {source_file.name} does not contain the "
                f"'{TITLE_COLUMN}' column."
            )

        rows_before_deduplication = len(combined)
        combined["__title_key"] = normalized_title(combined[TITLE_COLUMN])
        combined = combined[combined["__title_key"] != ""]
        combined = combined.drop_duplicates(subset="__title_key", keep="first")
        combined = combined.drop(columns="__title_key")

        # Keep the original column order, then append any new manual columns.
        if not original.empty:
            ordered_columns = list(original.columns) + [
                column for column in combined.columns
                if column not in original.columns
            ]
            combined = combined.reindex(columns=ordered_columns)

        combined.to_csv(output_file, index=False, encoding="utf-8-sig")
        summary.append(
            {
                "domain": domain,
                "original_rows": len(original),
                "manual_rows": len(manual_domain),
                "duplicates_removed": rows_before_deduplication - len(combined),
                "output_rows": len(combined),
                "output_file": str(output_file),
            }
        )

    summary_df = pd.DataFrame(summary)
    summary_file = OUTPUT_DIR / SUMMARY_FILE_NAME
    summary_df.to_csv(summary_file, index=False, encoding="utf-8-sig")

    counts = count_articles_in_merged_files()

    print(f"Merged files were written to: {OUTPUT_DIR}")
    print(f"Merge summary: {summary_file}")
    print(f"Article counts: {OUTPUT_DIR / COUNT_FILE_NAME}\n")

    if counts.empty:
        print("No merged domain CSV files were found.")
    else:
        print("Number of articles in each merged domain file:")
        print(counts[["domain", "article_count"]].to_string(index=False))
        print(f"\nTotal articles across all domain files: {counts['article_count'].sum()}")


if __name__ == "__main__":
    main()
