import pandas as pd
import re
import os
import json
import csv

from pathlib import Path

# 1. Configuration
ART_DIR = "../../output"           # Folder with your parquet files
ANSWERS_DIR = "./answers"      # Folder that contains all *.txt files
EXPORT_DIR = "./trace_exports" # Output folder (per input file)

Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

# 2. Load Knowledge Base
text_units = pd.read_parquet(os.path.join(ART_DIR, "text_units.parquet"))
reports = pd.read_parquet(os.path.join(ART_DIR, "community_reports.parquet"))

# Fallback for human_readable_id if column is missing (it uses the index in some versions)
if "human_readable_id" not in text_units.columns:
    text_units["human_readable_id"] = text_units.index


def audit_traceability(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex to capture the statement and its following citation block.
    regex_pattern = r"(.*?)\[Data:\s*(.*?)\]"
    matches = re.findall(regex_pattern, content, re.DOTALL)

    audit_results = []

    for statement, citation in matches:
        # Extract numbers from "Sources (23, 16)" and "Reports (15, 55)"
        def parse_id_blocks(pattern: str, citation: str) -> list[int]:
            blocks = re.findall(pattern, citation)  # <-- collects ALL occurrences
            ids: list[int] = []
            for blk in blocks:
                for x in blk.split(","):
                    x = x.strip()
                    if x:
                        ids.append(int(x))
            # de-duplicate while preserving order
            seen = set()
            out = []
            for i in ids:
                if i not in seen:
                    out.append(i)
                    seen.add(i)
            return out

        source_ids = parse_id_blocks(r"Sources \(([\d, ]+)\)", citation)
        report_ids = parse_id_blocks(r"Reports \(([\d, ]+)\)", citation)

        print("DEBUG:", statement.strip()[:60], "=> sources", source_ids, "reports", report_ids)

        source_texts = []
        report_texts = []

        # Fetch the actual text for Source IDs
        for s_id in source_ids:
            chunk = text_units[text_units["human_readable_id"] == s_id]["text"].tolist()
            if chunk:
                source_texts.append(f"SOURCE {s_id}:\n{chunk[0]}")

        # Fetch the actual text for Report IDs
        for r_id in report_ids:
            rpt = reports[reports["community"] == r_id]["full_content"].tolist()
            if not rpt and "human_readable_id" in reports.columns:
                rpt = reports[reports["human_readable_id"] == r_id]["full_content"].tolist()
            if rpt:
                report_texts.append(f"REPORT {r_id}:\n{rpt[0]}")

        audit_results.append(
            {
                "Statement": statement.strip(),
                "Data Source Number": ", ".join(map(str, source_ids)),
                "Data Source Text": "\n\n".join(source_texts),
                "Report Number": ", ".join(map(str, report_ids)),
                "Community Report Text": "\n\n".join(report_texts),
            }
        )

    return pd.DataFrame(audit_results)


def one_line(s: str) -> str:
    """Collapse all whitespace (incl. newlines) into single spaces for readability."""
    if not isinstance(s, str):
        return ""
    return " ".join(s.split())


# ===== Batch Run + Per-file Export =====
QUESTION_TEXT = "Is the statement supported by the evidence?"

answer_files = sorted(Path(ANSWERS_DIR).glob("*.txt"))
if not answer_files:
    raise FileNotFoundError(f"No .txt files found in: {ANSWERS_DIR}")

for answer_path in answer_files:
    print(f"\n=== Processing: {answer_path.name} ===")

    df_audit = audit_traceability(str(answer_path))

    df_ragas = pd.DataFrame()
    df_ragas["answer"] = df_audit["Statement"].fillna("").astype(str).apply(one_line)
    df_ragas["question"] = QUESTION_TEXT
    df_ragas["context"] = (
        (df_audit["Data Source Text"].fillna("").astype(str) + "\n\n" + df_audit["Community Report Text"].fillna("").astype(str))
        .apply(one_line)
    )

    df_ragas = df_ragas[["question", "answer", "context"]]
    df_ragas = df_ragas[df_ragas["answer"].str.strip().ne("")].reset_index(drop=True)

    stem = answer_path.stem  # e.g., "answer2"
    csv_out = Path(EXPORT_DIR) / f"traceability_ragas_{stem}.csv"
    json_out = Path(EXPORT_DIR) / f"traceability_ragas_{stem}.json"

    df_ragas.to_csv(csv_out, index=False, encoding="utf-8-sig")

    records = df_ragas.to_dict(orient="records")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print("Exported:")
    print(f" - {csv_out}")
    print(f" - {json_out}")