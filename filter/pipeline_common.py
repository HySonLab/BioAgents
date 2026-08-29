from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
from typing import Any
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data_raw"
DATA_OUT = PROJECT_ROOT / "data"
REPORTS = PROJECT_ROOT / "outputs" / "reports"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "search_config.json"

SOURCE_PRIORITY = {
    "PubMed": 6,
    "Europe PMC": 5,
    "bioRxiv": 4,
    "Crossref": 3,
    "arXiv": 2,
}

COLUMN_ALIASES = {
    "source": ["source", "database"],
    "source_id": ["source_id", "id", "record_id"],
    "title": ["title", "article_title"],
    "authors": ["authors", "author", "author_string"],
    "year": ["year", "pub_year", "publication_year"],
    "doi": ["doi"],
    "pmid": ["pmid"],
    "pmcid": ["pmcid"],
    "arxiv_id": ["arxiv_id"],
    "url": ["url", "link"],
    "abstract": ["abstract", "abstract_text", "summary"],
    "keywords": ["keywords", "keyword", "categories", "category"],
    "publication_type": ["publication_type", "pub_type", "type"],
    "venue": ["venue", "journal", "journal_title"],
    "query_domain": ["query_domain", "domain", "domain_group"],
    "matched_domains": ["matched_domains", "all_matched_domains"],
    "domain_hits_json": ["domain_hits_json"],
    "query_domain_hits": ["query_domain_hits"],
    "explicit_agent_hits": ["explicit_agent_hits", "agent_hits"],
    "explicit_agent_hit_count": ["explicit_agent_hit_count"],
    "domain_hit_count_total": ["domain_hit_count_total"],
    "search_logic_keep": ["search_logic_keep", "keep"],
    "retrieval_status": ["retrieval_status"],
    "reject_reason": ["reject_reason", "search_logic_rejection_reason"],
}

CANONICAL_COLUMNS = list(COLUMN_ALIASES)


def clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def norm_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_doi(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.rstrip(".,; )]}>")


def norm_arxiv(value: Any) -> str:
    match = re.search(r"(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?", clean(value).lower())
    return match.group(1) if match else ""


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"true", "1", "yes", "y"}


def split_values(value: Any) -> list[str]:
    return [part.strip() for part in re.split(r"[;|]", clean(value)) if part.strip()]


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or DEFAULT_CONFIG
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config["domain_order"]) != set(config["domain_groups"]):
        raise ValueError("domain_order and domain_groups do not match")
    return config


def canonicalize(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy().fillna("")
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    output = pd.DataFrame(index=frame.index)
    for canonical, aliases in COLUMN_ALIASES.items():
        selected = next((lowered[a.lower()] for a in aliases if a.lower() in lowered), None)
        output[canonical] = frame[selected].astype(str) if selected else ""
    return output.fillna("")


def find_hits(text: Any, terms: list[str]) -> list[str]:
    normalized = f" {norm_text(text)} "
    hits = []
    seen = set()
    for term in terms:
        key = norm_text(term)
        if key and key not in seen and f" {key} " in normalized:
            seen.add(key)
            hits.append(term)
    return hits


def domain_evidence(row: dict[str, Any], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    title = clean(row.get("title"))
    abstract = clean(row.get("abstract"))
    keywords = clean(row.get("keywords"))
    evidence = {}
    for domain, terms in config["domain_groups"].items():
        title_hits = find_hits(title, terms)
        keyword_hits = find_hits(keywords, terms)
        abstract_hits = find_hits(abstract, terms)
        unique_hits = list(dict.fromkeys(title_hits + keyword_hits + abstract_hits))
        score = sum(max(1, len(norm_text(term).split())) * 6 for term in title_hits)
        score += sum(max(1, len(norm_text(term).split())) * 3 for term in keyword_hits)
        score += sum(max(1, len(norm_text(term).split())) for term in abstract_hits)
        if unique_hits:
            evidence[domain] = {
                "score": score,
                "title_hits": title_hits,
                "keyword_hits": keyword_hits,
                "abstract_hits": abstract_hits,
                "all_hits": unique_hits,
            }
    return evidence


def assign_domains(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    evidence = domain_evidence(row, config)
    order = {domain: index for index, domain in enumerate(config["domain_order"])}
    ranked = sorted(evidence, key=lambda domain: (-evidence[domain]["score"], order.get(domain, 999)))
    primary = ranked[0] if ranked else "unclassified"
    return {
        "primary_domain": primary,
        "all_matched_domains": "; ".join(ranked),
        "domain_scores_json": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    }


def classify_data_type(row: dict[str, Any]) -> str:
    text = norm_text(" ".join([clean(row.get("title")), clean(row.get("abstract")), clean(row.get("publication_type"))]))
    benchmark_patterns = ["benchmark", "evaluating ai agents", "evaluation suite", "deterministic grader", "test suite"]
    review_patterns = ["systematic review", "scoping review", "narrative review", "survey of", "review of"]
    component_patterns = ["foundation model", "prediction model", "language model for", "classifier", "segmentation model"]
    if any(pattern in text for pattern in benchmark_patterns):
        return "benchmark_evaluation_resource"
    if any(pattern in text for pattern in review_patterns):
        return "review_perspective"
    if any(pattern in text for pattern in component_patterns) and "agent" not in text:
        return "model_or_component"
    return "agent_system_candidate"
