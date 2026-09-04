from __future__ import annotations

import argparse
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd
import requests

from common import (
    BASE_FIELDS,
    RAW,
    clean,
    ensure_dirs,
    load_config,
    norm_arxiv,
    norm_text,
    stable_id,
    unique_terms,
    validate_for_query_domain,
    write_rows,setup_logger
)
from http_helpers import request_with_retry


URL = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Preserve the complete date in chunk and final CSV files. This supports exact
# date validation when date_from/date_until fall within the same calendar year.
OUTPUT_FIELDS = list(BASE_FIELDS)
if "published_date" not in OUTPUT_FIELDS:
    OUTPUT_FIELDS.append("published_date")

logger = setup_logger('./logs/', 'search_arxiv')
# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def parse_config_date(value: Any, field_name: str) -> date:
    text = clean(value)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must use YYYY-MM-DD format; received {text!r}"
        ) from error


def parse_atom_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def in_date_range(
    published_date: date | None,
    date_from: date,
    date_until: date,
) -> bool:
    return (
        published_date is not None
        and date_from <= published_date <= date_until
    )


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"true", "1", "yes", "y"}


def chunks(values: Iterable[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise ValueError("Chunk size must be positive")

    materialized = list(values)
    for start in range(0, len(materialized), size):
        yield materialized[start : start + size]


def arxiv_term(value: Any) -> str:
    """Search one exact phrase in title OR abstract."""
    value = " ".join(clean(value).replace('"', " ").split())
    if not value:
        raise ValueError("Cannot create an arXiv term from an empty value")
    return f'(ti:"{value}" OR abs:"{value}")'


def arxiv_or_block(values: Iterable[Any]) -> str:
    terms = [arxiv_term(value) for value in unique_terms(values)]
    if not terms:
        raise ValueError("Cannot create an empty arXiv query block")
    return "(" + " OR ".join(terms) + ")"


def implicit_support_groups(config: dict[str, Any]) -> list[str]:
    rules = config.get("implicit_agent_rules", {})
    return list(
        rules.get(
            "support_groups",
            [
                "knowledge_grounding_terms",
                "planning_control_terms",
                "state_memory_terms",
                "repair_verification_terms",
            ],
        )
    )


def arxiv_settings(config: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("arxiv", {})
    return {
        "batch_size": int(settings.get("batch_size", 25)),
        "max_records": int(settings.get("max_records_per_small_query", 100)),
        "pause_seconds": float(settings.get("pause_seconds", 15.0)),
        "retry_attempts": int(settings.get("max_retry_attempts", 3)),
        "retry_base_wait": float(
            settings.get("retry_base_wait_seconds", 120.0)
        ),
        "cooldown_429": float(
            settings.get("global_cooldown_429_seconds", 900.0)
        ),
        "resume": bool(settings.get("resume", True)),
        "continue_on_error": bool(
            settings.get("continue_on_http_error", True)
        ),
        "explicit_chunk_size": int(settings.get("agent_terms_per_query", 6)),
        "domain_chunk_size": int(settings.get("domain_terms_per_query", 8)),
        "implicit_lm_chunk_size": int(
            settings.get("implicit_language_model_terms_per_query", 5)
        ),
        "implicit_tool_chunk_size": int(
            settings.get("implicit_tool_terms_per_query", 5)
        ),
        # Server retrieval can use LM + tool + domain for high recall. The
        # complete implicit rule, including support groups, is enforced by
        # validate_for_query_domain() after metadata is downloaded.
        "enable_implicit": bool(settings.get("enable_implicit_queries", True)),
    }


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------


def small_queries(
    config: dict[str, Any],
    domain: str,
) -> Iterator[tuple[str, int, int, str]]:
    """Generate explicit and implicit arXiv retrieval routes.

    Explicit route:
        explicit-agent phrase AND current biological-domain phrase.

    Implicit route:
        language-model phrase AND tool-execution phrase
        AND current biological-domain phrase.

    The implicit route intentionally does not require support terms at the
    arXiv server. The full implicit rule is applied locally after retrieval,
    preventing abstracts from being missed simply because only some agentic
    capabilities are reported in the metadata.
    """
    settings = arxiv_settings(config)

    domain_chunks = list(
        chunks(
            unique_terms(config["domain_groups"][domain]),
            settings["domain_chunk_size"],
        )
    )

    explicit_chunks = list(
        chunks(
            unique_terms(config["explicit_agent_terms"]),
            settings["explicit_chunk_size"],
        )
    )

    for agent_number, agent_terms in enumerate(explicit_chunks, start=1):
        for domain_number, domain_terms in enumerate(domain_chunks, start=1):
            query = (
                f"{arxiv_or_block(agent_terms)} AND "
                f"{arxiv_or_block(domain_terms)}"
            )
            yield "explicit_agents", agent_number, domain_number, query

    if not settings["enable_implicit"]:
        return

    components = config.get("implicit_agent_components", {})
    language_model_terms = unique_terms(
        components.get("language_model_terms", [])
    )
    tool_execution_terms = unique_terms(
        components.get("tool_execution_terms", [])
    )

    if not language_model_terms or not tool_execution_terms:
        return

    lm_chunks = list(
        chunks(language_model_terms, settings["implicit_lm_chunk_size"])
    )
    tool_chunks = list(
        chunks(tool_execution_terms, settings["implicit_tool_chunk_size"])
    )

    implicit_number = 0
    for lm_terms in lm_chunks:
        for tool_terms in tool_chunks:
            implicit_number += 1
            for domain_number, domain_terms in enumerate(
                domain_chunks,
                start=1,
            ):
                query = (
                    f"{arxiv_or_block(lm_terms)} AND "
                    f"{arxiv_or_block(tool_terms)} AND "
                    f"{arxiv_or_block(domain_terms)}"
                )
                yield (
                    "implicit_functional_agents",
                    implicit_number,
                    domain_number,
                    query,
                )


# ---------------------------------------------------------------------------
# Atom parsing
# ---------------------------------------------------------------------------


def parse_page(
    content: bytes,
    search_id: str,
    query_mode: str,
    domain: str,
    config: dict[str, Any],
    date_from: date,
    date_until: date,
) -> tuple[list[dict[str, Any]], int, date | None, date | None]:
    """Parse one Atom page and retain records in the precise date interval."""
    root = ET.fromstring(content)
    entries = root.findall("atom:entry", NS)
    rows: list[dict[str, Any]] = []
    raw_dates: list[date] = []

    for entry in entries:
        published_text = clean(entry.findtext("atom:published", "", NS))
        published_date = parse_atom_date(published_text)

        if published_date is not None:
            raw_dates.append(published_date)

        if not in_date_range(published_date, date_from, date_until):
            continue

        title = " ".join(
            clean(entry.findtext("atom:title", "", NS)).split()
        )
        abstract = " ".join(
            clean(entry.findtext("atom:summary", "", NS)).split()
        )
        url = clean(entry.findtext("atom:id", "", NS))
        arxiv_id = norm_arxiv(url)

        authors = "; ".join(
            name
            for name in (
                clean(author.findtext("atom:name", "", NS))
                for author in entry.findall("atom:author", NS)
            )
            if name
        )
        keywords = "; ".join(
            term
            for term in (
                clean(category.attrib.get("term", ""))
                for category in entry.findall("atom:category", NS)
            )
            if term
        )
        doi = clean(entry.findtext("arxiv:doi", "", NS))

        row: dict[str, Any] = {
            "search_id": search_id,
            "query_mode": query_mode,
            "query_domain": domain,
            "source": "arXiv",
            "source_id": arxiv_id,
            "title": title,
            "authors": authors,
            "year": str(published_date.year),
            "published_date": published_date.isoformat(),
            "doi": doi,
            "pmid": "",
            "pmcid": "",
            "arxiv_id": arxiv_id,
            "url": url,
            "abstract": abstract,
            "keywords": keywords,
            "publication_type": "preprint",
            "venue": "arXiv",
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

    oldest = min(raw_dates) if raw_dates else None
    newest = max(raw_dates) if raw_dates else None
    return rows, len(entries), oldest, newest


# ---------------------------------------------------------------------------
# Deduplication and revalidation
# ---------------------------------------------------------------------------


def record_key(row: dict[str, Any]) -> str:
    arxiv_id = norm_arxiv(
        row.get("arxiv_id", "") or row.get("source_id", "")
    )
    if arxiv_id:
        return f"ARXIV:{arxiv_id}"
    return f"TITLE:{norm_text(row.get('title', ''))}"


def row_quality(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(bool(clean(row.get("published_date")))),
        len(clean(row.get("abstract", ""))),
        len(clean(row.get("authors", ""))),
        len(clean(row.get("keywords", ""))),
    )


def merge_query_modes(existing: Any, incoming: Any) -> str:
    modes: list[str] = []
    for value in (existing, incoming):
        for mode in clean(value).split("; "):
            if mode and mode not in modes:
                modes.append(mode)
    return "; ".join(modes)


def merge_duplicate(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if row_quality(incoming) > row_quality(existing):
        primary, secondary = incoming.copy(), existing
    else:
        primary, secondary = existing.copy(), incoming

    for field in OUTPUT_FIELDS:
        if not clean(primary.get(field)) and clean(secondary.get(field)):
            primary[field] = secondary[field]

    primary["query_mode"] = merge_query_modes(
        existing.get("query_mode"),
        incoming.get("query_mode"),
    )
    primary["title_normalized"] = norm_text(primary.get("title"))
    return primary


def deduplicate_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}

    for row in rows:
        key = record_key(row)
        if key in {"TITLE:", "ARXIV:"}:
            continue

        if key not in best:
            best[key] = row
        else:
            best[key] = merge_duplicate(best[key], row)

    return list(best.values())


def split_rows(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in rows:
        if as_bool(row.get("search_logic_keep")):
            kept.append(row)
        else:
            rejected.append(row)

    return kept, rejected


def parse_stored_publication_date(row: dict[str, Any]) -> date | None:
    published_date = parse_atom_date(row.get("published_date"))
    if published_date is not None:
        return published_date

    # Legacy chunk fallback. A year-only record is accepted only where the
    # entire year lies inside the configured interval. New chunks always store
    # the precise publication date.
    year_text = clean(row.get("year"))
    if re_full_year(year_text):
        return date(int(year_text), 1, 1)
    return None


def re_full_year(value: str) -> bool:
    return len(value) == 4 and value.isdigit()


def read_all_domain_chunks(
    chunk_directory: Path,
    domain: str,
    config: dict[str, Any],
    date_from: date,
    date_until: date,
) -> list[dict[str, Any]]:
    """Read kept and rejected chunks, then revalidate every unique record."""
    rows: list[dict[str, Any]] = []

    for path in sorted(chunk_directory.glob("*.csv")):
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
        if frame.empty:
            continue

        for row in frame.to_dict("records"):
            stored_date = parse_stored_publication_date(row)

            if clean(row.get("published_date")):
                if not in_date_range(stored_date, date_from, date_until):
                    continue
            else:
                # Conservative compatibility for old year-only chunks.
                try:
                    row_year = int(clean(row.get("year")))
                except ValueError:
                    continue
                if not (date_from.year <= row_year <= date_until.year):
                    continue

            row.update(
                validate_for_query_domain(
                    row=row,
                    config=config,
                    query_domain=domain,
                )
            )
            row["query_domain"] = domain
            rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Resume fingerprint
# ---------------------------------------------------------------------------


def domain_config_fingerprint(
    config: dict[str, Any],
    domain: str,
) -> str:
    payload = {
        "date_from": config["date_from"],
        "date_until": config["date_until"],
        "explicit_agent_terms": config.get("explicit_agent_terms", []),
        "implicit_agent_components": config.get(
            "implicit_agent_components",
            {},
        ),
        "implicit_agent_rules": config.get("implicit_agent_rules", {}),
        "domain_terms": config["domain_groups"][domain],
        "arxiv_settings": config.get("arxiv", {}),
        "collector_version": 3,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def final_output_is_current(
    final_kept: Path,
    final_rejected: Path,
    fingerprint_path: Path,
    expected_fingerprint: str,
) -> bool:
    if not (
        final_kept.exists()
        and final_rejected.exists()
        and fingerprint_path.exists()
    ):
        return False

    actual = clean(fingerprint_path.read_text(encoding="utf-8"))
    return actual == expected_fingerprint


# ---------------------------------------------------------------------------
# Main crawler
# ---------------------------------------------------------------------------


def run(config: dict[str, Any]) -> None:
    ensure_dirs()
    settings = arxiv_settings(config)

    date_from = parse_config_date(config["date_from"], "date_from")
    date_until = parse_config_date(config["date_until"], "date_until")
    if date_from > date_until:
        raise ValueError("date_from cannot be later than date_until")

    batch_size = settings["batch_size"]
    maximum_records = settings["max_records"]
    if batch_size <= 0 or maximum_records <= 0:
        raise ValueError(
            "batch_size and max_records_per_small_query must be positive"
        )

    output_directory = RAW / "arxiv"
    output_directory.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "FEV-domain-search/3.0 "
                f"(mailto:{clean(config.get('contact_email', ''))})"
            ),
            "Accept": "application/atom+xml",
        }
    )

    total_domains = len(config["domain_order"])

    for domain_index, domain in enumerate(
        config["domain_order"],
        start=1,
    ):
        chunk_directory = output_directory / "chunks" / domain
        chunk_directory.mkdir(parents=True, exist_ok=True)

        final_kept = output_directory / f"{domain}.csv"
        final_rejected = output_directory / f"{domain}_rejected.csv"
        fingerprint_path = output_directory / f"{domain}.config.sha256"
        fingerprint = domain_config_fingerprint(config, domain)

        if settings["resume"] and final_output_is_current(
            final_kept,
            final_rejected,
            fingerprint_path,
            fingerprint,
        ):
            print(
                f"DOMAIN {domain_index}/{total_domains} {domain}: "
                "current configuration already completed, skipping"
            )
            continue

        queries = list(small_queries(config, domain))
        explicit_count = sum(mode == "explicit_agents" for mode, *_ in queries)
        implicit_count = sum(
            mode == "implicit_functional_agents" for mode, *_ in queries
        )

        logger.info(f"\nDOMAIN {domain_index}/{total_domains}: {domain}")
        logger.info(
            f"Date range: {date_from.isoformat()} to {date_until.isoformat()}"
        )
        logger.info(
            f"Small queries: {len(queries)} "
            f"(explicit={explicit_count}, implicit={implicit_count})"
        )

        for sequence, (
            query_mode,
            agent_chunk,
            domain_chunk,
            query,
        ) in enumerate(queries, start=1):
            search_id = stable_id(
                "arxiv",
                domain,
                (
                    f"v3|{query_mode}|{date_from.isoformat()}|"
                    f"{date_until.isoformat()}|{agent_chunk}|"
                    f"{domain_chunk}|{query}"
                ),
            )
            chunk_kept = chunk_directory / f"{search_id}.csv"
            chunk_rejected = chunk_directory / f"{search_id}_rejected.csv"

            if (
                settings["resume"]
                and chunk_kept.exists()
                and chunk_rejected.exists()
            ):
                logger.info(
                    f"[{domain} {sequence}/{len(queries)}] "
                    f"{query_mode}: completed chunk, skipping"
                )
                continue

            chunk_rows: list[dict[str, Any]] = []

            try:
                for start in range(0, maximum_records, batch_size):
                    logger.info(
                        f"[{domain} {sequence}/{len(queries)}] "
                        f"mode={query_mode}; start={start}"
                    )

                    response = request_with_retry(
                        session,
                        URL,
                        params={
                            "search_query": query,
                            "start": start,
                            "max_results": batch_size,
                            "sortBy": "submittedDate",
                            "sortOrder": "descending",
                        },
                        attempts=settings["retry_attempts"],
                        base_wait=settings["retry_base_wait"],
                        cooldown_429=settings["cooldown_429"],
                    )

                    (
                        page_rows,
                        raw_entry_count,
                        oldest_date,
                        newest_date,
                    ) = parse_page(
                        content=response.content,
                        search_id=search_id,
                        query_mode=query_mode,
                        domain=domain,
                        config=config,
                        date_from=date_from,
                        date_until=date_until,
                    )

                    if raw_entry_count == 0:
                        break

                    chunk_rows.extend(page_rows)

                    logger.info(
                        f"[{domain} {sequence}/{len(queries)}] "
                        f"raw dates={oldest_date}..{newest_date}; "
                        f"raw entries={raw_entry_count}; "
                        f"in-range rows={len(page_rows)}"
                    )

                    # Stop only if the newest record on the page is already
                    # older than date_from. This means the whole page is old.
                    if newest_date is not None and newest_date < date_from:
                        logger.info(
                            f"[{domain} {sequence}/{len(queries)}] "
                            "entire page predates date_from; stopping query"
                        )
                        break

                    if raw_entry_count < batch_size:
                        break

                    time.sleep(settings["pause_seconds"])

                chunk_rows = deduplicate_rows(chunk_rows)
                kept_rows, rejected_rows = split_rows(chunk_rows)

                write_rows(chunk_kept, kept_rows, OUTPUT_FIELDS)
                write_rows(chunk_rejected, rejected_rows, OUTPUT_FIELDS)

                logger.info(
                    f"[{domain} {sequence}/{len(queries)}] "
                    f"unique kept={len(kept_rows)}, "
                    f"unique rejected={len(rejected_rows)}"
                )
                time.sleep(settings["pause_seconds"])

            except KeyboardInterrupt:
                logger.info("\nInterrupted. Completed chunks are preserved.")
                raise
            except Exception as error:
                logger.info(f"[WARNING] {search_id}: {error!r}")
                if not settings["continue_on_error"]:
                    raise

        # Re-read BOTH kept and rejected chunk files. Every record is then
        # revalidated under the current common.py and current configuration.
        domain_rows = read_all_domain_chunks(
            chunk_directory=chunk_directory,
            domain=domain,
            config=config,
            date_from=date_from,
            date_until=date_until,
        )
        domain_rows = deduplicate_rows(domain_rows)

        # Revalidate once more after duplicate merging so the final status is
        # based on the most complete title/abstract/keyword record.
        for row in domain_rows:
            row.update(
                validate_for_query_domain(
                    row=row,
                    config=config,
                    query_domain=domain,
                )
            )

        kept_rows, rejected_rows = split_rows(domain_rows)

        # Exact final date assertion using published_date, not year alone.
        invalid_rows = []
        for row in kept_rows:
            stored_date = parse_atom_date(row.get("published_date"))
            if not in_date_range(stored_date, date_from, date_until):
                invalid_rows.append(row)

        if invalid_rows:
            raise AssertionError(
                f"Exact date filtering failed for {len(invalid_rows)} "
                f"kept rows in {domain}"
            )

        write_rows(final_kept, kept_rows, OUTPUT_FIELDS)
        write_rows(final_rejected, rejected_rows, OUTPUT_FIELDS)
        fingerprint_path.write_text(fingerprint + "\n", encoding="utf-8")

        logger.info(
            f"\n{domain}: final unique kept={len(kept_rows)}, "
            f"final unique rejected={len(rejected_rows)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search arXiv using explicit and implicit functional-agent "
            "routes, enforce an exact publication-date interval, resume "
            "safely, revalidate all chunks, and deduplicate by arXiv ID."
        )
    )
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    run(load_config(arguments.config))


if __name__ == "__main__":
    main()
