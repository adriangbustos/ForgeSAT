import os
import json
import time
import fitz  # PyMuPDF
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

TARGET_QIDS = [
    "b0d54c22", "4bc98629", "c83508f3", "d8e0ab29", "42d700d0",
    "7fa2cfb0", "fb75c2e6", "5ad0b3b6", "dde323c1", "43687700",
    "0abd16fa", "5c9ca033", "c5526332", "e914e737", "9a67367f",
    "7ae15e38", "3c65fb48", "bdd782e9", "1ad71c23", "bc6c6829",
    "ccb84027", "e4e977a4", "56b227af", "012136ca", "8d7fb037",
    "6492b769", "80243fdf", "1e7acd85", "3aaf7740", "52f5fe7b",
    "f66febb9", "733b819d", "f2af8e90", "0f88eb2d", "d6e97054",
    "629fb8a9", "43f4013a", "d4572f55", "f6c18a66", "89ff6a0a",
    "f496d2c0", "1fe41c6b"
]

PDF_PATHS = {
    "Reading and Writing": {
        "batch1": "PDFs/Questions/1st_Batch/English.pdf",
        "batch2": "PDFs/Questions/2nd_Batch/EnglishNew.pdf"
    },
    "Math": {
        "batch1": "PDFs/Questions/1st_Batch/Math.pdf",
        "batch2": "PDFs/Questions/2nd_Batch/MathNew.pdf"
    }
}

class TableData(BaseModel):
    headers: list[str]
    rows: list[list[str]]

def find_question_page(question_id, pdf_path):
    if not os.path.exists(pdf_path):
        return None
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        if question_id in text:
            doc.close()
            return page_num
    doc.close()
    return None

def process_single_page(client, pdf_path, page_num, question_id):
    # Create chunk
    doc = fitz.open(pdf_path)
    chunk_doc = fitz.open()
    chunk_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
    chunk_filename = f"temp_{question_id}.pdf"
    chunk_doc.save(chunk_filename)
    chunk_doc.close()
    doc.close()
    
    uploaded_file = client.files.upload(file=chunk_filename)
    
    prompt = f"""
    You are an expert data extraction pipeline. Extract the table data for the SAT question with ID {question_id} from this page.
    Ensure that you capture the headers and the rows accurately.
    Return ONLY a JSON matching the requested schema.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TableData,
                temperature=0.0
            ),
        )
        return json.loads(response.text)
    finally:
        client.files.delete(name=uploaded_file.name)
        if os.path.exists(chunk_filename):
            os.remove(chunk_filename)

def main():
    client = genai.Client()
    
    with open('questions_database.json', 'r', encoding='utf-8') as f:
        db = json.load(f)
        
    questions_by_id = {q["question_id"]: q for q in db}
    
    missing_tables = []
    
    # 1. Check which are ACTUALLY missing tables
    for qid in TARGET_QIDS:
        q = questions_by_id.get(qid)
        if not q:
            print(f"Warning: {qid} not found in database.")
            continue
            
        has_table = "table_data" in q and q["table_data"].get("rows")
        if not has_table:
            missing_tables.append(q)
            print(f"{qid} is missing its table.")
        else:
            print(f"{qid} already has a table, skipping.")
            
    print(f"\nFound {len(missing_tables)} questions actually missing tables.\n")
    
    results = []
    
    # 2. Extract tables
    for q in missing_tables:
        qid = q["question_id"]
        section = q["section"]
        
        batch1_path = PDF_PATHS[section]["batch1"]
        batch2_path = PDF_PATHS[section]["batch2"]
        
        page_num = find_question_page(qid, batch1_path)
        source_pdf = batch1_path
        
        if page_num is None:
            page_num = find_question_page(qid, batch2_path)
            source_pdf = batch2_path
            
        if page_num is None:
            print(f"Error: Could not find {qid} in either batch PDF.")
            continue
            
        print(f"Found {qid} in {source_pdf} on page {page_num + 1}. Extracting with Gemini...")
        
        try:
            table_data = process_single_page(client, source_pdf, page_num, qid)
            print(f"Success for {qid}: {table_data}")
            
            results.append({
                "question_id": qid,
                "table_data": table_data
            })
            
            print("Waiting 15 seconds to avoid rate limits...")
            time.sleep(15)
            
        except Exception as e:
            print(f"Failed to extract table for {qid}: {e}")
            
    # Save output
    with open("recovered_tables.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
        
    print(f"\nDone! Saved {len(results)} tables to recovered_tables.json.")

if __name__ == "__main__":
    main()
