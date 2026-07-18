import pandas as pd
import re
import os
import json
from pathlib import Path

# Configuration
ART_DIR = "../../output"
ANSWERS_DIR = "./answers"
EXPORT_DIR = "./trace_exports"
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)

# Load all four artefacts
text_units = pd.read_parquet(os.path.join(ART_DIR, "text_units.parquet"))
reports = pd.read_parquet(os.path.join(ART_DIR, "community_reports.parquet"))
entities = pd.read_parquet(os.path.join(ART_DIR, "entities.parquet"))
relationships = pd.read_parquet(os.path.join(ART_DIR, "relationships.parquet"))

if "human_readable_id" not in text_units.columns:
    text_units["human_readable_id"] = text_units.index


# ---------- Statement-citation extraction with block boundaries ----------

def extract_pairs(content: str):
    """Yield (statement, citation, offset). Citations only own prose within their
    own paragraph/bullet block, so meta-prose and uncited recommendations don't
    get attached to the next evidential statement.
    """
    block_break = re.compile(
        r"(?:\n\s*\n)|(?:\n[ \t]*(?:[-*•]|\d+[.)])\s)",
        re.MULTILINE,
    )
    boundaries = [0] + [m.end() for m in block_break.finditer(content)] + [len(content)]
    cite_re = re.compile(r"\[Data:\s*(.*?)\]", re.DOTALL)

    for i in range(len(boundaries) - 1):
        block_start, block_end = boundaries[i], boundaries[i + 1]
        block = content[block_start:block_end]
        last_end = 0
        for m in cite_re.finditer(block):
            stmt = block[last_end:m.start()].strip()
            if stmt:
                yield stmt, m.group(1), block_start + m.start()
            last_end = m.end()


def parse_id_blocks(pattern: str, citation: str) -> list[int]:
    blocks = re.findall(pattern, citation)
    ids, seen = [], set()
    for blk in blocks:
        for x in blk.split(","):
            x = x.strip()
            if x and x.isdigit():
                i = int(x)
                if i not in seen:
                    ids.append(i)
                    seen.add(i)
    return ids


def audit_traceability(file_path: str) -> pd.DataFrame:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    audit_results = []

    for statement, citation, _offset in extract_pairs(content):
        source_ids = parse_id_blocks(r"Sources?\s*\(([\d, ]+)\)", citation)
        report_ids = parse_id_blocks(r"Reports?\s*\(([\d, ]+)\)", citation)
        entity_ids = parse_id_blocks(r"Entit(?:y|ies)\s*\(([\d, ]+)\)", citation)
        rel_ids    = parse_id_blocks(r"Relationships?\s*\(([\d, ]+)\)", citation)

        source_texts, report_texts, entity_texts, rel_texts = [], [], [], []

        for s_id in source_ids:
            chunk = text_units[text_units["human_readable_id"] == s_id]["text"].tolist()
            if chunk:
                source_texts.append(f"SOURCE {s_id}:\n{chunk[0]}")

        for r_id in report_ids:
            rpt = reports[reports["community"] == r_id]["full_content"].tolist()
            if not rpt and "human_readable_id" in reports.columns:
                rpt = reports[reports["human_readable_id"] == r_id]["full_content"].tolist()
            if rpt:
                report_texts.append(f"REPORT {r_id}:\n{rpt[0]}")

        for e_id in entity_ids:
            row = entities[entities["human_readable_id"] == e_id]
            if len(row):
                title = row.iloc[0].get("title", "")
                desc = row.iloc[0].get("description", "")
                entity_texts.append(f"ENTITY {e_id} ({title}):\n{desc}")

        for r_id in rel_ids:
            row = relationships[relationships["human_readable_id"] == r_id]
            if len(row):
                src = row.iloc[0].get("source", "")
                tgt = row.iloc[0].get("target", "")
                desc = row.iloc[0].get("description", "")
                rel_texts.append(f"RELATIONSHIP {r_id} ({src} → {tgt}):\n{desc}")

        audit_results.append({
            "Statement": statement,
            "Source IDs": ", ".join(map(str, source_ids)),
            "Report IDs": ", ".join(map(str, report_ids)),
            "Entity IDs": ", ".join(map(str, entity_ids)),
            "Relationship IDs": ", ".join(map(str, rel_ids)),
            "Source Text": "\n\n".join(source_texts),
            "Report Text": "\n\n".join(report_texts),
            "Entity Text": "\n\n".join(entity_texts),
            "Relationship Text": "\n\n".join(rel_texts),
        })

    return pd.DataFrame(audit_results)


def one_line(s: str) -> str:
    return " ".join(s.split()) if isinstance(s, str) else ""


# ---------- Batch run ----------

QUESTION_TEXT = "Is the statement supported by the evidence?"

answer_files = sorted(Path(ANSWERS_DIR).glob("*.txt"))
if not answer_files:
    raise FileNotFoundError(f"No .txt files found in: {ANSWERS_DIR}")

for answer_path in answer_files:
    print(f"\n=== Processing: {answer_path.name} ===")
    df_audit = audit_traceability(str(answer_path))

    def build_context(row) -> str:
        parts = []
        if str(row["Source Text"]).strip():
            parts.append("=== CITED SOURCES ===\n" + str(row["Source Text"]))
        if str(row["Report Text"]).strip():
            parts.append("=== CITED REPORTS ===\n" + str(row["Report Text"]))
        if str(row["Entity Text"]).strip():
            parts.append("=== CITED ENTITIES ===\n" + str(row["Entity Text"]))
        if str(row["Relationship Text"]).strip():
            parts.append("=== CITED RELATIONSHIPS ===\n" + str(row["Relationship Text"]))
        return "\n\n".join(parts)

    df_ragas = pd.DataFrame({
        "answer": df_audit["Statement"].fillna("").astype(str).apply(one_line),
    })
    df_ragas["question"] = QUESTION_TEXT
    df_ragas["context"]  = df_audit.fillna("").apply(build_context, axis=1)
    df_ragas = df_ragas[df_ragas["answer"].str.strip().ne("")].reset_index(drop=True)
    df_ragas = df_ragas[["question", "answer", "context"]]

    print(f"  total statement-citation pairs: {len(df_ragas)}")

    stem = answer_path.stem
    df_ragas.to_csv(
        Path(EXPORT_DIR) / f"traceability_ragas_{stem}.csv",
        index=False, encoding="utf-8-sig",
    )
    with open(
        Path(EXPORT_DIR) / f"traceability_ragas_{stem}.json",
        "w", encoding="utf-8",
    ) as f:
        json.dump(df_ragas.to_dict(orient="records"), f, ensure_ascii=False, indent=2)