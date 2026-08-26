from pathlib import Path
import pandas as pd

INPUT_FILE = Path("outputs/prisma_counts.csv")
OUTPUT_FILE = Path("outputs/prisma_counts.tex")
MACROS = {
    "records_identified": "NRecordsIdentified",
    "duplicates_removed": "NDuplicatesRemoved",
    "records_screened": "NRecordsScreened",
    "title_abstract_excluded": "NTitleAbstractExcluded",
    "full_text_assessed": "NFullTextsAssessed",
    "full_text_excluded": "NFullTextsExcluded",
    "system_publications": "NSystemPublications",
    "benchmark_publications": "NBenchmarkPublications",
    "overlap_publications": "NOverlapPublications",
    "unique_publications": "NUniquePublications",
}

def main():
    df = pd.read_csv(INPUT_FILE)
    values = dict(zip(df["flow_item"], df["count"]))
    lines = ["% Auto-generated from prisma_counts.csv. Do not edit manually."]
    for key, macro in MACROS.items():
        lines.append(rf"\newcommand{{\{macro}}}{{{int(values.get(key, 0))}}}")
    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved LaTeX macros to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
