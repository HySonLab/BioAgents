from pathlib import Path
import pandas as pd
from rapidfuzz import fuzz

INPUT_FILE = Path("data/master_records.csv")
OUTPUT_FILE = Path("data/master_records_with_duplicates.csv")
REVIEW_FILE = Path("outputs/possible_duplicate_pairs.csv")
TITLE_SIMILARITY_THRESHOLD = 94

def assign_exact_duplicates(df):
    df["duplicate_status"] = "UNIQUE"
    df["duplicate_of"] = ""
    for _, indices in df.loc[df["doi_normalized"].ne("")].groupby("doi_normalized").groups.items():
        indices = list(indices)
        if len(indices) > 1:
            preferred_id = df.loc[indices[0], "record_id"]
            for index in indices[1:]:
                df.loc[index, ["duplicate_status", "duplicate_of"]] = ["EXACT_DOI_DUPLICATE", preferred_id]
    subset = df.loc[df["doi_normalized"].eq("") & df["title_normalized"].ne("")]
    for _, indices in subset.groupby("title_normalized").groups.items():
        indices = list(indices)
        if len(indices) > 1:
            preferred_id = df.loc[indices[0], "record_id"]
            for index in indices[1:]:
                if df.loc[index, "duplicate_status"] == "UNIQUE":
                    df.loc[index, ["duplicate_status", "duplicate_of"]] = ["EXACT_TITLE_DUPLICATE", preferred_id]
    return df

def find_near_duplicate_pairs(df):
    candidates = df.loc[df["duplicate_status"].eq("UNIQUE") & df["title_normalized"].ne("")]
    rows = candidates.to_dict("records")
    pairs = []
    for i, first in enumerate(rows):
        for second in rows[i + 1:]:
            score = fuzz.token_set_ratio(first["title_normalized"], second["title_normalized"])
            if score >= TITLE_SIMILARITY_THRESHOLD:
                pairs.append({
                    "record_id_1": first["record_id"], "record_id_2": second["record_id"],
                    "title_1": first["title"], "title_2": second["title"],
                    "year_1": first["year"], "year_2": second["year"],
                    "doi_1": first["doi"], "doi_2": second["doi"],
                    "title_similarity": score, "manual_decision": "",
                    "version_group_id": "", "notes": ""
                })
    return pd.DataFrame(pairs)

def main():
    df = pd.read_csv(INPUT_FILE, dtype=str).fillna("")
    df = assign_exact_duplicates(df)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    pairs = find_near_duplicate_pairs(df)
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(REVIEW_FILE, index=False)
    print(f"Saved duplicate-annotated records to {OUTPUT_FILE}")
    print(f"Saved {len(pairs)} possible duplicate/version pairs to {REVIEW_FILE}")

if __name__ == "__main__":
    main()
