import os
import json
import re
from typing import Dict, List, Any
import pdfplumber

def clean_text(text: str) -> str:
    """Removes non-printable unicode glyphs (chart fonts) and normalizes whitespace."""
    if not text:
        return ""
    # Strip Private Use Area unicode glyphs common in PDF graphs (e.g. \uE000-\uF8FF)
    text = re.sub(r'[\uE000-\uF8FF\uFFF0-\uFFFF]', '', text)
    # Normalize whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_exact_metadata_from_tables(page_tables: List[Any]) -> Dict[str, str]:
    """
    Directly extracts metadata by mapping table column indices:
    Col 0: Assessment (SAT)
    Col 1: Test (Reading and Writing / Math) -> section
    Col 2: Domain -> domain
    Col 3: Skill -> skill
    """
    for table in page_tables:
        if not table or len(table) < 2:
            continue
        
        # Normalize header row cells
        header_row = [clean_text(cell).lower() for cell in table[0] if cell]
        
        # Check if this table is the metadata header grid
        if any("assessment" in cell for cell in header_row) and any("domain" in cell for cell in header_row):
            value_row = table[1]
            
            # Map columns cleanly
            section = clean_text(value_row[1]) if len(value_row) > 1 else "Unknown"
            domain = clean_text(value_row[2]) if len(value_row) > 2 else "Unknown"
            skill = clean_text(value_row[3]) if len(value_row) > 3 else "Unknown"
            
            return {
                "section": section,
                "domain": domain,
                "skill": skill
            }
            
    return {"section": "Unknown", "domain": "Unknown", "skill": "Unknown"}

def parse_single_question(q_id: str, text: str, page_tables: List[Any]) -> Dict[str, Any]:
    # 1. Metadata from precise table column mapping
    metadata = extract_exact_metadata_from_tables(page_tables)
    
    # Fallback regex if table wasn't isolated
    if metadata["section"] == "Unknown":
        meta_match = re.search(r'SAT\s+(Reading and Writing|Math)\s+(.*?)\s+(.*?)\s+ID:', text)
        if meta_match:
            metadata["section"] = clean_text(meta_match.group(1))
            metadata["domain"] = clean_text(meta_match.group(2))
            metadata["skill"] = clean_text(meta_match.group(3))

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
    
    # Clean out stray chart glyphs before parsing prompt/options
    body_text = clean_text(body_text)

    # Check for Multiple Choice Options (A. ... B. ... C. ... D. ...)
    options_match = re.search(
        r'A\.\s*(.*?)\s*B\.\s*(.*?)\s*C\.\s*(.*?)\s*D\.\s*(.*?)(?=\s*ID:|$)', 
        body_text
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
        question_prompt = body_text

    # Separate Stimulus from Prompt
    stimulus = ""
    question_text = question_prompt
    
    prompt_split = re.split(
        r'(Which choice completes the text|Which choice best|According to the text|Based on the passage|Which choice most effectively)', 
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

    raw_blocks = re.split(r'Question ID\s+([a-f0-9]{8})', full_text, flags=re.IGNORECASE)
    
    for i in range(1, len(raw_blocks), 2):
        q_id = raw_blocks[i].strip()
        block_content = raw_blocks[i+1]
        
        try:
            parsed_q = parse_single_question(q_id, block_content, all_page_tables)
            if parsed_q:
                questions.append(parsed_q)
        except Exception as e:
            print(f"  ⚠️ Skipping Question ID {q_id}: {e}")

    return questions

def process_pdf_folder(input_folder: str, output_json_path: str):
    if not os.path.exists(input_folder):
        print(f"❌ Error: Folder '{input_folder}' does not exist.")
        return

    all_questions = []
    seen_ids = set()
    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]

    for file_name in pdf_files:
        full_path = os.path.join(input_folder, file_name)
        extracted_questions = parse_sat_pdf(full_path)
        
        for q in extracted_questions:
            if q["question_id"] not in seen_ids:
                seen_ids.add(q["question_id"])
                all_questions.append(q)

    difficulty_order = {"Easy": 1, "Medium": 2, "Hard": 3}
    all_questions.sort(key=lambda x: difficulty_order.get(x.get("difficulty", "Medium"), 2))

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)

    print(f"✅ Reparsed successfully! Total unique questions: {len(all_questions)}")

if __name__ == "__main__":
    process_pdf_folder("PDFs", "questions_database.json")