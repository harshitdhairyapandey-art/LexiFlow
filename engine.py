import os, time, json, threading
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from ai_provider import AIProviderError
# Internal Imports
from ingestion import IngestionEngine
from out import OutputAssembler
from flash import translate_chunk,DEFAULT_PROMPT as FLASH_DEFAULT
from pro import polish_chunk,DEFAULT_PROMPT as PRO_DEFAULT

load_dotenv()

class LexiFlowMasterEngine:
    def __init__(self, ui_callback=None):
        self.ui_callback = ui_callback
        self.stop_event = threading.Event()
        self.base_dir = Path("LexiFlow")
        self.state_file = self.base_dir / "engine_state.json"

        # Define paths but do NOT create them in __init__
        self.paths = {
            "chunks": self.base_dir / "2_extracted_chunks",
            "trans": self.base_dir / "3_translated_chunks",
            "pro": self.base_dir / "4_polished_output",
            "error": self.base_dir / "ERROR_FILES",
            "export": self.base_dir / "5_final_novel"
        }

        self.chunks_per_batch = 4
        self.state = {"completed_y": [], "polished_y": []}
        
        # API Config
        self.flash_engine = None
        self.pro_engine = None
        self.flash_prompt = FLASH_DEFAULT
        self.pro_prompt = PRO_DEFAULT

    def _prepare_workspace(self):
        """Creates directories only when the process actually starts."""
        for p in self.paths.values():
            p.mkdir(parents=True, exist_ok=True)
        self.state = self.load_session()

    def load_session(self) -> Dict[str, list]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.emit("Warning",0,"State file corrupted. Starting fresh session")
        return {"completed_y": [], "polished_y": []}

    def save_session(self):
        temp= self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state,indent=4),encoding="utf-8")
        temp.replace(self.state_file)

        

    def emit(self, status, progress, log, stats=""):
        if self.ui_callback:
            self.ui_callback({
                "status": status,
                "progress": progress,
                "log": log,
                "stats": stats
            })

    def configure_engines(self, flash_engine, pro_engine, flash_prompt, pro_prompt):
        self.flash_engine = flash_engine
        self.pro_engine = pro_engine
        if flash_prompt: self.flash_prompt = flash_prompt
        if pro_prompt: self.pro_prompt = pro_prompt

    def start_engine(self, source_file):
        """The main orchestration loop."""
        if not self.flash_engine or not self.pro_engine:
            self.emit("Error",0,"Engines not configured. Please set API keys first.")
            return

        try:
            self._prepare_workspace()
            self.stop_event.clear()

            # Phase 1: Ingestion
            if source_file and Path(source_file).exists():
                self.emit("Ingesting",5,"Breaking novel into chunks...")
                ingestor=IngestionEngine(source_file,ui_callback=self.ui_callback)
                if not ingestor.run():
                    raise Exception("Ingestion failed.")
            else:
                existing=list(self.paths["chunks"].glob("chunk_*.txt"))
                if not existing:
                    self.emit("Error",0,"No source file and no existing chunks found.")
                    return
                self.emit("Ingesting",5,"Resuming from existing chunks...")

            # Phase 2: Load Chunks
            all_chunks = sorted(list(self.paths["chunks"].glob("chunk_*.txt")))
            if not all_chunks:
                self.emit("Error", 0, "No chunks found to process.")
                return

            total_batches = (len(all_chunks) + self.chunks_per_batch - 1) // self.chunks_per_batch

            # Phase 3: Translation Loop
            for i in range(0, len(all_chunks), self.chunks_per_batch):
                if self.stop_event.is_set():
                    self.emit("Stopped", 0, "Process halted.")
                    return

                batch_num = (i // self.chunks_per_batch) + 1
                y_name = f"y{batch_num:03d}.txt"
                progress = int((batch_num / total_batches) * 90)

                if y_name in self.state["completed_y"]:
                    continue

                # Batch Translation (Flash)
                self.emit("Flash", progress, f"Translating Batch {batch_num}...")
                current_group = all_chunks[i : i + self.chunks_per_batch]
                combined_raw = "\n\n".join([f.read_text(encoding="utf-8") for f in current_group])
                
                translated = self.safe_call("flash", combined_raw, batch_num, progress)
                (self.paths["trans"] / y_name).write_text(translated, encoding="utf-8")

                # Batch Polishing (Pro)
                self.emit("Pro", progress, f"Polishing Batch {batch_num}...")
                polished = self.safe_call("pro", translated, batch_num, progress)
                (self.paths["pro"] / y_name).write_text(polished, encoding="utf-8")
                self.state["polished_y"].append(y_name)

                # Update State
                self.state["completed_y"].append(y_name)
                self.save_session()
                
                # Cooldown to avoid API Rate Limits
                self.countdown_sleep(10, batch_num, progress)

            # Phase 4: Final Export
            self.emit("Exporting", 95, "Generating final Word document...")
            title=f"LexiFlow_{Path(source_file).stem}" if source_file else "LexiFlow_Novel"
            assembler = OutputAssembler(title=title)
            assembler.merge_files(self.paths["pro"])
            self.emit("Complete", 100, "Process Finished Successfully!")

        except Exception as e:
            self.emit("Error", 0, f"Fatal Engine Error: {str(e)}")

    def safe_call(self, mode, text, batch_id, progress):
        """Handles API calls with automatic retries for rate limits."""
        engine = self.flash_engine if mode == "flash" else self.pro_engine
        func = translate_chunk if mode == "flash" else polish_chunk
        prompt = self.flash_prompt if mode == "flash" else self.pro_prompt

        for attempt in range(3):
            if self.stop_event.is_set():
                raise Exception("Engine stopped by user.")
            try:
                res = func(engine, prompt, text)
                if res: return str(res).strip()
            except Exception as e:
                if "429" in str(e) or "Quota" in str(e) or "rate" in str(e).lower():
                    wait = (attempt + 1) * 20
                    self.emit("Quota", progress, f"Rate limit hit. Waiting {wait}s...")
                    time.sleep(wait)
                else: raise e
        raise Exception(f"Batch {batch_id} failed after 3 minutes due to rate limits")

    def countdown_sleep(self, seconds, batch_id, progress):
        for s in range(seconds, 0, -1):
            if self.stop_event.is_set(): break
            self.emit("Cooldown", progress, f"API Safety Sleep: {s}s", f"Batch {batch_id}")
            time.sleep(1)