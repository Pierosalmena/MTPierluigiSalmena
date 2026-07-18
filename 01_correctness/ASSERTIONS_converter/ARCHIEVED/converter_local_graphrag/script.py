import json
import os
import glob

def clean_text(raw_text):
    """
    Cleans the text by removing line breaks and replacing weird unicode 
    characters with their standard keyboard equivalents.
    """
    # 1. Replace all line breaks and tabs with a single space
    text = raw_text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')
    
    # 2. Replace weird unicode characters (smart quotes, arrows, dashes)
    replacements = {
        '“': '"', '”': '"',   # Smart double quotes (\u201c, \u201d)
        '‘': "'", '’': "'",   # Smart single quotes (\u2018, \u2019)
        '—': '-', '–': '-',   # Em and en dashes (\u2014, \u2013)
        '→': '->',            # Right arrow (\u2192)
        '\u00a0': ' ',        # Non-breaking spaces
        '\u001e': '-'         # Hidden record separators
    }
    
    for weird_char, normal_char in replacements.items():
        text = text.replace(weird_char, normal_char)
        
    # 3. Clean up any accidental double spaces created by replacing newlines
    while '  ' in text:
        text = text.replace('  ', ' ')
        
    return text.strip()

def process_text_files():
    # Find all .txt files in the current directory
    txt_files = glob.glob("*.txt")
    
    if not txt_files:
        print("No .txt files found in this directory.")
        return

    print(f"Found {len(txt_files)} text file(s). Processing...\n")

    for file_path in txt_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as infile:
                raw_text = infile.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        # Clean the text using our new function
        cleaned_text = clean_text(raw_text)

        # Put it into the dictionary structure
        data = {
            "answers": cleaned_text
        }

        # Dump to JSON. 
        # ensure_ascii=False prevents Python from generating ANY \uXXXX codes!
        json_string = json.dumps(data, ensure_ascii=False)

        # Save it as a new .json file
        base_name = os.path.splitext(file_path)[0]
        output_filename = f"{base_name}.json"

        with open(output_filename, 'w', encoding='utf-8') as outfile:
            outfile.write(json_string)

        print(f"Success: '{file_path}' --> '{output_filename}'")

if __name__ == "__main__":
    process_text_files()