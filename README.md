# Evaluating Agentic Bioinformatics through Functionality, Evidence, and Validation

This repository provides the reproducible literature-retrieval and candidate-screening pipeline used to construct the evidence map for the manuscript **“Evaluating Agentic Bioinformatics through Functionality, Evidence, and Validation.”**

<p align="center">
  <img
    src="assets/Overview.png"
    ter">
  <em>
  Conceptual overview of agentic bioinformatics.
  </em>
</p>

The pipeline searches **PubMed**, **Europe PMC**, and **arXiv**; applies explicit and implicit agent-retrieval strategies; verifies biological-domain evidence; preserves retrieval provenance; standardizes records from different sources; filters ineligible entries; deduplicates publications; assigns each candidate a primary domain and preliminary record type; and exports review-ready files for human verification.


## Workflow
<p align="center">
  <img
    src="assets/PRISMA.png"
    ter">
  <em>
Overview of the literature retrieval, filtering, deduplication, domain assignment, and human-verification workflow.
  </em>
</p>


```text
config/search_config.json
        |
        v
run_all_searches.py
        |
        +--> arXiv
        +--> Europe PMC
        +--> PubMed
        |
        v
data_raw/
        |
        v
run_filter.py
        |
        +--> combine
        +--> filter
        +--> deduplicate
        +--> assign domains and export
        |
        v
data/04_candidates_sorted_by_domain.csv
        |
        v
Human verification and final FEV coding
```

## Quick start

Python 3.10 or later is recommended.

```bash
conda create -n fev python=3.10 -y
conda activate fev
python -m pip install -r requirements.txt
```

Review the search settings in:

```text
config/search_config.json
```

Then run:

```bash
python run_all_searches.py
python run_filter.py
```

The manuscript search interval is **2022-01-01 through 2026-09-01**.

Optional environment variables:

```bash
export NCBI_API_KEY="your-api-key"
export FEV_PROJECT_ROOT="/absolute/path/to/BioAgents"
```

## Repository structure

```text
config/                  Search vocabulary and execution settings
crawl_data/              Source-specific retrieval scripts
 data_raw/               Raw retained and rejected retrieval records
filter/                  Combination, filtering, deduplication, and export stages
data/                    Screening outputs and human-review files
logs/                    Timestamped retrieval logs
outputs/reports/         Pipeline manifests and count summaries
visualization/           Figure and statistical-analysis scripts
run_all_searches.py      Retrieval entry point
run_filter.py            Post-retrieval processing entry point
requirements.txt         Python dependencies
```

## Retrieval

The retrieval pipeline searches **arXiv**, **Europe PMC**, and **PubMed** using explicit agent terms and an implicit functional-agent route defined in `config/search_config.json`.

Run all sources:

```bash
python run_all_searches.py
```

Run selected sources:

```bash
python run_all_searches.py --sources pubmed
python run_all_searches.py --sources europe_pmc arxiv
```

Source outputs are written to:

```text
data_raw/arxiv/
data_raw/europe_pmc/
data_raw/pubmed/
```

Do not manually edit `data_raw/`; it forms the retrieval audit trail. Review `logs/` for failed requests, rate-limit waits, warnings, or incomplete searches before filtering.

## Screening pipeline

`run_filter.py` executes four ordered stages:

1. combine source files;
2. apply the post-retrieval eligibility gate;
3. deduplicate by DOI, PMID, arXiv identifier, and normalized title;
4. assign domains, classify candidate type, sort records, and export review files.

```bash
python run_filter.py
```

Primary output:

```text
data/04_candidates_sorted_by_domain.csv
```

Supporting reports:

```text
outputs/reports/input_file_manifest.csv
outputs/reports/domain_data_type_counts.csv
```

> **Important:** The crawler supports implicit functional-agent retrieval, but the current post-combination gate requires nonempty `explicit_agent_hits`. Records retained only through implicit evidence may therefore be excluded. Confirm that this behavior is intended before generating the final review set.

## Human verification

Manual review files are stored in `data/HumanVerification/`:

```text
HumanVerification.csv    Automated candidates for eligibility review
ManuallyIdentified.csv   Records added through targeted searches or citation tracing
AgenticSystem.csv        Final agentic and agent-adjacent system-use-case coding
Benchmark.csv            Final benchmark and evaluation-resource coding
```

The audit trail should retain eligibility decisions, exclusion reasons, agentic status, analytic category, biological domain, identifiers, supporting evidence, and adjudication information where applicable.

## Visualization and analysis

Generate manuscript figures and association analyses from finalized coding data:

```bash
python visualization/visualization.py
python visualization/association_analysis.py \
  --input data/HumanVerification/AgenticSystem.csv \
  --output-dir visualization/association_outputs \
  --dpi 300 \
  --exclude-duplicates
```
