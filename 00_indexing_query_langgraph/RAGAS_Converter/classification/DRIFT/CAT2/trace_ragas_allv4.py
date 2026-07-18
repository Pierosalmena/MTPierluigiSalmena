import pandas as pd
import re
import os
import json
from pathlib import Path

# Configuration
ART_DIR = "../../../../output"
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


# ---------- Robust ID lookup ----------

def _resolve_in_df(df: pd.DataFrame, target_id: int, candidate_cols: list, text_cols: list):
    """Try each candidate column with both int and string variants of target_id.
    Return a dict of the requested text columns if found, else None.
    Silent drops are eliminated: every call either returns a row or returns None
    so the caller can log the miss."""
    for col in candidate_cols:
        if col not in df.columns:
            continue
        for val in (target_id, str(target_id)):
            try:
                match = df[df[col] == val]
            except Exception:
                continue
            if len(match):
                row = match.iloc[0]
                return {k: row.get(k, "") for k in text_cols}
    return None


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

        # Track attached vs dropped for the audit output
        src_attached, src_dropped = [], []
        rep_attached, rep_dropped = [], []
        ent_attached, ent_dropped = [], []
        rel_attached, rel_dropped = [], []

        source_texts, report_texts, entity_texts, rel_texts = [], [], [], []

        for s_id in source_ids:
            rec = _resolve_in_df(text_units, s_id,
                                 candidate_cols=["human_readable_id", "id"],
                                 text_cols=["text"])
            if rec:
                source_texts.append(f"SOURCE {s_id}:\n{rec['text']}")
                src_attached.append(s_id)
            else:
                src_dropped.append(s_id)
                print(f"  [WARN] {os.path.basename(file_path)}: Source {s_id} cited but not resolvable")

        for r_id in report_ids:
            rec = _resolve_in_df(reports, r_id,
                                 candidate_cols=["community", "human_readable_id", "id"],
                                 text_cols=["full_content"])
            if rec:
                report_texts.append(f"REPORT {r_id}:\n{rec['full_content']}")
                rep_attached.append(r_id)
            else:
                rep_dropped.append(r_id)
                print(f"  [WARN] {os.path.basename(file_path)}: Report {r_id} cited but not resolvable")

        for e_id in entity_ids:
            rec = _resolve_in_df(entities, e_id,
                                 candidate_cols=["human_readable_id", "id"],
                                 text_cols=["title", "description"])
            if rec:
                entity_texts.append(f"ENTITY {e_id} ({rec['title']}):\n{rec['description']}")
                ent_attached.append(e_id)
            else:
                ent_dropped.append(e_id)
                print(f"  [WARN] {os.path.basename(file_path)}: Entity {e_id} cited but not resolvable")

        for r_id in rel_ids:
            rec = _resolve_in_df(relationships, r_id,
                                 candidate_cols=["human_readable_id", "id"],
                                 text_cols=["source", "target", "description"])
            if rec:
                rel_texts.append(f"RELATIONSHIP {r_id} ({rec['source']} → {rec['target']}):\n{rec['description']}")
                rel_attached.append(r_id)
            else:
                rel_dropped.append(r_id)
                print(f"  [WARN] {os.path.basename(file_path)}: Relationship {r_id} cited but not resolvable")

        audit_results.append({
            "Statement": statement,
            # original cited (kept for completeness)
            "Source IDs":       ", ".join(map(str, source_ids)),
            "Report IDs":       ", ".join(map(str, report_ids)),
            "Entity IDs":       ", ".join(map(str, entity_ids)),
            "Relationship IDs": ", ".join(map(str, rel_ids)),
            # new: attached vs dropped per type
            "Sources Retrieved":      ", ".join(map(str, src_attached)),
            "Sources Dropped":        ", ".join(map(str, src_dropped)),
            "Reports Retrieved":      ", ".join(map(str, rep_attached)),
            "Reports Dropped":        ", ".join(map(str, rep_dropped)),
            "Entities Retrieved":     ", ".join(map(str, ent_attached)),
            "Entities Dropped":       ", ".join(map(str, ent_dropped)),
            "Relationships Retrieved":", ".join(map(str, rel_attached)),
            "Relationships Dropped":  ", ".join(map(str, rel_dropped)),
            # the text payloads (kept so the RAGAS context can be built downstream)
            "Source Text":       "\n\n".join(source_texts),
            "Report Text":       "\n\n".join(report_texts),
            "Entity Text":       "\n\n".join(entity_texts),
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

# Global accumulator so we can print a summary of drops at the end
global_drop_counter = {}

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

    # RAGAS-input CSV (unchanged format: question, answer, context)
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

    # ---------- NEW: per-statement audit CSV ----------
    audit_cols = [
        "Statement",
        "Sources Retrieved", "Sources Dropped",
        "Reports Retrieved", "Reports Dropped",
        "Entities Retrieved", "Entities Dropped",
        "Relationships Retrieved", "Relationships Dropped",
    ]
    df_audit_export = df_audit[audit_cols].copy()
    df_audit_export.insert(0, "#", range(1, len(df_audit_export) + 1))
    df_audit_export["Statement"] = df_audit_export["Statement"].apply(one_line)

    audit_path = Path(EXPORT_DIR) / f"traceability_audit_{stem}.csv"
    df_audit_export.to_csv(audit_path, index=False, encoding="utf-8-sig")

    # Per-file drop summary
    n_drops_this_file = sum(
        sum(1 for x in str(v).split(",") if x.strip())
        for col in ("Sources Dropped", "Reports Dropped", "Entities Dropped", "Relationships Dropped")
        for v in df_audit[col]
    )
    print(f"  audit CSV written ({audit_path.name}); dropped citations in this file: {n_drops_this_file}")

    # Accumulate global drops by (kind, id)
    for _, row in df_audit.iterrows():
        for kind, col in [("Source", "Sources Dropped"),
                          ("Report", "Reports Dropped"),
                          ("Entity", "Entities Dropped"),
                          ("Relationship", "Relationships Dropped")]:
            for x in str(row[col]).split(","):
                x = x.strip()
                if x:
                    key = (kind, int(x))
                    global_drop_counter[key] = global_drop_counter.get(key, 0) + 1


# ---------- Overall summary ----------
print("\n" + "=" * 60)
print("OVERALL DROP SUMMARY (across all processed answer files)")
print("=" * 60)
if not global_drop_counter:
    print("No silent drops detected. Every cited ID was resolved.")
else:
    print(f"{len(global_drop_counter)} distinct ID(s) failed to resolve. Top offenders:")
    for (kind, i), n in sorted(global_drop_counter.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {kind} {i}: dropped {n} time(s)")
