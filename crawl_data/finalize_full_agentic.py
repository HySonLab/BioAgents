from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from common import DATA, classify_full_agentic

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, default=DATA / "explicit_agent_domain_candidates_deduplicated_sorted.csv"); args = parser.parse_args()
    frame = pd.read_csv(args.input, dtype=str, keep_default_na=False).fillna("")
    frame["full_agentic_status_final"] = frame.apply(lambda row: classify_full_agentic(row["criterion_goal_directed_control_final"], row["criterion_stateful_tool_execution_final"], row["criterion_inspectable_support_final"]), axis=1)
    frame["include_in_full_agent_sensitivity_analysis"] = frame["full_agentic_status_final"].eq("FULL_AGENTIC")
    frame.to_csv(args.input, index=False)
    frame[frame["full_agentic_status_final"].eq("FULL_AGENTIC")].to_csv(DATA / "confirmed_full_agentic_systems.csv", index=False)
    print(frame["full_agentic_status_final"].value_counts(dropna=False).to_string())
if __name__ == "__main__": main()
