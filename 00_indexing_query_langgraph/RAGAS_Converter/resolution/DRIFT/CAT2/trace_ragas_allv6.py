import pandas as pd
import re
import os
import json
from pathlib import Path

# ===================== configuration =====================
ART_DIR     = "../../../../output"
ANSWERS_DIR = "./answers"
EXPORT_DIR  = "./trace_exports"
Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)
# =========================================================

# Load all four artefacts
text_units    = pd.read_parquet(os.path.join(ART_DIR, "text_units.parquet"))
reports       = pd.read_parquet(os.path.join(ART_DIR, "community_reports.parquet"))
entities      = pd.read_parquet(os.path.join(ART_DIR, "entities.parquet"))
relationships = pd.read_parquet(os.path.join(ART_DIR, "relationships.parquet"))

if "human_readable_id" not in text_units.columns:
    text_units["human_readable_id"] = text_units.index


# ---------- Robust ID lookup helper ----------

def _resolve_in_df(df: pd.DataFrame, target_id: int,
                   candidate_cols: list, text_cols: list):
    """Try each candidate column with both int and string variants of target_id.
    Return a dict of the requested text columns if found, else None."""
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


# ---------- Type-agnostic resolvers ----------

# Each citation type has a primary table and ordered fallback tables. The
# primary is what the label is supposed to refer to; the fallbacks handle the
# observation that DRIFT generators apply citation labels loosely.
#
# Resolver returns (text_block, resolved_as) where:
#   text_block  = rendered text for the context column, or None if all tables fail
#   resolved_as = one of "text_unit", "community_report", "entity", "relationship",
#                 or None when not resolved.

def _try_text_unit(tid: int):
    rec = _resolve_in_df(text_units, tid,
                         candidate_cols=["human_readable_id", "id"],
                         text_cols=["text"])
    if rec:
        return f"{rec['text']}", "text_unit"
    return None, None


def _try_community_report(tid: int):
    rec = _resolve_in_df(reports, tid,
                         candidate_cols=["community", "human_readable_id", "id"],
                         text_cols=["full_content"])
    if rec:
        return f"{rec['full_content']}", "community_report"
    return None, None


def _try_entity(tid: int):
    rec = _resolve_in_df(entities, tid,
                         candidate_cols=["human_readable_id", "id"],
                         text_cols=["title", "type", "description"])
    if rec:
        title = rec.get("title", "")
        etype = rec.get("type", "")
        desc  = rec.get("description", "")
        header = f"(entity {title}"
        if etype:
            header += f", type {etype}"
        header += ")"
        return f"{header}:\n{desc}", "entity"
    return None, None


def _try_relationship(tid: int):
    rec = _resolve_in_df(relationships, tid,
                         candidate_cols=["human_readable_id", "id"],
                         text_cols=["source", "target", "description"])
    if rec:
        src  = rec.get("source", "")
        tgt  = rec.get("target", "")
        desc = rec.get("description", "")
        return f"({src} → {tgt}):\n{desc}", "relationship"
    return None, None


# Primary-then-fallback chains per citation label
RESOLVER_CHAIN = {
    "Sources":       (_try_text_unit,        [_try_community_report, _try_entity]),
    "Reports":       (_try_community_report, [_try_entity,           _try_text_unit]),
    "Entities":      (_try_entity,           [_try_community_report, _try_text_unit]),
    "Relationships": (_try_relationship,     []),
}


def resolve_id(label: str, tid: int):
    """Type-agnostic resolution. Returns (text_block, resolved_as)."""
    primary, fallbacks = RESOLVER_CHAIN[label]
    text, kind = primary(tid)
    if text is not None:
        return text, kind
    for fb in fallbacks:
        text, kind = fb(tid)
        if text is not None:
            return text, kind
    return None, None


# ---------- Statement-citation extraction ----------

def extract_pairs(content: str):
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


# ---------- Per-answer trace ----------

def audit_traceability(file_path: str) -> pd.DataFrame:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    audit_results = []
    fname = os.path.basename(file_path)

    for statement, citation, _offset in extract_pairs(content):
        # Parse cited IDs per label
        label_ids = {
            "Sources":       parse_id_blocks(r"Sources?\s*\(([\d, ]+)\)", citation),
            "Reports":       parse_id_blocks(r"Reports?\s*\(([\d, ]+)\)", citation),
            "Entities":      parse_id_blocks(r"Entit(?:y|ies)\s*\(([\d, ]+)\)", citation),
            "Relationships": parse_id_blocks(r"Relationships?\s*\(([\d, ]+)\)", citation),
        }

        # Resolve each label's IDs with type-agnostic fallback
        attached = {label: [] for label in label_ids}
        dropped  = {label: [] for label in label_ids}
        # Track cross-type resolutions so the audit shows how each ID was resolved
        cross_type_resolutions = []

        # Aggregate text for the RAGAS context, grouped by resolved type
        text_by_kind = {
            "text_unit": [], "community_report": [],
            "entity":    [], "relationship":     [],
        }

        for label, ids in label_ids.items():
            for tid in ids:
                text, kind = resolve_id(label, tid)
                if text is None:
                    dropped[label].append(tid)
                    print(f"  [WARN] {fname}: {label} ({tid}) cited but not resolvable in any table")
                    continue
                attached[label].append(tid)
                # Note the cross-type resolution if the resolved kind doesn't
                # match the label's primary type
                primary_kind = {
                    "Sources":       "text_unit",
                    "Reports":       "community_report",
                    "Entities":      "entity",
                    "Relationships": "relationship",
                }[label]
                if kind != primary_kind:
                    cross_type_resolutions.append(f"{label}({tid}) -> {kind}")
                # Render with a header that records the original label and the
                # resolved kind, so the RAGAS judge sees clear provenance
                header = f"{label.upper()[:-1]} {tid} [resolved-as: {kind}]"
                text_by_kind[kind].append(f"{header}:\n{text}")

        audit_results.append({
            "Statement": statement,
            # original cited (kept for completeness)
            "Source IDs":       ", ".join(map(str, label_ids["Sources"])),
            "Report IDs":       ", ".join(map(str, label_ids["Reports"])),
            "Entity IDs":       ", ".join(map(str, label_ids["Entities"])),
            "Relationship IDs": ", ".join(map(str, label_ids["Relationships"])),
            # attached vs dropped per label
            "Sources Retrieved":       ", ".join(map(str, attached["Sources"])),
            "Sources Dropped":         ", ".join(map(str, dropped["Sources"])),
            "Reports Retrieved":       ", ".join(map(str, attached["Reports"])),
            "Reports Dropped":         ", ".join(map(str, dropped["Reports"])),
            "Entities Retrieved":      ", ".join(map(str, attached["Entities"])),
            "Entities Dropped":        ", ".join(map(str, dropped["Entities"])),
            "Relationships Retrieved": ", ".join(map(str, attached["Relationships"])),
            "Relationships Dropped":   ", ".join(map(str, dropped["Relationships"])),
            # cross-type resolutions, e.g. "Sources(373) -> community_report"
            "Cross-type resolutions":  "; ".join(cross_type_resolutions),
            # text payloads, grouped by what they were resolved as
            "Source Text":       "\n\n".join(text_by_kind["text_unit"]),
            "Report Text":       "\n\n".join(text_by_kind["community_report"]),
            "Entity Text":       "\n\n".join(text_by_kind["entity"]),
            "Relationship Text": "\n\n".join(text_by_kind["relationship"]),
        })

    return pd.DataFrame(audit_results)


def one_line(s: str) -> str:
    return " ".join(s.split()) if isinstance(s, str) else ""


# ---------- Batch run ----------

QUESTION_TEXT = "Is the statement supported by the evidence?"

answer_files = sorted(Path(ANSWERS_DIR).glob("*.txt"))
if not answer_files:
    raise FileNotFoundError(f"No .txt files found in: {ANSWERS_DIR}")

global_drop_counter      = {}
global_crosstype_counter = {}

for answer_path in answer_files:
    print(f"\n=== Processing: {answer_path.name} ===")
    df_audit = audit_traceability(str(answer_path))

    def build_context(row) -> str:
        parts = []
        # Note: the "Source Text" / "Report Text" / etc. payloads are grouped
        # by the RESOLVED kind, not by the original label. This means a
        # citation written as Sources (373) appears in the CITED REPORTS block
        # when 373 turns out to be a community report. The header inside each
        # entry records both the original label and the resolved kind so the
        # provenance is preserved.
        if str(row["Source Text"]).strip():
            parts.append("=== CITED TEXT UNITS ===\n" + str(row["Source Text"]))
        if str(row["Report Text"]).strip():
            parts.append("=== CITED COMMUNITY REPORTS ===\n" + str(row["Report Text"]))
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

    # Per-statement audit CSV
    audit_cols = [
        "Statement",
        "Sources Retrieved", "Sources Dropped",
        "Reports Retrieved", "Reports Dropped",
        "Entities Retrieved", "Entities Dropped",
        "Relationships Retrieved", "Relationships Dropped",
        "Cross-type resolutions",
    ]
    df_audit_export = df_audit[audit_cols].copy()
    df_audit_export.insert(0, "#", range(1, len(df_audit_export) + 1))
    df_audit_export["Statement"] = df_audit_export["Statement"].apply(one_line)

    audit_path = Path(EXPORT_DIR) / f"traceability_audit_{stem}.csv"
    df_audit_export.to_csv(audit_path, index=False, encoding="utf-8-sig")

    # Per-file summary numbers
    n_drops_this_file = sum(
        sum(1 for x in str(v).split(",") if x.strip())
        for col in ("Sources Dropped", "Reports Dropped",
                    "Entities Dropped", "Relationships Dropped")
        for v in df_audit[col]
    )
    n_crosstype_this_file = sum(
        len([x for x in str(r).split(";") if x.strip()])
        for r in df_audit["Cross-type resolutions"]
    )
    print(f"  audit CSV written ({audit_path.name})")
    print(f"  dropped citations in this file:           {n_drops_this_file}")
    print(f"  cross-type resolutions in this file:      {n_crosstype_this_file}")

    # Accumulate global counters
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
        for x in str(row["Cross-type resolutions"]).split(";"):
            x = x.strip()
            if x:
                global_crosstype_counter[x] = global_crosstype_counter.get(x, 0) + 1


# ---------- Overall summary ----------
print("\n" + "=" * 60)
print("OVERALL SUMMARY (across all processed answer files)")
print("=" * 60)

if not global_drop_counter:
    print("\nDROPS: No silent drops detected. Every cited ID was resolved.")
else:
    print(f"\nDROPS: {len(global_drop_counter)} distinct ID(s) failed to resolve in any table.")
    for (kind, i), n in sorted(global_drop_counter.items(), key=lambda kv: -kv[1])[:30]:
        print(f"  {kind} {i}: dropped {n} time(s)")

if not global_crosstype_counter:
    print("\nCROSS-TYPE RESOLUTIONS: none.")
else:
    print(f"\nCROSS-TYPE RESOLUTIONS: {len(global_crosstype_counter)} distinct patterns observed.")
    for pat, n in sorted(global_crosstype_counter.items(), key=lambda kv: -kv[1])[:30]:
        print(f"  {pat}: {n} time(s)")
