import os
import time
import shutil
from pathlib import Path
from dotenv import load_dotenv
from ai_provider import get_ai_provider

# --- PATHS ---
BASE_DIR = Path("LexiFlow")
TRANS_FOLDER = BASE_DIR / "3_translated_chunks"
PRO_FOLDER = BASE_DIR / "4_polished_output"
ERROR_FOLDER = BASE_DIR / "ERROR_FILES"



# --- SETTINGS ---
COOLDOWN = 15  # Slightly lower for polishing batches
RETRY_WAIT = 15
MAX_RETRIES = 2
CHUNKS_PER_BATCH = 1
DEFAULT_PROMPT = """
You are a senior Hindi literary editor polishing a translated novel for professional publication.

RULES:
1. SCRIPT: 100% Devanagari only. Zero English alphabet in output.
2. PRESERVE: Do not add, remove, or summarize any content. Only improve language quality.
3. FLOW: Fix awkward phrasing so it reads like an originally written Hindi novel.
4. TONE: Maintain dramatic, emotional, and atmospheric tone throughout.
5. TERMS: Keep ALL Beyonder terms exactly as they appear in input — do NOT translate or replace terms like 'सील्ड आर्टिफैक्ट', 'सीक्वेंस', 'बियोंडर' etc. into Hindi equivalents.
6. NAMES: Keep all character names exactly as given in Devanagari.
7. FORMATTING: Preserve all paragraph breaks and structure from input.

Output polished Hindi text ONLY. No commentary or explanations.
"""
# --- ENGINE INITIALIZATION ---
def init_engine(provider_type="gemini", api_key=None, model_name=None):
    """
    Initialize any AI provider.
    Returns a tuple (type, provider, model) for the Master Engine.
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

# --- POLISH FUNCTION (FIXED SIGNATURE) ---
def polish_chunk(engine, prompt, text):
    """
    Matched signature for engine.py orchestration: (engine, prompt, text).
    """
    provider_type, provider, model_name = engine
    
    try:
        result = provider.generate_content(
            system_prompt=prompt,
            user_text=text,
            temperature=0.3
        )
        if result and result.strip():
            return result.strip()
        else:
            raise Exception(f"{provider_type} returned empty response")
    except Exception as e:
        raise Exception(f"Polish Error ({provider_type}): {str(e)}")

# --- BATCH PROCESSOR ---
def process_polish_batches(engine, prompt=DEFAULT_PROMPT):
    """
    Standalone processor for refining translated files.
    """
    PRO_FOLDER.mkdir(parents=True, exist_ok=True)
    ERROR_FOLDER.mkdir(parents=True, exist_ok=True)
    all_files = sorted(list(TRANS_FOLDER.glob("y*.txt")))
    if not all_files:
        print("❌ No files found in 3_translated_chunks.")
        return

    for i in range(0, len(all_files), CHUNKS_PER_BATCH):
        current_pair = all_files[i : i + CHUNKS_PER_BATCH]
        batch_id = (i // CHUNKS_PER_BATCH) + 1
        target_file = PRO_FOLDER / f"y{batch_id:03d}.txt"

        if target_file.exists():
            continue

        batch_results = []
        for file_path in current_pair:
            chunk_success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    print(f"✨ Polishing {file_path.name} (Attempt {attempt})...")
                    raw_text = file_path.read_text(encoding="utf-8")
                    
                    # Using the matched signature
                    polished_text = polish_chunk(engine, prompt, raw_text)
                    
                    batch_results.append(polished_text.strip())
                    time.sleep(COOLDOWN)
                    chunk_success = True
                    break
                except Exception as e:
                    print(f"⚠️ Error on {file_path.name}: {e}")
                    time.sleep(RETRY_WAIT + (attempt * 5))

            if not chunk_success:
                print(f"❌ FAILED: {file_path.name} moved to ERROR_FILES.")
                shutil.copy(str(file_path), str(ERROR_FOLDER / f"PRO_FAILED_{file_path.name}"))
                batch_results.append(f"\n[SECTION ERROR: {file_path.name} could not be polished]\n")

        if batch_results:
            target_file.write_text("\n\n".join(batch_results), encoding="utf-8")
            print(f"🌟 BATCH READY: {target_file.name}")

if __name__ == "__main__":
    p_type = input("Enter provider (gemini/lightning): ").strip().lower()
    key = input("Enter API key: ").strip()
    model = input("Enter model name: ").strip()
    
    engine_obj = init_engine(provider_type=p_type, api_key=key, model_name=model)
    process_polish_batches(engine_obj)