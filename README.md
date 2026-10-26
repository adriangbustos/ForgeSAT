# ForgeSAT

[![Companion Platform](https://img.shields.io/badge/Companion_Platform-LibreSAT-blue?style=for-the-badge&logo=netlify)](https://libresat.netlify.app/)

An automated question extraction, LaTeX formatting, and standardized digital exam generation pipeline built in Python and powered by Google Gemini Vision. Serves as the extraction engine feeding [LibreSAT](https://github.com/adriangbustos/LibreSAT).

<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Google_Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white" alt="Google Gemini" />
  <img src="https://img.shields.io/badge/LaTeX-008080?style=for-the-badge" alt="LaTeX" />
  <img src="https://img.shields.io/badge/PDFPlumber-E0234E?style=for-the-badge" alt="PDFPlumber" />
  <img src="https://img.shields.io/badge/License-MIT-44CC11?style=for-the-badge" alt="MIT License" />
</div>

---

## Architecture Overview

```
                      ┌───────────────────────────┐
                      │  College Board SAT PDFs   │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │    unifiedExtractor.py    │
                      │  (Gemini Multimodal AI)   │
                      └─────────────┬─────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
       ┌────────────────────────┐      ┌────────────────────────┐
       │     table_fixer.py     │      │   vocabExtractor.py    │
       │ (Tabular Data & Visuals│      │  (Vocabulary Flashcards│
       └────────────┬───────────┘      └────────────┬───────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                      ┌───────────────────────────┐
                      │     examGenerator.py      │
                      │ (Constraint-based Sampler)│
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │   LibreSAT Web Platform   │
                      └───────────────────────────┘
```

---

## Key Modules

### 1. Unified Question Extractor (`unifiedExtractor.py`)
- Ingests raw College Board question bank PDFs.
- Multimodal parsing with Gemini converts inline mathematical symbols, geometry formulas, and exponents into clean LaTeX notation.
- Categorizes questions by section (Reading and Writing, Math), domain, skill, and difficulty tier.

### 2. Tabular & Visual Data Normalizer (`table_fixer.py`)
- Recovers, cleans, and standardizes extracted HTML/Markdown tables from PDF visual regions.
- Preserves layout fidelity for reading comprehension passages and math data representations.

### 3. Exam Suite Generator (`examGenerator.py`)
- Consumes the processed question database to sample realistic Digital SAT exam suites.
- Applies College Board module distribution constraints (e.g. 30% Easy, 50% Medium, 20% Hard) with zero cross-test question overlap.

### 4. Vocabulary Extractor (`vocabExtractor.py`)
- Extracts advanced academic vocabulary in context with definitions and sample sentences for flashcards.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Google Gemini API Key

### Setup
```bash
# Clone the repository
git clone https://github.com/adriangbustos/ForgeSAT.git
cd ForgeSAT

# Set up environment variables
echo "GEMINI_API_KEY=your_key_here" > .env
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
