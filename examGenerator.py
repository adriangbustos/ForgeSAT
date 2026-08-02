"""
SAT Static Exam Suite Generator
Generates non-overlapping static exams from questions_database.json
Output: sat-platform/public/exam_suites.json
"""

import json
import random
import math
from collections import defaultdict

random.seed(42)  # Deterministic output

# Load database
with open("questions_database.json", "r", encoding="utf-8") as f:
    all_questions = json.load(f)

# Separate by section
rw_questions = [q for q in all_questions if q["section"] == "Reading and Writing"]
math_questions = [q for q in all_questions if q["section"] == "Math"]

print(f"Total R&W: {len(rw_questions)}, Total Math: {len(math_questions)}")

# ──────────────────────────────────────────────────────────────────────────────
# DIFFICULTY DISTRIBUTION CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
# Module 1: 30% Easy, 50% Medium, 20% Hard
# Module 2 (Hard Route): 10% Easy, 30% Medium, 60% Hard

# R&W Module: 27 questions each
RW_MOD1_COUNT = 27
RW_MOD2_COUNT = 27

# Math Module: 22 questions each
MATH_MOD1_COUNT = 22
MATH_MOD2_COUNT = 22

def compute_split(count, easy_pct, med_pct, hard_pct):
    easy = round(count * easy_pct)
    hard = round(count * hard_pct)
    med = count - easy - hard
    return easy, med, hard

RW_M1_EASY, RW_M1_MED, RW_M1_HARD = compute_split(RW_MOD1_COUNT, 0.30, 0.50, 0.20)
RW_M2_EASY, RW_M2_MED, RW_M2_HARD = compute_split(RW_MOD2_COUNT, 0.10, 0.30, 0.60)
MATH_M1_EASY, MATH_M1_MED, MATH_M1_HARD = compute_split(MATH_MOD1_COUNT, 0.30, 0.50, 0.20)
MATH_M2_EASY, MATH_M2_MED, MATH_M2_HARD = compute_split(MATH_MOD2_COUNT, 0.10, 0.30, 0.60)

print(f"R&W Mod1 split: Easy={RW_M1_EASY}, Med={RW_M1_MED}, Hard={RW_M1_HARD} (total={RW_M1_EASY+RW_M1_MED+RW_M1_HARD})")
print(f"R&W Mod2 split: Easy={RW_M2_EASY}, Med={RW_M2_MED}, Hard={RW_M2_HARD} (total={RW_M2_EASY+RW_M2_MED+RW_M2_HARD})")
print(f"Math Mod1 split: Easy={MATH_M1_EASY}, Med={MATH_M1_MED}, Hard={MATH_M1_HARD} (total={MATH_M1_EASY+MATH_M1_MED+MATH_M1_HARD})")
print(f"Math Mod2 split: Easy={MATH_M2_EASY}, Med={MATH_M2_MED}, Hard={MATH_M2_HARD} (total={MATH_M2_EASY+MATH_M2_MED+MATH_M2_HARD})")

# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN DISTRIBUTION (proportional to database)
# ──────────────────────────────────────────────────────────────────────────────

def group_by(questions, key):
    result = defaultdict(list)
    for q in questions:
        result[q[key]].append(q)
    return result

def proportional_sample(pool_by_domain, total_count, used_ids, easy_count, med_count, hard_count):
    """
    Sample questions from pool maintaining difficulty distribution.
    Tries to maintain domain proportionality. Avoids used_ids.
    Returns list of question dicts.
    """
    available = [q for q in sum(pool_by_domain.values(), []) if q["question_id"] not in used_ids]
    
    easy_pool = [q for q in available if q["difficulty"] == "Easy"]
    med_pool = [q for q in available if q["difficulty"] == "Medium"]
    hard_pool = [q for q in available if q["difficulty"] == "Hard"]

    # Shuffle for randomness within deterministic seed
    random.shuffle(easy_pool)
    random.shuffle(med_pool)
    random.shuffle(hard_pool)

    selected = []
    selected += easy_pool[:easy_count]
    selected += med_pool[:med_count]
    selected += hard_pool[:hard_count]

    if len(selected) < total_count:
        # Fall back: take any remaining to fill
        remaining = [q for q in available if q not in selected]
        random.shuffle(remaining)
        selected += remaining[:total_count - len(selected)]

    return selected

# ──────────────────────────────────────────────────────────────────────────────
# COMPUTE MAX POSSIBLE EXAMS
# ──────────────────────────────────────────────────────────────────────────────

rw_by_domain = group_by(rw_questions, "domain")
math_by_domain = group_by(math_questions, "domain")

# Per-difficulty counts in each section
rw_by_diff = group_by(rw_questions, "difficulty")
math_by_diff = group_by(math_questions, "difficulty")

rw_easy_total = len(rw_by_diff["Easy"])
rw_med_total = len(rw_by_diff["Medium"])
rw_hard_total = len(rw_by_diff["Hard"])

math_easy_total = len(math_by_diff["Easy"])
math_med_total = len(math_by_diff["Medium"])
math_hard_total = len(math_by_diff["Hard"])

print(f"\nR&W by difficulty: Easy={rw_easy_total}, Med={rw_med_total}, Hard={rw_hard_total}")
print(f"Math by difficulty: Easy={math_easy_total}, Med={math_med_total}, Hard={math_hard_total}")

# Easy needed per full-length RW exam = M1_EASY + M2_EASY
rw_easy_per_exam = RW_M1_EASY + RW_M2_EASY
rw_med_per_exam = RW_M1_MED + RW_M2_MED
rw_hard_per_exam = RW_M1_HARD + RW_M2_HARD

math_easy_per_exam = MATH_M1_EASY + MATH_M2_EASY
math_med_per_exam = MATH_M1_MED + MATH_M2_MED
math_hard_per_exam = MATH_M1_HARD + MATH_M2_HARD

max_rw_exams = min(
    rw_easy_total // rw_easy_per_exam,
    rw_med_total // rw_med_per_exam,
    rw_hard_total // rw_hard_per_exam
)
max_math_exams = min(
    math_easy_total // math_easy_per_exam,
    math_med_total // math_med_per_exam,
    math_hard_total // math_hard_per_exam
)

# Full-length needs both
max_full_exams = min(max_rw_exams, max_math_exams)

print(f"\nMax non-overlapping R&W-only exams: {max_rw_exams}")
print(f"Max non-overlapping Math-only exams: {max_math_exams}")
print(f"Max non-overlapping Full-Length exams: {max_full_exams}")

# ──────────────────────────────────────────────────────────────────────────────
# GENERATE STATIC EXAM SUITES
# ──────────────────────────────────────────────────────────────────────────────

def build_module(section_questions, mod_easy, mod_med, mod_hard, used_ids):
    """Build a single module of questions, updating used_ids in place."""
    available = [q for q in section_questions if q["question_id"] not in used_ids]
    
    easy_pool = [q for q in available if q["difficulty"] == "Easy"]
    med_pool = [q for q in available if q["difficulty"] == "Medium"]
    hard_pool = [q for q in available if q["difficulty"] == "Hard"]

    random.shuffle(easy_pool)
    random.shuffle(med_pool)
    random.shuffle(hard_pool)

    selected = easy_pool[:mod_easy] + med_pool[:mod_med] + hard_pool[:mod_hard]
    total_needed = mod_easy + mod_med + mod_hard

    if len(selected) < total_needed:
        remaining = [q for q in available if q["question_id"] not in {s["question_id"] for s in selected}]
        random.shuffle(remaining)
        selected += remaining[:total_needed - len(selected)]

    # Shuffle within module for realistic presentation
    random.shuffle(selected)
    
    for q in selected:
        used_ids.add(q["question_id"])
    
    return [q["question_id"] for q in selected]


# Global used sets (full non-overlap guarantee WITHIN each suite type)
# For full-length exams: use questions once across all full-length exams
# For diagnostic (RW-only): use a separate pool
# For diagnostic (Math-only): use a separate pool

rw_full_used = set()      # used in full-length exams (RW portion)
math_full_used = set()    # used in full-length exams (Math portion)
rw_diag_used = set()      # used in RW-only diagnostics
math_diag_used = set()    # used in Math-only diagnostics

full_length_exams = []
rw_diagnostic_exams = []
math_diagnostic_exams = []

# --- FULL LENGTH EXAMS ---
for i in range(max_full_exams):
    rw_mod1 = build_module(rw_questions, RW_M1_EASY, RW_M1_MED, RW_M1_HARD, rw_full_used)
    rw_mod2 = build_module(rw_questions, RW_M2_EASY, RW_M2_MED, RW_M2_HARD, rw_full_used)
    math_mod1 = build_module(math_questions, MATH_M1_EASY, MATH_M1_MED, MATH_M1_HARD, math_full_used)
    math_mod2 = build_module(math_questions, MATH_M2_EASY, MATH_M2_MED, MATH_M2_HARD, math_full_used)
    
    if len(rw_mod1) < RW_MOD1_COUNT or len(rw_mod2) < RW_MOD2_COUNT:
        print(f"  ⚠️  Full exam {i+1}: RW pool exhausted, stopping.")
        break
    if len(math_mod1) < MATH_MOD1_COUNT or len(math_mod2) < MATH_MOD2_COUNT:
        print(f"  ⚠️  Full exam {i+1}: Math pool exhausted, stopping.")
        break

    full_length_exams.append({
        "exam_id": f"full_{i+1}",
        "label": f"Full-Length Exam {i+1}",
        "type": "full",
        "modules": [
            {"module_num": 1, "section": "Reading and Writing", "time_minutes": 32, "question_ids": rw_mod1},
            {"module_num": 2, "section": "Reading and Writing", "time_minutes": 32, "question_ids": rw_mod2},
            {"module_num": 3, "section": "Math", "time_minutes": 35, "question_ids": math_mod1},
            {"module_num": 4, "section": "Math", "time_minutes": 35, "question_ids": math_mod2},
        ]
    })
    print(f"  [OK] Full-Length Exam {i+1}: RW({len(rw_mod1)}+{len(rw_mod2)}) Math({len(math_mod1)}+{len(math_mod2)})")

# --- R&W DIAGNOSTIC EXAMS ---
for i in range(max_rw_exams):
    rw_mod1 = build_module(rw_questions, RW_M1_EASY, RW_M1_MED, RW_M1_HARD, rw_diag_used)
    rw_mod2 = build_module(rw_questions, RW_M2_EASY, RW_M2_MED, RW_M2_HARD, rw_diag_used)
    
    if len(rw_mod1) < RW_MOD1_COUNT or len(rw_mod2) < RW_MOD2_COUNT:
        print(f"  ⚠️  R&W Diagnostic {i+1}: pool exhausted, stopping.")
        break

    rw_diagnostic_exams.append({
        "exam_id": f"rw_{i+1}",
        "label": f"Reading & Writing Diagnostic {i+1}",
        "type": "rw",
        "modules": [
            {"module_num": 1, "section": "Reading and Writing", "time_minutes": 32, "question_ids": rw_mod1},
            {"module_num": 2, "section": "Reading and Writing", "time_minutes": 32, "question_ids": rw_mod2},
        ]
    })
    print(f"  ✅ R&W Diagnostic {i+1}: Mod1={len(rw_mod1)}, Mod2={len(rw_mod2)}")

# --- MATH DIAGNOSTIC EXAMS ---
for i in range(max_math_exams):
    math_mod1 = build_module(math_questions, MATH_M1_EASY, MATH_M1_MED, MATH_M1_HARD, math_diag_used)
    math_mod2 = build_module(math_questions, MATH_M2_EASY, MATH_M2_MED, MATH_M2_HARD, math_diag_used)
    
    if len(math_mod1) < MATH_MOD1_COUNT or len(math_mod2) < MATH_MOD2_COUNT:
        print(f"  ⚠️  Math Diagnostic {i+1}: pool exhausted, stopping.")
        break

    math_diagnostic_exams.append({
        "exam_id": f"math_{i+1}",
        "label": f"Math Diagnostic {i+1}",
        "type": "math",
        "modules": [
            {"module_num": 1, "section": "Math", "time_minutes": 35, "question_ids": math_mod1},
            {"module_num": 2, "section": "Math", "time_minutes": 35, "question_ids": math_mod2},
        ]
    })
    print(f"  ✅ Math Diagnostic {i+1}: Mod1={len(math_mod1)}, Mod2={len(math_mod2)}")

# ──────────────────────────────────────────────────────────────────────────────
# COMPILE AND WRITE OUTPUT
# ──────────────────────────────────────────────────────────────────────────────

output = {
    "generated_at": "2026-07-23",
    "full_length": full_length_exams,
    "rw_diagnostic": rw_diagnostic_exams,
    "math_diagnostic": math_diagnostic_exams,
    "stats": {
        "full_length_count": len(full_length_exams),
        "rw_diagnostic_count": len(rw_diagnostic_exams),
        "math_diagnostic_count": len(math_diagnostic_exams),
        "total_questions": len(all_questions),
        "rw_questions": len(rw_questions),
        "math_questions": len(math_questions)
    }
}

output_path = "sat-platform/public/exam_suites.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, separators=(',', ':'))

print(f"\n🏁 Done!")
print(f"   Full-Length Exams: {len(full_length_exams)}")
print(f"   R&W Diagnostics: {len(rw_diagnostic_exams)}")
print(f"   Math Diagnostics: {len(math_diagnostic_exams)}")
print(f"   Written to: {output_path}")
print(f"   File size: {len(json.dumps(output)):,} bytes")
