import pandas as pd
import re
import os
import json
import csv

# 1. Configuration
ART_DIR = "./output"  # Folder with your parquet files
ANSWER_PATH = "./answers/answer2.txt"

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

# Run and Export
df_audit = audit_traceability(ANSWER_PATH)
df_audit.to_excel("traceability_audit_results.xlsx", index=False)
print("Traceability audit exported to traceability_audit_results.xlsx")