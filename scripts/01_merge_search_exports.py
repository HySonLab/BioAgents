from pathlib import Path
import re
import unicodedata
import pandas as pd

RAW_DIR = Path("data_raw")
OUTPUT_FILE = Path("data/master_records.csv")

COLUMN_ALIASES = {
    "title": ["title", "article title", "document title"],
    "authors": ["authors", "author", "author(s)"],
    "year": ["year", "publication year", "pub year"],
    "doi": ["doi", "digital object identifier"],
    "pmid": ["pmid", "pubmed id"],
    "url": ["url", "link", "document url"],
    "abstract": ["abstract", "summary"],
}

def normalize_column_name(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())

def find_column(df, possible_names):
    normalized = {normalize_column_name(c): c for c in df.columns}
    for name in possible_names:
        if name in normalized:
            return normalized[name]
    return None

def normalize_title(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def normalize_doi(value):
    if pd.isna(value):
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip().rstrip(".,;")

def standardize_export(path):
    df = pd.read_csv(path)
    output = pd.DataFrame()
    for standard_name, aliases in COLUMN_ALIASES.items():
        source_column = find_column(df, aliases)
        output[standard_name] = "" if source_column is None else df[source_column]
    output["source_file"] = path.name
    output["source_database"] = path.parent.name
    output["title_normalized"] = output["title"].map(normalize_title)
    output["doi_normalized"] = output["doi"].map(normalize_doi)
    return output

def main():
    frames = [standardize_export(path) for path in RAW_DIR.rglob("*.csv")]
    if not frames:
        raise RuntimeError("No CSV exports were found under data_raw/.")
    records = pd.concat(frames, ignore_index=True)
    records.insert(0, "record_id", [f"REC-{i:05d}" for i in range(1, len(records) + 1)])
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    records.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(records)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
