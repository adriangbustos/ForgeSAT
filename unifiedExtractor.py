import os
import json
import time
import fitz  # PyMuPDF
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
from google.genai import types
from PIL import Image
import io

load_dotenv()

# --- Schemas for Step 1 (Chunk Extraction) ---
class QuestionOptions(BaseModel):
    A: Optional[str] = Field(default=None, description="Option A text (LaTeX allowed)")
    B: Optional[str] = Field(default=None, description="Option B text (LaTeX allowed)")
    C: Optional[str] = Field(default=None, description="Option C text (LaTeX allowed)")
    D: Optional[str] = Field(default=None, description="Option D text (LaTeX allowed)")

class VisualData(BaseModel):
    has_visual: bool = Field(description="True if the question relies on a graph, chart, diagram, or data table.")
    visual_type: str = Field(description="'table', 'graph', or 'none'")
    table_headers: Optional[List[str]] = Field(default=[], description="If table, list of column headers. Else empty.")
    table_rows: Optional[List[List[str]]] = Field(default=[], description="If table, list of rows, where each row is a list of cell values. Else empty.")

class SATQuestion(BaseModel):
    question_id: str = Field(description="The 8-character ID, e.g., 618d94c4")
    section: str = Field(description="Either 'Reading and Writing' or 'Math'")
    domain: str = Field(description="The content domain, e.g., 'Algebra'")
    skill: str = Field(description="The specific skill tested")
    difficulty: str = Field(description="Either 'Easy', 'Medium', or 'Hard'")
    is_open_ended: bool = Field(description="True if it is a Math Grid-In with no options")
    stimulus: str = Field(description="The passage, context, or scenario provided BEFORE the actual question prompt. Do NOT describe images here. Use $ for inline LaTeX math.")
    question_text: str = Field(description="The actual question prompt that asks what needs to be solved. Do NOT describe images here. Use LaTeX for math.")
    options: Optional[QuestionOptions] = Field(default=None, description="Options A, B, C, D. Null if is_open_ended is true.")
    correct_answer: str = Field(description="The correct letter or the numeric grid-in answer")
    explanation: str = Field(description="The official rationale. Use LaTeX for math.")
    visual_data: Optional[VisualData] = Field(default=None, description="Information about visual elements like tables or graphs associated with this question.")

class QuestionDatabase(BaseModel):
    questions: List[SATQuestion]

# --- Schema for Step 2 (Graph Bounding Box Extraction) ---
class BoundingBoxExtraction(BaseModel):
    bounding_box: List[int] = Field(description="[ymin, xmin, ymax, xmax] normalized 0 to 1000 for the graph/image. [0,0,0,0] if none.")


# --- Helper Functions ---
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

def find_question_in_pdfs(question_id: str, pdf_path: str):
    """Searches the specific PDF for the question_id and returns the page_num."""
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        if question_id in text:
            doc.close()
            return page_num
    doc.close()
    return None

# --- Pipeline Steps ---

def process_pdf_chunk(chunk_pdf_path: str, client: genai.Client) -> list:
    """Uploads and processes a 12-page PDF chunk via Gemini Vision."""
    uploaded_file = client.files.upload(file=chunk_pdf_path)
    
    prompt = """
    You are an expert data extraction pipeline. Read this SAT Question Bank PDF chunk and extract EVERY question.
    
    CRITICAL RULES:
    1. Every single mathematical symbol, fraction, exponent, variable, and number inside the stimulus, question, options, and explanation MUST be converted to standard LaTeX.
    2. Enclose inline LaTeX in single dollar signs (e.g., $x^2 + 3 = 10$).
    3. Ensure the Difficulty, Domain, and Skill match the metadata in the header/footer of each question block.
    4. If a question is an open-ended Math Grid-In, set is_open_ended to true and options to null.
    5. Clearly separate the `stimulus` (the contextual passage, scenario, or information provided BEFORE the question) and the `question_text` (the specific prompt asking what needs to be solved). Do not combine them.
    6. Do NOT attempt to describe graphs, charts, diagrams, or tables in text within the `stimulus` or `question_text`.
    7. If a question relies on a graph, chart, diagram, or data table, set `has_visual` to true in `visual_data`, and provide `visual_type` ("table" or "graph").
    8. If "table", extract the `table_headers` and `table_rows`.
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuestionDatabase,
                temperature=0.0
            ),
        )
        extracted_data = json.loads(response.text)
        return extracted_data.get("questions", [])
    finally:
        client.files.delete(name=uploaded_file.name)

def run_step1_chunk_extraction(full_path: str, client: genai.Client, chunk_size: int = 12) -> list:
    """Extracts text and table data by chunking the PDF to save RPD and RPM."""
    file_name = os.path.basename(full_path)
    print(f"\n📄 STEP 1: Processing {file_name} in {chunk_size}-page chunks...")
    
    doc = fitz.open(full_path)
    total_pages = len(doc)
    
    cache_dir = "chunk_cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    all_questions = []
    
    for start_page in range(0, total_pages, chunk_size):
        end_page = min(start_page + chunk_size - 1, total_pages - 1)
        cache_file = os.path.join(cache_dir, f"{file_name}_pages_{start_page}_{end_page}.json")
        
        if os.path.exists(cache_file):
            print(f"  -> Skipping pages {start_page + 1}-{end_page + 1} (Loaded from cache)")
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_questions = json.load(f)
            all_questions.extend(cached_questions)
            continue
            
        print(f"  -> Sending pages {start_page + 1} to {end_page + 1} to API...")
        
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
        chunk_filename = f"temp_chunk_{start_page}.pdf"
        chunk_doc.save(chunk_filename)
        chunk_doc.close()
        
        try:
            questions = process_pdf_chunk(chunk_filename, client)
            
            # Post process table data right away
            for q in questions:
                q_dict = q if isinstance(q, dict) else q.model_dump()
                visual_data = q_dict.pop("visual_data", None)
                if visual_data and visual_data.get("has_visual"):
                    if visual_data.get("visual_type") == "table":
                        q_dict["table_data"] = {
                            "headers": visual_data.get("table_headers", []),
                            "rows": visual_data.get("table_rows", [])
                        }
                    # We save the visual_type temporarily so Step 2 knows what to do
                    q_dict["_temp_visual_type"] = visual_data.get("visual_type")
                
                # Replace the original object with the dict
                idx = questions.index(q)
                questions[idx] = q_dict

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(questions, f, indent=2, ensure_ascii=False)
                
            all_questions.extend(questions)
            print(f"     ✅ Extracted {len(questions)} questions.")
            
        except Exception as e:
            print(f"     ❌ API Error on chunk {start_page}-{end_page}: {e}")
            if os.path.exists(chunk_filename):
                os.remove(chunk_filename)
            doc.close()
            exit(1)
            
        finally:
            if os.path.exists(chunk_filename):
                os.remove(chunk_filename)
        
        # 10 second cooldown to respect 15 RPM
        print("     ⏳ 10-second cooldown...")
        time.sleep(10)
        
    doc.close()
    return all_questions


def run_step2_graph_extraction(questions: list, pdf_path: str, client: genai.Client, images_dir: str):
    """Iterates through questions that need a graph and processes only those specific pages."""
    file_name = os.path.basename(pdf_path)
    print(f"\n🖼️ STEP 2: Extracting graphs for {file_name}...")
    
    graphs_to_process = [q for q in questions if q.get("_temp_visual_type") == "graph" and "image_url" not in q]
    print(f"  -> Found {len(graphs_to_process)} questions with graphs.")
    
    if not graphs_to_process:
        return questions
        
    doc = fitz.open(pdf_path)
    
    for i, q in enumerate(graphs_to_process):
        print(f"  -> [{i+1}/{len(graphs_to_process)}] Extracting graph for {q['question_id']}...")
        
        page_num = find_question_in_pdfs(q['question_id'], pdf_path)
        if page_num is None:
            print(f"     ⚠️ Could not find question ID in PDF!")
            continue
            
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img_data = pix.tobytes("png")
        
        temp_img_path = f"temp_graph_page_{q['question_id']}.png"
        with open(temp_img_path, "wb") as f:
            f.write(img_data)
            
        uploaded_file = client.files.upload(file=temp_img_path)
        prompt = f"""
        Here is a page from an SAT test. It contains a question with ID: {q['question_id']}.
        Identify the graph/diagram for this question and provide its bounding_box as [ymin, xmin, ymax, xmax] normalized from 0 to 1000.
        The bounding box MUST ONLY cover the graph/diagram/image itself. DO NOT include the question text or options.
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BoundingBoxExtraction,
                    temperature=0.0
                ),
            )
            
            result = json.loads(response.text)
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
                
                image_filename = f"{q['question_id']}.png"
                image_path = os.path.join(images_dir, image_filename)
                cropped_img.save(image_path)
                
                q["image_url"] = f"/images/questions/{image_filename}"
                print(f"     ✅ Saved cropped image.")
            else:
                print(f"     ⚠️ No bounding box found.")
                
        except Exception as e:
            print(f"     ❌ API Error: {e}")
        finally:
            client.files.delete(name=uploaded_file.name)
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
                
        # 5 second cooldown for graph extraction to respect RPM
        time.sleep(5)
        
    doc.close()
    
    # Cleanup temp field
    for q in questions:
        q.pop("_temp_visual_type", None)
        
    return questions


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_folder = os.path.join(script_dir, "PDFs", "Questions", "2nd_Batch")
    output_file = os.path.join(script_dir, "questions_database_2nd_batch.json")
    
    sat_practice_platform_dir = os.path.join(script_dir, "..", "SAT PRACTICE PLATFORM")
    if os.path.exists(sat_practice_platform_dir):
        images_dir = os.path.join(sat_practice_platform_dir, "public", "images", "questions")
    else:
        images_dir = os.path.join(script_dir, "public", "images", "questions")
    os.makedirs(images_dir, exist_ok=True)
        
    if not os.path.exists(input_folder):
        print(f"❌ Error: Folder '{input_folder}' not found.")
    else:
        pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print(f"⚠️ No PDF files found in '{input_folder}'.")
        else:
            client = genai.Client()
            final_database = []
            
            for file_name in pdf_files:
                full_path = os.path.join(input_folder, file_name)
                
                # Step 1: Chunk extraction (Heavy lift, but chunked to save RPD)
                questions = run_step1_chunk_extraction(full_path, client, chunk_size=12)
                
                # Step 2: Targeted visual extraction (Only exactly what is needed)
                questions = run_step2_graph_extraction(questions, full_path, client, images_dir)
                
                final_database.extend(questions)
                
            # Write final unified database
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(final_database, f, indent=2, ensure_ascii=False)
                
            print(f"\n🏁 BATCH COMPLETE: All PDFs processed. Saved to {output_file}")
