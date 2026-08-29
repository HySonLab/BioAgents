from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from common import *

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--config", default=None); args = parser.parse_args(); config = load_config(args.config)
    domain_frames = []; manifest = []
    for domain in config["domain_order"]:
        frames = []
        for source in ("pubmed", "europe_pmc", "arxiv", "crossref"):
            path = RAW / source / f"{domain}.csv"
            if not path.exists(): continue
            try: frame = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
            except pd.errors.EmptyDataError: continue
            frame["retrieval_file"] = str(path); frames.append(frame); manifest.append({"source": source, "domain": domain, "rows": len(frame), "file": str(path)})
        if not frames: continue
        merged = pd.concat(frames, ignore_index=True, sort=False).fillna("")
        merged["title_normalized"] = merged["title"].map(norm_text)
        merged = merged[merged["title_normalized"].ne("")]
        merged = merged.sort_values(merged["abstract"].str.len().rename("abstract_length"), ascending=False).drop_duplicates("title_normalized")
        output = DATA / "by_domain" / f"{domain}.csv"; output.parent.mkdir(parents=True, exist_ok=True); merged.to_csv(output, index=False)
        domain_frames.append(merged)
    if not domain_frames: raise RuntimeError("No retained domain records found")
    all_rows = pd.concat(domain_frames, ignore_index=True, sort=False).fillna("")
    all_rows["title_normalized"] = all_rows["title"].map(norm_text)
    order = {domain: index for index, domain in enumerate(config["domain_order"])}
    final = []
    for number, (title_key, group) in enumerate(all_rows.groupby("title_normalized", sort=False), 1):
        domains = list(dict.fromkeys(group["query_domain"]))
        primary = min(domains, key=lambda x: (order.get(x, 999), x))
        ranked = group.assign(_score=group["doi"].ne("").astype(int)*4 + group["pmid"].ne("").astype(int)*3 + group["pmcid"].ne("").astype(int)*2 + group["abstract"].str.len()/100000).sort_values("_score", ascending=False)
        canonical = ranked.iloc[0]
        screened = full_agent_screen(dict(canonical), config)
        row = {"candidate_record_id": f"CAND-{number:06d}", "primary_domain": primary, "all_matched_domains": "; ".join(domains), "title": max(group["title"], key=len), "authors": max(group["authors"], key=len), "year": max(group["year"]), "doi": canonical["doi"], "pmid": canonical["pmid"], "pmcid": canonical["pmcid"], "arxiv_id": canonical["arxiv_id"], "url": canonical["url"], "abstract": max(group["abstract"], key=len), "retrieved_from_sources": "; ".join(dict.fromkeys(group["source"])), "merged_row_count": len(group), "title_normalized": title_key, "criterion_goal_directed_control_final": "NR", "criterion_stateful_tool_execution_final": "NR", "criterion_inspectable_support_final": "NR", "full_agentic_status_final": "UNCLEAR_OR_NOT_REPORTED", **screened}
        final.append(row)
    output = pd.DataFrame(final); output["_domain_order"] = output["primary_domain"].map(order).fillna(999); output["_year"] = pd.to_numeric(output["year"], errors="coerce").fillna(0)
    output = output.sort_values(["_domain_order", "full_text_review_priority", "_year", "title_normalized"], ascending=[True, True, False, True]).drop(columns=["_domain_order", "_year"])
    assert not output["title_normalized"].duplicated().any()
    DATA.mkdir(parents=True, exist_ok=True); output.to_csv(DATA / "explicit_agent_domain_candidates_deduplicated_sorted.csv", index=False)
    REPORTS.mkdir(parents=True, exist_ok=True); pd.DataFrame(manifest).to_csv(REPORTS / "source_domain_manifest.csv", index=False)
    print("Final unique candidates:", len(output))

if __name__ == "__main__": main()
