from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from pipeline_common import DATA_OUT, REPORTS, assign_domains, classify_data_type, load_config


def safe_name(value):
    return "".join(character if character.isalnum() or character in "_-" else "_" for character in value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    frame = pd.read_csv(DATA_OUT / "03_deduplicated_candidates.csv", dtype=str, keep_default_na=False).fillna("")
    rows = []
    for row in frame.to_dict("records"):
        row.update(assign_domains(row, config))
        row["data_type"] = classify_data_type(row)
        rows.append(row)
    output = pd.DataFrame(rows).fillna("")
    order = {domain: index for index, domain in enumerate(config["domain_order"])}
    output["_domain_order"] = output["primary_domain"].map(order).fillna(999)
    output["_year"] = pd.to_numeric(output["year"], errors="coerce").fillna(0)
    priority = {"agent_system_candidate": 1, "benchmark_evaluation_resource": 2, "review_perspective": 3, "model_or_component": 4}
    output["_type_order"] = output["data_type"].map(priority).fillna(9)
    output = output.sort_values(["_domain_order", "_type_order", "_year", "title_normalized"], ascending=[True, True, False, True]).drop(columns=["_domain_order", "_type_order", "_year"]).reset_index(drop=True)
    output.insert(0, "candidate_record_id", [f"CAND-{index:06d}" for index in range(1, len(output)+1)])
    output.to_csv(DATA_OUT / "04_candidates_sorted_by_domain.csv", index=False)

    by_domain = DATA_OUT / "by_domain"
    by_type = DATA_OUT / "by_data_type"
    by_domain.mkdir(parents=True, exist_ok=True)
    by_type.mkdir(parents=True, exist_ok=True)
    for domain, group in output.groupby("primary_domain", sort=False):
        group.to_csv(by_domain / f"{safe_name(domain)}.csv", index=False)
    for data_type, group in output.groupby("data_type", sort=False):
        group.to_csv(by_type / f"{safe_name(data_type)}.csv", index=False)

    summary = output.groupby(["primary_domain", "data_type"], dropna=False).size().reset_index(name="publication_count")
    REPORTS.mkdir(parents=True, exist_ok=True)
    summary.to_csv(REPORTS / "domain_data_type_counts.csv", index=False)
    print(f"Exported {len(output):,} unique publications")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
