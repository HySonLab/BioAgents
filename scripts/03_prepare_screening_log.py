from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/master_records_with_duplicates.csv")
OUTPUT_FILE = Path("data/review_screening_log.csv")

SCREENING_COLUMNS = [
    "record_id", "title", "authors", "year", "doi", "pmid", "url",
    "source_database", "source_file", "duplicate_status", "duplicate_of",
    "version_group_id", "preferred_version", "title_abstract_decision",
    "full_text_decision", "primary_exclusion_reason", "exclusion_note",
    "system_map", "benchmark_map", "publication_id", "coder_1", "coder_2",
    "adjudicated_decision"
]

def main():
    df = pd.read_csv(INPUT_FILE, dtype=str).fillna("")
    for column in SCREENING_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df[SCREENING_COLUMNS].to_csv(OUTPUT_FILE, index=False)
    print(f"Saved screening template with {len(df)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
