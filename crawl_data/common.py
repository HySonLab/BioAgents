from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import pandas as pd

ROOT = Path(os.environ.get("FEV_PROJECT_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
RAW = ROOT / "data_raw"
DATA = ROOT / "data"
REPORTS = ROOT / "outputs" / "reports"
LOGS = ROOT / "logs"
CONFIG = ROOT / "config"
SUPPORTED_SOURCES = {"pubmed", "europe_pmc", "arxiv"}
FINAL_CODES = {"D", "A", "U", "NR", "NA"}

IMPLICIT_GROUPS = (
    "language_model_terms",
    "tool_execution_terms",
    "knowledge_grounding_terms",
    "planning_control_terms",
    "state_memory_terms",
    "repair_verification_terms",
)

BASE_FIELDS = [
    "search_id", "query_mode", "query_domain", "source", "source_id",
    "title", "authors", "year", "doi", "pmid", "pmcid", "arxiv_id",
    "url", "abstract", "keywords", "publication_type", "venue",
    "search_logic_keep", "retrieval_status", "retrieval_route",
    "retrieval_confidence", "reject_reason",
    "explicit_agent_hits", "explicit_agent_hit_count",
    "implicit_language_model_hits", "implicit_tool_execution_hits",
    "implicit_knowledge_grounding_hits", "implicit_planning_control_hits",
    "implicit_state_memory_hits", "implicit_repair_verification_hits",
    "implicit_component_groups_hit", "implicit_component_group_count",
    "query_domain_hits", "query_domain_hit_count", "matched_domains",
    "matched_domain_count", "domain_hit_count_total", "domain_hits_json",
    "title_normalized",
]


def ensure_dirs() -> None:
    for path in (RAW, DATA, REPORTS, LOGS, CONFIG):
        path.mkdir(parents=True, exist_ok=True)


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
    text = unicodedata.normalize("NFKD", clean(value)).lower().replace("&", " and ")
    text = re.sub(r"<[^>]+>", " ", text)
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


def unique_terms(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = clean(value)
        key = norm_text(term)
        if term and key not in seen:
            seen.add(key)
            output.append(term)
    return output


def quote_term(value: Any) -> str:
    return '"' + clean(value).replace('"', '\\"') + '"'


def block(values: Iterable[Any]) -> str:
    terms = [quote_term(value) for value in unique_terms(values)]
    if not terms:
        raise ValueError("Empty Boolean term block")
    return "(" + " OR ".join(terms) + ")"


def fielded_block(values: Iterable[Any], field: str) -> str:
    terms = [f"{field}:{quote_term(value)}" for value in unique_terms(values)]
    if not terms:
        raise ValueError("Empty fielded term block")
    return "(" + " OR ".join(terms) + ")"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else CONFIG / "search_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))

    required = {"explicit_agent_terms", "implicit_agent_components", "domain_groups", "domain_order"}
    missing = required.difference(config)
    if missing:
        raise ValueError("Missing config keys: " + ", ".join(sorted(missing)))

    if set(config["domain_order"]) != set(config["domain_groups"]):
        raise ValueError("domain_order must contain each domain exactly once")

    components = config["implicit_agent_components"]
    missing_groups = set(IMPLICIT_GROUPS).difference(components)
    if missing_groups:
        raise ValueError("Missing implicit component groups: " + ", ".join(sorted(missing_groups)))

    unknown_sources = set(config.get("sources", {})).difference(SUPPORTED_SOURCES)
    if unknown_sources:
        raise ValueError("Unsupported sources: " + ", ".join(sorted(unknown_sources)))

    # Defaults implement: LM + tool + at least one additional functional group.
    config.setdefault("implicit_agent_rules", {})
    rules = config["implicit_agent_rules"]
    rules.setdefault("required_groups", ["language_model_terms", "tool_execution_terms"])
    rules.setdefault("minimum_groups_hit", 3)
    rules.setdefault(
        "support_groups",
        [
            "knowledge_grounding_terms",
            "planning_control_terms",
            "state_memory_terms",
            "repair_verification_terms",
        ],
    )

    invalid_required = set(rules["required_groups"]).difference(IMPLICIT_GROUPS)
    invalid_support = set(rules["support_groups"]).difference(IMPLICIT_GROUPS)
    if invalid_required or invalid_support:
        raise ValueError("implicit_agent_rules refers to unknown component groups")
    if int(rules["minimum_groups_hit"]) < len(rules["required_groups"]):
        raise ValueError("minimum_groups_hit cannot be smaller than required_groups")

    config["ncbi_api_key"] = os.getenv("NCBI_API_KEY") or clean(config.get("ncbi_api_key"))
    return config


def explicit_query_block(config: dict[str, Any]) -> str:
    return block(config["explicit_agent_terms"])


def implicit_query_block(config: dict[str, Any]) -> str:
    """Sensitive server-side retrieval block.

    Local screening remains stricter. The query requires an LM term and a tool
    term, plus one functional support group, to capture systems that do not use
    the word agent.
    """
    components = config["implicit_agent_components"]
    support = []
    for group in config["implicit_agent_rules"]["support_groups"]:
        support.extend(components[group])
    return (
        f"{block(components['language_model_terms'])} AND "
        f"{block(components['tool_execution_terms'])} AND "
        f"{block(support)}"
    )


def combined_agent_query_block(config: dict[str, Any]) -> str:
    return f"({explicit_query_block(config)} OR ({implicit_query_block(config)}))"


def domain_queries(config: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Backward-compatible combined queries, one per biological domain."""
    agent = combined_agent_query_block(config)
    for domain in config["domain_order"]:
        yield domain, f"{agent} AND {block(config['domain_groups'][domain])}"


def retrieval_mode_queries(config: dict[str, Any]) -> Iterator[tuple[str, str, str]]:
    """Optional separate query modes for collectors that support mode labels."""
    explicit = explicit_query_block(config)
    implicit = implicit_query_block(config)
    for domain in config["domain_order"]:
        domain_block = block(config["domain_groups"][domain])
        yield "explicit_agents", domain, f"{explicit} AND {domain_block}"
        yield "implicit_functional_agents", domain, f"({implicit}) AND {domain_block}"


def europe_domain_queries(config: dict[str, Any]) -> Iterator[tuple[str, str]]:
    components = config["implicit_agent_components"]
    explicit = fielded_block(config["explicit_agent_terms"], "TITLE_ABS")
    support_terms: list[str] = []
    for group in config["implicit_agent_rules"]["support_groups"]:
        support_terms.extend(components[group])
    implicit = (
        f"{fielded_block(components['language_model_terms'], 'TITLE_ABS')} AND "
        f"{fielded_block(components['tool_execution_terms'], 'TITLE_ABS')} AND "
        f"{fielded_block(support_terms, 'TITLE_ABS')}"
    )
    date = f"FIRST_PDATE:[{config['date_from']} TO {config['date_until']}]"
    for domain in config["domain_order"]:
        domain_block = fielded_block(config["domain_groups"][domain], "TITLE_ABS")
        yield domain, f"({explicit} OR ({implicit})) AND {domain_block} AND {date}"


def pubmed_query(query: str, config: dict[str, Any]) -> str:
    tokens = re.findall(r'"[^"]+"|\bAND\b|\bOR\b|\(|\)|[^\s()]+', query)
    fielded = [
        token if token in {"AND", "OR", "(", ")"} else f"{token}[Title/Abstract]"
        for token in tokens
    ]
    start = config["date_from"].replace("-", "/")
    end = config["date_until"].replace("-", "/")
    return " ".join(fielded) + f' AND ("{start}"[Date - Publication] : "{end}"[Date - Publication])'


def record_blob(row: Mapping[str, Any]) -> str:
    return norm_text(" ".join(clean(row.get(field, "")) for field in ("title", "abstract", "keywords")))


def term_pattern(term: Any) -> re.Pattern[str] | None:
    normalized = norm_text(term)
    if not normalized:
        return None
    tokens = normalized.split()
    escaped = [re.escape(token) for token in tokens]
    pluralizable = {
        "agent": "agents?",
        "system": "systems?",
        "framework": "frameworks?",
        "workflow": "workflows?",
        "model": "models?",
        "tool": "tools?",
        "database": "databases?",
    }
    if tokens[-1] in pluralizable:
        escaped[-1] = pluralizable[tokens[-1]]
    return re.compile(r"\b" + r"\s+".join(escaped) + r"\b", flags=re.IGNORECASE)


def find_hits(blob: str, terms: Iterable[Any]) -> list[str]:
    text = norm_text(blob)
    hits: list[str] = []
    for term in unique_terms(terms):
        pattern = term_pattern(term)
        if pattern is not None and pattern.search(text):
            hits.append(term)
    return hits


def implicit_component_hits(blob: str, config: dict[str, Any]) -> dict[str, list[str]]:
    components = config["implicit_agent_components"]
    return {group: find_hits(blob, components[group]) for group in IMPLICIT_GROUPS}


def implicit_rule_passes(hits: dict[str, list[str]], config: dict[str, Any]) -> bool:
    rules = config["implicit_agent_rules"]
    required_ok = all(bool(hits[group]) for group in rules["required_groups"])
    groups_hit = sum(bool(hits[group]) for group in IMPLICIT_GROUPS)
    support_ok = any(bool(hits[group]) for group in rules["support_groups"])
    return required_ok and support_ok and groups_hit >= int(rules["minimum_groups_hit"])


def validate_for_query_domain(
    row: dict[str, Any],
    config: dict[str, Any],
    query_domain: str,
) -> dict[str, Any]:
    """Apply: (explicit OR sufficient implicit components) AND exact biology domain."""
    blob = record_blob(row)
    explicit_hits = find_hits(blob, config["explicit_agent_terms"])
    implicit_hits = implicit_component_hits(blob, config)
    implicit_pass = implicit_rule_passes(implicit_hits, config)

    query_domain_hits = find_hits(blob, config["domain_groups"][query_domain])
    all_domain_hits = {
        domain: hits
        for domain, terms in config["domain_groups"].items()
        if (hits := find_hits(blob, terms))
    }

    explicit_path = bool(explicit_hits)
    agent_evidence = explicit_path or implicit_pass
    domain_evidence = bool(query_domain_hits)
    keep = agent_evidence and domain_evidence

    groups_hit = [group for group in IMPLICIT_GROUPS if implicit_hits[group]]

    if keep and explicit_path and implicit_pass:
        route, confidence = "EXPLICIT_AND_IMPLICIT_AGENT_DOMAIN", "HIGH"
    elif keep and explicit_path:
        route, confidence = "EXPLICIT_AGENT_DOMAIN", "HIGH"
    elif keep:
        route, confidence = "IMPLICIT_FUNCTIONAL_AGENT_DOMAIN", "MEDIUM_HIGH"
    elif not domain_evidence:
        route, confidence = "NO_QUERY_DOMAIN_EVIDENCE", "LOW"
    elif not explicit_path and not implicit_pass:
        route, confidence = "INSUFFICIENT_AGENT_EVIDENCE", "LOW"
    else:
        route, confidence = "EXCLUDE_AT_RETRIEVAL", "LOW"

    if keep:
        reason = ""
    elif not domain_evidence:
        reason = "NO_QUERY_DOMAIN_TERM"
    else:
        reason = "NO_EXPLICIT_OR_SUFFICIENT_IMPLICIT_AGENT_EVIDENCE"

    return {
        "search_logic_keep": keep,
        "retrieval_status": "AGENT_DOMAIN_CANDIDATE" if keep else "EXCLUDE_AT_RETRIEVAL",
        "retrieval_route": route,
        "retrieval_confidence": confidence,
        "reject_reason": reason,
        "query_domain": query_domain,
        "explicit_agent_hits": "; ".join(explicit_hits),
        "explicit_agent_hit_count": len(explicit_hits),
        "implicit_language_model_hits": "; ".join(implicit_hits["language_model_terms"]),
        "implicit_tool_execution_hits": "; ".join(implicit_hits["tool_execution_terms"]),
        "implicit_knowledge_grounding_hits": "; ".join(implicit_hits["knowledge_grounding_terms"]),
        "implicit_planning_control_hits": "; ".join(implicit_hits["planning_control_terms"]),
        "implicit_state_memory_hits": "; ".join(implicit_hits["state_memory_terms"]),
        "implicit_repair_verification_hits": "; ".join(implicit_hits["repair_verification_terms"]),
        "implicit_component_groups_hit": "; ".join(groups_hit),
        "implicit_component_group_count": len(groups_hit),
        "query_domain_hits": "; ".join(query_domain_hits),
        "query_domain_hit_count": len(query_domain_hits),
        "matched_domains": "; ".join(all_domain_hits),
        "matched_domain_count": len(all_domain_hits),
        "domain_hit_count_total": sum(len(hits) for hits in all_domain_hits.values()),
        "domain_hits_json": json.dumps(all_domain_hits, ensure_ascii=False, sort_keys=True),
    }


def full_agent_screen(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    blob = record_blob(row)
    groups = config["full_agent_verification_terms"]
    goal = find_hits(blob, groups["goal_directed_control"])
    state = find_hits(blob, groups["stateful_tool_execution"])
    support = find_hits(blob, groups["inspectable_scientific_support"])
    repair = find_hits(blob, groups.get("repair_and_verification", []))
    suggested = sum(bool(value) for value in (goal, state, support))
    priority = ["LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH"][suggested]
    return {
        "abstract_goal_control_hits": "; ".join(goal),
        "abstract_stateful_execution_hits": "; ".join(state),
        "abstract_inspectable_support_hits": "; ".join(support),
        "abstract_repair_verification_hits": "; ".join(repair),
        "full_text_review_priority": priority,
        "agentic_status_preliminary": "NEEDS_FULL_TEXT_REVIEW",
    }


def classify_full_agentic(goal: str, state: str, support: str) -> str:
    values = [clean(value).upper() for value in (goal, state, support)]
    if any(value not in FINAL_CODES for value in values):
        raise ValueError("Final codes must be D, A, U, NR, or NA")
    if values == ["D", "D", "D"]:
        return "FULL_AGENTIC"
    if "A" in values:
        return "NOT_FULL_AGENTIC"
    if "U" in values or "NR" in values:
        return "UNCLEAR_OR_NOT_REPORTED"
    return "NOT_FULL_AGENTIC"


def stable_id(source: str, domain: str, query: str) -> str:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    return f"{source}-AGENT-CANDIDATES-{domain}-{digest}".upper().replace("_", "-")


def write_rows(
    path: str | Path,
    rows: Iterable[dict[str, Any]],
    fields: list[str] = BASE_FIELDS,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
