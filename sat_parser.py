import os
import json
import re
from typing import Dict, List, Any
import pdfplumber

def clean_text(text: str) -> str:
    """Removes excess whitespace and normalizes text extracted from PDF streams."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_single_question(q_id: str, text: str) -> Dict[str, Any]:
    """Parses a single raw question text block into a structured dictionary."""
    # 1. Extract Metadata Table Header (Section, Domain, Skill)
    test_match = re.search(
        r'Assessment\s*\|\s*Test\s*\|\s*Domain\s*\|\s*Skill\s*\|\s*Difficulty\s*\n\s*SAT\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|', 
        text
    )
    
    section = clean_text(test_match.group(1)) if test_match else "Unknown"
    domain = clean_text(test_match.group(2)) if test_match else "Unknown"
    skill = clean_text(test_match.group(3)) if test_match else "Unknown"
    
    # Extract Difficulty from the footer block
    diff_match = re.search(r'Question Difficulty:\s*(Easy|Medium|Hard)', text)
    difficulty = diff_match.group(1) if diff_match else "Medium"
    
    # 2. Extract Correct Answer and Rationale
    answer_block_match = re.search(
        rf'ID:\s*{q_id}\s*Answer\s*\n\s*Correct Answer:\s*(.*?)\n\s*Rationale\s*\n(.*?)Question Difficulty:', 
        text, 
        re.DOTALL
    )
    
    correct_answer = ""
    rationale = ""
    if answer_block_match:
        correct_answer = clean_text(answer_block_match.group(1))
        rationale = clean_text(answer_block_match.group(2))
    
    # 3. Extract Question Body and Options
    content_match = re.search(rf'ID:\s*{q_id}\s*\n(.*?)\n\s*ID:\s*{q_id}\s*Answer', text, re.DOTALL)
    body_text = content_match.group(1) if content_match else ""
    
    # Check for Multiple Choice Options (A. ... B. ... C. ... D. ...)
    options_match = re.search(
        r'A\.\s*(.*?)\n\s*B\.\s*(.*?)\n\s*C\.\s*(.*?)\n\s*D\.\s*(.*?)(?=\n\s*ID:|$)', 
        body_text, 
        re.DOTALL
    )
    
    if options_match:
        # Multiple Choice Question
        is_open_ended = False
        options = {
            "A": clean_text(options_match.group(1)),
            "B": clean_text(options_match.group(2)),
            "C": clean_text(options_match.group(3)),
            "D": clean_text(options_match.group(4))
        }
        question_prompt = clean_text(body_text[:options_match.start()])
    else:
        # Student-Produced Response / Math Open Question Grid-In
        is_open_ended = True
        options = None
        question_prompt = clean_text(body_text)

    # Separate Stimulus (Passage) from Question Prompt if applicable
    stimulus = ""
    question_text = question_prompt
    
    prompt_split = re.split(
        r'(Which choice completes the text|Which choice best|According to the text|Based on the passage)', 
        question_prompt
    )
    if len(prompt_split) > 1:
        stimulus = clean_text(prompt_split[0])
        question_text = clean_text("".join(prompt_split[1:]))

    return {
        "question_id": f"SAT_{q_id}",
        "section": section,
        "domain": domain,
        "skill": skill,
        "difficulty": difficulty,
        "is_open_ended": is_open_ended,
        "stimulus": stimulus,
        "question_text": question_text,
        "options": options,
        "correct_answer": correct_answer,
        "explanation": rationale
    }

def parse_sat_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Extracts continuous text across pages and splits into individual questions."""
    questions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                full_text += page_text + "\n---PAGE_BREAK---\n"

    # Split document stream by Question ID anchors
    raw_blocks = re.split(r'Question ID\s+([a-f0-9]{8})', full_text)
    
    for i in range(1, len(raw_blocks), 2):
        q_id = raw_blocks[i].strip()
        block_content = raw_blocks[i+1]
        
        try:
            parsed_q = parse_single_question(q_id, block_content)
            if parsed_q:
                questions.append(parsed_q)
        except Exception as e:
            print(f"  ⚠️ Skipping Question ID {q_id} in {os.path.basename(pdf_path)} due to parse error: {e}")

    return questions

def process_pdf_folder(input_folder: str, output_json_path: str):
    """Scans entire folder, extracts questions from all PDFs, de-duplicates, and sorts by difficulty."""
    if not os.path.exists(input_folder):
        print(f"❌ Error: Folder '{input_folder}' does not exist. Create it and place your College Board PDFs inside.")
        return

    all_questions = []
    seen_ids = set()
    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]

    if not pdf_files:
        print(f"⚠️ No PDF files found inside '{input_folder}'.")
        return

    print(f"🔍 Found {len(pdf_files)} PDF(s) in '{input_folder}'. Beginning parsing...\n")

    for file_name in pdf_files:
        full_path = os.path.join(input_folder, file_name)
        print(f"Processing: {file_name}...")
        
        extracted_questions = parse_sat_pdf(full_path)
        added_count = 0
        
        for q in extracted_questions:
            # Deduplicate across multiple PDFs
            if q["question_id"] not in seen_ids:
                seen_ids.add(q["question_id"])
                all_questions.append(q)
                added_count += 1

        print(f"  └── Extracted {len(extracted_questions)} questions ({added_count} new, {len(extracted_questions) - added_count} duplicate).\n")

    # Sort final question pool by Difficulty: Easy -> Medium -> Hard
    difficulty_order = {"Easy": 1, "Medium": 2, "Hard": 3}
    all_questions.sort(key=lambda x: difficulty_order.get(x.get("difficulty", "Medium"), 2))

    # Save to final JSON database file
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)

    print(f"✅ Finished! Total unique questions saved to '{output_json_path}': {len(all_questions)}")

if __name__ == "__main__":
    # Folder containing all College Board PDF downloads
    INPUT_DIR = "PDFs"
    # Destination database file for the Next.js/Antigravity application
    OUTPUT_FILE = "questions_database.json"

    process_pdf_folder(INPUT_DIR, OUTPUT_FILE)