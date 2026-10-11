# Evaluating Agentic Bioinformatics through Functionality, Evidence, and Validation

This repository contains the reproducible literature-retrieval and candidate-screening pipeline used to construct the evidence map for the manuscript **“Evaluating Agentic Bioinformatics through Functionality, Evidence, and Validation.”**

The workflow searches **PubMed**, **Europe PMC**, and **arXiv**, applies explicit and implicit agent-retrieval routes, validates biological-domain evidence, preserves retrieval provenance, combines heterogeneous source files into a common schema, filters ineligible rows, deduplicates publications, assigns a primary domain and preliminary data type, and exports review-ready files for human verification.

> The automated pipeline identifies **candidates for manual review**. Automated retention, domain assignment, data-type classification, and abstract-based agentic screening do not replace full-text verification or final FEV coding.

## Contents

- [Workflow overview](#workflow-overview)
- [Repository structure](#repository-structure)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Stage 1: Retrieve records](#stage-1-retrieve-records)
- [Stage 2: Combine, filter, deduplicate, and export](#stage-2-combine-filter-deduplicate-and-export)
- [Output files](#output-files)
- [Human verification](#human-verification)
- [Search and screening logic](#search-and-screening-logic)
- [Resume, logging, and error handling](#resume-logging-and-error-handling)
- [Reproducibility checklist](#reproducibility-checklist)
- [Troubleshooting](#troubleshooting)
- [Citation](#citation)

## Workflow overview

```text
config/search_config.json
          |
          v
run_all_searches.py
          |
          +--> crawl_data/search_arxiv.py
          +--> crawl_data/search_europe_pmc.py
          +--> crawl_data/search_pubmed.py
          |
          v
data_raw/{arxiv,europe_pmc,pubmed}/
          |
          v
run_filter.py
          |
          +--> filter/01_combine.py
          +--> filter/02_filter.py
          +--> filter/03_deduplicate.py
          +--> filter/04_assign_sort_export.py
          |
          v
data/04_candidates_sorted_by_domain.csv
          |
          v
Human verification and final evidence-map coding
```

The root-level entry points are:

```bash
python run_all_searches.py
python run_filter.py
```

## Repository structure

```text
.
├── config/
│   └── search_config.json
├── crawl_data/
│   ├── common.py
│   ├── http_helpers.py
│   ├── search_arxiv.py
│   ├── search_europe_pmc.py
│   └── search_pubmed.py
├── data_raw/
│   ├── arxiv/
│   ├── europe_pmc/
│   └── pubmed/
├── filter/
│   ├── 01_combine.py
│   ├── 02_filter.py
│   ├── 03_deduplicate.py
│   ├── 04_assign_sort_export.py
│   └── pipeline_common.py
├── data/
│   ├── by_domain/
│   ├── by_data_type/
│   └── HumanVerification/
├── logs/
├── outputs/
│   └── reports/
├── visualizing/
├── run_all_searches.py
├── run_filter.py
└── README.md
```

### `config/`

Contains the search vocabulary and execution settings. The default configuration is:

```text
config/search_config.json
```

The code expects, at minimum:

- `explicit_agent_terms`
- `implicit_agent_components`
- `domain_groups`
- `domain_order`

The implicit-agent configuration uses the following component groups:

- `language_model_terms`
- `tool_execution_terms`
- `knowledge_grounding_terms`
- `planning_control_terms`
- `state_memory_terms`
- `repair_verification_terms`

The configuration can also define:

- `date_from` and `date_until`
- `contact_email`
- source-specific chunk sizes, pauses, retry settings, and resume behavior
- `max_records_per_query`
- optional `ncbi_api_key`
- full-agent verification terms

`domain_order` must contain exactly the same domains as `domain_groups`.

### `crawl_data/`

Contains the source-specific retrieval implementation and shared search utilities.

- `common.py` loads configuration, builds queries, normalizes identifiers and text, applies local agent/domain validation, and writes standardized CSV files.
- `http_helpers.py` sends HTTP requests with retry, exponential backoff, handling for rate limit responses, and handling for temporary server errors.
- `search_arxiv.py` retrieves and parses arXiv Atom records.
- `search_europe_pmc.py` retrieves Europe PMC records using cursor-based pagination.
- `search_pubmed.py` uses NCBI ESearch and EFetch to retrieve PubMed records.

### `data_raw/`

Contains source-level outputs created by `run_all_searches.py`.

```text
data_raw/arxiv/
data_raw/europe_pmc/
data_raw/pubmed/
```

Each source directory contains one retained CSV and, where produced, one rejected CSV per biological domain. PubMed and arXiv also preserve completed query chunks to support safe resume.

Do not manually edit these files. They provide the retrieval audit trail.

### `filter/`

Contains the four ordered processing stages called by `run_filter.py`:

1. combine source files;
2. apply the post-combination gate;
3. deduplicate publications;
4. assign domains and preliminary data types, sort candidates, and export review files.

### `data/`

Contains intermediate and final machine-generated screening outputs.

### `data/HumanVerification/`

Contains files used or produced during manual eligibility review, including the candidate set, manually identified records, consolidated system records, benchmark records, and decision rationales.

### `logs/`

Contains timestamped retrieval logs. PubMed, Europe PMC, and arXiv use source-specific log names.

### `outputs/reports/`

Contains pipeline manifests and count summaries, including the input-file manifest and domain-by-data-type counts.

### `visualizing/`

Contains scripts that generate manuscript figures and statistical summaries from finalized, adjudicated coding data.

## Requirements

The scripts require Python 3.10 or later because the code uses modern type annotations such as `Path | None` and built-in generic types.

Main Python dependencies include:

```text
pandas
requests
PyYAML
```

A recommended Conda setup is:

```bash
conda create -n bioagents python=3.11 pandas requests pyyaml -y
conda activate bioagents
```

If `environment.yml` is available, use:

```bash
conda env create -f environment.yml
conda activate <environment-name>
```

An optional NCBI API key may be supplied through the environment:

```bash
export NCBI_API_KEY="your-api-key"
```

The project root used by the crawler can be overridden with:

```bash
export FEV_PROJECT_ROOT="/absolute/path/to/BioAgents"
```

> `run_filter.py` currently declares `ROOT = Path("/home/phpham/Work/BioAgents")`. If the repository is located elsewhere, change this value or revise the script to derive the root from `Path(__file__).resolve().parent` before running the filter pipeline.

## Configuration

The default file is:

```text
config/search_config.json
```

Before retrieval, verify:

- the publication interval;
- the contact email used for API requests;
- explicit agent terms;
- implicit functional-agent terms;
- domain terms and domain order;
- record limits;
- source-specific pause and retry values;
- resume behavior.

The manuscript search interval is:

```text
2022-01-01 through 2026-09-01
```

### Explicit retrieval route

The explicit route searches for:

```text
explicit agent terms AND current biological-domain terms
```

Examples of explicit concepts are configured in `explicit_agent_terms`.

### Implicit functional-agent route

The implicit route retrieves systems that may not use the word “agent.” The local rule requires:

1. at least one language-model term;
2. at least one tool-execution term;
3. at least one configured supporting functional group;
4. at least the configured minimum number of implicit component groups;
5. evidence for the current biological domain.

The default rule requires language-model and tool-execution groups and at least three implicit component groups in total.

### Local validation

Downloaded metadata are screened using title, abstract, and keywords. A record is retained at retrieval when it has:

```text
(explicit agent evidence OR sufficient implicit functional-agent evidence)
AND
query-domain evidence
```

Possible routes include:

- `EXPLICIT_AND_IMPLICIT_AGENT_DOMAIN`
- `EXPLICIT_AGENT_DOMAIN`
- `IMPLICIT_FUNCTIONAL_AGENT_DOMAIN`
- `NO_QUERY_DOMAIN_EVIDENCE`
- `INSUFFICIENT_AGENT_EVIDENCE`
- `EXCLUDE_AT_RETRIEVAL`

Retained rows receive:

```text
retrieval_status = AGENT_DOMAIN_CANDIDATE
```

Rejected rows receive:

```text
retrieval_status = EXCLUDE_AT_RETRIEVAL
```

## Stage 1: Retrieve records

### Run all sources

```bash
python run_all_searches.py
```

By default, the runner executes the source scripts in this order:

1. arXiv;
2. Europe PMC;
3. PubMed.

It continues to later sources if one source exits with an error, records failed return codes, and returns a nonzero status if any source fails.

### Run selected sources

```bash
python run_all_searches.py --sources pubmed
```

```bash
python run_all_searches.py --sources europe_pmc arxiv
```

Valid names are:

```text
arxiv
europe_pmc
pubmed
```

### Use a different configuration

```bash
python run_all_searches.py --config config/search_config.json
```

### arXiv behavior

The arXiv collector:

- searches title and abstract fields;
- creates small explicit and implicit queries from configured chunks;
- downloads Atom pages in batches;
- sorts by submission date in descending order;
- applies the exact `date_from` and `date_until` interval using complete publication dates;
- stores `published_date` in addition to publication year;
- deduplicates by normalized arXiv identifier, falling back to normalized title;
- preserves both retained and rejected chunk files;
- re-reads and revalidates all chunks with the current code and configuration;
- uses a SHA-256 configuration fingerprint to determine whether a completed domain output is current;
- checks that every retained final row satisfies the exact date range.

Final files are written as:

```text
data_raw/arxiv/<domain>.csv
data_raw/arxiv/<domain>_rejected.csv
```

Chunk files are stored in:

```text
data_raw/arxiv/chunks/<domain>/
```

### Europe PMC behavior

The Europe PMC collector:

- uses `TITLE_ABS` fielded search blocks;
- combines explicit or implicit agent logic with domain terms;
- applies the configured publication-date interval using `FIRST_PDATE`;
- requests core metadata in JSON;
- uses cursor-based pagination with up to 1,000 records per page;
- disables synonym expansion;
- limits each domain query to `max_records_per_query`;
- applies the same local agent/domain validation used by the other collectors.

Final files are written as:

```text
data_raw/europe_pmc/<domain>.csv
data_raw/europe_pmc/<domain>_rejected.csv
```

### PubMed behavior

The PubMed collector:

- creates small explicit and implicit `Title/Abstract` queries;
- uses NCBI ESearch with `usehistory=y`;
- submits ESearch by POST to avoid URL-length limits;
- limits results by publication date using `mindate`, `maxdate`, and `datetype=pdat`;
- retrieves metadata in XML batches using EFetch, `query_key`, and `WebEnv`;
- extracts PMID, PMCID, DOI, title, abstract, authors, keywords, publication type, venue, and year;
- deduplicates primarily by PMID, then DOI, then normalized title;
- preserves completed chunks for resume;
- revalidates and deduplicates domain records before writing final outputs.

Final files are written as:

```text
data_raw/pubmed/<domain>.csv
data_raw/pubmed/<domain>_rejected.csv
```

Chunk files are stored in:

```text
data_raw/pubmed/chunks/<domain>/
```

## Stage 2: Combine, filter, deduplicate, and export

Run the complete post-retrieval pipeline with:

```bash
python run_filter.py
```

Optional arguments are:

```bash
python run_filter.py \
  --config config/search_config.json \
  --input-root data_raw/
```

`run_filter.py` calls the following scripts sequentially and stops immediately if a stage fails.

### Stage 2.1: Combine source files

Script:

```text
filter/01_combine.py
```

This stage recursively discovers CSV files under the input root. It excludes:

- files inside a `chunks` directory;
- filenames containing `rejected`;
- filenames containing `audit`;
- filenames containing `checkpoint`.

Readable, nonempty CSV files are canonicalized to a common column schema and combined. The original path is retained in `retrieval_file`.

Outputs:

```text
data/01_combined_source_rows.csv
outputs/reports/input_file_manifest.csv
```

The manifest records:

- input filename;
- number of rows;
- source values found in the canonicalized file.

### Stage 2.2: Apply the post-combination gate

Script:

```text
filter/02_filter.py
```

A row is retained only when all of the following are true:

1. `search_logic_keep` evaluates to true;
2. `retrieval_status` is not `EXCLUDE_AT_RETRIEVAL`;
3. `explicit_agent_hits` is nonempty;
4. either `query_domain_hits` or `matched_domains` is nonempty.

Outputs:

```text
data/02_filtered_candidate_rows.csv
data/02_postcombine_rejected_rows.csv
```

Rejected rows receive:

```text
postcombine_reject_reason = FAILED_RETRIEVAL_GATE_OR_MISSING_EVIDENCE
```

> Important: although the crawler supports an implicit functional-agent route, the current post-combination gate requires `explicit_agent_hits` to be nonempty. Therefore, records retained only through implicit evidence may be removed by `filter/02_filter.py`. Keep this behavior only if it is intentional; otherwise revise the gate before producing the final review set.

### Stage 2.3: Deduplicate publications

Script:

```text
filter/03_deduplicate.py
```

The first deduplication key uses the first available identifier in this order:

1. normalized DOI;
2. PMID;
3. normalized arXiv identifier;
4. normalized title.

Within each duplicate group, the canonical record is selected using:

1. source priority;
2. presence of DOI;
3. presence of PMID;
4. abstract length;
5. author-string length.

Current source priority is:

```text
PubMed > Europe PMC > bioRxiv > Crossref > arXiv
```

The script then performs a second merge by normalized title. During merging, it preserves or aggregates:

- the longest title, abstract, author string, and keywords;
- DOI, PMID, PMCID, arXiv ID, URL, year, venue, and publication type;
- all retrieval sources;
- all retrieval files;
- all retrieved domains;
- all DOI, PMID, and arXiv identifiers;
- number of merged source rows.

Output:

```text
data/03_deduplicated_candidates.csv
```

### Stage 2.4: Assign domain, classify type, sort, and export

Script:

```text
filter/04_assign_sort_export.py
```

#### Domain assignment

Domain evidence is calculated from configured terms found in title, keywords, and abstract. The score is weighted as follows:

```text
title hit:    6 x number of words in the matched term
keyword hit:  3 x number of words in the matched term
abstract hit: 1 x number of words in the matched term
```

The highest-scoring domain becomes `primary_domain`. Ties are resolved using `domain_order` from the configuration. All domain matches and their evidence are retained in:

```text
all_matched_domains
domain_scores_json
```

If no domain term is detected, the primary domain is `unclassified`.

#### Preliminary data-type classification

The classifier searches normalized title, abstract, and publication type in the following priority order:

1. `benchmark_evaluation_resource`
2. `review_perspective`
3. `model_or_component`
4. `agent_system_candidate`

Benchmark patterns include phrases such as `benchmark`, `evaluation suite`, and `test suite`. Review patterns include `systematic review`, `scoping review`, `narrative review`, and related forms. Component patterns include `foundation model`, `prediction model`, `classifier`, and `segmentation model`; component classification applies only when the text does not contain `agent`.

This classification is preliminary and must be checked manually.

#### Sorting and record identifiers

Candidates are sorted by:

1. configured domain order;
2. preliminary data-type priority;
3. publication year, descending;
4. normalized title.

Each publication receives a sequential identifier:

```text
CAND-000001
CAND-000002
...
```

Outputs:

```text
data/04_candidates_sorted_by_domain.csv
data/by_domain/<domain>.csv
data/by_data_type/<data_type>.csv
outputs/reports/domain_data_type_counts.csv
```

## Output files

### Retrieval outputs

```text
data_raw/arxiv/<domain>.csv
data_raw/arxiv/<domain>_rejected.csv
data_raw/europe_pmc/<domain>.csv
data_raw/europe_pmc/<domain>_rejected.csv
data_raw/pubmed/<domain>.csv
data_raw/pubmed/<domain>_rejected.csv
```

### Filtering outputs

```text
data/01_combined_source_rows.csv
```

All eligible source-level rows after schema canonicalization, before the post-combination gate.

```text
data/02_filtered_candidate_rows.csv
```

Source-level rows that pass the post-combination gate.

```text
data/02_postcombine_rejected_rows.csv
```

Rows excluded by the post-combination gate, with a machine-generated rejection reason.

```text
data/03_deduplicated_candidates.csv
```

Publication-level records produced by identifier-based and title-based deduplication.

```text
data/04_candidates_sorted_by_domain.csv
```

The principal automated-screening output for human review. It contains one deduplicated candidate publication per row, a candidate identifier, primary domain, all matched domains, domain evidence, and preliminary data type.

### Reports

```text
outputs/reports/input_file_manifest.csv
```

Lists every source CSV loaded by the filtering pipeline and its row count.

```text
outputs/reports/domain_data_type_counts.csv
```

Contains candidate publication counts by primary domain and preliminary data type.

### Human-verification files

```text
data/HumanVerification/04_candidates_sorted_by_domain.csv
```

Review copy of the automated candidate set. Each row should receive a documented manual inclusion or exclusion decision.

```text
data/HumanVerification/Manually Identified.csv
```

Additional publications identified through manual searches, citation tracing, system-name searches, companion publications, or updated versions. Apply the same eligibility criteria used for database-derived candidates.

```text
data/HumanVerification/AgenticSystem.csv
```

Consolidated publications classified after human review as agentic or agent-adjacent systems.

```text
data/HumanVerification/Benchmark.csv
```

Consolidated publications classified after human review as benchmark or evaluation resources.

The human-verification audit trail should record:

- inclusion or exclusion;
- exclusion reason;
- full-agentic or agent-adjacent status when applicable;
- system, benchmark, or overlapping analytic category;
- primary domain;
- supporting notes and source evidence;
- publication identifiers;
- reviewer and adjudication information where applicable.

## Search and screening logic

### Standardized fields

The crawler and filtering pipeline preserve a common set of fields, including:

- search and query identifiers;
- source and source record ID;
- title, authors, year, abstract, keywords, venue, and publication type;
- DOI, PMID, PMCID, and arXiv ID;
- query mode and query domain;
- explicit and implicit agent-term hits;
- matched domain terms;
- retrieval route, confidence, status, and rejection reason;
- normalized title.

### Full-agent screening support

The crawler includes abstract-based support for prioritizing full-text review. It searches for evidence related to:

- goal-directed control;
- stateful tool execution;
- inspectable scientific support;
- repair and verification.

The abstract screen assigns a review priority but does not make a final full-agentic determination:

```text
agentic_status_preliminary = NEEDS_FULL_TEXT_REVIEW
```

Final manual criterion codes use:

```text
D  demonstrated
A  absent
U  unclear
NR not reported
NA not applicable
```

A system is classified as `FULL_AGENTIC` only when all three final criteria are `D`:

- goal-directed control;
- stateful tool execution;
- inspectable scientific support.

Final full-agentic classification must be based on manual review, not abstract keyword hits alone.

## Resume, logging, and error handling

### HTTP retries

Network requests support:

- configurable retry attempts;
- exponential backoff with random jitter;
- special handling for HTTP 429;
- retries for HTTP 500, 502, 503, and 504;
- connection and timeout retries;
- maximum waits capped at 1,800 seconds.

### Resume behavior

PubMed and arXiv preserve completed chunks. If resume is enabled, completed chunks are skipped.

arXiv additionally stores a configuration fingerprint for each final domain file. A domain is skipped only when retained output, rejected output, and the expected fingerprint are all present.

Europe PMC writes domain-level files directly and does not use the same chunk-level resume implementation.

### Interruption

If the search runner is interrupted with `Ctrl+C`, completed domain or chunk files remain available. Rerun the same command to continue where supported.

### Logs

Search logs are written to `logs/` with timestamps, for example:

```text
search_arxiv_YYYYMMDD_HHMMSS.log
search_europe_pmc_YYYYMMDD_HHMMSS.log
search_pubmed_YYYYMMDD_HHMMSS.log
```

Review logs for warnings, failed API calls, rate-limit waits, incomplete domains, and source failures before running the filtering stage.

## Reproducibility checklist

Before manuscript submission or repository archiving, confirm that:

- `search_config.json` matches the manuscript search vocabulary and dates;
- `contact_email` is valid;
- all source searches completed successfully;
- retrieval logs have been reviewed;
- source-level retained and rejected CSV files are preserved;
- `input_file_manifest.csv` contains the expected files;
- post-combination filtering behavior is intentional, especially the explicit-hit requirement;
- deduplication outputs have been inspected for preprint/journal and title variants;
- every candidate has a documented human-verification decision;
- manually identified records were screened using the same rules;
- final system and benchmark files match the manuscript counts;
- independent pre-adjudication coding and adjudication records are retained;
- figures and statistical summaries are generated from finalized data;
- the Python environment is exported;
- the repository version associated with the manuscript is archived.

Recommended environment export:

```bash
conda env export --no-builds > environment.yml
```

Recommended run record:

```bash
python --version
python run_all_searches.py --config config/search_config.json
python run_filter.py --config config/search_config.json --input-root data_raw/
```

## Troubleshooting

### `No eligible CSV files found`

Confirm that retained source CSV files exist under `data_raw/`. The combine stage intentionally ignores chunk directories and filenames containing `rejected`, `audit`, or `checkpoint`.

### `All discovered CSV files were empty or unreadable`

Inspect source logs and source CSV encoding. Empty CSV files and files that raise `EmptyDataError` or `UnicodeDecodeError` are skipped.

### `No eligible CSV files` despite completed searches

Check that final domain outputs were written outside the source `chunks/` directories and their filenames do not contain `rejected`.

### Filtering path points to the wrong repository

Update the hard-coded root in `run_filter.py` or make it derive the root dynamically. The current script uses:

```text
/home/phpham/Work/BioAgents
```

### PubMed rate limiting

Set `NCBI_API_KEY`, use a valid contact email, and retain the configured pauses. The code automatically uses a slower default pause when an API key is absent.

### arXiv skips a completed domain after the configuration changes

The arXiv collector compares a SHA-256 fingerprint of search dates, term groups, domain vocabulary, settings, and collector version. If the fingerprint differs, the domain is rerun.

### Implicit-agent records disappear after retrieval

Inspect `filter/02_filter.py`. The current post-combination gate requires a nonempty `explicit_agent_hits` field, even when the crawler retained a record through sufficient implicit functional-agent evidence.

### Duplicate preprint and journal records remain

Inspect normalized DOI, PMID, arXiv ID, and title values in `03_deduplicated_candidates.csv`. The pipeline does not perform fuzzy-title matching; materially different normalized titles may remain separate and require manual consolidation.

## Citation

If you use this repository, cite the associated manuscript:

```text
Pham P, Hy TS. Evaluating Agentic Bioinformatics through Functionality, Evidence, and Validation.
```

Replace this placeholder with the final journal citation and DOI after publication. Add the archived repository DOI when available.

## Contact

For questions about the search pipeline, screening decisions, or evidence-map files, contact the corresponding author listed in the manuscript.
