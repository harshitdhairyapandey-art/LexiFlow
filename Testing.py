"""
Token ceiling + Devanagari multiplier test.
Tests:
  1. Actual output token ceiling before timeout
  2. Input token cap behavior  
  3. Devanagari output multiplier vs English input
  4. Parallel call behavior (3 vs 4 vs 5 simultaneous)
  5. Where hallucination/truncation starts

Replace YOUR_SCITELY_KEY_HERE before running.
Run with: python testing.py
"""

import sys
import time
import re
import threading
import concurrent.futures

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI

API_KEY = "YOUR_SCITELY_KEY_HERE"
MODEL   = "deepseek-v3.2"   # change to qwen3-max to compare

# ── Single chapter slice for parallel tests ───────────────────────────────────
# ~600 tokens input, clean Devanagari output expected

CHAPTER_SINGLE = """Chapter 1: Beyonder Terms

Klein Moretti, a Sequence 7 Magician of the Fool pathway, carefully unsealed the 
Sealed Artifact and felt the spirituality drain from his body. The Beyonder 
characteristics within the ancient relic pulsed with a cold, alien intelligence.
He whispered the activation code — "Mr. Fool grants me clarity" — and the 
mystical domain responded. His Spirit Body flickered as the Beyonder power 
surged through his veins like liquid fire, threatening to corrupt his sanity.

The Tarot Club meeting was called to order. The Hanged Man adjusted his 
illusory disguise while the Hermit reviewed the potion formula for Sequence 6.
Sequence advancement was never simple — the Restraint ritual demanded absolute 
mental fortitude, or the Beyonder would descend into madness, lost forever 
between the waking world and the domain of the True Creator."""

CHAPTER_GRIEF = """Chapter 2: Grief and Revenge

He had waited three years for this moment.

Three years of silence. Three years of swallowing his rage like shattered glass,
letting it cut him from the inside, letting the pain sharpen him into something 
cold and precise and utterly without mercy.

Her name had been Melissa. She had laughed like rain on a summer afternoon.
She had called his name in a voice so soft it felt like the world was whispering 
a secret only meant for him. And they had taken her. Not with swords or bullets —
with paperwork, with power, with the comfortable cruelty of men who would never 
once lose sleep over what they had done.

He stood now in the doorway of the man responsible. 
The man was eating dinner. Wine. Roasted lamb. A fire crackling in the hearth.
The normalcy of it made something behind his eyes go very, very quiet.

"Do you remember me?" he asked.
The man looked up. His face cycled through confusion, recognition, then a fear 
so total it was almost beautiful.
"I remember you," Klein said softly. "I just wanted you to know that." """

CHAPTER_ACTION = """Chapter 3: Action Sequence

He moved. Not like a man — like a decision. Pure and instant and irreversible.

The first guard went down before he registered the movement. Elbow to jaw.
The second reached for his weapon. Too slow. Wrist lock, rotation, crack.
Third one was smart — backed away, gave himself room, drew his blade properly.
Klein respected that. He threw the Sealed Artifact anyway.

The explosion of spiritual energy shattered the corridor wall. Dust. Screaming.
The distant sound of boots on marble — reinforcements, thirty seconds away.
He counted exits. Three. He needed one. He ran.

Behind him, the manor burned with pale blue Beyonder fire that no ordinary water 
could extinguish. Above him, the moon watched without expression, indifferent to 
the small violent drama playing out in its silver light."""

SYSTEM_TRANSLATE = (
    "You are a professional Hindi literary translator. "
    "Translate the following English text into publication-quality Hindi (Devanagari script only). "
    "Translate every sentence completely. Output Hindi ONLY. No notes or explanations."
)

SYSTEM_POLISH = (
    "You are a senior Hindi literary editor. "
    "Rewrite the following into publication-quality Hindi prose that reads like it was originally written in Hindi. "
    "Output Hindi text ONLY."
)

# Full 10-chapter input from original test
FULL_INPUT = """Chapter 1: Beyonder Terms

Klein Moretti, a Sequence 7 Magician of the Fool pathway, carefully unsealed the 
Sealed Artifact and felt the spirituality drain from his body. The Beyonder 
characteristics within the ancient relic pulsed with a cold, alien intelligence.
He whispered the activation code — "Mr. Fool grants me clarity" — and the 
mystical domain responded. His Spirit Body flickered as the Beyonder power 
surged through his veins like liquid fire, threatening to corrupt his sanity.

The Tarot Club meeting was called to order. The Hanged Man adjusted his 
illusory disguise while the Hermit reviewed the potion formula for Sequence 6.
Sequence advancement was never simple — the Restraint ritual demanded absolute 
mental fortitude, or the Beyonder would descend into madness, lost forever 
between the waking world and the domain of the True Creator.

Chapter 2: Grief and Revenge

He had waited three years for this moment.

Three years of silence. Three years of swallowing his rage like shattered glass,
letting it cut him from the inside, letting the pain sharpen him into something 
cold and precise and utterly without mercy.

Her name had been Melissa. She had laughed like rain on a summer afternoon.
She had called his name in a voice so soft it felt like the world was whispering 
a secret only meant for him. And they had taken her. Not with swords or bullets —
with paperwork, with power, with the comfortable cruelty of men who would never 
once lose sleep over what they had done.

He stood now in the doorway of the man responsible. 
The man was eating dinner. 
Wine. Roasted lamb. A fire crackling in the hearth.

The normalcy of it made something behind his eyes go very, very quiet.

"Do you remember me?" he asked.

The man looked up. His face cycled through confusion, recognition, then a fear 
so total it was almost beautiful.

"I remember you," Klein said softly. "I just wanted you to know that."

Chapter 3: Action Sequence

He moved.

Not like a man — like a decision. Pure and instant and irreversible.

The first guard went down before he registered the movement. Elbow to jaw.
The second reached for his weapon. Too slow. Wrist lock, rotation, crack.
Third one was smart — backed away, gave himself room, drew his blade properly.

Klein respected that.

He threw the Sealed Artifact anyway.

The explosion of spiritual energy shattered the corridor wall. Dust. Screaming.
The distant sound of boots on marble — reinforcements, thirty seconds away, maybe 
twenty. He counted exits. Three. He needed one.

He ran.

Behind him, the manor burned with pale blue Beyonder fire that no ordinary water 
could extinguish. Above him, the moon watched without expression, indifferent to 
the small violent drama playing out in its silver light.

Chapter 4: Philosophical Inner Monologue

What is a man, Klein wondered, who has lived three lives?

He had been a modern man once — a graduate student, unremarkable, 
underpaid, threading through the anonymous crowds of a city that 
never once acknowledged his existence. Then death. Then rebirth into 
a Victorian-era city of fog and gaslight and ancient conspiracy, where 
gods were real and knowledge was dangerous and the line between 
human and monster was negotiated rather than fixed.

And now — what? A deity in waiting? A fool, as the card suggested?

Perhaps both. Perhaps the distance between godhood and foolishness 
was not as vast as civilization preferred to believe.

He thought of a phrase he had once read: "The higher you climb, 
the more you must forget of what you were." He had never understood 
it fully then. He understood it now with the particular clarity of a man 
who had forgotten — deliberately, surgically — more than most people 
ever had the opportunity to know.

Memory, he had concluded, was not treasure. It was ballast.
You jettisoned it or it drowned you.

Chapter 5: Dialogue Heavy

"You're late," Audrey said, without looking up from her book.

"I'm precisely on time," Klein replied. "You were simply early."

"That's a very diplomatic way of describing incompetence."

He sat down across from her. The Tarot Club's illusory gathering space 
felt colder tonight — perhaps a reflection of the topic at hand.

"The Hanged Man has information about the Numinous Episcopate," he said.

Audrey finally looked up. Her eyes, always too perceptive for comfort,
studied him with that particular attention she gave to things she 
considered genuinely dangerous.

"How reliable is it?"

"Reliable enough that I called this meeting at midnight instead of waiting."

She set down her book. "Then we have a problem."

"We have had a problem," he corrected gently. "We are only now 
becoming aware of its shape."

Silence settled between them like a third person at the table.
Outside, Backlund's church bells struck the hour — solemn, distant, 
indifferent to human catastrophe as church bells have always been.

Chapter 6: Horror and Dread

The street was empty.

It should not have been empty. Even at this hour — even in this district 
of fog and narrow lanes and gas lamps that flickered without wind —
there were always people. Dock workers. Night watchmen. 
The particular category of desperate souls for whom darkness 
was simply the cheaper shift.

But there was no one.

Klein stopped walking.

The silence was not natural. Natural silence had texture — 
the distant lap of harbour water, the creak of old buildings settling, 
the anonymous sounds a city makes when it breathes in its sleep.
This silence was intentional. Curated. The silence of something 
that had removed everything else so that it could have his 
complete and undivided attention.

He did not turn around.

"I know you're there," he said quietly.

The lamplight behind him stretched his shadow long and thin 
across the cobblestones. Then — slowly, impossibly — 
his shadow turned its head.

He had not moved.

Chapter 7: Technical Arcane Description

The potion formula for Sequence 6 — Idol — required seven components,
each sourced from a different tier of Beyonder existence.

First: the dried neural tissue of a Sequence 8 Telepathist, ground to 
fine powder under moonlight. Second: three drops of distilled willpower — 
not metaphorical, but literal, extracted through the Loen alchemical 
process requiring a spirituality rating of no less than 0.4. Third through 
fifth components involved the crystallized remnants of two failed 
Beyonder advancements — dangerous to acquire, more dangerous to handle,
as residual madness clung to them like heat to iron.

The sixth component was the variable. Every Sequence pathway's formula 
shifted slightly based on the individual's spiritual characteristic profile.
For Klein, whose primary characteristic leaned toward the Observer 
sub-branch, this meant substituting the standard aromatic compound 
with an extract harvested from the optic fluid of a Deep-Sea Creature 
classified at danger level: Extraordinary.

He stared at the formula for a long moment.

"Well," he said to no one in particular. "This will be unpleasant."

Chapter 8: Mixed English Terms

The Steam locomotive hissed into Backlund Central Station as Klein 
checked his pocket watch — a standard-issue Police Inspector's timepiece,
nothing Beyonder about it, which was itself something of a comfort.

He carried: one Sealed Artifact (Class C), two standard-issue revolver 
rounds consecrated by a Sequence 9 Priest, his Police badge, 
a business card reading "Investigator - Paranormal Division",
and a notebook containing seventeen observations about the murders 
on Boklund Street that Scotland Yard had officially classified as 
"gas explosion related" and unofficially never spoke of again.

The Newspaper headlines screamed: THIRD NOBLE FOUND DEAD —
SPIRITUALISM BLAMED. The Radio broadcast across the street counter-programmed 
with a cheerful Orchestra performance. A Telegram boy sprinted past,
nearly colliding with Klein's briefcase.

Modernity, Klein reflected, was simply ancient chaos wearing a better coat.

Chapter 9: Pure Sadness

He kept her photograph in the inside pocket of his coat.

Not for sentiment — or not only for sentiment. In his line of work,
remembering what you were fighting for was a practical necessity,
as functional as a loaded weapon or a charged Beyonder artifact.

But sometimes, in the hours between midnight and dawn when the 
city went quiet and the distance between the living and the dead 
felt negotiable, he would take it out.

She was laughing in the photograph. Something off-camera had caught 
her attention — something funny, something small, the kind of moment 
that seems worth nothing at all until it is the only thing left.

He would look at it for exactly as long as he could bear.
Then he would put it away.
Then he would go back to work.

This was not strength. He understood that now.
It was simply the particular shape that grief takes in people 
who have no remaining option except to continue.

Chapter 10: Climax

"You don't have to do this," she said.

"I know," Klein replied.

He stood at the edge of the ritual circle, the Sealed Artifact humming 
in his hand with a frequency that made his back teeth ache. Below them,
three hundred feet of empty air and then the fog-shrouded streets of 
Backlund — indifferent, eternal, utterly unconcerned with whatever 
sacrifice was being negotiated above them.

"There are other ways —"

"Name one that saves everyone in this room."

She was quiet for a moment that felt longer than it was.

"I can't," she admitted.

"Then you have your answer."

He had made his peace with this. That was the thing about 
decisions made at the absolute edge of everything — they arrived 
with a strange clarity, like the world finally consenting to be 
simple for just long enough to let you act.

He thought of his sister. His brother. The photograph in his coat pocket.
He thought of all the things he had not said, not done, not become.
He thought — briefly, with something approaching fondness — of 
the unremarkable graduate student he had once been, 
threading through anonymous crowds, certain that nothing 
remarkable would ever happen to him.

"Mr. Fool," he whispered. "One last time."

The ritual circle ignited.

The city below did not notice.
The city below never did."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def count_devanagari_chars(text: str) -> int:
    return sum(1 for c in text if "\u0900" <= c <= "\u097F")

def detect_last_chapter(text: str) -> int:
    chapters = re.findall(r"अध्याय\s*(\d+)", text)
    if not chapters:
        chapters = re.findall(r"Chapter\s+(\d+)", text, re.IGNORECASE)
    return max(int(c) for c in chapters) if chapters else 0

def is_truncated(text: str) -> bool:
    """Detect mid-sentence cutoff — ends without punctuation."""
    if not text:
        return True
    last = text.rstrip()[-1]
    return last not in ".।!?'"


def single_call(client, system, user, max_tokens=8192, temperature=0.5, label=""):
    """One call, returns full result dict."""
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=150,
        )
        elapsed   = round(time.time() - start, 2)
        content   = resp.choices[0].message.content if resp.choices else ""
        out_tok   = resp.usage.completion_tokens if resp.usage else 0
        in_tok    = resp.usage.prompt_tokens     if resp.usage else 0
        dev_chars = count_devanagari_chars(content)
        multiplier = round(out_tok / max(in_tok, 1), 2)
        truncated = is_truncated(content)
        last_ch   = detect_last_chapter(content)

        return {
            "label":      label,
            "elapsed":    elapsed,
            "in_tokens":  in_tok,
            "out_tokens": out_tok,
            "chars_out":  len(content),
            "dev_chars":  dev_chars,
            "multiplier": multiplier,
            "last_ch":    last_ch,
            "truncated":  truncated,
            "empty":      len(content.strip()) < 10,
            "error":      None,
            "preview":    content[:100].strip() if content else "",
        }
    except Exception as e:
        return {
            "label": label, "elapsed": round(time.time() - start, 2),
            "in_tokens": 0, "out_tokens": 0, "chars_out": 0,
            "dev_chars": 0, "multiplier": 0, "last_ch": 0,
            "truncated": True, "empty": True,
            "error": f"{type(e).__name__}: {str(e)[:80]}",
            "preview": "",
        }


def print_result(r: dict):
    status = "ERROR" if r["error"] else ("EMPTY" if r["empty"] else ("TRUNC" if r["truncated"] else "OK   "))
    print(f"  [{status}] {r['label']}")
    if r["error"]:
        print(f"         Error: {r['error']}")
        return
    print(f"         Time   : {r['elapsed']}s")
    print(f"         Tokens : in={r['in_tokens']}  out={r['out_tokens']}")
    print(f"         Chars  : total={r['chars_out']:,}  devanagari={r['dev_chars']:,}")
    print(f"         Multiplier: {r['multiplier']}x  (out/in tokens)")
    if r["last_ch"]:
        print(f"         Last chapter detected: {r['last_ch']}")
    print(f"         Preview: {r['preview']}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Single chapter baseline
# Measures: Devanagari multiplier, output token count, time for ~600 token input
# ══════════════════════════════════════════════════════════════════════════════

def test_single_chapter_baseline(client):
    print(f"\n{'='*60}")
    print("TEST 1 — Single chapter baseline (~600 token input)")
    print("Goal: measure output tokens, Devanagari multiplier, time")
    print(f"{'='*60}\n")

    chapters = [
        ("Ch1 Beyonder (technical)",  CHAPTER_SINGLE),
        ("Ch2 Grief (emotional)",     CHAPTER_GRIEF),
        ("Ch3 Action (fast paced)",   CHAPTER_ACTION),
    ]

    results = []
    for label, text in chapters:
        print(f"  Running {label}...")
        r = single_call(client, SYSTEM_TRANSLATE, text, max_tokens=4096, label=label)
        print_result(r)
        results.append(r)
        time.sleep(2)

    # Summary
    ok = [r for r in results if not r["error"] and not r["empty"]]
    if ok:
        avg_out  = sum(r["out_tokens"]  for r in ok) / len(ok)
        avg_mult = sum(r["multiplier"]  for r in ok) / len(ok)
        avg_time = sum(r["elapsed"]     for r in ok) / len(ok)
        print(f"  BASELINE SUMMARY")
        print(f"  Avg output tokens : {avg_out:.0f}")
        print(f"  Avg multiplier    : {avg_mult:.2f}x  (Devanagari out / English in)")
        print(f"  Avg time          : {avg_time:.1f}s per chapter")
        print(f"  Projected 3 parallel: ~{avg_out*3:.0f} tokens total output")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Output ceiling: how many tokens before truncation/timeout
# Sends increasing input sizes, watches where output stops growing
# ══════════════════════════════════════════════════════════════════════════════

def test_output_ceiling(client):
    print(f"\n{'='*60}")
    print("TEST 2 — Output ceiling detection")
    print("Goal: find where output token count plateaus (= ceiling)")
    print(f"{'='*60}\n")

    # Build inputs of increasing size: 2, 4, 6, 8, 10 chapters
    chapter_blocks = [
        CHAPTER_SINGLE,
        CHAPTER_GRIEF,
        CHAPTER_ACTION,
        CHAPTER_SINGLE + "\n\n" + CHAPTER_GRIEF,
        FULL_INPUT,
    ]
    labels = ["2 chapters", "3 chapters", "4 chapters", "6 chapters", "10 chapters (full)"]

    results = []
    for label, text in zip(labels, chapter_blocks):
        char_count = len(text)
        approx_tokens = char_count // 4
        print(f"  Running {label} (~{approx_tokens} input tokens)...")
        r = single_call(client, SYSTEM_TRANSLATE, text,
                        max_tokens=16384, temperature=0.5, label=label)
        print_result(r)
        results.append(r)
        time.sleep(5)

    # Show the curve
    print(f"  OUTPUT CEILING CURVE")
    print(f"  {'Input label':<20} {'In tok':>8} {'Out tok':>8} {'Time':>7} {'Status'}")
    print(f"  {'-'*55}")
    for r in results:
        status = r["error"] or ("TRUNC" if r["truncated"] else "OK")
        print(f"  {r['label']:<20} {r['in_tokens']:>8} {r['out_tokens']:>8} {r['elapsed']:>6}s  {status}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Parallel calls: 2, 3, 4, 5 simultaneous
# Measures: where quality degrades, which parallel count is safe
# ══════════════════════════════════════════════════════════════════════════════

def test_parallel_calls(client, parallel_count: int):
    print(f"\n  --- {parallel_count} parallel calls ---")
    chapters = [CHAPTER_SINGLE, CHAPTER_GRIEF, CHAPTER_ACTION,
                CHAPTER_SINGLE, CHAPTER_GRIEF]
    inputs   = chapters[:parallel_count]
    results  = [None] * parallel_count
    lock     = threading.Lock()

    def run_one(idx, text):
        r = single_call(client, SYSTEM_TRANSLATE, text,
                        max_tokens=4096, temperature=0.5,
                        label=f"P{parallel_count}-call{idx+1}")
        with lock:
            results[idx] = r

    threads = [threading.Thread(target=run_one, args=(i, t)) for i, t in enumerate(inputs)]
    start   = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    wall    = round(time.time() - start, 1)

    ok        = [r for r in results if r and not r["error"] and not r["empty"]]
    truncated = [r for r in results if r and r["truncated"] and not r["error"]]
    errors    = [r for r in results if r and r["error"]]
    total_out = sum(r["out_tokens"] for r in ok)

    print(f"  Wall time : {wall}s")
    print(f"  Complete  : {len(ok)}/{parallel_count}")
    print(f"  Truncated : {len(truncated)}/{parallel_count}")
    print(f"  Errors    : {len(errors)}/{parallel_count}")
    print(f"  Total output tokens across all calls: {total_out}")
    for r in results:
        if r:
            print_result(r)

    return {
        "parallel":   parallel_count,
        "wall_time":  wall,
        "complete":   len(ok),
        "truncated":  len(truncated),
        "errors":     len(errors),
        "total_out":  total_out,
    }


def test_all_parallel(client):
    print(f"\n{'='*60}")
    print("TEST 3 — Parallel call safety (2 / 3 / 4 / 5 simultaneous)")
    print("Goal: find max safe parallel count before truncation/errors")
    print(f"{'='*60}")

    summary = []
    for n in [2, 3, 4, 5]:
        r = test_parallel_calls(client, n)
        summary.append(r)
        if n < 5:
            print(f"  Cooling down 20s before next batch...\n")
            time.sleep(20)

    print(f"\n  PARALLEL SUMMARY")
    print(f"  {'N':<4} {'Wall':>6} {'OK':>4} {'Trunc':>6} {'Err':>5} {'Total out tokens':>18}")
    print(f"  {'-'*50}")
    for r in summary:
        print(f"  {r['parallel']:<4} {r['wall_time']:>5}s {r['complete']:>4} "
              f"{r['truncated']:>6} {r['errors']:>5} {r['total_out']:>18}")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Retry behavior: empty first call pattern
# Confirms the empty-first-response behavior and measures how many retries needed
# ══════════════════════════════════════════════════════════════════════════════

def test_retry_pattern(client):
    print(f"\n{'='*60}")
    print("TEST 4 — Retry pattern (empty first call behavior)")
    print("Goal: confirm empty-first, measure how many retries to get content")
    print(f"{'='*60}\n")

    attempt_results = []
    for attempt in range(1, 8):
        print(f"  Attempt {attempt}/7 (no sleep between)...")
        r = single_call(client, SYSTEM_TRANSLATE, CHAPTER_SINGLE,
                        max_tokens=4096, label=f"retry-{attempt}")
        got_content = not r["empty"] and not r["error"]
        print(f"  {'GOT CONTENT' if got_content else 'EMPTY/ERROR'} "
              f"| {r['out_tokens']} tokens | {r['elapsed']}s")
        attempt_results.append(got_content)

        if got_content:
            print(f"\n  Content arrived on attempt {attempt}")
            break

    print(f"\n  RETRY SUMMARY: needed {sum(1 for _ in attempt_results)} attempts")
    print(f"  Pattern: {' -> '.join('OK' if x else 'EMPTY' for x in attempt_results)}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"{'='*60}")
    print(f"LexiFlow Token Ceiling + Parallel Test Suite")
    print(f"Model : {MODEL}")
    print(f"{'='*60}")

    client = OpenAI(api_key=API_KEY, base_url="https://api.scitely.com/v1")

    # Run all 4 tests in sequence
    # Comment out any you don't want to run

    test_single_chapter_baseline(client)  # ~3 calls, ~1 min
    time.sleep(10)

    test_output_ceiling(client)           # ~5 calls, ~5 min
    time.sleep(10)

    test_all_parallel(client)             # ~14 calls, ~5 min
    time.sleep(10)

    test_retry_pattern(client)            # up to 7 calls, ~2 min

    print(f"\n{'='*60}")
    print("ALL TESTS COMPLETE")
    print(f"{'='*60}")
    print()
    print("Key numbers to note:")
    print("  Test 1 multiplier  → Devanagari output / English input ratio")
    print("  Test 2 ceiling     → output token count where truncation starts")
    print("  Test 3 parallel    → max safe simultaneous calls before degradation")
    print("  Test 4 retry       → how many immediate retries needed for content")
    print()
    print("Feed these numbers back to update:")
    print("  max_chunk_tokens   (settings.py)")
    print("  translation_workers (settings.py)")
    print("  immediate_retries  (shared/errors/retry.py)")
    print("  timeout values     (shared/ai/scitely_client.py)")

