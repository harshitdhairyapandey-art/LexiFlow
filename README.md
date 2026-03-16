# LexiFlow v1.0.0
### Universal AI Novel Translation Pipeline

> *From raw English novel to publication-quality Hindi prose — fully automated, context-aware, resumable, and provider-agnostic.*

---

## Table of Contents

1. [What is LexiFlow?](#what-is-lexiflow)
2. [Why It Exists](#why-it-exists)
3. [Architecture Overview](#architecture-overview)
4. [The Pipeline — Phase by Phase](#the-pipeline--phase-by-phase)
   - [Phase 0: Ingestion](#phase-0-ingestion)
   - [Phase 1: Preprocessing](#phase-1-preprocessing)
   - [Phase 2: Translation (Flash)](#phase-2-translation-flash)
   - [Phase 3: Polish (Pro)](#phase-3-polish-pro)
   - [Phase 4: Export](#phase-4-export)
5. [The Two-Engine Design](#the-two-engine-design)
6. [Context Injection System](#context-injection-system)
7. [Chapter-Aware Temperature](#chapter-aware-temperature)
8. [Glossary System](#glossary-system)
9. [Error Handling Architecture](#error-handling-architecture)
10. [Provider System](#provider-system)
11. [Batch System](#batch-system)
12. [Database & Run History](#database--run-history)
13. [File Structure](#file-structure)
14. [Supported Providers & Models](#supported-providers--models)
15. [Configuration](#configuration)
16. [Quick Start](#quick-start)
17. [Known Limitations](#known-limitations)
18. [Design Philosophy](#design-philosophy)

---

## What is LexiFlow?

LexiFlow is a production-grade AI pipeline for translating novels from English to Hindi. It is not a simple "send text to API" wrapper. It is a multi-stage, context-aware, fault-tolerant orchestration system that:

- Breaks a novel into semantically meaningful chunks
- Analyzes each chapter's emotional arc, character states, and narrative structure before translation
- Translates using a fast "Flash" model with full context injection
- Polishes the translation using a more powerful "Pro" model with literary editorial freedom
- Handles API failures, rate limits, and network errors with intelligent retry logic
- Resumes interrupted runs from exactly where they stopped
- Tracks every batch, every retry, every error in a SQLite database
- Exports to DOCX, PDF, or EPUB

---

## Why It Exists

Raw LLM translation produces output that reads like a translation — stiff, literal, vocabulary-poor. The problem is not the model's capability, it is the lack of context. A model translating Chapter 47 does not know what happened in Chapter 1. It does not know that a character speaks in a formal register. It does not know the emotional arc of the volume. It does not know which fantasy terms should be transliterated vs translated.

LexiFlow solves this by building a **context layer** before translation begins. The preprocessing stage reads the entire novel and produces per-chapter metadata — emotional timelines, character states, sentence type analysis, glossary of terms, character voice profiles, forbidden repetition patterns — which is then injected into every translation and polish prompt.

The result is translation that reads like it was originally written in Hindi.

---

## Architecture Overview

```
Input Novel (PDF/DOCX/EPUB/TXT)
         │
         ▼
┌─────────────────────┐
│   INGESTION ENGINE  │  Splits novel into chapters → chunks
│   (ingestion.py)    │  Writes chunk files + JSON manifests
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  PREPROCESSING      │  Analyzes chapters with Gemini
│  (preprocessing.py) │  Builds: glossary, character voices,
│                     │  chapter metas, volume flow, forbidden patterns
└─────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  MASTER ENGINE (engine.py)           │
│                                                     │
│  ┌──────────────┐         ┌──────────────────────┐  │
│  │  FLASH ENGINE│ ──────► │    PRO ENGINE        │  │
│  │ (flash.py)   │         │    (pro.py)          │  │
│  │              │         │                      │  │
│  │ Fast model   │         │ Powerful model       │  │
│  │ Translation  │         │ Literary polish      │  │
│  │ + context    │         │ + editorial freedom  │  │
│  └──────────────┘         └──────────────────────┘  │
│                                                     │
│  Error handling ◄──── errors.py                     │
│  Run tracking   ◄──── store.py (SQLite)             │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────┐
│   EXPORT ENGINE     │  Merges polished chunks
│   (Exporters.py)    │  Outputs DOCX / PDF / EPUB
└─────────────────────┘
```

---

## The Pipeline — Phase by Phase

### Phase 0: Ingestion

**File:** `ingestion.py`

The ingestion engine reads the source novel and splits it into chunks. It:

1. Detects file format (PDF, DOCX, EPUB, TXT) and extracts raw text
2. Identifies chapter boundaries using heading patterns (`Chapter N:`, `अध्याय N`, etc.)
3. Groups chapters into chunks respecting the `chunk_size` parameter (default: 3,000 chars)
4. Writes each chunk as a `.txt` file in `LexiFlow/2_extracted_chunks/`
5. Writes a `.json` manifest alongside each chunk containing: chapter numbers, headings, char count, source file info
6. Records the book in the SQLite store with total chapters, chunks, file size

**Why chunks instead of chapters?** Chapters vary wildly in length. A 500-char chapter and a 15,000-char chapter need different handling. Chunks normalize the input so every API call is within a predictable size range.

**Output:**
```
LexiFlow/2_extracted_chunks/
  chunk_0001.txt
  chunk_0001.json   ← manifest: {chapters: [{num, heading, char_count}]}
  chunk_0002.txt
  chunk_0002.json
  ...
```

---

### Phase 1: Preprocessing

**File:** `preprocessing.py`

This is the intelligence layer of LexiFlow. It runs once per book using Gemini (required — other models are not supported here yet) and produces structured metadata that drives all subsequent translation decisions.

For each chapter it produces a `chapter_XXXX_meta.json` containing:

```json
{
  "chapter_num": 2,
  "tokens": 312,
  "story_focus": ["protagonist confronts antagonist", "revenge arc climax"],
  "emotion_timeline": ["grief", "cold resolve", "resignation"],
  "character_state": {
    "Klein": "Three years of suppressed rage, now externalized as calm precision"
  },
  "sentence_types_present": ["narration", "dialogue", "description"],
  "narrative_tense": "past",
  "key_terms": ["Melissa", "Beyonder", "Sealed Artifact"],
  "entity_frequency": {"Beyonder": 4, "Klein": 7},
  "context_prev_summary": "Klein activated the artifact in the Tarot Club...",
  "context_next_summary": "Klein confronts the man responsible for Melissa's death...",
  "volume_direction": "Maintain cold technical precision regarding supernatural danger"
}
```

It also produces volume-level files:
- `LexiFlow/global_glossary.json` — all proper nouns, fantasy terms, places, organizations with their locked Devanagari forms
- `LexiFlow/character_voices.json` — each character's speech style, register, notable patterns
- `LexiFlow/volume_flow.json` — overall arc, dominant tone, protagonist state
- `LexiFlow/forbidden_patterns.json` — repetitive phrases to actively avoid

**Why Gemini for preprocessing?** Preprocessing requires understanding the entire novel's context to build accurate glossaries and character profiles. Gemini's large context window (up to 1M tokens) allows it to process entire volumes in one pass. This is a known hard dependency — other providers cannot substitute here without context window limitations.

**Output:**
```
LexiFlow/2_preprocessing/
  chapter_0001_meta.json
  chapter_0002_meta.json
  ...
LexiFlow/global_glossary.json
LexiFlow/character_voices.json
LexiFlow/volume_flow.json
LexiFlow/forbidden_patterns.json
```

---

### Phase 2: Translation (Flash)

**File:** `flash.py`

The Flash engine translates each batch using a fast, cost-effective model. Before each batch:

1. It reads the chunk manifests to find which chapters are in this batch
2. It loads the chapter metadata for those chapters from `2_preprocessing/`
3. It loads global context (glossary, character voices, volume flow, forbidden patterns)
4. It builds a context-aware system prompt using `build_flash_prompt()`
5. It sends the combined chunk text to the Flash model

**The Flash prompt contains:**
- Volume-level context (arc, tone, protagonist state)
- Locked glossary (exact Devanagari forms — no exceptions)
- Chapter-specific context (story focus, emotional arc, character states)
- Sentence type hints (dialogue → natural spoken Hindi, description → literary Hindi)
- Narrative tense (keep consistently past/present)
- Character voice profiles
- Forbidden patterns (avoid these repetitive phrases)
- Core translation rules (never skip, never summarize, preserve structure)

**Output:** `LexiFlow/3_translated_chunks/y001_model_x_model.txt`

---

### Phase 3: Polish (Pro)

**File:** `pro.py`

The Pro engine rewrites the translated text into publication-quality Hindi prose. It has **full editorial freedom** — the only constraints are:
- Preserve all plot facts and meaning
- Keep glossary terms exactly as specified
- Keep paragraph structure intact

Everything else — sentence structure, word choice, rhythm, register — can be completely rewritten. The pro prompt explicitly instructs the model:

> *"Every sentence that sounds translated → rewrite it completely. Flat or weak emotional moments → strengthen them. Awkward dialogue → make it sound natural for Hindi readers."*

**Vocabulary register guidance:**
The pro prompt specifies Urdu-Persian derived Hindi for emotional, atmospheric, and literary moments:
- ख़ामोशी (not चुप्पी)
- ग़म (not दुःख)  
- रूह (not आत्मा)
- ज़िंदगी (not जीवन)
- ख़याल (not विचार)
- लम्हा (not पल/क्षण)

Action and technical chapters use clean direct standard Hindi.

**Temperature:** Dynamically set per batch based on the chapter's emotion timeline (see [Chapter-Aware Temperature](#chapter-aware-temperature)).

**Output:** `LexiFlow/4_polished_output/y001_model_x_model.txt`

---

### Phase 4: Export

**File:** `Exporters.py`

After all batches complete, the export engine:

1. Sorts all polished output files by batch number
2. Merges them in order
3. Optionally injects translated chapter headings from the database
4. Outputs to the chosen format: DOCX, PDF, or EPUB

The export is also available on-demand from the UI without rerunning the full pipeline — useful for exporting partial runs or re-exporting with different heading settings.

**Output:** `LexiFlow/5_final_novel/LexiFlow_[title]_[timestamp].[format]`

---

## The Two-Engine Design

LexiFlow uses two separate AI engines for a deliberate reason.

**Flash engine** (translation) needs to be:
- Fast — it processes every word of the novel
- Accurate — it must follow the glossary and context precisely
- Consistent — same term should always produce same output

**Pro engine** (polish) needs to be:
- Powerful — it needs genuine literary sensibility
- Creative — it should rewrite freely, not translate literally
- Contextually sensitive — it needs to understand what makes a sentence feel "translated"

These are different tasks requiring different model characteristics. A model optimized for speed and instruction-following (Flash) is not the same as a model optimized for literary creativity (Pro). Separating them allows each to be tuned independently — different providers, different models, different temperatures, different prompts.

In practice the best results come from:
- Flash: A fast, instruction-following model (Gemini Flash, deepseek-v3.2, kimi-k2)
- Pro: A powerful creative model (qwen3-max, gpt-oss-120b, claude-sonnet)

---

## Context Injection System

This is the core innovation of LexiFlow. Every API call receives a dynamically constructed prompt built from the preprocessing metadata for the specific chapters being processed.

**`load_chapter_context(chunk_files)`** in `flash.py`:
- Reads the JSON manifests for the chunk files in the current batch
- Finds the chapter numbers covered by this batch
- Loads each chapter's meta file from `2_preprocessing/`
- Merges them (for multi-chapter batches): deduplicates story_focus, extends emotion_timeline, merges character_state

**`load_global_context()`** in `flash.py`:
- Reads `volume_flow.json`, `global_glossary.json`, `character_voices.json`, `forbidden_patterns.json`
- Returns them as Python objects for prompt injection

The prompts are rebuilt fresh for every batch — not cached — because each batch may cover different chapters with different emotional arcs.

**Without preprocessing:** The model receives raw text with no context. It translates literally. Output reads like a translation.

**With preprocessing:** The model knows this chapter has a grief arc, the protagonist is in cold resolve mode, dialogue should sound naturally spoken, and these specific Urdu-Persian words should be preferred for emotional moments. Output reads like it was written in Hindi.

---

## Chapter-Aware Temperature

**Function:** `get_polish_temperature()` in `pro.py`

Temperature controls how "creative" the Pro model is allowed to be. LexiFlow sets temperature dynamically based on the emotional content of the chapter being polished.

```python
def get_polish_temperature(chapter_meta):
    emotions = set(chapter_meta.get("emotion_timeline", []))
    high_creative = {"sadness", "grief", "horror", "dread", "nostalgia", "resignation"}
    high_control  = {"focus", "trepidation", "anxiety"}
    if emotions & high_creative:
        return 0.75
    elif emotions & high_control:
        return 0.45
    else:
        return 0.65
```

**Why this matters:**
- Grief/horror chapters need creative vocabulary freedom → 0.75 temperature → model reaches for रसूखदार, आतिशदान, सँवारी हुई
- Action/technical chapters need controlled precision → 0.45 temperature → model stays disciplined
- Standard chapters get 0.65 → balanced creativity

**Manual override:** The sidebar provides a temperature override slider. Setting it above 0.0 disables the auto system and applies a fixed temperature to all batches. Setting it to 0.0 (default) re-enables automatic chapter-aware temperature.

**Known limitation:** The `> 0.0` check means you cannot force temperature to exactly 0.0 via the slider — the auto system kicks in instead. This is a known minor issue.

---

## Glossary System

The glossary is built during preprocessing and stored in `LexiFlow/global_glossary.json`:

```json
[
  {"term": "Beyonder", "devanagari": "बियॉन्डर", "type": "system_term"},
  {"term": "Klein Moretti", "devanagari": "क्लेन मोरेटी", "type": "character"},
  {"term": "Backlund", "devanagari": "बैक्लंड", "type": "place"}
]
```

**How it works:** Every term in the glossary is injected into both the Flash and Pro prompts as a "locked" list — the model is instructed to use these exact Devanagari forms with no exceptions.

**What should be in the glossary:**
- Character names (proper nouns with no Hindi equivalent)
- Place names
- Organization names
- Fantasy system terms that should be transliterated (Beyonder, Sequence, Pathway)

**What should NOT be in the glossary:**
- Common emotions (grief, fear, joy — let the model choose naturally)
- Generic objects — let the model translate contextually
- Overloading the glossary with too many terms reduces literary quality because the model becomes overly mechanical

**The tension:** A strong model like qwen3-max follows the glossary perfectly but clusters all transliterated terms together in dense chapters, making the prose feel heavy. This is a source material problem, not a pipeline problem — fantasy novels with dense world-building terminology will always have this characteristic regardless of translation approach.

---

## Error Handling Architecture

**File:** `errors.py`

LexiFlow has a dedicated error classification system. Every exception in the entire pipeline flows through `classify_error()` which categorizes it into one of four types:

### Error Categories

| Category | Description | Action |
|----------|-------------|--------|
| `FATAL` | Wrong API key, invalid model, unknown provider, missing file | Stop immediately — no retry possible |
| `RATE_LIMIT` | HTTP 429, quota exceeded, RPM/TPM limits, status 439 (Scitely) | Wait with exponential backoff, retry |
| `TRANSIENT` | Network timeout, connection reset, empty response, 5xx errors | Wait fixed time, retry |
| `BATCH_ERROR` | All retries exhausted for this batch | Skip batch, write error file, continue run |

### Classification Logic

The classifier checks the exception message against compiled regex patterns:

```python
_FATAL_PATTERNS    = [r'api.?key', r'authentication', r'unauthorized', ...]
_RATE_LIMIT_PATTERNS = [r'429', r'439', r'rate.?limit', r'quota', ...]
_TRANSIENT_PATTERNS  = [r'timeout', r'connection.?reset', r'empty.?response', ...]
```

`ImportError` and `ModuleNotFoundError` are always Fatal — retrying won't fix a missing package.

### Retry Policy

Each provider has a tuned `RetryPolicy` specifying:
- `rate_limit_retries` — max retries on 429/quota (Groq: 5, others: 3-4)
- `rate_limit_base_wait` — initial backoff in seconds (doubles each retry: 20→40→80→160s)
- `transient_retries` — max retries on network errors (typically 3)
- `transient_wait` — fixed wait between transient retries (5-15s depending on provider)

### Pro Polish Fallback

If the Pro engine fails all retries on a batch, LexiFlow does NOT skip the batch. Instead it uses the Flash translation as the output (better than nothing) and records the error. The run continues.

### Error Files

Every error writes a detailed JSON file to `LexiFlow/ERROR_FILES/`:
```json
{
  "timestamp": "20260315_122030",
  "run_id": "abc123",
  "batch_num": 7,
  "mode": "pro",
  "category": "TRANSIENT",
  "error_type": "APIConnectionError",
  "error_msg": "Connection reset by peer",
  "traceback": "...",
  "input_preview": "first 500 chars of the batch..."
}
```

---

## Provider System

**File:** `ai_provider.py`

All AI providers implement the `AIProvider` abstract base class with a single method:

```python
def generate_content(self, system_prompt, user_text, temperature=0.7) -> str:
```

This abstraction means the rest of the pipeline is completely provider-agnostic. The engine calls `engine.provider_obj.generate_content()` and does not know or care whether that's Gemini, Claude, GPT, or any other model.

### Available Providers

| Provider | Class | Notes |
|----------|-------|-------|
| `gemini` | `GeminiProvider` | Uses `google-genai` SDK, supports system instructions |
| `gemma` | `GemmaProvider` | Gemini API but flattens system+user into single prompt (Gemma models don't support system role) |
| `openai` | `OpenAIProvider` | Standard OpenAI SDK |
| `anthropic` | `AnthropicProvider` | Special handling: opus-4/opus-4-5 require temperature=1.0 (extended thinking models) |
| `groq` | `GroqProvider` | Uses `groq` SDK |
| `huggingface` | `HuggingFaceProvider` | Uses OpenAI SDK with HuggingFace router base URL |
| `lightning` | `LightningAIProvider` | Uses `litai` SDK with message format fallback for older versions |
| `openrouter` | `OpenRouterProvider` | Uses OpenAI SDK with OpenRouter base URL + LexiFlow headers |
| `scitely` | `ScitelyProvider` | Uses OpenAI SDK with Scitely base URL, `timeout=120`, `max_tokens=16384` |

### Adding a New Provider

1. Create a class inheriting from `AIProvider` in `ai_provider.py`
2. Implement `generate_content()`
3. Add to `PROVIDER_REGISTRY`
4. Add batch defaults to `PROVIDER_BATCH_DEFAULTS` in `models.py`
5. Add retry policy to `RetryPolicy.for_provider()` in `errors.py`
6. Add models list to `MODELS` dict in `main.py`

---

## Batch System

**File:** `engine.py` → `_build_batches()`

LexiFlow uses a dynamic batching system that respects character limits per API call.

### Normal Batching

Chunks are grouped into batches respecting `flash_batch_chars` (max chars per Flash API call). If adding the next chunk would exceed the limit, the current batch is flushed and a new one starts.

### Micro-batching

If a single chunk is larger than `flash_batch_chars`, it cannot fit in any batch. The micro-batcher splits it at paragraph boundaries (`\n\n`) into sub-chunks that each fit within the limit. These micro-chunks are tracked with a special key format: `chunk_file::micro0`, `chunk_file::micro1`, etc.

**Cache:** All chunk texts are read once and cached in `_chunk_text_cache` during batch building. The translation loop reads from this cache instead of disk.

### Batch Sizing by Provider

Different providers have different optimal batch sizes based on their rate limits and context windows:

| Provider | Flash default | Pro default |
|----------|--------------|-------------|
| gemini | 12,000 chars | 10,000 chars |
| openai | 10,000 chars | 8,000 chars |
| anthropic | 8,000 chars | 6,000 chars |
| scitely | 10,000 chars | 8,000 chars |
| groq | 3,000 chars | 2,500 chars |
| gemma | 4,000 chars | 3,000 chars |

These are defaults. The sidebar sliders allow manual override per run.

### Cooldown

After each completed batch, LexiFlow sleeps for 10 seconds (`countdown_sleep(10, ...)`). This is an API safety measure originally designed for Gemini's strict rate limits. For providers like Groq and Scitely with higher RPM limits this is unnecessary overhead — future versions should make this provider-specific.

---

## Database & Run History

**File:** `store.py`

LexiFlow uses SQLite (`LexiFlow/lexiflow.db`) to track everything. The schema covers:

### Tables

**`books`** — One row per ingested novel
- `book_id`, `file_name`, `source_format`, `total_chapters`, `total_chunks`, `file_size_kb`

**`chunks`** — One row per chunk file
- `chunk_id`, `book_id`, `chunk_num`, `chapter_start`, `chapter_end`, `char_count`
- `status`: `extracted` → `translated` → `polished`
- `raw_path`, `translated_path`, `polished_path`

**`runs`** — One row per translation run
- `run_id`, `book_id`, `source_file`, `status`
- `flash_provider`, `flash_model`, `pro_provider`, `pro_model`
- `chunk_size`, `flash_batch_chars`, `pro_batch_chars`
- `started_at`, `finished_at`, `total_batches`

**`batches`** — One row per processed batch
- `batch_num`, `run_id`, `file_name`
- `input_chars`, `translated_chars`, `polished_chars`
- `translate_ms`, `polish_ms`, `retries`, `status`

**`errors`** — One row per error event
- `batch_num`, `run_id`, `mode`, `category`, `error_type`, `error_msg`
- `input_preview`, `input_chars`, `error_file`

**`headings`** — Translated chapter headings
- `run_id`, `chapter_num`, `original_heading`, `translated_heading`

**`exports`** — Export records
- `run_id`, `file_path`, `export_format`, `batches_merged`, `include_headings`

### Resume Logic

When RESUME MISSION is clicked, the engine:
1. Calls `store.get_latest_incomplete_run()` to find the most recent non-complete run
2. Calls `store.get_completed_batches(run_id)` to get the set of already-finished batch filenames
3. In the translation loop, skips any batch whose output filename is in the completed set

This means a run interrupted at batch 47 of 100 resumes at batch 48 with zero re-work.

---

## File Structure

```
LexiFlowv1.0.0/
├── main.py                    # Streamlit UI — all tabs and sidebar
├── engine.py                  # Master orchestration engine
├── ai_provider.py             # All provider implementations + registry
├── models.py                  # Data models, batch defaults, rate limits
├── errors.py                  # Error classification, retry logic, error files
├── flash.py                   # Flash engine: prompt builder, translation function
├── pro.py                     # Pro engine: prompt builder, polish function, temperature
├── preprocessing.py           # Gemini-based chapter analysis
├── ingestion.py               # Novel parsing and chunking
├── store.py                   # SQLite database layer
├── Exporters.py               # DOCX/PDF/EPUB export
├── exporter.py                # Lower-level export utilities
├── splitter.py                # Text splitting utilities
├── .env                       # API keys (never commit this)
│
└── LexiFlow/                  # Working directory (auto-created)
    ├── 1_input_copy/          # Sanitized copy of uploaded novel
    ├── 2_extracted_chunks/    # chunk_XXXX.txt + chunk_XXXX.json manifests
    ├── 2_extracted_chapters/  # Raw chapter files
    ├── 2_preprocessing/       # chapter_XXXX_meta.json files
    ├── 3_translated_chunks/   # Flash translation output
    ├── 4_polished_output/     # Pro polish output
    ├── 5_final_novel/         # Final exported files
    ├── ERROR_FILES/           # Detailed error JSON files
    ├── lexiflow.db            # SQLite database
    ├── global_glossary.json   # Locked term translations
    ├── character_voices.json  # Character speech profiles
    ├── volume_flow.json       # Volume-level narrative context
    └── forbidden_patterns.json # Repetition patterns to avoid
```

---

## Supported Providers & Models

### Gemini (Google)
```
gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro
gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro
gemini-3-flash, gemini-3-pro-preview
gemini-3.1-flash-lite-preview, gemini-3.1-flash-preview
```

### Gemma (Google)
```
gemma-3-27b-it, gemma-3-12b-it, gemma-3-4b-it
```

### OpenAI
```
gpt-4.1, gpt-4o, gpt-4-turbo, gpt-4, gpt-3.5-turbo, o3-mini, o3
```

### Anthropic
```
claude-haiku-4-5-20251001, claude-sonnet-4-5, claude-sonnet-4-6
claude-opus-4, claude-opus-4-5
```
> ⚠️ claude-opus-4 and claude-opus-4-5 use extended thinking and require temperature=1.0. LexiFlow handles this automatically.

### Groq
```
llama-3.3-70b-versatile, llama-3.1-8b-instant
meta-llama/llama-4-scout-17b-16e-instruct
moonshotai/kimi-k2-instruct, qwen/qwen3-32b
openai/gpt-oss-20b, openai/gpt-oss-120b
groq/compound, groq/compound-mini
```

### Lightning AI
```
lightning/gpt-oss-20b, lightning/gpt-oss-120b
lightning/llama-3.3-70b, lightning/deepseek-v3.1, lightning/kimi-k2.5
google/gemini-2.5-flash-lite, google/gemini-2.5-flash, google/gemini-2.5-pro
openai/gpt-4.1, openai/gpt-4o
anthropic/claude-sonnet-4-5, anthropic/claude-sonnet-4-6, anthropic/claude-opus-4
```

### OpenRouter
```
google/gemini-2.5-flash-preview-05-20, google/gemini-2.5-pro-preview
anthropic/claude-sonnet-4-5, anthropic/claude-opus-4
openai/gpt-4.1, openai/gpt-4o
meta-llama/llama-4-maverick:free, meta-llama/llama-3.3-70b-instruct:free
qwen/qwen3-235b-a22b:free, mistralai/mistral-small-3.2-24b-instruct:free
deepseek/deepseek-r1-0528:free, moonshotai/kimi-k2:free
```

### Scitely
```
qwen3-coder-plus  (1M context, 16384 output — coding focused, not recommended for translation)
deepseek-v3.2     (128K context, 16384 output — strong general model)
deepseek-r1       (128K context, 32768 output — reasoning model, slower)
qwen3-max         (256K context, 16384 output — WARNING: unreliable on large inputs via Scitely)
kimi-k2           (128K context, 16384 output — strong multilingual)
qwen3-235b-a22b-thinking-2507 (256K context, 32768 output — thinking model, very slow)
```

> ⚠️ **Scitely reliability note:** Testing shows qwen3-max returns empty responses on large inputs (~10K chars) even on sequential single requests. deepseek-v3.2 and kimi-k2 are more reliable. Scitely tokens expire every 7 days — regenerate at https://platform.iflow.cn/docs/api-key

### HuggingFace
```
Qwen/Qwen3.5-397B-A17B:novita
```

---

## Configuration

### .env File

```env
GEMINI_API_KEY=your_gemini_key        # Required for preprocessing
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
LIGHTNING_API_KEY=your_lightning_key
HF_TOKEN=your_huggingface_token
OPENROUTER_API_KEY=your_openrouter_key
SCITELY_API_KEY=your_scitely_key
```

API keys are auto-loaded from `.env` and pre-fill the sidebar inputs. Keys can also be entered manually in the UI.

### Sidebar Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Flash Provider | gemini | Provider for translation stage |
| Flash Model | gemini-2.5-flash | Model for translation |
| Pro Provider | gemini | Provider for polish stage |
| Pro Model | gemini-2.5-pro | Model for polish |
| Export Format | docx | Output format: docx/epub/pdf |
| Include chapter headings | true | Inject translated headings into export |
| Pro temperature override | 0.0 | 0.0 = auto chapter-aware; >0.0 = manual fixed |
| Flash batch chars | provider default | Max chars per Flash API call |
| Pro batch chars | provider default | Max chars per Pro API call |
| Base chunk size | 3000 | Chars per chunk file on disk |
| Gemini preprocessing key | from .env | Separate key for preprocessing (always Gemini) |

---

## Quick Start

### Prerequisites
```
Python 3.10+
pip install streamlit openai anthropic groq google-genai litai python-docx
```

### Run
```bash
cd LexiFlowv1.0.0
streamlit run main.py
```

### First Run
1. Add API keys to `.env` or enter them in the sidebar
2. Select Flash provider + model (recommended: `gemini` / `gemini-2.5-flash`)
3. Select Pro provider + model (recommended: `gemini` / `gemini-2.5-pro`)
4. Upload your novel (PDF, DOCX, EPUB, or TXT)
5. Enter your Gemini key in the preprocessing field
6. Click **🚀 LAUNCH MISSION**

### Recommended Combos (tested)

| Quality | Flash | Pro | Notes |
|---------|-------|-----|-------|
| Best tested | `groq/moonshotai/kimi-k2-instruct` | `groq/openai/gpt-oss-120b` | Reliable, fast |
| High quality | `scitely/deepseek-v3.2` | `scitely/deepseek-v3.2` | 121s/batch, ~60% success rate |
| Free tier | `openrouter/kimi-k2:free` | `openrouter/qwen3-235b:free` | Rate limited |

---

## Known Limitations

**Preprocessing requires Gemini.** The preprocessing stage is hardcoded to use Gemini due to its large context window. A warning appears in the sidebar when the Flash provider is not Gemini — this warning is technically misleading since preprocessing uses a separate dedicated key and is independent of the Flash provider choice. This will be fixed in a future version.

**Temperature override cannot be set to exactly 0.0.** The `> 0.0` check in `safe_call()` means the auto system always activates when the slider is at 0.0. To force true zero temperature you would need to set the override to a very small value like 0.01.

**Scitely qwen3-max unreliable on large inputs.** Testing shows qwen3-max returns empty responses on inputs larger than ~5K chars via Scitely. deepseek-v3.2 is more reliable but still has a ~40% failure rate on large inputs due to Scitely's routing infrastructure. The retry system handles this automatically but it adds latency.

**10-second cooldown between batches.** The inter-batch cooldown was designed for Gemini's strict rate limits. For Groq and Scitely with higher RPM this is unnecessary and adds significant runtime on large books.

**No async translation.** The pipeline is fully sequential: translate batch N, polish batch N, then translate batch N+1. Async pipelining (translate N+1 while polishing N) is a planned improvement that would reduce total runtime by 30-40%.

**UI uses polling refresh.** The Streamlit UI refreshes every 2 seconds with a safeguard cap of 100 refreshes. This is a workaround for Streamlit's lack of true push updates from background threads.

---

## Design Philosophy

LexiFlow was built on one core insight: **the quality of an AI translation is determined almost entirely by the quality of the context provided to the model, not the model itself.**

A GPT-4 with no context produces output that reads like a translation. A Groq Llama with full preprocessing context produces output that reads like it was written in Hindi. The model matters less than the context layer.

This shaped every architectural decision:

**Two stages instead of one.** Translation and polishing are cognitively different tasks. Separating them allows each model to specialize — one for accuracy, one for artistry.

**Preprocessing before translation.** Most translation pipelines translate chapter by chapter with no cross-chapter awareness. LexiFlow analyzes the entire volume first, building the context layer that every subsequent API call depends on.

**Error tolerance over perfection.** A pipeline that fails on one bad batch and loses 500 pages of work is worse than a pipeline that skips a bad batch and continues. LexiFlow will always produce *something* — even if Pro polish fails, the Flash translation survives. Even if a batch errors out, the run continues.

**Resume over restart.** Long translation runs take hours. Power cuts happen. Network fails. LexiFlow tracks every completed batch in SQLite so any interruption can be resumed from exactly where it stopped.

**Provider agnosticism.** The AI landscape changes fast. A model that is best today is average in six months. LexiFlow's provider abstraction means the entire pipeline can be switched to a new model by changing two dropdown selections — no code changes required.

---

*LexiFlow v1.0.0 — Built for translating novels, designed as reusable infrastructure.*
