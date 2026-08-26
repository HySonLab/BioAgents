from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/review_screening_log.csv")
OUTPUT_FILE = Path("outputs/prisma_counts.csv")
EXCLUSIONS_FILE = Path("outputs/full_text_exclusion_counts.csv")

def count_unique_publications(df, condition):
    values = df.loc[condition, "publication_id"]
    return values[values.ne("")].nunique()

def main():
    df = pd.read_csv(INPUT_FILE, dtype=str).fillna("")
    unique_records = df["duplicate_status"].eq("UNIQUE")
    included = df["full_text_decision"].eq("INCLUDE")
    system_pubs = count_unique_publications(df, included & df["system_map"].eq("YES"))
    benchmark_pubs = count_unique_publications(df, included & df["benchmark_map"].eq("YES"))
    overlap_pubs = count_unique_publications(df, included & df["system_map"].eq("YES") & df["benchmark_map"].eq("YES"))
    unique_pubs = count_unique_publications(df, included)
    calculated = system_pubs + benchmark_pubs - overlap_pubs
    rows = [
        ("records_identified", len(df)),
        ("duplicates_removed", df["duplicate_status"].isin({"EXACT_DOI_DUPLICATE", "EXACT_TITLE_DUPLICATE"}).sum()),
        ("records_screened", (unique_records & df["title_abstract_decision"].ne("NOT_SCREENED")).sum()),
        ("title_abstract_excluded", df["title_abstract_decision"].eq("EXCLUDE").sum()),
        ("full_text_assessed", df["full_text_decision"].isin({"INCLUDE", "EXCLUDE"}).sum()),
        ("full_text_excluded", df["full_text_decision"].eq("EXCLUDE").sum()),
        ("system_publications", system_pubs),
        ("benchmark_publications", benchmark_pubs),
        ("overlap_publications", overlap_pubs),
        ("unique_publications", unique_pubs),
        ("calculated_unique_publications", calculated),
    ]
    counts = pd.DataFrame(rows, columns=["flow_item", "count"])
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    counts.to_csv(OUTPUT_FILE, index=False)
    exclusions = (df.loc[df["full_text_decision"].eq("EXCLUDE"), "primary_exclusion_reason"]
                  .value_counts(dropna=False).rename_axis("exclusion_reason").reset_index(name="count"))
    exclusions.to_csv(EXCLUSIONS_FILE, index=False)
    if unique_pubs != calculated:
        raise ValueError("system publications + benchmark publications - overlap != unique publications")
    print(counts.to_string(index=False))

if __name__ == "__main__":
    main()
