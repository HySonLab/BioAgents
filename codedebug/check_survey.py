from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


REMOVE_REASON = "Survey, Review, Perspective"


# ============================================================
# 1. BẰNG CHỨNG CHẮC CHẮN TRONG PUBLICATION TYPE
# ============================================================

PUBLICATION_TYPE_PATTERN = re.compile(
    r"""
    (?:^|[;,|/]\s*)
    (?:
        review
        |systematic[\s-]+review
        |scoping[\s-]+review
        |narrative[\s-]+review
        |meta[\s-]*analysis
    )
    (?:$|\s*[;,|/])
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# 2. BẰNG CHỨNG CHẮC CHẮN TRONG TITLE
# ============================================================

TITLE_PATTERN = re.compile(
    r"""
    \b(?:
        systematic[\s-]+review
        |systematic[\s-]+literature[\s-]+review
        |scoping[\s-]+review
        |narrative[\s-]+review
        |literature[\s-]+review
        |integrative[\s-]+review
        |umbrella[\s-]+review
        |rapid[\s-]+review
        |critical[\s-]+review
        |comprehensive[\s-]+review
        |mini[\s-]*review
        |state[\s-]+of[\s-]+the[\s-]+art[\s-]+review
        |review[\s-]+article
        |review[\s-]+of

        |systematic[\s-]+survey
        |literature[\s-]+survey
        |comprehensive[\s-]+survey
        |survey[\s-]+of
        |survey[\s-]+paper
        |survey[\s-]+article

        |perspective[\s-]+article
        |a[\s-]+perspective[\s-]+on
        |perspective[\s-]+on

        |systematic[\s-]+review[\s-]+and[\s-]+meta[\s-]*analysis
        |meta[\s-]*analysis
        |meta[\s-]*synthesis
        |evidence[\s-]+synthesis
    )\b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# 3. ABSTRACT TỰ NÓI RÕ ĐÂY LÀ REVIEW/PERSPECTIVE/SURVEY
# ============================================================

ABSTRACT_DECLARATION_PATTERN = re.compile(
    r"""
    \b(?:
        this[\s-]+
        (?:
            systematic[\s-]+
            |scoping[\s-]+
            |narrative[\s-]+
            |integrative[\s-]+
            |comprehensive[\s-]+
            |critical[\s-]+
            |rapid[\s-]+
            |mini[\s-]*
        )?
        review[\s-]+
        (?:
            summarizes
            |examines
            |discusses
            |explores
            |highlights
            |synthesizes
            |assesses
            |evaluates
            |focuses
            |outlines
        )

        |in[\s-]+this[\s-]+
        (?:
            systematic[\s-]+
            |scoping[\s-]+
            |narrative[\s-]+
            |comprehensive[\s-]+
        )?
        review

        |we[\s-]+conducted[\s-]+a[\s-]+
        (?:
            systematic
            |scoping
            |narrative
            |literature
            |integrative
            |rapid
        )
        [\s-]+review

        |we[\s-]+performed[\s-]+a[\s-]+
        (?:
            systematic
            |scoping
            |narrative
            |literature
            |integrative
            |rapid
        )
        [\s-]+review

        |we[\s-]+systematically[\s-]+review(?:ed)?
        [\s-]+the[\s-]+literature

        |we[\s-]+review(?:ed)?
        [\s-]+the[\s-]+literature

        |this[\s-]+article[\s-]+
        (?:
            reviews
            |surveys
            |synthesizes
            |provides[\s-]+an[\s-]+overview
        )

        |this[\s-]+paper[\s-]+
        (?:
            reviews
            |surveys
            |synthesizes
        )

        |this[\s-]+perspective[\s-]+
        (?:
            examines
            |discusses
            |explores
            |outlines
            |argues
            |considers
        )

        |in[\s-]+this[\s-]+perspective

        |we[\s-]+provide[\s-]+a[\s-]+perspective
        |we[\s-]+offer[\s-]+a[\s-]+perspective

        |this[\s-]+survey[\s-]+
        (?:
            reviews
            |examines
            |summarizes
            |covers
            |presents
            |analyzes
            |analyses
        )

        |in[\s-]+this[\s-]+survey
        |we[\s-]+survey[\s-]+the[\s-]+literature
    )\b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# 4. FALSE POSITIVES
# Nếu match các cụm này thì không dùng abstract để auto-remove
# ============================================================

FALSE_POSITIVE_PATTERN = re.compile(
    r"""
    \b(?:
        cross[\s-]+sectional[\s-]+survey
        |web[\s-]+based[\s-]+survey
        |online[\s-]+survey
        |questionnaire[\s-]+survey
        |participant[\s-]+survey
        |user[\s-]+survey
        |patient[\s-]+survey
        |clinician[\s-]+survey
        |survey[\s-]+respondents?
        |survey[\s-]+participants?
        |survey[\s-]+data
        |survey[\s-]+study
        |survey[\s-]+results?

        |chart[\s-]+review
        |medical[\s-]+record[\s-]+review
        |clinical[\s-]+record[\s-]+review
        |retrospective[\s-]+review
        |manual[\s-]+review
        |human[\s-]+review
        |expert[\s-]+review
        |blinded[\s-]+review
        |peer[\s-]+review
        |peer[\s-]+reviewed
        |reviewed[\s-]+by

        |review[\s-]+agent
        |reviewer[\s-]+agent
        |review[\s-]+module
        |review[\s-]+subagent
        |review[\s-]+workflow
        |review[\s-]+process
        |review[\s-]+step

        |systematic[\s-]+analysis
        |systematic[\s-]+comparison
        |systematic[\s-]+evaluation
        |systematic[\s-]+benchmark
        |systematic[\s-]+benchmarking
        |systematic[\s-]+replication
        |systematic[\s-]+integration
        |systematic[\s-]+testing
        |systematic[\s-]+screening
        |systematic[\s-]+discovery
        |systematic[\s-]+reanalysis
        |systematic[\s-]+approach
        |systematic[\s-]+workflow
        |systematic[\s-]+framework
        |systematic[\s-]+validation

        |patient[\s-]+perspectives?
        |clinician[\s-]+perspectives?
        |user[\s-]+perspectives?
        |from[\s-]+a[\s-]+clinical[\s-]+perspective
        |from[\s-]+a[\s-]+technical[\s-]+perspective
        |from[\s-]+a[\s-]+biological[\s-]+perspective
    )\b
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# 5. UTILITIES
# ============================================================

def clean_text(value: object) -> str:
    if value is None:
        return ""

    return " ".join(str(value).split())


def get_matches(
    pattern: re.Pattern,
    text: str,
) -> list[str]:
    results = []
    seen = set()
    for match in pattern.finditer(text or ""):
        value = clean_text(match.group(0))
        normalized = value.casefold()

        if value and normalized not in seen:
            seen.add(normalized)
            results.append(value)

    return results


def join_matches(matches: list[str]) -> str:
    return "; ".join(matches)


# ============================================================
# 6. CONSERVATIVE CLASSIFICATION
# ============================================================

def classify_certain_only(row: dict) -> dict[str, str]:
    title = clean_text(row.get("title"))
    abstract = clean_text(row.get("abstract"))
    publication_type = clean_text(
        row.get("publication_type")
    )

    publication_type_matches = get_matches(
        PUBLICATION_TYPE_PATTERN,
        publication_type,
    )

    title_matches = get_matches(
        TITLE_PATTERN,
        title,
    )

    abstract_matches = get_matches(
        ABSTRACT_DECLARATION_PATTERN,
        abstract,
    )

    false_positive_matches = get_matches(
        FALSE_POSITIVE_PATTERN,
        f"{title}\n{abstract}",
    )

    # Thứ tự ưu tiên:
    # 1. Publication type chính thức
    # 2. Title gọi rõ article type
    # 3. Abstract tự xác định, nhưng không có false-positive context

    if publication_type_matches:
        return {
            "certain_review_remove": "YES",
            "certain_review_source": "publication_type",
            "certain_review_evidence": join_matches(
                publication_type_matches
            ),
            "certain_review_reason": (
                "Publication metadata explicitly identifies "
                "the article as a review or evidence synthesis."
            ),
        }

    if title_matches:
        return {
            "certain_review_remove": "YES",
            "certain_review_source": "title",
            "certain_review_evidence": join_matches(
                title_matches
            ),
            "certain_review_reason": (
                "The title explicitly identifies the article "
                "as a review, survey, perspective, or "
                "meta-analysis."
            ),
        }

    if abstract_matches and not false_positive_matches:
        return {
            "certain_review_remove": "YES",
            "certain_review_source": "abstract",
            "certain_review_evidence": join_matches(
                abstract_matches
            ),
            "certain_review_reason": (
                "The abstract explicitly self-identifies the "
                "publication as a review, survey, or "
                "perspective article."
            ),
        }

    return {
        "certain_review_remove": "NO",
        "certain_review_source": "",
        "certain_review_evidence": "",
        "certain_review_reason": (
            "No sufficiently certain article-type evidence "
            "was found."
        ),
    }


# ============================================================
# 7. READ AND WRITE CSV
# ============================================================

def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("CSV không có header.")

        required_columns = {
            "title",
            "abstract",
        }

        missing = required_columns - set(
            reader.fieldnames
        )

        if missing:
            raise ValueError(
                "CSV thiếu cột: "
                + ", ".join(sorted(missing))
            )

        return list(reader.fieldnames), list(reader)


def write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        mode="w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# 8. PROCESS FILE
# ============================================================

def process_file(
    input_file: Path,
    output_file: Path,
    removed_file: Path,
) -> None:
    fields, rows = read_csv(input_file)

    added_fields = [
        "certain_review_remove",
        "certain_review_source",
        "certain_review_evidence",
        "certain_review_reason",
    ]

    if "Reason Remove" not in fields:
        fields.insert(0, "Reason Remove")

    for field in added_fields:
        if field not in fields:
            fields.append(field)

    removed_rows = []

    for row_number, row in enumerate(rows, start=2):
        result = classify_certain_only(row)
        row.update(result)

        if result["certain_review_remove"] == "YES":
            row["Reason Remove"] = REMOVE_REASON
            removed_rows.append(row)

            print("=" * 90)
            print("CSV line:", row_number)
            print(
                "Candidate ID:",
                row.get("candidate_record_id", ""),
            )
            print(
                "Title:",
                clean_text(row.get("title")),
            )
            print(
                "Evidence source:",
                result["certain_review_source"],
            )
            print(
                "Evidence:",
                result["certain_review_evidence"],
            )

        else:
            # Không xóa Reason Remove đã tồn tại do lý do khác.
            row.setdefault("Reason Remove", "")

    write_csv(
        output_file,
        fields,
        rows,
    )

    write_csv(
        removed_file,
        fields,
        removed_rows,
    )

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("Total rows:", len(rows))
    print("Certain removals:", len(removed_rows))
    print(
        "Rows retained:",
        len(rows) - len(removed_rows),
    )
    print("Updated file:", output_file)
    print("Removed-only file:", removed_file)


# ============================================================
# 9. COMMAND LINE
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Conservatively identify definite survey, review, "
            "perspective, and meta-analysis publications."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="CSV đầu vào.",
    )

    parser.add_argument(
        "--output",
        default="certain_review_checked.csv",
        help="CSV đầy đủ sau khi cập nhật.",
    )

    parser.add_argument(
        "--removed-output",
        default="certain_review_removed.csv",
        help="CSV chỉ chứa các hàng chắc chắn bị remove.",
    )

    args = parser.parse_args()

    input_file = Path(args.input)

    if not input_file.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file: {input_file}"
        )

    process_file(
        input_file=input_file,
        output_file=Path(args.output),
        removed_file=Path(args.removed_output),
    )


if __name__ == "__main__":
    main()