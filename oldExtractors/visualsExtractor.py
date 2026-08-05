import os
import json
import time
import fitz  # PyMuPDF
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
from google.genai import types
from PIL import Image, ImageChops
import io

load_dotenv()

# Schema for Gemini
class VisualExtraction(BaseModel):
    has_visual: bool = Field(description="True if the specified question has a graph, chart, diagram, or data table.")
    visual_type: str = Field(description="'table', 'graph', 'none'")
    table_headers: List[str] = Field(description="If table, list of column headers. Else empty.")
    table_rows: List[List[str]] = Field(description="If table, list of rows, where each row is a list of cell values. Else empty.")
    bounding_box: List[int] = Field(description="If graph, [ymin, xmin, ymax, xmax] normalized 0 to 1000. Give [0,0,0,0] if none.")

def find_bounds(sums, max_artifact_size=30, max_gap=20):
    segments = []
    start = None
    last_non_zero = None
    
    for i, val in enumerate(sums):
        if val > 0:
            if start is None:
                start = i
            last_non_zero = i
        else:
            if start is not None and last_non_zero is not None:
                if i - last_non_zero > max_gap:
                    segments.append((start, last_non_zero))
                    start = None
                    last_non_zero = None
                    
    if start is not None and last_non_zero is not None:
        segments.append((start, last_non_zero))
        
    if not segments:
        return 0, len(sums) - 1
        
    if len(segments) > 1:
        while len(segments) > 1 and (segments[0][1] - segments[0][0]) < max_artifact_size:
            segments.pop(0)
        while len(segments) > 1 and (segments[-1][1] - segments[-1][0]) < max_artifact_size:
            segments.pop()
            
    return segments[0][0], segments[-1][1]

def auto_crop_white(img, padding=10):
    """Automatically crops excess white space and ignores UI artifacts like edge triangles."""
    if img.mode != 'RGB':
        img = img.convert('RGB')
        
    gray = img.convert('L')
    bw = gray.point(lambda x: 0 if x > 240 else 255, '1')
    
    width, height = bw.size
    pixels = list(bw.getdata())
    
    col_sums = [sum(1 for y in range(height) if pixels[y * width + x] > 0) for x in range(width)]
    row_sums = [sum(1 for x in range(width) if pixels[y * width + x] > 0) for y in range(height)]
    
    left, right = find_bounds(col_sums, max_artifact_size=40, max_gap=25)
    top, bottom = find_bounds(row_sums, max_artifact_size=40, max_gap=25)
    
    if left < right and top < bottom:
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(width, right + padding)
        bottom = min(height, bottom + padding)
        return img.crop((left, top, right, bottom))
    return img


def find_question_in_pdfs(question_id: str, pdf_folder: str):
    """Searches all PDFs for the question_id and returns (pdf_path, page_num)."""
    for file_name in os.listdir(pdf_folder):
        if file_name.lower().endswith('.pdf'):
            pdf_path = os.path.join(pdf_folder, file_name)
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if question_id in text:
                    doc.close()
                    return pdf_path, page_num
            doc.close()
    return None, None

def process_visual_question(question, pdf_path, page_num, client, output_image_dir):
    """Extracts table or graph using Gemini."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    
    # Render page to image
    pix = page.get_pixmap(dpi=200)
    img_data = pix.tobytes("png")
    
    # Upload to Gemini
    with open("temp_page.png", "wb") as f:
        f.write(img_data)
        
    uploaded_file = client.files.upload(file="temp_page.png")
    
    prompt = f"""
    Here is a page from an SAT test. It contains a question with ID: {question['question_id']}.
    The question text is: "{question['stimulus']}"
    
    Does this specific question have a visual component (a data table, a graph, or a diagram)?
    If it has a data table:
    - visual_type should be "table"
    - extract the table_headers and table_rows.
    
    If it has a graph or diagram:
    - visual_type should be "graph"
    - provide its bounding box as [ymin, xmin, ymax, xmax] normalized from 0 to 1000.
    The bounding box MUST ONLY cover the graph/diagram/image itself. DO NOT include the question text or options in the bounding box.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VisualExtraction,
                temperature=0.0
            ),
        )
        
        result = json.loads(response.text)
        client.files.delete(name=uploaded_file.name)
        
        if result.get("has_visual"):
            if result.get("visual_type") == "table":
                question["table_data"] = {
                    "headers": result.get("table_headers", []),
                    "rows": result.get("table_rows", [])
                }
                print(f"  -> Extracted Table for {question['question_id']}")
                
            elif result.get("visual_type") == "graph":
                bbox = result.get("bounding_box", [0, 0, 0, 0])
                if bbox != [0, 0, 0, 0]:
                    ymin, xmin, ymax, xmax = bbox
                    
                    img = Image.open(io.BytesIO(img_data))
                    width, height = img.size
                    
                    left = (xmin / 1000.0) * width
                    top = (ymin / 1000.0) * height
                    right = (xmax / 1000.0) * width
                    bottom = (ymax / 1000.0) * height
                    
                    padding = 10
                    left = max(0, left - padding)
                    top = max(0, top - padding)
                    right = min(width, right + padding)
                    bottom = min(height, bottom + padding)
                    
                    cropped_img = img.crop((left, top, right, bottom))
                    cropped_img = auto_crop_white(cropped_img)

                    
                    image_filename = f"{question['question_id']}.png"
                    image_path = os.path.join(output_image_dir, image_filename)
                    cropped_img.save(image_path)
                    
                    question["image_url"] = f"/images/questions/{image_filename}"
                    print(f"  -> Extracted Graph for {question['question_id']}")
                    
        return True
    except Exception as e:
        print(f"  -> Error processing {question['question_id']}: {e}")
        return False
    finally:
        if os.path.exists("temp_page.png"):
            os.remove("temp_page.png")
        doc.close()

def main():
    client = genai.Client()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_folder = os.path.join(script_dir, "PDFs", "Questions")
    db_path = os.path.join(script_dir, "..", "public", "questions_database.json")
    output_image_dir = os.path.join(script_dir, "..", "public", "images", "questions")
    
    os.makedirs(output_image_dir, exist_ok=True)
    
    print("Loading database...")
    with open(db_path, "r", encoding="utf-8") as f:
        database = json.load(f)
        
    visual_keywords = [
        "table", "graph", "plot", "chart", "diagram", "figure",
        "triangle", "circle", "xy-plane", "plane", "shown", "above", "histogram", "box plots"
    ]
    
    target_questions = []
    for q in database:
        if "image_url" in q or "table_data" in q:
            continue
            
        text_to_check = (q.get("stimulus", "") + " " + q.get("question_text", "")).lower()
        if any(keyword in text_to_check for keyword in visual_keywords):
            target_questions.append(q)
            
    print(f"Found {len(target_questions)} questions that potentially have visuals.")
    
    # We don't need test_limit anymore if we want to run the whole thing, but we can set it to a large number
    test_limit = 500
    processed = 0
    
    for q in target_questions:
        if processed >= test_limit:
            break
            
        print(f"Processing {q['question_id']}...")
        pdf_path, page_num = find_question_in_pdfs(q["question_id"], pdf_folder)
        
        if pdf_path is not None:
            success = process_visual_question(q, pdf_path, page_num, client, output_image_dir)
            if success:
                processed += 1
                # Save every 5 questions to prevent data loss on crash
                if processed % 5 == 0:
                    print(f"--- Checkpoint: Saving database after {processed} successful extractions ---")
                    with open(db_path, "w", encoding="utf-8") as f:
                        json.dump(database, f, indent=2, ensure_ascii=False)
                time.sleep(5)
        else:
            print(f"  -> Could not find question {q['question_id']} in PDFs.")
            
    print("Saving final updated database...")
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
        
    print("Done!")

if __name__ == "__main__":
    main()
