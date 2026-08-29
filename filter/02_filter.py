from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from pipeline_common import DATA_OUT, load_config, as_bool, clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    frame = pd.read_csv(DATA_OUT / "01_combined_source_rows.csv", dtype=str, keep_default_na=False).fillna("")
    keep = frame["search_logic_keep"].map(as_bool)
    status_ok = ~frame["retrieval_status"].str.upper().eq("EXCLUDE_AT_RETRIEVAL")
    agent_ok = frame["explicit_agent_hits"].map(clean).ne("")
    domain_ok = frame["query_domain_hits"].map(clean).ne("") | frame["matched_domains"].map(clean).ne("")
    final_keep = keep & status_ok & agent_ok & domain_ok
    kept = frame[final_keep].copy()
    rejected = frame[~final_keep].copy()
    rejected["postcombine_reject_reason"] = "FAILED_RETRIEVAL_GATE_OR_MISSING_EVIDENCE"
    kept.to_csv(DATA_OUT / "02_filtered_candidate_rows.csv", index=False)
    rejected.to_csv(DATA_OUT / "02_postcombine_rejected_rows.csv", index=False)
    print(f"Input={len(frame):,}; kept={len(kept):,}; rejected={len(rejected):,}")

if __name__ == "__main__":
    main()
