from __future__ import annotations
import json
import pandas as pd
from pipeline_common import DATA_OUT, SOURCE_PRIORITY, clean, norm_text, norm_doi, norm_arxiv, split_values


def key_for(row):
    doi = norm_doi(row.get("doi"))
    pmid = clean(row.get("pmid"))
    arxiv = norm_arxiv(row.get("arxiv_id") or row.get("source_id"))
    title = norm_text(row.get("title"))
    if doi: return "DOI:" + doi
    if pmid: return "PMID:" + pmid
    if arxiv: return "ARXIV:" + arxiv
    return "TITLE:" + title


def quality(row):
    return (
        SOURCE_PRIORITY.get(clean(row.get("source")), 1),
        int(bool(norm_doi(row.get("doi")))),
        int(bool(clean(row.get("pmid")))),
        len(clean(row.get("abstract"))),
        len(clean(row.get("authors"))),
    )


def merge_group(group):
    records = group.to_dict("records")
    canonical = max(records, key=quality).copy()
    for field in ("title", "abstract", "authors", "keywords"):
        canonical[field] = max((clean(row.get(field)) for row in records), key=len, default="")
    for field in ("doi", "pmid", "pmcid", "arxiv_id", "url", "year", "venue", "publication_type"):
        if not clean(canonical.get(field)):
            canonical[field] = next((clean(row.get(field)) for row in records if clean(row.get(field))), "")
    canonical["title_normalized"] = norm_text(canonical.get("title"))
    canonical["retrieved_from_sources"] = "; ".join(dict.fromkeys(clean(row.get("source")) for row in records if clean(row.get("source"))))
    canonical["retrieval_files"] = "; ".join(dict.fromkeys(clean(row.get("retrieval_file")) for row in records if clean(row.get("retrieval_file"))))
    domains = []
    for row in records:
        domains += split_values(row.get("matched_domains")) + split_values(row.get("query_domain"))
    canonical["retrieved_from_domains"] = "; ".join(dict.fromkeys(domains))
    canonical["all_dois"] = "; ".join(dict.fromkeys(norm_doi(row.get("doi")) for row in records if norm_doi(row.get("doi"))))
    canonical["all_pmids"] = "; ".join(dict.fromkeys(clean(row.get("pmid")) for row in records if clean(row.get("pmid"))))
    canonical["all_arxiv_ids"] = "; ".join(dict.fromkeys(norm_arxiv(row.get("arxiv_id") or row.get("source_id")) for row in records if norm_arxiv(row.get("arxiv_id") or row.get("source_id"))))
    canonical["merged_row_count"] = len(records)
    return canonical


def main():
    frame = pd.read_csv(DATA_OUT / "02_filtered_candidate_rows.csv", dtype=str, keep_default_na=False).fillna("")
    frame["dedup_key_initial"] = frame.apply(key_for, axis=1)
    first = pd.DataFrame([merge_group(group) for _, group in frame.groupby("dedup_key_initial", sort=False)])
    first["title_key"] = first["title"].map(norm_text)
    final = pd.DataFrame([merge_group(group) for _, group in first.groupby("title_key", sort=False)])
    final.to_csv(DATA_OUT / "03_deduplicated_candidates.csv", index=False)
    print(f"Source rows={len(frame):,}; unique publications={len(final):,}")

if __name__ == "__main__":
    main()
