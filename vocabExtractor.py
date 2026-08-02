import os
import json
import time
import fitz  # PyMuPDF
from typing import List
from pydantic import BaseModel, Field
from google import genai
from dotenv import load_dotenv
from google.genai import types

load_dotenv()

# 1. Pydantic Schemas
class VocabularyWord(BaseModel):
    word: str = Field(description="The vocabulary word being defined")
    meaning: str = Field(description="The definition or meaning of the word")

class VocabularyDatabase(BaseModel):
    words: List[VocabularyWord]


# 2. Processing Logic
def process_pdf_chunk(pdf_chunk_path: str, client: genai.Client) -> list:
    """Uploads and processes a single PDF chunk via Gemini Vision."""
    uploaded_file = client.files.upload(file=pdf_chunk_path)
    
    prompt = """
    You are an expert data extraction pipeline. Read this SAT Vocabulary PDF chunk and extract EVERY vocabulary word and its exact definition/meaning.
    
    CRITICAL RULES:
    1. Ensure the meaning accurately reflects the definition given in the text.
    2. Maintain accurate spelling.
    3. If there are example sentences, do NOT include them in the meaning unless it's necessary for the definition. Just give the core definition.
    """

    response = client.models.generate_content(
        model='gemini-3.5-flash-lite',
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VocabularyDatabase,
            temperature=0.0
        ),
    )

    extracted_data = json.loads(response.text)
    client.files.delete(name=uploaded_file.name)
    
    return extracted_data.get("words", [])


def chunk_and_process_pdf(full_path: str, output_path: str, chunk_size: int = 12):
    """Splits PDF, caches progress locally, and live-updates the target JSON."""
    file_name = os.path.basename(full_path)
    print(f"\n📄 Processing {file_name} in {chunk_size}-page chunks...")
    
    client = genai.Client()
    doc = fitz.open(full_path)
    total_pages = len(doc)
    
    # Setup caching directory to prevent lost progress
    cache_dir = "vocab_chunk_cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    all_words = []
    
    for start_page in range(0, total_pages, chunk_size):
        end_page = min(start_page + chunk_size - 1, total_pages - 1)
        cache_file = os.path.join(cache_dir, f"{file_name}_pages_{start_page}_{end_page}.json")
        
        # Auto-Resume: Check if this chunk was already successfully processed
        if os.path.exists(cache_file):
            print(f"  -> Skipping pages {start_page + 1}-{end_page + 1} (Loaded from cache)")
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_words = json.load(f)
            all_words.extend(cached_words)
            continue
            
        print(f"  -> Sending pages {start_page + 1} to {end_page + 1} to API...")
        
        # Generate temporary PDF chunk
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
        chunk_filename = f"vocab_temp_chunk_{start_page}.pdf"
        chunk_doc.save(chunk_filename)
        chunk_doc.close()
        
        try:
            words = process_pdf_chunk(chunk_filename, client)
            
            # Save strictly to chunk cache
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(words, f, indent=2, ensure_ascii=False)
                
            all_words.extend(words)
            print(f"     ✅ Extracted {len(words)} words.")
            
        except Exception as e:
            print(f"     ❌ API Error on chunk {start_page}-{end_page}: {e}")
            print(f"     🛑 Execution halted. Run the script again to resume from this exact point.")
            os.remove(chunk_filename)
            doc.close()
            exit(1) # Immediately exit so the user can see the error
            
        finally:
            if os.path.exists(chunk_filename):
                os.remove(chunk_filename)
        
        # Live-update the main output file so you can inspect it in parallel
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_words, f, indent=2, ensure_ascii=False)
            
        print("     ⏳ 15-second cooldown to bypass rate limits...")
        time.sleep(15)
        
    doc.close()
    print(f"🎯 SUCCESS: Compiled {len(all_words)} words for {file_name}")


# 3. Batch Execution
if __name__ == "__main__":
    input_folder = os.path.join("PDFs", "Vocabulary")
    output_file = "vocabulary_database.json"
    
    if not os.path.exists(input_folder):
        print(f"❌ Error: Folder '{input_folder}' not found.")
    else:
        pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]
        if not pdf_files:
            print(f"⚠️ No PDF files found in '{input_folder}'.")
        else:
            final_database = []
            
            for file_name in pdf_files:
                full_path = os.path.join(input_folder, file_name)
                temp_output = f"temp_vocab_{file_name}.json"
                
                # Execute chunking processor
                chunk_and_process_pdf(full_path, temp_output, chunk_size=12)
                
                # Merge into master sequence
                if os.path.exists(temp_output):
                    with open(temp_output, "r", encoding="utf-8") as temp_file:
                        final_database.extend(json.load(temp_file))
                
            # Write final unified database
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(final_database, f, indent=2, ensure_ascii=False)
                
            print(f"\n🏁 BATCH COMPLETE: All vocabulary PDFs processed. Saved to {output_file}")
