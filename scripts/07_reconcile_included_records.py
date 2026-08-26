from pathlib import Path
import re
import unicodedata
import pandas as pd
from rapidfuzz import process, fuzz

MASTER_FILE = Path("data/master_records.csv")
INCLUDED_FILE = Path("data/current_supplementary_publications.csv")
OUTPUT_FILE = Path("outputs/included_record_reconciliation.csv")

def normalize_title(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()

def main():
    master = pd.read_csv(MASTER_FILE, dtype=str).fillna("")
    included = pd.read_csv(INCLUDED_FILE, dtype=str).fillna("")
    if "title_normalized" not in included.columns:
        included["title_normalized"] = included["title"].map(normalize_title)
    titles = master["title_normalized"].tolist()
    rows = []
    for _, pub in included.iterrows():
        doi = pub.get("doi_normalized", "")
        doi_match = master.loc[master["doi_normalized"].eq(doi)] if doi else pd.DataFrame()
        if not doi_match.empty:
            match = doi_match.iloc[0]
            method, score = "DOI", 100
        else:
            result = process.extractOne(pub["title_normalized"], titles, scorer=fuzz.token_set_ratio)
            if result is None:
                match = None
                method, score = "NO_MATCH", 0
            else:
                _, score, index = result
                match = master.iloc[index]
                method = "TITLE"
        rows.append({
            "publication_id": pub.get("publication_id", ""),
            "included_title": pub.get("title", ""),
            "matched_record_id": "" if match is None else match["record_id"],
            "matched_title": "" if match is None else match["title"],
            "match_method": method,
            "match_score": score,
            "discovery_source": "" if match is None else match["source_database"],
            "manual_review": "REQUIRED" if score < 97 else "",
        })
    pd.DataFrame(rows).to_csv(OUTPUT_FILE, index=False)
    print(f"Saved reconciliation to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
