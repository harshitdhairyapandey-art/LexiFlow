import os
import time
import shutil
from pathlib import Path
from ai_provider import get_ai_provider

# --- SETTINGS ---
BASE_DIR = Path("LexiFlow")
INPUT_FOLDER = BASE_DIR / "2_extracted_chunks"
OUTPUT_FOLDER = BASE_DIR / "3_translated_chunks"
CORRUPT_FOLDER = BASE_DIR / "ERROR_FILES"

# API Timing
COOLDOWN = 12
RETRY_WAIT = 10
MAX_RETRIES = 3

# --- DEFAULT MASTER PROMPT ---
DEFAULT_PROMPT = """
You are a world-class Hindi literary translator producing a professionally published novel.

RULES:
1. SCRIPT: 100% Devanagari only. Zero English alphabet in output.
2. COMPLETENESS: Translate EVERY single sentence without exception. Never skip, summarize, or shorten.
3. TONE: Modern Urban Hindi (Hindustani) — natural, engaging, and emotionally rich.
4. LOAN WORDS: Transliterate to Devanagari (e.g., 'Office' → 'ऑफिस', 'Sequence' → 'सीक्वेंस').
5. CHARACTER NAMES: Transliterate exactly (e.g., 'Klein' → 'क्लेन', 'Audrey' → 'ऑड्री').
6. TONE MATCHING: Dramatic moments stay dramatic. Humor stays humorous. Tension stays tense.
7. FORMATTING: Double newline between paragraphs. Match original structure exactly.
8. FLOW: Write like a native Hindi novel author — smooth, immersive, page-turning prose.

Output translated text ONLY. No commentary, notes, or explanations.
"""
# --- ENGINE INITIALIZATION ---
def init_engine(provider_type="gemini", api_key=None, model_name=None):
    """
    Initializes the AI provider.
    Returns a tuple (type, provider_object, model) for the Master Engine.
    """
    if not api_key:
        raise ValueError("❌ No API key provided.")
    if not model_name:
        raise ValueError("❌ No model name provided.")

    try:
        provider = get_ai_provider(provider_type, api_key, model_name)
        return (provider_type, provider, model_name)
    except Exception as e:
        raise ValueError(f"❌ Failed to initialize {provider_type}: {e}")

# --- TRANSLATION FUNCTION ---
def translate_chunk(engine, prompt, text):
    """
    Matched signature for engine.py: (engine, prompt, text).
    """
    provider_type, provider, model_name = engine
    try:
        return provider.generate_content(
            system_prompt=prompt,
            user_text=text,
            temperature=0.7
        )
    except Exception as e:
        raise Exception(f"Translation Error ({provider_type}): {str(e)}")

# --- STANDALONE BATCH PROCESSOR ---
def process_precise_batches(engine, prompt=DEFAULT_PROMPT, chunks_per_batch=1):
    """
    Can be run independently or called by the engine.
    """
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    CORRUPT_FOLDER.mkdir(parents=True, exist_ok=True)

    all_x_files = sorted(list(INPUT_FOLDER.glob("chunk_*.txt")))

    for i in range(0, len(all_x_files), chunks_per_batch):
        current_pair = all_x_files[i : i + chunks_per_batch]
        batch_id = (i // chunks_per_batch) + 1
        target_y_file = OUTPUT_FOLDER / f"y{batch_id:03d}.txt"

        if target_y_file.exists():
            continue

        batch_results = []
        for file_path in current_pair:
            chunk_success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    print(f"📖 Translating {file_path.name} (Attempt {attempt})...")
                    raw_text = file_path.read_text(encoding="utf-8")
                    translated_text = translate_chunk(engine, prompt, raw_text)
                    batch_results.append(translated_text.strip())
                    time.sleep(COOLDOWN)
                    chunk_success = True
                    break
                except Exception as e:
                    print(f"⚠️ Error on {file_path.name}: {e}")
                    time.sleep(RETRY_WAIT + (attempt * 5))

            if not chunk_success:
                print(f"❌ FAILED: {file_path.name} copied to ERROR_FILES.")
                shutil.copy(str(file_path), str(CORRUPT_FOLDER / f"FAILED_{file_path.name}"))
                batch_results.append(f"\n[SECTION ERROR: {file_path.name} could not be translated]\n")

        if batch_results:
            target_y_file.write_text("\n\n".join(batch_results), encoding="utf-8")
            print(f"🌟 BATCH READY: {target_y_file.name}")

if __name__ == "__main__":
    p_type = input("Provider (gemini/lightning): ").strip().lower()
    key = input("API Key: ").strip()
    model = input("Model Name: ").strip()

    engine_obj = init_engine(provider_type=p_type, api_key=key, model_name=model)
    process_precise_batches(engine_obj)