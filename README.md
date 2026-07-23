# SAT Question Scraper & Exam Generator

This project is a suite of tools designed to analyze PDF files containing SAT question banks, extract the questions into a structured format using AI, and generate non-overlapping, realistic static exam suites.

## Features

1. **PDF Question Extraction (`sat_parser.py`)**
   - Reads SAT Question Bank PDFs (e.g., from the `PDFs` directory).
   - Utilizes Google's Gemini Vision AI to accurately parse and extract questions, options, and explanations.
   - Automatically converts mathematical symbols, equations, and expressions into standard LaTeX.
   - Categorizes questions by section (Reading and Writing, Math), domain, skill, and difficulty.
   - Outputs the structured data to a centralized `questions_database.json` file.

2. **Exam Suite Generation (`generate_exam_suites.py`)**
   - Consumes the `questions_database.json`.
   - Generates deterministic, non-overlapping static exams simulating the structure of the digital SAT.
   - Distributes questions according to specific module constraints (e.g., 30% Easy, 50% Medium, 20% Hard for Module 1).
   - Outputs the final exams to be consumed by a frontend platform.

## Project Structure

- `sat_parser.py`: The main script for parsing PDFs using Gemini.
- `generate_exam_suites.py`: Script to generate exam suites from the extracted database.
- `questions_database.json`: The central database of all extracted SAT questions.
- `PDFs/`: Directory containing the source SAT Question Bank PDFs.
- `chunk_cache/`: Directory used for caching PDF chunks during processing.
- `.env`: Environment variables configuration file (e.g., API keys).

## Prerequisites

- Python 3.x
- Google Gemini API Key

## Setup

1. Clone the repository.
2. Install the required Python packages (e.g., `PyMuPDF` (fitz), `pydantic`, `google-genai`, `python-dotenv`).
3. Create a `.env` file in the root directory and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```
4. Place your source PDFs in the `PDFs` directory.

## Usage

### 1. Extract Questions
To parse the PDFs and update the question database, run:
```bash
python sat_parser.py
```

### 2. Generate Exams
To generate static exam suites from the database, run:
```bash
python generate_exam_suites.py
```
