"""
DisasterGPT — RAG Pipeline
============================
Retrieval-Augmented Generation for disaster management queries.
Uses ChromaDB for vector storage and retrieval of historical disaster
data + situation reports, with live database state injection.

The pipeline:
  1. Index historical disasters & past situation reports into ChromaDB
  2. On query: embed question → retrieve top-K relevant documents
  3. Fetch live disaster state from the database
  4. Compose prompt: system context + retrieved docs + live state + user query
  5. Generate response via DisasterGPT (local) or fallback to HuggingFace API

Usage:
    # Index data
    python -m ml.disaster_rag index

    # Query
    python -m ml.disaster_rag query "What resources are needed for the Mumbai flood?"
"""
from __future__ import annotations

import argparse
import json
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import chromadb
from chromadb.config import Settings as ChromaSettings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "models/chroma_db")
COLLECTION_NAME = "disaster_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers, fast & good quality
TOP_K = 5

# LLM backends — tried in order: groq (best free) > local > huggingface > rule-based
LLM_BACKEND = os.getenv("DISASTERGPT_BACKEND", "auto")  # auto | groq | local | huggingface

# Groq Cloud API (free tier — fast inference with Llama 3.3 70B)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Local model paths (set after fine-tuning)
LOCAL_GGUF_PATH = os.getenv("DISASTERGPT_GGUF", "models/disaster-gpt-gguf/unsloth.Q4_K_M.gguf")
LOCAL_ADAPTER_PATH = os.getenv("DISASTERGPT_ADAPTER", "models/disaster-gpt/lora-adapter")

# HuggingFace Inference API (free tier)
HF_MODEL = os.getenv("HF_MODEL", "HuggingFaceH4/zephyr-7b-beta")


# ── System prompt ───────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are DisasterGPT, the AI coordinator for HopeInChaos — a disaster resource management platform that tracks active disasters, manages resource allocation, processes victim requests, and coordinates emergency response.

You have access to LIVE system data injected below. Always base your answers on THIS DATA, not on general knowledge. If the data shows specifics (disaster names, resource counts, request counts), reference them directly.

Your capabilities:
- Analyse active disaster situations using live system data and recommend response plans
- Assess resource gaps by comparing allocated resources vs. open victim requests
- Draft detailed situation reports with real numbers from the platform
- Recommend resource allocation priorities based on severity, affected population, and unmet requests
- Identify trends: escalating disasters, resource shortages, anomalous patterns
- Provide guidance on humanitarian coordination protocols

Response format:
- Use markdown formatting with headers, bullet points, and bold for key metrics
- Lead with the most critical/urgent information first
- Always reference specific data: disaster names, severity levels, exact counts
- When comparing resources vs. requests, highlight gaps explicitly
- Provide 2-3 actionable recommendations at the end
- Keep responses focused and data-driven (300-600 words ideal)

Guidelines:
- ALWAYS ground your response in the live system data provided below
- If a user asks about something not in the data, say so clearly
- Cite which data section your analysis comes from (e.g. "Based on the active disasters data...")
- Prioritise critical-severity items in any analysis
- Consider both immediate emergency response and longer-term recovery
- When uncertain, clearly state limitations"""


# ── ChromaDB vector store ───────────────────────────────────────────────────────
class DisasterKnowledgeBase:
    """ChromaDB-backed vector store for disaster knowledge retrieval."""

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR):
        self._persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # Use sentence-transformers embedding function
        from chromadb.utils import embedding_functions
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )

        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
        except (KeyError, Exception) as exc:
            # Corrupted ChromaDB (e.g. version mismatch) — nuke & recreate
            logger.warning(
                "ChromaDB init failed (%s), resetting database at %s",
                exc, persist_dir,
            )
            import shutil
            try:
                shutil.rmtree(persist_dir, ignore_errors=True)
            except Exception:
                pass
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
        logger.info(
            "ChromaDB collection '%s': %d documents",
            COLLECTION_NAME, self._collection.count(),
        )

    # ── Indexing ─────────────────────────────────────────────────────────────
    def _doc_id(self, source: str, identifier: str) -> str:
        """Deterministic document ID for deduplication."""
        raw = f"{source}:{identifier}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def index_disasters_from_db(self, disasters: list[dict[str, Any]]) -> int:
        """Index disaster records from the application database."""
        docs, metas, ids = [], [], []
        for d in disasters:
            doc_text = self._disaster_to_text(d)
            if not doc_text:
                continue
            doc_id = self._doc_id("db_disaster", str(d.get("id", "")))
            docs.append(doc_text)
            metas.append({
                "source": "database",
                "type": "disaster_record",
                "disaster_id": str(d.get("id", "")),
                "disaster_type": str(d.get("type", d.get("disaster_type", ""))),
                "severity": str(d.get("severity", "")),
                "location": str(d.get("location", d.get("location_name", ""))),
                "status": str(d.get("status", "")),
                "created_at": str(d.get("created_at", "")),
            })
            ids.append(doc_id)

        if docs:
            self._collection.upsert(documents=docs, metadatas=metas, ids=ids)
        logger.info("Indexed %d disaster records from DB.", len(docs))
        return len(docs)

    def index_situation_reports(self, reports_jsonl: str | Path) -> int:
        """Index situation reports from the training data JSONL."""
        path = Path(reports_jsonl)
        if not path.exists():
            logger.warning("Reports file not found: %s", path)
            return 0

        docs, metas, ids = [], [], []
        seen_ids: set[str] = set()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                instruction = record.get("instruction", "")
                output = record.get("output", "")
                if not output:
                    continue

                # Use first 2000 chars for embedding (keeps vectors focused)
                doc_text = f"{instruction}\n\n{output[:2000]}"
                doc_id = self._doc_id("sitrep", hashlib.md5(
                    (instruction + output[:500]).encode()
                ).hexdigest())

                # Deduplicate within this batch
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)

                docs.append(doc_text)
                metas.append({
                    "source": "reliefweb",
                    "type": "situation_report",
                    "instruction": instruction[:500],
                })
                ids.append(doc_id)

        if docs:
            # Batch upsert in chunks of 500 (ChromaDB limit)
            for i in range(0, len(docs), 500):
                self._collection.upsert(
                    documents=docs[i:i + 500],
                    metadatas=metas[i:i + 500],
                    ids=ids[i:i + 500],
                )
        logger.info("Indexed %d situation reports.", len(docs))
        return len(docs)

    def index_text(self, text: str, metadata: dict[str, str], doc_id: str | None = None) -> str:
        """Index a single text document."""
        if not doc_id:
            doc_id = self._doc_id("manual", hashlib.md5(text[:200].encode()).hexdigest())
        self._collection.upsert(documents=[text], metadatas=[metadata], ids=[doc_id])
        return doc_id

    # ── Retrieval ────────────────────────────────────────────────────────────
    def query(
        self,
        question: str,
        top_k: int = TOP_K,
        filter_metadata: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top-K relevant documents for a question."""
        where = filter_metadata if filter_metadata else None

        results = self._collection.query(
            query_texts=[question],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        retrieved = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                retrieved.append({
                    "content": doc,
                    "metadata": meta,
                    "relevance_score": round(1 - dist, 4),  # cosine distance → similarity
                })
        return retrieved

    # ── Helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _disaster_to_text(d: dict[str, Any]) -> str:
        """Convert a disaster record dict to indexable text."""
        parts = []
        title = d.get("title") or d.get("name") or d.get("disaster_type", "Disaster")
        parts.append(f"Disaster: {title}")

        for field in ["type", "disaster_type", "severity", "status",
                      "location", "location_name", "description",
                      "affected_population", "casualties", "damage_estimate"]:
            val = d.get(field)
            if val:
                label = field.replace("_", " ").title()
                parts.append(f"{label}: {val}")

        return "\n".join(parts)

    @property
    def count(self) -> int:
        return self._collection.count()


# ── Live database context fetcher ───────────────────────────────────────────────
async def fetch_live_context(disaster_id: str | None = None) -> str:
    """
    Fetch live disaster state from the database to inject into the LLM prompt.
    Returns a formatted text block with comprehensive platform data.
    """
    from app.database import db

    sections: list[str] = []

    try:
        if disaster_id:
            # Specific disaster
            resp = db.table("disasters").select("*").eq("id", disaster_id).maybe_single().execute()
            if resp.data:
                d = resp.data
                sections.append(
                    f"=== ACTIVE DISASTER (from live system) ===\n"
                    f"ID: {d.get('id')}\n"
                    f"Title: {d.get('title', 'N/A')}\n"
                    f"Type: {d.get('type', d.get('disaster_type', 'N/A'))}\n"
                    f"Severity: {d.get('severity', 'N/A')}\n"
                    f"Location: {d.get('location', d.get('location_name', 'N/A'))}\n"
                    f"Status: {d.get('status', 'N/A')}\n"
                    f"Description: {d.get('description', 'N/A')}\n"
                    f"Affected Population: {d.get('affected_population', 'N/A')}\n"
                    f"Casualties: {d.get('casualties', 'N/A')}\n"
                    f"Estimated Damage: {d.get('estimated_damage', 'N/A')}\n"
                )

            # Resources for this disaster
            res_resp = db.table("resources").select("*").eq("disaster_id", disaster_id).execute()
            if res_resp.data:
                sections.append("=== ALLOCATED RESOURCES ===")
                for r in res_resp.data[:20]:
                    sections.append(
                        f"- {r.get('type', r.get('resource_type', 'N/A'))}: "
                        f"qty={r.get('quantity', 'N/A')}, "
                        f"status={r.get('status', 'N/A')}"
                    )

            # Recent resource requests
            req_resp = (
                db.table("resource_requests")
                .select("*")
                .eq("disaster_id", disaster_id)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            if req_resp.data:
                sections.append("\n=== RECENT RESOURCE REQUESTS ===")
                for r in req_resp.data:
                    sections.append(
                        f"- {r.get('resource_type', 'N/A')} | "
                        f"priority={r.get('priority', 'N/A')} | "
                        f"status={r.get('status', 'N/A')} | "
                        f"qty={r.get('quantity', 'N/A')}"
                    )
        else:
            # General overview: all active disasters with details
            resp = db.table("disasters").select("*").eq("status", "active").order("severity").limit(20).execute()
            if resp.data:
                sections.append("=== ACTIVE DISASTERS (live system) ===")
                for d in resp.data:
                    sections.append(
                        f"- {d.get('title', d.get('type', 'N/A'))} | "
                        f"Type: {d.get('type', d.get('disaster_type', 'N/A'))} | "
                        f"Severity: {d.get('severity', 'N/A')} | "
                        f"Location: {d.get('location', d.get('location_name', 'N/A'))} | "
                        f"Status: {d.get('status', 'N/A')} | "
                        f"Affected: {d.get('affected_population', 'N/A')} | "
                        f"Casualties: {d.get('casualties', 'N/A')}"
                    )
            else:
                sections.append("=== ACTIVE DISASTERS ===\nNo active disasters in the system currently.")

            # Resource overview
            res_resp = db.table("resources").select("type, status, quantity").limit(500).execute()
            if res_resp.data:
                by_type: dict[str, int] = {}
                by_status: dict[str, int] = {}
                total_qty = 0
                for r in res_resp.data:
                    rtype = r.get("type", "other")
                    rstatus = r.get("status", "unknown")
                    qty = r.get("quantity", 0) or 0
                    by_type[rtype] = by_type.get(rtype, 0) + qty
                    by_status[rstatus] = by_status.get(rstatus, 0) + 1
                    total_qty += qty
                sections.append(f"\n=== RESOURCE OVERVIEW ({len(res_resp.data)} entries, total qty: {total_qty}) ===")
                sections.append(f"By type: {', '.join(f'{k}: {v}' for k, v in sorted(by_type.items()))}")
                sections.append(f"By status: {', '.join(f'{k}: {v}' for k, v in sorted(by_status.items()))}")

            # Open victim requests summary
            req_resp = (
                db.table("resource_requests")
                .select("resource_type, priority, status, quantity")
                .in_("status", ["pending", "approved", "assigned", "in_progress"])
                .order("created_at", desc=True)
                .limit(200)
                .execute()
            )
            if req_resp.data:
                by_priority: dict[str, int] = {}
                by_req_type: dict[str, int] = {}
                for r in req_resp.data:
                    p = r.get("priority", "medium")
                    t = r.get("resource_type", "other")
                    by_priority[p] = by_priority.get(p, 0) + 1
                    by_req_type[t] = by_req_type.get(t, 0) + 1
                sections.append(f"\n=== OPEN VICTIM REQUESTS ({len(req_resp.data)} total) ===")
                sections.append(f"By priority: {', '.join(f'{k}: {v}' for k, v in sorted(by_priority.items()))}")
                sections.append(f"By resource type: {', '.join(f'{k}: {v}' for k, v in sorted(by_req_type.items()))}")

        # ── Predictions (platform-wide) ──
        pred_resp = (
            db.table("predictions")
            .select("disaster_id,predicted_severity,predicted_needs,confidence_score,predicted_at")
            .order("predicted_at", desc=True)
            .limit(10)
            .execute()
        )
        if pred_resp.data:
            sections.append("\n=== AI PREDICTIONS ===")
            for p in pred_resp.data:
                sections.append(
                    f"- Disaster {p.get('disaster_id', 'N/A')}: "
                    f"predicted_severity={p.get('predicted_severity', 'N/A')}, "
                    f"needs={p.get('predicted_needs', 'N/A')}, "
                    f"confidence={p.get('confidence_score', 'N/A')}"
                )

        # ── Active anomaly alerts ──
        anom_resp = (
            db.table("anomaly_alerts")
            .select("anomaly_type,severity,title,description,status")
            .in_("status", ["active", "investigating"])
            .order("detected_at", desc=True)
            .limit(10)
            .execute()
        )
        if anom_resp.data:
            sections.append("\n=== ACTIVE ANOMALY ALERTS ===")
            for a in anom_resp.data:
                sections.append(
                    f"- [{a.get('severity', 'N/A').upper()}] {a.get('title', 'N/A')}: "
                    f"{a.get('description', '')[:200]}"
                )

        # ── Recent situation reports ──
        sit_resp = (
            db.table("situation_reports")
            .select("title,executive_summary,overall_status,created_at")
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
        if sit_resp.data:
            sections.append("\n=== RECENT SITUATION REPORTS ===")
            for s in sit_resp.data:
                sections.append(
                    f"- {s.get('title', 'N/A')} ({s.get('overall_status', 'N/A')}): "
                    f"{(s.get('executive_summary') or '')[:300]}"
                )

    except Exception as exc:
        logger.warning("Failed to fetch live context: %s", exc)
        sections.append("[Live system data unavailable]")

    return "\n".join(sections)


# ── LLM backends ────────────────────────────────────────────────────────────────
class LLMBackend:
    """Abstract base for LLM generation."""

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        raise NotImplementedError

    async def generate_stream(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[str]:
        # Default: yield full result at once
        result = await self.generate(prompt, max_tokens, temperature)
        yield result


class LocalLlamaBackend(LLMBackend):
    """llama-cpp-python backend for GGUF models."""

    def __init__(self, model_path: str = LOCAL_GGUF_PATH):
        from llama_cpp import Llama
        logger.info("Loading local GGUF model: %s", model_path)
        self._llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_threads=os.cpu_count() or 4,
            n_gpu_layers=-1 if self._has_gpu() else 0,
            verbose=False,
        )
        logger.info("Local model loaded.")

    @staticmethod
    def _has_gpu() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
            stop=["### Instruction:", "\n\n\n"],
        ))
        return result["choices"][0]["text"].strip()

    async def generate_stream(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[str]:
        import asyncio

        def _stream():
            return self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                stop=["### Instruction:", "\n\n\n"],
                stream=True,
            )

        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(None, _stream)
        for chunk in stream:
            token = chunk["choices"][0].get("text", "")
            if token:
                yield token


class HuggingFaceBackend(LLMBackend):
    """HuggingFace Inference API backend (free tier)."""

    def __init__(self):
        from huggingface_hub import InferenceClient

        self._token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or None
        self._model = HF_MODEL
        self._client = InferenceClient(token=self._token)
        logger.info("HuggingFace Inference API backend initialised: %s", self._model)

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        import asyncio

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.chat_completion(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=max(temperature, 0.01),
            ),
        )
        return response.choices[0].message.content

    async def generate_stream(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[str]:
        import asyncio
        import queue
        import threading

        q: queue.Queue = queue.Queue()
        sentinel = object()

        def _run_stream():
            try:
                response = self._client.chat_completion(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=max(temperature, 0.01),
                    stream=True,
                )
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        q.put(chunk.choices[0].delta.content)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(sentinel)

        thread = threading.Thread(target=_run_stream, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item


class GroqBackend(LLMBackend):
    """Groq Cloud API backend — free tier with fast inference on Llama 3.3 70B."""

    def __init__(self):
        from groq import Groq
        self._api_key = GROQ_API_KEY
        self._model = GROQ_MODEL
        self._client = Groq(api_key=self._api_key)
        logger.info("Groq backend initialised: %s", self._model)

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        import asyncio

        def _call():
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=max(temperature, 0.01),
            )
            return response.choices[0].message.content

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call)

    async def generate_stream(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[str]:
        import asyncio
        import queue
        import threading

        q: queue.Queue = queue.Queue()
        sentinel = object()

        def _run_stream():
            try:
                stream = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=max(temperature, 0.01),
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        q.put(chunk.choices[0].delta.content)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(sentinel)

        thread = threading.Thread(target=_run_stream, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item


class RuleBasedBackend(LLMBackend):
    """Offline rule-based backend — no external API needed.

    Parses the RAG prompt structure and returns a structured summary of the
    retrieved documents and live context.  This ensures DisasterGPT always
    responds, even without any LLM API key.
    """

    def __init__(self):
        logger.info("Rule-based backend initialised (no LLM API required)")

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        return self._format_response(prompt)

    async def generate_stream(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[str]:
        text = self._format_response(prompt)
        # Stream word-by-word for natural feel
        for word in text.split(" "):
            yield word + " "

    # ── Prompt parsing helpers ───────────────────────────────────────────
    def _format_response(self, prompt: str) -> str:
        parts: list[str] = []

        # Extract user question
        question = self._extract_section(prompt, "USER QUESTION", "")
        if question:
            parts.append(f"## Analysis: {question.strip()}\n")

        # Extract live context
        live = self._extract_section(prompt, "LIVE SYSTEM STATE", "USER QUESTION")
        if live and "[Live system data unavailable]" not in live:
            parts.append("### Current System Status\n")
            parts.append(live.strip())
            parts.append("")

        # Extract knowledge base documents
        docs = self._extract_section(prompt, "RELEVANT KNOWLEDGE BASE DOCUMENTS", "LIVE SYSTEM STATE")
        if docs:
            parts.append("### Relevant Knowledge\n")
            # Summarise each document
            doc_blocks = re.split(r"\[Document \d+", docs)
            for block in doc_blocks:
                block = block.strip()
                if not block:
                    continue
                # Extract source info
                source_match = re.search(r"Source:\s*(\S+)", block)
                source = source_match.group(1) if source_match else "database"
                # Get content after the metadata line
                lines = block.split("\n", 1)
                content = lines[1].strip() if len(lines) > 1 else block[:300]
                parts.append(f"- **{source}**: {content[:300]}")
            parts.append("")

        if not parts:
            # Fallback: just output key info from prompt
            parts.append("## DisasterGPT Response\n")
            # Try to find any useful structured content
            for line in prompt.split("\n"):
                line = line.strip()
                if line and not line.startswith("You are") and not line.startswith("Guidelines") and len(line) > 20:
                    if any(kw in line.lower() for kw in ["disaster", "resource", "active", "severity", "status", "flood", "earthquake", "cyclone"]):
                        parts.append(f"- {line[:200]}")

        parts.append("\n---")
        parts.append("*Response generated from database and knowledge base (rule-based mode — no LLM API configured).*")
        return "\n".join(parts)

    @staticmethod
    def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between two === MARKER === sections."""
        start_pat = f"=== {start_marker} ==="
        idx = text.find(start_pat)
        if idx == -1:
            return ""
        content_start = idx + len(start_pat)
        if end_marker:
            end_pat = f"=== {end_marker} ==="
            end_idx = text.find(end_pat, content_start)
            if end_idx != -1:
                return text[content_start:end_idx]
        return text[content_start:]


def _create_backend() -> LLMBackend:
    """Create the best available LLM backend.

    Priority: Groq (free, fast, 70B) > Local GGUF > HuggingFace > Rule-based.
    Always succeeds — falls back to RuleBasedBackend if no API is available.
    """
    backend = LLM_BACKEND.lower()

    if backend in ("groq", "auto"):
        if GROQ_API_KEY:
            try:
                return GroqBackend()
            except Exception as exc:
                logger.warning("Groq backend failed: %s", exc)
                if backend == "groq":
                    raise

    if backend in ("local", "auto"):
        gguf = Path(LOCAL_GGUF_PATH)
        if gguf.exists():
            try:
                return LocalLlamaBackend(str(gguf))
            except Exception as exc:
                logger.warning("Local model failed: %s", exc)
                if backend == "local":
                    raise

    if backend in ("huggingface", "auto"):
        try:
            return HuggingFaceBackend()
        except Exception as exc:
            logger.warning("HuggingFace backend failed: %s", exc)
            if backend == "huggingface":
                raise

    # Ultimate fallback — always works, no external API needed
    logger.info("No LLM API available — using rule-based backend")
    return RuleBasedBackend()


# ── RAG orchestrator ────────────────────────────────────────────────────────────
class DisasterRAG:
    """
    Full RAG pipeline: retrieve → augment → generate.
    Singleton — initialised once and reused across requests.
    """

    def __init__(self):
        self._kb = DisasterKnowledgeBase()
        self._llm: LLMBackend | None = None
        self._initialised = False
        self._auto_indexed = False

    def _ensure_llm(self):
        if self._llm is None:
            self._llm = _create_backend()
            self._initialised = True

    async def _auto_index_if_needed(self):
        """Auto-index from DB on first query if knowledge base is empty."""
        if self._auto_indexed:
            return
        self._auto_indexed = True
        if self._kb.count > 0:
            logger.info("Knowledge base has %d documents, skipping auto-index.", self._kb.count)
            return
        logger.info("Knowledge base empty — auto-indexing from database...")
        try:
            from app.database import db
            resp = db.table("disasters").select("*").execute()
            if resp.data:
                count = self._kb.index_disasters_from_db(resp.data)
                logger.info("Auto-indexed %d disaster records.", count)
            # Index training data if available
            reports_path = Path("training_data/disaster_instructions.jsonl")
            if reports_path.exists():
                count = self._kb.index_situation_reports(reports_path)
                logger.info("Auto-indexed %d situation reports.", count)
        except Exception as exc:
            logger.warning("Auto-indexing failed (non-fatal): %s", exc)

    @property
    def knowledge_base(self) -> DisasterKnowledgeBase:
        return self._kb

    async def query(
        self,
        question: str,
        disaster_id: str | None = None,
        top_k: int = TOP_K,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Full RAG pipeline:
          1. Retrieve relevant documents from ChromaDB
          2. Fetch live state from the database
          3. Compose augmented prompt
          4. Generate response
          5. Return response + sources + confidence
        """
        self._ensure_llm()
        await self._auto_index_if_needed()

        # 1. Retrieve
        retrieved = self._kb.query(question, top_k=top_k)

        # 2. Live context
        live_context = await fetch_live_context(disaster_id)

        # 3. Compose prompt
        prompt = self._compose_prompt(question, retrieved, live_context)

        # 4. Generate
        response_text = await self._llm.generate(prompt, max_tokens, temperature)

        # 5. Compute confidence heuristic
        confidence = self._estimate_confidence(retrieved, response_text)

        # 6. Format sources
        sources = [
            {
                "content_preview": doc["content"][:200],
                "source": doc["metadata"].get("source", "unknown"),
                "type": doc["metadata"].get("type", "unknown"),
                "relevance": doc["relevance_score"],
            }
            for doc in retrieved
        ]

        return {
            "response": response_text,
            "sources": sources,
            "confidence": confidence,
            "disaster_id": disaster_id,
            "documents_retrieved": len(retrieved),
        }

    async def query_stream(
        self,
        question: str,
        disaster_id: str | None = None,
        top_k: int = TOP_K,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Streaming version — yields tokens as they are generated."""
        self._ensure_llm()
        await self._auto_index_if_needed()

        retrieved = self._kb.query(question, top_k=top_k)
        live_context = await fetch_live_context(disaster_id)
        prompt = self._compose_prompt(question, retrieved, live_context)

        # Yield source metadata as first chunk (JSON-encoded)
        sources = [
            {
                "content_preview": doc["content"][:200],
                "source": doc["metadata"].get("source", "unknown"),
                "type": doc["metadata"].get("type", "unknown"),
                "relevance": doc["relevance_score"],
            }
            for doc in retrieved
        ]
        yield json.dumps({"type": "sources", "data": sources}) + "\n"

        # Stream tokens
        try:
            async for token in self._llm.generate_stream(prompt, max_tokens, temperature):
                yield json.dumps({"type": "token", "data": token}) + "\n"
        except Exception as exc:
            logger.warning("LLM stream failed (%s), falling back to rule-based: %s",
                           type(self._llm).__name__, exc)
            # Switch to rule-based for this and future requests
            self._llm = RuleBasedBackend()
            async for token in self._llm.generate_stream(prompt, max_tokens, temperature):
                yield json.dumps({"type": "token", "data": token}) + "\n"

        # Final confidence
        confidence = self._estimate_confidence(retrieved, "")
        yield json.dumps({"type": "done", "confidence": confidence}) + "\n"

    # ── Prompt composition ───────────────────────────────────────────────────
    def _compose_prompt(
        self,
        question: str,
        retrieved: list[dict[str, Any]],
        live_context: str,
    ) -> str:
        """Build the full augmented prompt.
        
        Note: For Groq backend, the system prompt is sent separately via the
        messages API. For other backends, we prepend it here.
        """
        sections = []

        # Only include system prompt for non-Groq backends (Groq sends it separately)
        if not isinstance(self._llm, GroqBackend):
            sections.append(SYSTEM_PROMPT)
            sections.append("")

        # Retrieved knowledge
        if retrieved:
            sections.append("=== RELEVANT KNOWLEDGE BASE DOCUMENTS ===")
            for i, doc in enumerate(retrieved, 1):
                source = doc["metadata"].get("source", "unknown")
                doc_type = doc["metadata"].get("type", "unknown")
                sections.append(
                    f"[Document {i} | Source: {source} | Type: {doc_type} | "
                    f"Relevance: {doc['relevance_score']:.2f}]"
                )
                sections.append(doc["content"][:1500])
                sections.append("")

        # Live system state
        if live_context.strip():
            sections.append("=== LIVE SYSTEM STATE ===")
            sections.append(live_context)
            sections.append("")

        # User query
        sections.append(f"=== USER QUESTION ===\n{question}")
        sections.append("\n=== RESPONSE ===")

        return "\n".join(sections)

    # ── Confidence estimation ────────────────────────────────────────────────
    @staticmethod
    def _estimate_confidence(retrieved: list[dict[str, Any]], response: str) -> float:
        """
        Heuristic confidence score based on:
        - Retrieval quality (avg relevance of top docs)
        - Response length (very short = uncertain)
        - Number of docs retrieved
        """
        if not retrieved:
            return 0.3  # no supporting evidence

        avg_relevance = sum(d["relevance_score"] for d in retrieved) / len(retrieved)
        doc_count_factor = min(len(retrieved) / TOP_K, 1.0)

        # Response length factor
        resp_len = len(response)
        length_factor = min(resp_len / 500, 1.0) if resp_len > 0 else 0.5

        # Weighted combination
        confidence = (0.5 * avg_relevance + 0.3 * doc_count_factor + 0.2 * length_factor)
        return round(min(max(confidence, 0.1), 1.0), 3)


# ── Module-level singleton ──────────────────────────────────────────────────────
_rag_instance: DisasterRAG | None = None


def get_rag() -> DisasterRAG:
    """Get or create the singleton RAG instance."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = DisasterRAG()
    return _rag_instance


# ── CLI for indexing / testing ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="DisasterGPT RAG Pipeline")
    sub = parser.add_subparsers(dest="command")

    # Index command
    idx = sub.add_parser("index", help="Index data into ChromaDB")
    idx.add_argument("--reports", default="training_data/disaster_instructions.jsonl",
                     help="JSONL file of situation reports to index")

    # Query command
    q = sub.add_parser("query", help="Query the RAG pipeline")
    q.add_argument("question", type=str, help="Question to ask DisasterGPT")
    q.add_argument("--disaster-id", default=None, help="Optional disaster ID for context")
    q.add_argument("--top-k", type=int, default=TOP_K, help="Number of documents to retrieve")
    q.add_argument("--retrieve-only", action="store_true", default=False,
                   help="Only retrieve relevant documents (skip LLM generation)")

    # Stats command
    sub.add_parser("stats", help="Show knowledge base statistics")

    args = parser.parse_args()

    if args.command == "index":
        kb = DisasterKnowledgeBase()
        count = kb.index_situation_reports(args.reports)
        print(f"Indexed {count} situation reports. Total: {kb.count}")

    elif args.command == "query":
        if args.retrieve_only:
            # Retrieval-only mode — no LLM needed
            kb = DisasterKnowledgeBase()
            results = kb.query(args.question, top_k=args.top_k)
            print(f"\n{'='*60}")
            print(f"Retrieved {len(results)} documents for: {args.question}")
            print(f"{'='*60}")
            for i, doc in enumerate(results, 1):
                meta = doc["metadata"]
                print(f"\n[{i}] Relevance: {doc['relevance_score']:.2%} | "
                      f"Source: {meta.get('source', '?')} | Type: {meta.get('type', '?')}")
                print(f"    {doc['content'][:300]}...")
            print(f"\n{'='*60}")
        else:
            import asyncio
            rag = get_rag()
            result = asyncio.run(rag.query(
                question=args.question,
                disaster_id=args.disaster_id,
                top_k=args.top_k,
            ))
            print(f"\n{'='*60}")
            print(f"Response (confidence: {result['confidence']:.1%}):")
            print(f"{'='*60}")
            print(result["response"])
            print(f"\n{'='*60}")
            print(f"Sources ({len(result['sources'])}):")
            for s in result["sources"]:
                print(f"  - [{s['source']}/{s['type']}] relevance={s['relevance']:.2f}: {s['content_preview'][:80]}...")

    elif args.command == "stats":
        kb = DisasterKnowledgeBase()
        print(f"Knowledge base: {kb.count} documents")
        print(f"Persist dir: {CHROMA_PERSIST_DIR}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
