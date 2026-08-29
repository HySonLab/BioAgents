# FEV combine, deduplicate, and domain export pipeline

This pipeline consumes crawler CSV outputs under `data_raw/`.

## Processing

1. Recursively discover final CSV outputs.
2. Exclude chunk, rejected, audit, and checkpoint files.
3. Normalize heterogeneous source columns.
4. Keep rows that passed the retrieval gate and contain agent/domain evidence.
5. Deduplicate first by DOI, PMID, or arXiv ID, then by normalized title.
6. Assign a primary domain using title-weighted, keyword-weighted, and abstract-weighted evidence.
7. Classify the publication as an agent-system candidate, benchmark/evaluation resource, review/perspective, or model/component.
8. Export one combined sorted file and separate files by domain and data type.

## Install

```bash
pip install -r requirements.txt
```

## Run inside the project

Place this pipeline at the project root, beside `data_raw/` and `config/`, then run:

```bash
python run_pipeline.py --config config/search_config.json --input-root data_raw
```

## Main outputs

```text
data/01_combined_source_rows.csv
data/02_filtered_candidate_rows.csv
data/02_postcombine_rejected_rows.csv
data/03_deduplicated_candidates.csv
data/04_candidates_sorted_by_domain.csv
data/by_domain/*.csv
data/by_data_type/*.csv
outputs/reports/input_file_manifest.csv
outputs/reports/domain_data_type_counts.csv
```

`query_domain` records where a paper was discovered. `primary_domain` is reassigned from weighted content evidence. `all_matched_domains` preserves multi-domain membership.
