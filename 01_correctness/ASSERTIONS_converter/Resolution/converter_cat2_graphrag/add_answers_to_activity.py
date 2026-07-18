"""
add_answers_to_activity.py

Reads resolution_answer<N>.txt files in the current folder, cleans them
(same logic as the original script: strip newlines/tabs, normalize curly
quotes, dashes, arrows, etc.), and writes each cleaned text into the
'answer' field of the matching entry in activity_cat2.json.

Convention:
    resolution_answer1.txt   -> TI-EVAL-cat2-01
    resolution_answer2.txt   -> TI-EVAL-cat2-02
    ...
    resolution_answer10.txt  -> TI-EVAL-cat2-10

To use this for the LOCAL set instead, change ACTIVITY_FILE and ID_PREFIX
at the top of the script.
"""

import json
import os
import re
import glob

# --- Configuration ------------------------------------------------------

ACTIVITY_FILE = "activity_cat2.json"
ID_PREFIX = "TI-EVAL-cat2-"   # change to "TI-EVAL-LOCAL-" for local set
ANSWER_FILE_PATTERN = "resolution_answer*.txt"

# ------------------------------------------------------------------------


def clean_text(raw_text):
    """
    Cleans the text by removing line breaks and replacing weird unicode
    characters with their standard keyboard equivalents.
    """
    # 1. Replace all line breaks and tabs with a single space
    text = raw_text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')

    # 2. Replace weird unicode characters (smart quotes, arrows, dashes)
    replacements = {
        '\u201c': '"', '\u201d': '"',   # Smart double quotes
        '\u2018': "'", '\u2019': "'",   # Smart single quotes
        '\u2014': '-', '\u2013': '-',   # Em and en dashes
        '\u2192': '->',                 # Right arrow
        '\u00a0': ' ',                  # Non-breaking space
        '\u001e': '-',                  # Hidden record separator
    }
    for weird_char, normal_char in replacements.items():
        text = text.replace(weird_char, normal_char)

    # 3. Collapse any accidental double spaces
    while '  ' in text:
        text = text.replace('  ', ' ')

    return text.strip()


def load_json_lenient(path):
    """
    Load a JSON file, tolerating trailing commas before } or ].
    This protects against the kind of typo currently in activity_cat2.json
    (trailing comma after question_text in entry 1).
    """
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    # Strip trailing commas before } or ]
    cleaned = re.sub(r',(\s*[}\]])', r'\1', text)
    return json.loads(cleaned)


def main():
    if not os.path.exists(ACTIVITY_FILE):
        print(f"ERROR: '{ACTIVITY_FILE}' not found in the current directory.")
        return

    # Load the activity file
    try:
        data = load_json_lenient(ACTIVITY_FILE)
    except json.JSONDecodeError as e:
        print(f"ERROR parsing '{ACTIVITY_FILE}': {e}")
        return

    if not isinstance(data, list):
        print(f"ERROR: '{ACTIVITY_FILE}' is not a JSON array at the top level.")
        return

    # Build a lookup from question_id -> entry index
    id_to_index = {}
    for i, entry in enumerate(data):
        qid = entry.get("question_id")
        if qid:
            id_to_index[qid] = i

    # One-pass cleanup: migrate any stray 'answers' (plural) field to 'answer' (singular).
    # The old version of the script wrote 'answers'; the canonical field name is 'answer'.
    migrated = 0
    for entry in data:
        if "answers" in entry:
            if "answer" not in entry:
                # Preserve the old content under the correct field name
                entry["answer"] = entry["answers"]
            # Drop the stray field either way
            del entry["answers"]
            migrated += 1
    if migrated:
        print(f"Migrated {migrated} 'answers' (plural) field(s) to 'answer' (singular).\n")

    # Find all resolution_answer*.txt files
    txt_files = sorted(glob.glob(ANSWER_FILE_PATTERN))
    if not txt_files:
        print(f"No files matching '{ANSWER_FILE_PATTERN}' found in this directory.")
        return

    print(f"Found {len(txt_files)} answer file(s). Processing...\n")

    updated = 0
    skipped = 0

    for file_path in txt_files:
        # Extract the number from the filename
        m = re.search(r'resolution_answer(\d+)\.txt$', file_path)
        if not m:
            print(f"  SKIP  {file_path}  (filename does not match expected pattern)")
            skipped += 1
            continue

        n = int(m.group(1))
        question_id = f"{ID_PREFIX}{n:02d}"

        if question_id not in id_to_index:
            print(f"  SKIP  {file_path}  (no entry with question_id={question_id})")
            skipped += 1
            continue

        # Read the answer text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"  SKIP  {file_path}  (read error: {e})")
            skipped += 1
            continue

        cleaned = clean_text(raw)

        # Insert/replace the answer field
        idx = id_to_index[question_id]
        already_present = "answer" in data[idx]
        data[idx]["answer"] = cleaned

        action = "REPLACE" if already_present else "ADD    "
        print(f"  {action} {file_path} -> {question_id}  ({len(cleaned)} chars)")
        updated += 1

    # Write back
    try:
        with open(ACTIVITY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")  # trailing newline for nice diffs
    except Exception as e:
        print(f"\nERROR writing '{ACTIVITY_FILE}': {e}")
        return

    print(f"\nDone. Updated: {updated}, Skipped: {skipped}.")
    print(f"Output written to '{ACTIVITY_FILE}'.")


if __name__ == "__main__":
    main()
