from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from common import (
    BASE_FIELDS,
    RAW,
    clean,
    ensure_dirs,
    load_config,
    norm_doi,
    norm_text,
    stable_id,
    unique_terms,
    validate_for_query_domain,
    write_rows,
)
from http_helpers import request_with_retry


BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"true", "1", "yes", "y"}


def chunks(values: Iterable[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("Chunk size must be positive")
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def quote_pubmed_term(value: Any) -> str:
    text = clean(value).replace('"', " ")
    text = " ".join(text.split())
    return f'"{text}"[Title/Abstract]'


def pubmed_or_block(values: Iterable[Any]) -> str:
    terms = [quote_pubmed_term(value) for value in unique_terms(values)]
    if not terms:
        raise ValueError("Cannot create an empty PubMed term block")
    return "(" + " OR ".join(terms) + ")"


def pubmed_query_settings(config: dict[str, Any]) -> dict[str, int]:
    settings = config.get("pubmed", {})
    return {
        "explicit_terms_per_query": int(
            settings.get("explicit_terms_per_query", 8)
        ),
        "language_model_terms_per_query": int(
            settings.get("language_model_terms_per_query", 6)
        ),
        "tool_terms_per_query": int(
            settings.get("tool_terms_per_query", 6)
        ),
        "support_terms_per_query": int(
            settings.get("support_terms_per_query", 8)
        ),
        "domain_terms_per_query": int(
            settings.get("domain_terms_per_query", 8)
        ),
        "fetch_batch_size": int(settings.get("fetch_batch_size", 200)),
    }


def support_terms(config: dict[str, Any]) -> list[str]:
    components = config["implicit_agent_components"]
    rules = config.get("implicit_agent_rules", {})
    groups = rules.get(
        "support_groups",
        [
            "knowledge_grounding_terms",
            "planning_control_terms",
            "state_memory_terms",
            "repair_verification_terms",
        ],
    )

    output: list[str] = []
    for group in groups:
        output.extend(components.get(group, []))
    return unique_terms(output)


def small_queries(
    config: dict[str, Any],
    domain: str,
) -> Iterable[tuple[str, int, str]]:
    """Yield short explicit and implicit PubMed queries.

    Explicit route:
        explicit agent term AND biological domain term.

    Implicit route:
        language model term AND tool term AND support term
        AND biological domain term.

    Local validation in common.py remains the final inclusion gate.
    """
    sizes = pubmed_query_settings(config)
    domain_chunks = list(
        chunks(
            unique_terms(config["domain_groups"][domain]),
            sizes["domain_terms_per_query"],
        )
    )

    sequence = 0

    for agent_terms in chunks(
        unique_terms(config["explicit_agent_terms"]),
        sizes["explicit_terms_per_query"],
    ):
        for domain_terms in domain_chunks:
            sequence += 1
            query = (
                f"{pubmed_or_block(agent_terms)} AND "
                f"{pubmed_or_block(domain_terms)}"
            )
            yield "explicit_agents", sequence, query

    components = config["implicit_agent_components"]
    lm_chunks = list(
        chunks(
            unique_terms(components["language_model_terms"]),
            sizes["language_model_terms_per_query"],
        )
    )
    tool_chunks = list(
        chunks(
            unique_terms(components["tool_execution_terms"]),
            sizes["tool_terms_per_query"],
        )
    )
    support_chunks = list(
        chunks(
            support_terms(config),
            sizes["support_terms_per_query"],
        )
    )

    for lm_terms in lm_chunks:
        for tool_terms in tool_chunks:
            for functional_terms in support_chunks:
                for domain_terms in domain_chunks:
                    sequence += 1
                    query = (
                        f"{pubmed_or_block(lm_terms)} AND "
                        f"{pubmed_or_block(tool_terms)} AND "
                        f"{pubmed_or_block(functional_terms)} AND "
                        f"{pubmed_or_block(domain_terms)}"
                    )
                    yield "implicit_functional_agents", sequence, query


def xml_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def publication_year(article: ET.Element | None) -> str:
    if article is None:
        return ""

    year = clean(article.findtext("Journal/JournalIssue/PubDate/Year"))
    if year:
        return year[:4]

    medline_date = clean(
        article.findtext("Journal/JournalIssue/PubDate/MedlineDate")
    )
    match = re.search(r"\b(?:19|20)\d{2}\b", medline_date)
    return match.group(0) if match else ""


def parse_page(
    content: bytes,
    search_id: str,
    query_mode: str,
    domain: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    root = ET.fromstring(content)
    rows: list[dict[str, Any]] = []

    for item in root.findall("./PubmedArticle"):
        citation = item.find("./MedlineCitation")
        article = item.find("./MedlineCitation/Article")
        pmid = clean(item.findtext("./MedlineCitation/PMID"))

        title = xml_text(article.find("ArticleTitle") if article is not None else None)
        abstract = " ".join(
            xml_text(node)
            for node in (
                article.findall("Abstract/AbstractText")
                if article is not None
                else []
            )
            if xml_text(node)
        )
        authors = "; ".join(
            " ".join(
                part
                for part in (
                    clean(author.findtext("ForeName")),
                    clean(author.findtext("LastName")),
                )
                if part
            )
            for author in (
                article.findall("AuthorList/Author")
                if article is not None
                else []
            )
            if clean(author.findtext("ForeName"))
            or clean(author.findtext("LastName"))
        )

        doi = ""
        pmcid = ""
        for identifier in item.findall("./PubmedData/ArticleIdList/ArticleId"):
            kind = clean(identifier.attrib.get("IdType")).lower()
            if kind == "doi":
                doi = norm_doi(identifier.text)
            elif kind == "pmc":
                pmcid = clean(identifier.text)

        keywords = "; ".join(
            clean(keyword.text)
            for keyword in item.findall("./MedlineCitation/KeywordList/Keyword")
            if clean(keyword.text)
        )
        publication_types = "; ".join(
            clean(node.text)
            for node in (
                article.findall("PublicationTypeList/PublicationType")
                if article is not None
                else []
            )
            if clean(node.text)
        )

        row: dict[str, Any] = {
            "search_id": search_id,
            "query_mode": query_mode,
            "query_domain": domain,
            "source": "PubMed",
            "source_id": pmid,
            "title": title,
            "authors": authors,
            "year": publication_year(article),
            "doi": doi,
            "pmid": pmid,
            "pmcid": pmcid,
            "arxiv_id": "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "abstract": abstract,
            "keywords": keywords,
            "publication_type": publication_types or "article",
            "venue": clean(article.findtext("Journal/Title") if article is not None else ""),
            "title_normalized": norm_text(title),
        }
        row.update(
            validate_for_query_domain(
                row=row,
                config=config,
                query_domain=domain,
            )
        )
        rows.append(row)

    return rows


def record_key(row: dict[str, Any]) -> str:
    pmid = clean(row.get("pmid"))
    doi = norm_doi(row.get("doi"))
    title = norm_text(row.get("title"))

    if pmid:
        return f"PMID:{pmid}"
    if doi:
        return f"DOI:{doi}"
    return f"TITLE:{title}"


def record_quality(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        len(clean(row.get("abstract"))),
        len(clean(row.get("authors"))),
        len(clean(row.get("keywords"))),
    )


def deduplicate_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}

    for row in rows:
        key = record_key(row)
        if key == "TITLE:":
            continue

        existing = best.get(key)
        if existing is None or record_quality(row) > record_quality(existing):
            best[key] = row

    return list(best.values())


def read_chunk_rows(
    chunk_directory: Path,
    domain: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path in sorted(chunk_directory.glob("*.csv")):
        if path.name.endswith("_rejected.csv"):
            continue

        try:
            frame = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
            ).fillna("")
        except pd.errors.EmptyDataError:
            continue

        if "query_domain" not in frame.columns:
            continue

        frame = frame[frame["query_domain"].eq(domain)]
        for row in frame.to_dict("records"):
            row.update(
                validate_for_query_domain(
                    row=row,
                    config=config,
                    query_domain=domain,
                )
            )
            rows.append(row)

    return rows


def run(config: dict[str, Any]) -> None:
    ensure_dirs()

    pubmed_settings = config.get("pubmed", {})
    sizes = pubmed_query_settings(config)
    fetch_batch_size = sizes["fetch_batch_size"]
    max_records = int(config.get("max_records_per_query", 10000))
    resume = bool(pubmed_settings.get("resume", True))
    pause_seconds = float(
        pubmed_settings.get(
            "pause_seconds",
            0.12 if config.get("ncbi_api_key") else 0.36,
        )
    )
    retry_attempts = int(pubmed_settings.get("max_retry_attempts", 5))
    retry_base_wait = float(pubmed_settings.get("retry_base_wait_seconds", 10.0))
    cooldown_429 = float(pubmed_settings.get("global_cooldown_429_seconds", 60.0))
    continue_on_error = bool(pubmed_settings.get("continue_on_http_error", True))

    common_params: dict[str, Any] = {
        "db": "pubmed",
        "tool": "FEV_domain_search",
        "email": config["contact_email"],
    }
    if config.get("ncbi_api_key"):
        common_params["api_key"] = config["ncbi_api_key"]

    output_directory = RAW / "pubmed"
    output_directory.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "FEV-domain-search/1.0 "
                f"(mailto:{config['contact_email']})"
            )
        }
    )

    for domain_index, domain in enumerate(config["domain_order"], start=1):
        final_kept = output_directory / f"{domain}.csv"
        final_rejected = output_directory / f"{domain}_rejected.csv"
        chunk_directory = output_directory / "chunks" / domain
        chunk_directory.mkdir(parents=True, exist_ok=True)

        if resume and final_kept.exists() and final_rejected.exists():
            print(
                f"DOMAIN {domain_index}/{len(config['domain_order'])} "
                f"{domain}: completed, skipping",
                flush=True,
            )
            continue

        queries = list(small_queries(config, domain))
        print(
            f"\nDOMAIN {domain_index}/{len(config['domain_order'])}: {domain}",
            flush=True,
        )
        print(f"Small PubMed queries: {len(queries)}", flush=True)

        for query_index, (query_mode, sequence, query) in enumerate(
            queries,
            start=1,
        ):
            search_id = stable_id(
                "pubmed",
                domain,
                (
                    f"{query_mode}|{config['date_from']}|"
                    f"{config['date_until']}|{query}"
                ),
            )
            chunk_kept = chunk_directory / f"{search_id}.csv"
            chunk_rejected = chunk_directory / f"{search_id}_rejected.csv"

            if resume and chunk_kept.exists() and chunk_rejected.exists():
                print(
                    f"[{domain} {query_index}/{len(queries)}] "
                    "completed chunk, skipping",
                    flush=True,
                )
                continue

            rows: list[dict[str, Any]] = []

            try:
                # POST is required because the Boolean expression can exceed
                # practical URL limits when transmitted as a GET parameter.
                search_response = request_with_retry(
                    session,
                    BASE + "/esearch.fcgi",
                    method="POST",
                    data={
                        **common_params,
                        "term": query,
                        "retmode": "json",
                        "retmax": 0,
                        "usehistory": "y",
                        "datetype": "pdat",
                        "mindate": config["date_from"].replace("-", "/"),
                        "maxdate": config["date_until"].replace("-", "/"),
                    },
                    attempts=retry_attempts,
                    base_wait=retry_base_wait,
                    cooldown_429=cooldown_429,
                )
                payload = search_response.json()
                result = payload.get("esearchresult", {})

                if "ERROR" in result:
                    raise RuntimeError(result["ERROR"])

                total = min(int(result.get("count", 0)), max_records)
                query_key = clean(result.get("querykey"))
                web_env = clean(result.get("webenv"))

                print(
                    f"[{domain} {query_index}/{len(queries)}] "
                    f"mode={query_mode}; PubMed matches={total}",
                    flush=True,
                )

                if total and (not query_key or not web_env):
                    raise RuntimeError(
                        "PubMed did not return querykey/WebEnv for usehistory=y"
                    )

                for start in range(0, total, fetch_batch_size):
                    end = min(start + fetch_batch_size, total)
                    print(
                        f"[{domain} {query_index}/{len(queries)}] "
                        f"fetch={start}-{end} of {total}",
                        flush=True,
                    )

                    fetch_response = request_with_retry(
                        session,
                        BASE + "/efetch.fcgi",
                        params={
                            **common_params,
                            "query_key": query_key,
                            "WebEnv": web_env,
                            "retstart": start,
                            "retmax": fetch_batch_size,
                            "retmode": "xml",
                        },
                        attempts=retry_attempts,
                        base_wait=retry_base_wait,
                        cooldown_429=cooldown_429,
                    )
                    rows.extend(
                        parse_page(
                            content=fetch_response.content,
                            search_id=search_id,
                            query_mode=query_mode,
                            domain=domain,
                            config=config,
                        )
                    )
                    time.sleep(pause_seconds)

                rows = deduplicate_rows(rows)
                kept_rows = [
                    row for row in rows if as_bool(row.get("search_logic_keep"))
                ]
                rejected_rows = [
                    row for row in rows if not as_bool(row.get("search_logic_keep"))
                ]

                write_rows(chunk_kept, kept_rows, BASE_FIELDS)
                write_rows(chunk_rejected, rejected_rows, BASE_FIELDS)

                print(
                    f"[{domain} {query_index}/{len(queries)}] "
                    f"unique kept={len(kept_rows)}, "
                    f"rejected={len(rejected_rows)}",
                    flush=True,
                )
                time.sleep(pause_seconds)

            except KeyboardInterrupt:
                print("\nInterrupted. Completed chunks are preserved.")
                raise
            except Exception as error:
                print(f"[WARNING] {search_id}: {error!r}", flush=True)
                if not continue_on_error:
                    raise

        domain_rows = read_chunk_rows(
            chunk_directory=chunk_directory,
            domain=domain,
            config=config,
        )
        domain_rows = deduplicate_rows(domain_rows)

        kept_rows = [
            row for row in domain_rows if as_bool(row.get("search_logic_keep"))
        ]
        rejected_rows = [
            row for row in domain_rows if not as_bool(row.get("search_logic_keep"))
        ]

        write_rows(final_kept, kept_rows, BASE_FIELDS)
        write_rows(final_rejected, rejected_rows, BASE_FIELDS)

        print(
            f"{domain}: final unique kept={len(kept_rows)}, "
            f"rejected after revalidation={len(rejected_rows)}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search PubMed with chunked explicit and implicit agent routes, "
            "POST-based ESearch, date filtering, resume, and deduplication."
        )
    )
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    run(load_config(arguments.config))


if __name__ == "__main__":
    main()
