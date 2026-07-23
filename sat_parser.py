import os
import json
import re
from typing import Dict, List, Any
import pdfplumber

def clean_text(text: str) -> str:
    """Removes excess whitespace and normalizes line breaks."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_metadata_from_block_or_tables(block_content: str, page_tables: List[Any]) -> Dict[str, str]:
    """Extracts Section, Domain, and Skill using Regex first, falling back to PDF table extraction."""
    section, domain, skill = "Unknown", "Unknown", "Unknown"
    
    # Strategy A: Broad Regex matching line or tabular text
    # Matches patterns like: SAT | Reading and Writing | Standard English Conventions | Boundaries
    meta_match = re.search(
        r'SAT\s*\|\s*([^|\n]+)\|\s*([^|\n]+)\|\s*([^|\n]+)', 
        block_content, 
        re.IGNORECASE
    )
    
    if meta_match:
        section = clean_text(meta_match.group(1))
        domain = clean_text(meta_match.group(2))
        skill = clean_text(meta_match.group(3))
    else:
        # Strategy B: Table extraction fallback
        for table in page_tables:
            if not table:
                continue
            for row in table:
                row_str = " ".join([clean_text(cell) for cell in row if cell])
                if "SAT" in row_str or "Reading and Writing" in row_str or "Math" in row_str:
                    # Filter out empty header cells
                    clean_cells = [clean_text(cell) for cell in row if cell and clean_text(cell) not in ["Assessment", "Test", "Domain", "Skill", "Difficulty", "|"]]
                    if len(clean_cells) >= 3:
                        section = clean_cells[0]
                        domain = clean_cells[1]
                        skill = clean_cells[2]
                        break

    return {"section": section, "domain": domain, "skill": skill}

def parse_single_question(q_id: str, text: str, page_tables: List[Any]) -> Dict[str, Any]:
    """Parses a single question block using resilient header extraction."""
    # 1. Header Metadata Extraction
    metadata = extract_metadata_from_block_or_tables(text, page_tables)
    
    # 2. Extract Difficulty from footer
    diff_match = re.search(r'Question Difficulty:\s*(Easy|Medium|Hard)', text, re.IGNORECASE)
    difficulty = diff_match.group(1).capitalize() if diff_match else "Medium"
    
    # 3. Extract Correct Answer and Rationale
    answer_block_match = re.search(
        rf'ID:\s*{q_id}\s*Answer\s*\n\s*Correct Answer:\s*(.*?)\n\s*Rationale\s*\n(.*?)Question Difficulty:', 
        text, 
        re.DOTALL | re.IGNORECASE
    )
    
    correct_answer = ""
    rationale = ""
    if answer_block_match:
        correct_answer = clean_text(answer_block_match.group(1))
        rationale = clean_text(answer_block_match.group(2))
    
    # 4. Extract Question Body and Options
    content_match = re.search(rf'ID:\s*{q_id}\s*\n(.*?)\n\s*ID:\s*{q_id}\s*Answer', text, re.DOTALL | re.IGNORECASE)
    body_text = content_match.group(1) if content_match else ""
    
    # Check for Multiple Choice Options (A. ... B. ... C. ... D. ...)
    options_match = re.search(
        r'A\.\s*(.*?)\n\s*B\.\s*(.*?)\n\s*C\.\s*(.*?)\n\s*D\.\s*(.*?)(?=\n\s*ID:|$)', 
        body_text, 
        re.DOTALL
    )
    
    if options_match:
        is_open_ended = False
        options = {
            "A": clean_text(options_match.group(1)),
            "B": clean_text(options_match.group(2)),
            "C": clean_text(options_match.group(3)),
            "D": clean_text(options_match.group(4))
        }
        question_prompt = clean_text(body_text[:options_match.start()])
    else:
        is_open_ended = True
        options = None
        question_prompt = clean_text(body_text)

    # Separate Stimulus from Prompt
    stimulus = ""
    question_text = question_prompt
    
    prompt_split = re.split(
        r'(Which choice completes the text|Which choice best|According to the text|Based on the passage)', 
        question_prompt,
        flags=re.IGNORECASE
    )
    if len(prompt_split) > 1:
        stimulus = clean_text(prompt_split[0])
        question_text = clean_text("".join(prompt_split[1:]))

    return {
        "question_id": f"SAT_{q_id}",
        "section": metadata["section"],
        "domain": metadata["domain"],
        "skill": metadata["skill"],
        "difficulty": difficulty,
        "is_open_ended": is_open_ended,
        "stimulus": stimulus,
        "question_text": question_text,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": rationale
    }

def parse_sat_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Extracts continuous text and table data across pages."""
    questions = []
    full_text = ""
    all_page_tables = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            tables = page.extract_tables()
            if page_text:
                full_text += page_text + "\n---PAGE_BREAK---\n"
            if tables:
                all_page_tables.extend(tables)

    # Split document stream by Question ID anchors
    raw_blocks = re.split(r'Question ID\s+([a-f0-9]{8})', full_text, flags=re.IGNORECASE)
    
    for i in range(1, len(raw_blocks), 2):
        q_id = raw_blocks[i].strip()
        block_content = raw_blocks[i+1]
        
        try:
            parsed_q = parse_single_question(q_id, block_content, all_page_tables)
            if parsed_q:
                questions.append(parsed_q)
        except Exception as e:
            print(f"  ⚠️ Skipping Question ID {q_id} in {os.path.basename(pdf_path)} due to error: {e}")

    return questions

def process_pdf_folder(input_folder: str, output_json_path: str):
    """Scans 'PDFs' folder, parses questions, de-duplicates, and outputs JSON."""
    if not os.path.exists(input_folder):
        print(f"❌ Error: Folder '{input_folder}' does not exist.")
        return

    all_questions = []
    seen_ids = set()
    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]

    if not pdf_files:
        print(f"⚠️ No PDF files found inside '{input_folder}'.")
        return

    print(f"🔍 Found {len(pdf_files)} PDF(s) in '{input_folder}'. Processing...\n")

    for file_name in pdf_files:
        full_path = os.path.join(input_folder, file_name)
        print(f"Processing: {file_name}...")
        
        extracted_questions = parse_sat_pdf(full_path)
        added_count = 0
        
        for q in extracted_questions:
            if q["question_id"] not in seen_ids:
                seen_ids.add(q["question_id"])
                all_questions.append(q)
                added_count += 1

        print(f"  └── Extracted {len(extracted_questions)} questions ({added_count} new).\n")

    # Sort final pool by Difficulty: Easy -> Medium -> Hard
    difficulty_order = {"Easy": 1, "Medium": 2, "Hard": 3}
    all_questions.sort(key=lambda x: difficulty_order.get(x.get("difficulty", "Medium"), 2))

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)

    print(f"✅ Finished! Total unique questions saved to '{output_json_path}': {len(all_questions)}")

if __name__ == "__main__":
    process_pdf_folder("PDFs", "questions_database.json")