from pathlib import Path
import pandas as pd

INPUT_FILE = Path("data/review_screening_log.csv")
REPORT_FILE = Path("outputs/screening_validation_errors.csv")
VALID_TITLE_ABSTRACT = {"INCLUDE", "EXCLUDE", "UNCLEAR", "NOT_SCREENED"}
VALID_FULL_TEXT = {"INCLUDE", "EXCLUDE", "UNCLEAR", "NOT_ASSESSED"}
VALID_EXCLUSION_REASONS = {
    "", "NO_BIO_APPLICATION", "NO_WORKFLOW_CAPABILITY",
    "ISOLATED_PREDICTIVE_MODEL", "CONVERSATIONAL_ONLY",
    "INSUFFICIENT_DETAIL", "DUPLICATE", "SUPERSEDED_VERSION",
    "BENCHMARK_OUT_OF_SCOPE", "OTHER"
}

def main():
    df = pd.read_csv(INPUT_FILE, dtype=str).fillna("")
    errors = []
    def add_error(row, field, message):
        errors.append({"record_id": row["record_id"], "field": field, "message": message})
    for _, row in df.iterrows():
        if row["title_abstract_decision"] not in VALID_TITLE_ABSTRACT:
            add_error(row, "title_abstract_decision", "Invalid or blank title/abstract decision.")
        if row["full_text_decision"] not in VALID_FULL_TEXT:
            add_error(row, "full_text_decision", "Invalid or blank full-text decision.")
        if row["primary_exclusion_reason"] not in VALID_EXCLUSION_REASONS:
            add_error(row, "primary_exclusion_reason", "Invalid exclusion reason.")
        if row["full_text_decision"] == "EXCLUDE" and not row["primary_exclusion_reason"]:
            add_error(row, "primary_exclusion_reason", "Excluded full text needs one primary reason.")
        if row["full_text_decision"] == "INCLUDE" and not row["publication_id"]:
            add_error(row, "publication_id", "Included record needs a publication ID.")
        if row["full_text_decision"] == "INCLUDE" and row["system_map"] != "YES" and row["benchmark_map"] != "YES":
            add_error(row, "system_map/benchmark_map", "Included record must contribute to at least one map.")
        if row["duplicate_status"] != "UNIQUE" and row["full_text_decision"] == "INCLUDE":
            add_error(row, "duplicate_status", "Duplicate record should not be independently included.")
    report = pd.DataFrame(errors, columns=["record_id", "field", "message"])
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_FILE, index=False)
    if errors:
        raise SystemExit(f"Validation failed with {len(errors)} errors. See {REPORT_FILE}")
    print("Screening log passed validation.")

if __name__ == "__main__":
    main()
