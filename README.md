# SAT Question Scraper & Exam Generator

> **Note:** This project is a data scraper designed to feed questions into the main platform: [LibreSAT](https://github.com/adriangbustos/LibreSAT).

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

3. **Visual Data Extraction (`extract_visuals.py`)**
   - Identifies and extracts visual elements (graphs, charts, diagrams, tables) from the PDFs.

4. **Vocabulary Extraction (`extract_vocabulary.py`)**
   - Processes vocabulary PDFs to extract words and their definitions using AI.
   - Outputs a structured `vocabulary_database.json` to be used for flashcards.

## Project Structure

- `sat_parser.py`: The main script for parsing PDFs using Gemini.
- `generate_exam_suites.py`: Script to generate exam suites from the extracted database.
- `extract_visuals.py`: Script for extracting questions with graphs, charts, and tables.
- `extract_vocabulary.py`: Script to parse vocabulary words and definitions from PDFs.
- `questions_database.json`: The central database of all extracted SAT questions.
- `vocabulary_database.json`: Database containing extracted vocabulary words.
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

## Limitations

As this project relies heavily on AI (Google Gemini) for the data extraction process, there may be some minor mistakes. These typically include:
- **Image Cropping issues** when isolating charts or graphs.
- **Repeated text** between the stimulus and the question.
- **Formatting inconsistencies**.

However, there shouldn't be any major issues such as incorrect questions or answers, as the AI is constrained to accurately parse the provided text.

Note: This project uses the PDFs from College Board's Question Bank. If you wish to use another PDF with questions, there may be mistakes.
