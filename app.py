"""
AI Database Searcher - Backend
Flask app with NL-to-SQL engine for an attached SQLite database
"""

import json
import os
import re
import shutil
import sqlite3
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from google import genai
from google.genai import types
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
DATABASES_DIR = "databases"
DEFAULT_DB_FILENAME = "default.db"
DEFAULT_DB_PATH = os.path.join(DATABASES_DIR, DEFAULT_DB_FILENAME)

os.makedirs(DATABASES_DIR, exist_ok=True)
if not os.path.exists(DEFAULT_DB_PATH) and os.path.exists(DEFAULT_DB_FILENAME):
    try:
        shutil.copy(DEFAULT_DB_FILENAME, DEFAULT_DB_PATH)
    except Exception as e:
        print(f"Warning: could not copy default DB into {DATABASES_DIR}: {e}")

DB_PATH = os.environ.get("DB_PATH", "").strip() or DEFAULT_DB_PATH
if not os.path.exists(DB_PATH):
    if os.path.exists(DEFAULT_DB_PATH):
        DB_PATH = DEFAULT_DB_PATH
    elif os.path.exists(DEFAULT_DB_FILENAME):
        DB_PATH = DEFAULT_DB_FILENAME
    else:
        print("No database file found. Please upload a SQLite database.")

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  AI PROVIDER CONFIGURATION                                           ║
# ║  Change these values to switch providers and models.                 ║
# ║  API keys are still loaded from environment variables / .env         ║
# ╚══════════════════════════════════════════════════════════════════════╝

AI_PROVIDER       = "ollama"   # "google" | "openrouter" | "ollama"

AI_GOOGLE_MODEL   = "gemini-2.0-flash-lite"
AI_OPENROUTER_MODEL = "gpt-4o-mini"
AI_OLLAMA_MODEL   = "qwen2.5-coder:7b"  # Ollama local model name
AI_OLLAMA_BASE_URL = "http://localhost:11434/v1"  # Ollama local endpoint

# ── API keys (set via .env or environment) ─────────────────────────────
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URLS = [
    "https://openrouter.ai/api/v1/chat/completions",
    "https://openrouter.ai/v1/completions",
    "https://api.openrouter.ai/v1/chat/completions",
    "https://api.openrouter.ai/v1/completions",
]

# ── Validate provider and auto-fallback if needed ──────────────────────
VALID_PROVIDERS = {"google", "openrouter", "ollama"}
if AI_PROVIDER not in VALID_PROVIDERS:
    print(f"AI_PROVIDER='{AI_PROVIDER}' is invalid. Defaulting to 'ollama'.")
    AI_PROVIDER = "ollama"

# Fallback: if the selected provider's API key is missing, try another
if AI_PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
    if GEMINI_API_KEY:
        print("OpenRouter selected but OPENROUTER_API_KEY missing. Falling back to Google Gemini.")
        AI_PROVIDER = "google"
    else:
        print("OpenRouter selected but OPENROUTER_API_KEY missing. Falling back to Ollama.")
        AI_PROVIDER = "ollama"

if AI_PROVIDER == "google" and not GEMINI_API_KEY:
    if OPENROUTER_API_KEY:
        print("Google selected but GEMINI_API_KEY missing. Falling back to OpenRouter.")
        AI_PROVIDER = "openrouter"
    else:
        print("Google selected but GEMINI_API_KEY missing. Falling back to Ollama.")
        AI_PROVIDER = "ollama"

# Ollama needs no API key, so it can always be selected
gemini_client = None
if AI_PROVIDER == "google" and GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")

print(f"AI_PROVIDER={AI_PROVIDER} selected.")

# ── Schema-RAG Embedding Configuration ─────────────────────────────

# Embedding provider for Schema-RAG (vector search for relevant tables)
# "auto" = use the main AI_PROVIDER's embedding API, "off" = skip RAG
SCHEMA_RAG = os.environ.get("SCHEMA_RAG", "auto").strip().lower()

# Ollama embedding model (must be pulled locally)
AI_OLLAMA_EMBED_MODEL = "nomic-embed-text"

# Google embedding model
AI_GOOGLE_EMBED_MODEL = "text-embedding-004"

# How many top tables to retrieve via vector search
SCHEMA_RAG_TOP_K = 5

SCHEMA_EMBEDDINGS_FILE = "schema_embeddings.json"


# ── Schema-RAG: Table Embedding & Retrieval ──────────────────────────

def _get_embedding_db_key() -> str:
    """Return a unique key for the current database (path + mtime)."""
    try:
        mtime = os.path.getmtime(DB_PATH)
    except Exception:
        mtime = 0
    return f"{os.path.abspath(DB_PATH)}::{mtime}"


def _generate_table_descriptions() -> dict:
    """Generate a text description for each table for embedding."""
    info = get_table_info()
    fks = get_foreign_keys()
    descriptions = {}
    for t, cols in info.items():
        parts = [f"Table: {t}"]
        col_strs = []
        for c in cols:
            col_strs.append(f"{c['name']} ({c['type'] or 'unknown'})")
        parts.append(f"Columns: {', '.join(col_strs)}")
        table_fks = [fk for fk in fks if fk["table"] == t]
        if table_fks:
            fk_strs = [f"{fk['column']} references {fk['references_table']}.{fk['references_column']}" for fk in table_fks]
            parts.append(f"Relationships: {'; '.join(fk_strs)}")
        descriptions[t] = " | ".join(parts)
    return descriptions


def _ollama_embedding(text: str) -> list[float] | None:
    """Generate embedding using Ollama's embedding API."""
    base_url = AI_OLLAMA_BASE_URL.replace("/v1", "").replace("/chat", "")
    url = f"{base_url}/api/embed"
    try:
        response = requests.post(url, json={
            "model": AI_OLLAMA_EMBED_MODEL,
            "input": text
        }, timeout=30)
        response.raise_for_status()
        body = response.json()
        embeddings = body.get("embeddings", [])
        if embeddings:
            return embeddings[0]
        return None
    except Exception as e:
        print(f"Ollama embedding failed: {e}")
        return None


def _google_embedding(text: str) -> list[float] | None:
    """Generate embedding using Google's embedding model."""
    if not gemini_client:
        return None
    try:
        result = gemini_client.models.embed_content(
            model=AI_GOOGLE_EMBED_MODEL,
            contents=text
        )
        if result and result.embeddings:
            return result.embeddings[0].values
        return None
    except Exception as e:
        print(f"Google embedding failed: {e}")
        return None


def _generate_embedding(text: str) -> list[float] | None:
    """Generate embedding using the configured AI provider."""
    if SCHEMA_RAG == "off":
        return None
    # Try Ollama first (local, no API key needed)
    if AI_PROVIDER == "ollama":
        emb = _ollama_embedding(text)
        if emb:
            return emb
    # Try Google if available
    if gemini_client:
        emb = _google_embedding(text)
        if emb:
            return emb
    # Final fallback: try Ollama regardless of provider
    return _ollama_embedding(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


SCHEMA_EMBEDDINGS_CACHE: dict | None = None
TABLE_DESCRIPTIONS_CACHE: dict | None = None


def _load_schema_embeddings() -> dict | None:
    """Load cached embeddings from disk."""
    path = os.path.join(DATABASES_DIR, SCHEMA_EMBEDDINGS_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_schema_embeddings(data: dict) -> None:
    """Save embeddings to disk cache."""
    path = os.path.join(DATABASES_DIR, SCHEMA_EMBEDDINGS_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Failed to save schema embeddings: {e}")


def _initialize_schema_embeddings() -> None:
    """Generate and cache embeddings for all tables."""
    global SCHEMA_EMBEDDINGS_CACHE, TABLE_DESCRIPTIONS_CACHE

    db_key = _get_embedding_db_key()
    table_descriptions = _generate_table_descriptions()
    TABLE_DESCRIPTIONS_CACHE = table_descriptions

    # Check if we have cached embeddings for this exact DB
    cached = _load_schema_embeddings()
    if cached and cached.get("db_key") == db_key and cached.get("embeddings"):
        SCHEMA_EMBEDDINGS_CACHE = cached
        print(f"Schema-RAG: loaded {len(cached['embeddings'])} cached table embeddings")
        return

    if not table_descriptions:
        SCHEMA_EMBEDDINGS_CACHE = {"db_key": db_key, "embeddings": {}}
        return

    # Generate embeddings for each table
    emb_data = {}
    for table_name, description in table_descriptions.items():
        vector = _generate_embedding(description)
        if vector:
            emb_data[table_name] = vector
            print(f"Schema-RAG: embedded table '{table_name}' ({len(vector)} dims)")
        else:
            # No embedding available, skip
            print(f"Schema-RAG: no embedding for table '{table_name}', using keyword fallback")

    SCHEMA_EMBEDDINGS_CACHE = {
        "db_key": db_key,
        "embeddings": emb_data,
        "descriptions": table_descriptions
    }
    _save_schema_embeddings(SCHEMA_EMBEDDINGS_CACHE)
    print(f"Schema-RAG: embedded {len(emb_data)}/{len(table_descriptions)} tables")


def _find_relevant_tables(question: str, top_k: int | None = None) -> list[str] | None:
    """Find the most relevant table names for a question using vector similarity.
    Returns None if RAG is unavailable (falls back to full schema).
    """
    if top_k is None:
        top_k = SCHEMA_RAG_TOP_K

    # Lazy init embeddings if not yet loaded
    if SCHEMA_EMBEDDINGS_CACHE is None:
        _initialize_schema_embeddings()

    if not SCHEMA_EMBEDDINGS_CACHE:
        return None

    embeddings = SCHEMA_EMBEDDINGS_CACHE.get("embeddings", {})
    if not embeddings:
        return None

    # If the DB has fewer tables than top_k, return all
    if len(embeddings) <= top_k:
        return list(embeddings.keys())

    # Try to embed the question
    question_vec = _generate_embedding(question)
    if not question_vec:
        return None  # Fall back to full schema

    # Score each table by cosine similarity
    scored = []
    for table_name, table_vec in embeddings.items():
        sim = _cosine_similarity(question_vec, table_vec)
        scored.append((sim, table_name))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_tables = [name for _, name in scored[:top_k]]
    print(f"Schema-RAG: top {len(top_tables)} tables for '{question}': {top_tables}")
    return top_tables


def _build_schema_prompt_with_rag(question: str) -> str:
    """Build schema prompt using Schema-RAG to filter relevant tables."""
    relevant = _find_relevant_tables(question)
    if relevant:
        return schema_summary_compact(MAX_SCHEMA_TOKENS, relevant_tables=relevant)
    return schema_summary_compact(MAX_SCHEMA_TOKENS)


# ── AI Model Helpers ──────────────────────────────────────────────────

# SYSTEM PROMPT: classify any input, detect whether it is greeting, showcase,
# follow-up, database query, or irrelevant. If it is a follow-up,
# rewrite it into a standalone question using conversation history.
CLASSIFICATION_SYSTEM_PROMPT = (
    "You are a professional assistant for the attached SQLite database. "
    "Classify the user's input into exactly one category: greeting, showcase, "
    "followup, db_query, irrelevant. If the input is a follow-up, "
    "also rewrite it into a full standalone database question using the history. "
    "Return exactly one JSON object with keys: category, rewrite, reason. "
    "Do not include extra text."
)

# SYSTEM PROMPT: generate SQL or deny if the question is unrelated or the data is not available.
SQL_SYSTEM_PROMPT = (
    "You are a professional assistant for the attached SQLite database. Respond only with either: "
    "SQL: <sqlite SELECT query> or DENY: <reason>. Do not invent columns or data. "
    "If the question is unrelated to the database, respond with DENY."
)

# Conversation history for follow-up questions (last 5 turns)
_conversation_history = []
MAX_HISTORY = 5


def _safe_text(response) -> str:
    """Safely extract text from a Gemini response, returning '' on empty/blocked."""
    try:
        return (response.text or "").strip()
    except Exception:
        return ""


MAX_SCHEMA_TOKENS = 3000  # Rough token limit for schema context in prompts


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (characters / 3)."""
    return len(text) // 3


def get_foreign_keys() -> list:
    """Extract foreign key relationships from the database (cached)."""
    global TABLE_FKS
    if TABLE_FKS is not None:
        return TABLE_FKS
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    info = get_table_info()
    fks = []
    for table in info:
        try:
            cursor.execute(f'PRAGMA foreign_key_list("{table}")')
            for row in cursor.fetchall():
                fks.append({
                    "table": table,
                    "column": row[3],
                    "references_table": row[2],
                    "references_column": row[4],
                })
        except Exception:
            pass
    conn.close()
    TABLE_FKS = fks
    return fks


def _get_samples_cached() -> dict:
    """Return sample rows from each table (cached)."""
    global TABLE_SAMPLES
    if TABLE_SAMPLES is not None:
        return TABLE_SAMPLES
    info = get_table_info()
    if not info:
        TABLE_SAMPLES = {}
        return TABLE_SAMPLES
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    samples = {}
    for table in info:
        try:
            cursor.execute(f'SELECT * FROM "{table}" LIMIT 3')
            rows = [dict(row) for row in cursor.fetchall()]
            samples[table] = rows
        except Exception:
            samples[table] = []
    conn.close()
    TABLE_SAMPLES = samples
    return samples


def _get_column_value_preview(table: str, column: str, max_distinct: int = 8) -> list:
    """Get distinct sample values for a column (no caching, one-off)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL ORDER BY 1 LIMIT {max_distinct}')
        values = [str(r[0]) for r in cursor.fetchall()]
        return values
    except Exception:
        return []
    finally:
        conn.close()


def _get_key_column_values_cached() -> dict:
    """For each table, get preview values from key text columns (cached)."""
    global TABLE_KEY_VALUES
    if TABLE_KEY_VALUES is not None:
        return TABLE_KEY_VALUES
    info = get_table_info()
    previews = {}
    key_col_keywords = {
        "name", "title", "city", "country", "category", "company",
        "productname", "categoryname", "companyname", "contactname",
        "firstname", "lastname", "region", "description"
    }
    for table, cols in info.items():
        for col in cols:
            col_key = col["name"].lower().replace(" ", "").replace("_", "")
            if col_key in key_col_keywords:
                values = _get_column_value_preview(table, col["name"], max_distinct=6)
                if values:
                    if table not in previews:
                        previews[table] = {}
                    previews[table][col["name"]] = values
    TABLE_KEY_VALUES = previews
    return previews


def schema_summary() -> str:
    """Return a rich schema description including columns, sample data, foreign keys, and key values."""
    info = get_table_info()
    fks = get_foreign_keys()
    samples = _get_samples_cached()
    key_values = _get_key_column_values_cached()

    lines = []
    lines.append("=== DATABASE SCHEMA ===")
    lines.append("")

    for t, cols in info.items():
        lines.append(f"Table: {t}")
        for c in cols:
            lines.append(f"  - {c['name']} ({c['type'] or 'unknown'})")

        table_fks = [fk for fk in fks if fk["table"] == t]
        if table_fks:
            lines.append("  Foreign Keys:")
            for fk in table_fks:
                lines.append(f"    {fk['column']} -> {fk['references_table']}({fk['references_column']})")

        if samples.get(t):
            lines.append("  Sample rows (first 3):")
            for row in samples[t]:
                items = list(row.items())[:6]
                row_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in items)
                lines.append(f"    {{{row_str}}}")

        if t in key_values:
            for col_name, values in key_values[t].items():
                val_str = ", ".join(f"'{v}'" for v in values)
                lines.append(f"  {col_name} values: {val_str}")

        lines.append("")

    if fks:
        lines.append("Table Relationships:")
        for fk in fks:
            lines.append(f"  {fk['table']}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}")
        lines.append("")

    return "\n".join(lines)


def schema_summary_compact(max_tokens: int = MAX_SCHEMA_TOKENS, relevant_tables: list[str] | None = None) -> str:
    """Return a rich schema description truncated to fit within the token budget.
    If relevant_tables is provided, only include those tables (Schema-RAG).
    Tries levels from richest to most compact, computing only what's needed."""
    info = get_table_info()
    if relevant_tables is not None:
        info = {t: cols for t, cols in info.items() if t in relevant_tables}
    fks = get_foreign_keys()
    if relevant_tables is not None:
        fks = [fk for fk in fks if fk["table"] in relevant_tables or fk["references_table"] in relevant_tables]

    # Level 1: compact format without samples or key values (fast to compute)
    base_parts = ["=== DATABASE SCHEMA ===", ""]
    for t, cols in info.items():
        base_parts.append(f"Table: {t}")
        for c in cols:
            base_parts.append(f"  - {c['name']} ({c['type'] or 'unknown'})")
        table_fks = [fk for fk in fks if fk["table"] == t]
        if table_fks:
            base_parts.append("  Foreign Keys:")
            for fk in table_fks:
                base_parts.append(f"    {fk['column']} -> {fk['references_table']}({fk['references_column']})")
        base_parts.append("")
    if fks:
        base_parts.append("Table Relationships:")
        for fk in fks:
            base_parts.append(f"  {fk['table']}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}")
        base_parts.append("")
    base_text = "\n".join(base_parts)

    # If even the base doesn't fit, ultra-compact
    if _estimate_tokens(base_text) > max_tokens * 0.7:
        compact_lines = []
        for t, cols in info.items():
            col_names = [c['name'] for c in cols]
            fk_notes = []
            for fk in fks:
                if fk["table"] == t:
                    fk_notes.append(f"{fk['column']}->{fk['references_table']}.{fk['references_column']}")
            line = f"{t}({','.join(col_names)})"
            if fk_notes:
                line += f"  [FK: {'; '.join(fk_notes)}]"
            compact_lines.append(line)
        return "\n".join(compact_lines)

    # Level 2: try adding previews and samples
    samples = _get_samples_cached()
    key_values = _get_key_column_values_cached()
    rich_parts = base_parts[:]

    for t, cols in info.items():
        idx = None
        for i, p in enumerate(rich_parts):
            if p == f"Table: {t}":
                idx = i
                break
        if idx is None:
            continue

        insert_pos = idx
        for j in range(idx, len(rich_parts)):
            if rich_parts[j] == "":
                insert_pos = j
                break

        if t in key_values:
            kv_lines = []
            for col_name, values in key_values[t].items():
                val_str = ", ".join(f"'{v}'" for v in values)
                kv_lines.append(f"  {col_name} values: {val_str}")
            rich_parts = rich_parts[:insert_pos] + kv_lines + rich_parts[insert_pos:]

        if samples.get(t):
            sample_lines = ["  Sample rows (first 3):"]
            for row in samples[t]:
                items = list(row.items())[:6]
                row_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in items)
                sample_lines.append(f"    {{{row_str}}}")
            for j in range(insert_pos, len(rich_parts)):
                if rich_parts[j] == "":
                    insert_pos = j
                    break
            rich_parts = rich_parts[:insert_pos] + sample_lines + rich_parts[insert_pos:]

    rich_text = "\n".join(rich_parts)
    if _estimate_tokens(rich_text) <= max_tokens:
        return rich_text

    return base_text


def get_preferred_text_columns(table: str, info: dict) -> list:
    """Return schema columns most likely to contain natural-language values."""
    if not info or table not in info:
        return []

    text_cols = [
        c["name"] for c in info.get(table, [])
        if c["type"] and any(t in c["type"].upper() for t in ("CHAR", "CLOB", "TEXT", "VARCHAR"))
    ]
    if not text_cols:
        text_cols = [c["name"] for c in info.get(table, [])]

    preferred_order = [
        "name", "title", "description", "company", "category", "product",
        "artist", "customer", "supplier", "country", "city",
    ]
    ordered = []
    for key in preferred_order:
        for col in text_cols:
            if key in col.lower() and col not in ordered:
                ordered.append(col)
    for col in text_cols:
        if col not in ordered:
            ordered.append(col)
    return ordered


def _openrouter_request(json_payload: dict):
    """Send a request to OpenRouter, trying known endpoint URLs until one succeeds."""
    if not OPENROUTER_URLS:
        raise RuntimeError("No OpenRouter URL configured.")

    last_error = None
    for url in OPENROUTER_URLS:
        try:
            response = requests.post(url, headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }, json=json_payload, timeout=30)
            response.raise_for_status()
            return response
        except Exception as e:
            last_error = e
            print(f"OpenRouter request failed for {url}: {e}")
    if last_error:
        raise last_error
    raise RuntimeError("OpenRouter request failed for unknown reasons.")


def normalize_text(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def tokenize_text(text: str) -> set:
    return set(normalize_text(text).split())


def _schema_tokens() -> set:
    info = get_table_info()
    tokens = set()
    for table, cols in info.items():
        tokens.update(tokenize_text(table))
        for col in cols:
            tokens.update(tokenize_text(col["name"]))
    return tokens


def _looks_like_followup(question: str) -> bool:
    """Check if a short question looks like a conversational follow-up (e.g. "and white?")."""
    cleaned = question.strip().lower().rstrip('?!.')
    if not cleaned:
        return False
    followup_starts = ('and ', 'or ', 'also ', 'what about ', 'how about ')
    words = cleaned.split()
    return any(cleaned.startswith(s) for s in followup_starts) and len(words) <= 6


def check_relevance(question: str, history: list | None = None) -> dict:
    """Verify the input is relevant to the attached database."""
    q = (question or "").strip()
    if not q:
        return {"relevant": False, "reason": "Please enter a question."}

    q_lower = q.lower()
    irrelevant_keywords = [
        'weather', 'temperature', 'forecast', 'news', 'time', 'date', 'joke',
        'movie', 'sport', 'sports', 'recipe', 'recipe', 'song', 'music video',
        'how are you', 'bing', 'google', 'twitter', 'facebook', 'stock',
        'price of bitcoin', 'exchange rate', 'currency', 'election', 'politics',
    ]
    if any(word in q_lower for word in irrelevant_keywords):
        return {"relevant": False, "reason": "That question appears unrelated to the attached database."}

    schema_tokens = _schema_tokens()
    if schema_tokens and tokenize_text(q) & schema_tokens:
        return {"relevant": True, "reason": "Relevant"}

    question_words = re.search(r'\b(what|who|where|when|how|show|find|list|count|give me|display)\b', q_lower)
    if question_words:
        return {"relevant": True, "reason": "Relevant"}

    # If there is conversation history, allow short follow-up questions to pass through
    # to AI classification and follow-up rewriting. This handles cases like "and white?"
    # after a previous query about "company names with cheese in the name".
    if history and _looks_like_followup(q):
        return {"relevant": True, "reason": "Follow-up in conversation context"}

    return {"relevant": False, "reason": "Please ask a question about the attached database schema."}


def check_data_availability(question: str) -> dict:
    """Check whether the question is likely answerable from the attached schema."""
    q_lower = (question or "").lower()
    money_terms = [
        'money', 'salary', 'earnings', 'income', 'payroll', 'budget', 'profit',
        'revenue', 'revenue', 'million', 'billion', 'dollars', 'usd', '€', '$',
    ]
    if any(term in q_lower for term in money_terms):
        schema_tokens = _schema_tokens()
        allowed_money_tokens = {
            'price', 'cost', 'amount', 'total', 'revenue', 'income', 'salary',
            'balance', 'payment', 'paid', 'profit', 'loss', 'rate', 'fee'
        }
        if not schema_tokens & allowed_money_tokens:
            return {"available": False, "reason": "The attached database does not appear to contain money or salary information."}

    return {"available": True, "reason": "Available"}


def rewrite_followup_question(question: str, history: list) -> str:
    """Rewrite simple follow-up questions using the previous question context."""
    q = question.strip().rstrip('?!.')
    if not history:
        return q

    prev = history[-1].get("q", "")
    prev_sql = history[-1].get("sql", "")
    prev_lower = prev.lower()

    # If the question doesn't start with a follow-up indicator, return as-is
    if not re.match(r"^(?:what about|how about|and|or|also|now|next|continue|same)\b", q, re.I):
        return q

    target_match = re.search(r"(?:what about|how about|and|or|also)\s+([a-z][a-z .'-]+)$", q, re.I)
    if not target_match:
        return q

    target = target_match.group(1).strip()

    if "people who live in" in prev_lower or "people live in" in prev_lower:
        return f"what are the people who live in {target}"

    starts_with_match = re.search(r'^(?:what about|how about|and|or|also|now|next|continue|same)\s+(?:those\s+)?whose\s+name\s+starts?\s+with\s+(?:a\s+)?([a-z])\b', q, re.I)
    contains_match = re.search(r'^(?:what about|how about|and|or|also|now|next|continue|same)\s+(?:those\s+)?whose\s+name\s+(?:contains|has|includes?)\s+(?:a\s+)?([a-z])\b', q, re.I)
    if starts_with_match and ("employees" in prev_lower or "people" in prev_lower or "customer" in prev_lower or "company" in prev_lower):
        return f"what are the people whose names start with {starts_with_match.group(1)}"
    if contains_match and ("employees" in prev_lower or "people" in prev_lower or "customer" in prev_lower or "company" in prev_lower):
        return f"what are the people whose names contain {contains_match.group(1)}"

    followup_match = re.match(r"^(?:what about|how about|and|or|also|now|next|continue|same)\s+(.+)$", q, re.I)
    if followup_match:
        specific = followup_match.group(1).strip()
        if specific:
            if "people" in prev_lower or "customers" in prev_lower or "employees" in prev_lower or "employee" in prev_lower:
                return f"what are the people in {specific}"
            if "products" in prev_lower:
                return f"what are the products in {specific}"
            if "orders" in prev_lower:
                return f"what are the orders in {specific}"

    if re.match(r"^(?:what about|how about|and|or|also|now|next|continue|same)\s+([a-z][a-z .'-]*)$", q, re.I):
        specific = re.match(r"^(?:what about|how about|and|or|also|now|next|continue|same)\s+([a-z][a-z .'-]*)$", q, re.I).group(1).strip()
        if "people" in prev_lower or "customers" in prev_lower or "employees" in prev_lower or "employee" in prev_lower:
            return f"what are the people in {specific}"
        if "products" in prev_lower:
            return f"what are the products in {specific}"

    if "customers" in prev_lower and "from" in prev_lower:
        return f"what are the customers from {target}"
    if "customers" in prev_lower and "in" in prev_lower:
        return f"what are the customers in {target}"
    if "products" in prev_lower and "in" in prev_lower:
        return f"what are the products in {target}"

    # ── Smart follow-up via SQL pattern analysis ────────────────────────
    # For follow-ups like "and white?" when previous SQL used
    # "LIKE '%cheese%'" on CompanyName, build a new question that
    # replaces the old search term with the new one.
    if prev_sql and target:
        # Extract LIKE patterns from the previous SQL
        like_pattern = re.search(
            r"LIKE\s+'%([^']+)%'", prev_sql, re.I
        )
        if like_pattern:
            # Extract the column name used in the LIKE condition
            like_col_match = re.search(
                r"(\w+)\s+LIKE\s+'%[^']+%'", prev_sql, re.I
            )
            col_name = like_col_match.group(1) if like_col_match else "value"

            # Determine what kind of thing was being searched from the previous question
            if "customer" in prev_lower or "people" in prev_lower or "employee" in prev_lower:
                return f"what are the people with {target} in the name"
            elif "product" in prev_lower:
                return f"what are the products with {target} in the name"
            elif "company" in prev_lower or "companies" in prev_lower or "supplier" in prev_lower or "shipper" in prev_lower:
                return f"show me the companies with {target} in the name"
            elif "order" in prev_lower:
                return f"show me the orders with {target} in the name"
            elif "category" in prev_lower:
                return f"show me the categories with {target} in the name"
            else:
                # Generic fallback: reconstruct based on column name
                return f"find all where {col_name} contains {target}"

        # Extract equality patterns from previous SQL: Column = 'Value'
        eq_pattern = re.search(
            r"=\s+'([^']+)'", prev_sql, re.I
        )
        if eq_pattern:
            return q  # Can't reliably substitute arbitrary equality values

    return q


def _build_schema_prompt(question: str | None = None) -> str:
    """Build the schema portion of the AI prompt, using Schema-RAG if a question is provided.
    Auto-sizes to fit token limits."""
    if question and SCHEMA_RAG != "off":
        return _build_schema_prompt_with_rag(question)
    return schema_summary_compact(MAX_SCHEMA_TOKENS)


def _build_sql_prompt(question: str) -> str:
    """Build the full prompt for SQL generation including rich schema context."""
    schema = _build_schema_prompt(question)
    history_lines = ""
    if _conversation_history:
        history_lines = "\nPrevious questions and their SQL (for context):\n"
        for h in _conversation_history[-3:]:
            history_lines += f"Q: {h['q']}\nSQL: {h['sql']}\n"

    return (
        f"Attached SQLite DB schema (includes columns, types, sample data, foreign keys, and key column values):\n"
        f"{schema}\n"
        f"{history_lines}\n"
        f"New question: \"{question}\"\n\n"
        "Respond with one of:\n"
        "• SQL: <sqlite SELECT query>   — if answerable from this schema (use history for follow-ups)\n"
        "  Use sample data and column values above to determine correct table/column names, joins, and filter values. "
        "Use foreign key relationships to build correct JOIN conditions.\n"
        "• DENY: <reason>               — if question is unrelated to this DB, or asks for data not in schema\n"
        "Rules: SELECT only; quote names with spaces; no markdown; do not invent columns."
    )


def ask_gemini(question: str) -> dict:
    """
    Single Gemini call that uses rich database analysis for accurate SQL generation.

    Returns one of:
      {'action': 'SQL',     'sql': '<query>'}
      {'action': 'DENY',    'reason': '<short message>'}
      {'action': 'FALLBACK'}   -- Gemini unavailable/failed, use rule-based
    """
    if not gemini_client:
        return {"action": "FALLBACK"}

    model = AI_GOOGLE_MODEL
    prompt = _build_sql_prompt(question)

    try:
        response = gemini_client.models.generate_content(
            model=model,
            contents=prompt
        )
        text = _safe_text(response)
        if not text:
            print("ask_gemini: empty response — falling back")
            return {"action": "FALLBACK"}
        return _parse_ai_response_text(text)

    except Exception as e:
        print(f"ask_gemini error: {e}")
        return {"action": "FALLBACK"}


def _ollama_request(json_payload: dict):
    """Send a request to Ollama via its OpenAI-compatible endpoint."""
    base_url = AI_OLLAMA_BASE_URL
    url = f"{base_url}/chat/completions"
    try:
        response = requests.post(url, headers={
            "Content-Type": "application/json"
        }, json=json_payload, timeout=60)
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Ollama request failed for {url}: {e}")
        raise


def ask_openrouter(question: str) -> dict:
    if AI_PROVIDER != "openrouter" or not OPENROUTER_API_KEY:
        return {"action": "FALLBACK"}

    model = AI_OPENROUTER_MODEL
    prompt = _build_sql_prompt(question)

    try:
        response = _openrouter_request({
            "model": model,
            "messages": [
                {"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 500,
        })
        response.raise_for_status()
        body = response.json()
        text = ""
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = (msg.get("content") or "").strip()
        if not text:
            print("ask_openrouter: empty response — falling back")
            return {"action": "FALLBACK"}
        return _parse_ai_response_text(text)
    except Exception as e:
        print(f"ask_openrouter error: {e}")
        if gemini_client:
            print("OpenRouter unavailable, falling back to Gemini for SQL generation.")
            return ask_gemini(question)
        print("OpenRouter unavailable and Gemini unavailable, using local rule-based SQL fallback.")
        return {"action": "FALLBACK"}


def ask_ollama(question: str) -> dict:
    """Generate SQL using a locally running Ollama model."""
    model = AI_OLLAMA_MODEL
    prompt = _build_sql_prompt(question)

    try:
        response = _ollama_request({
            "model": model,
            "messages": [
                {"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
        })
        body = response.json()
        text = ""
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = (msg.get("content") or "").strip()
        if not text:
            print("ask_ollama: empty response — falling back")
            return {"action": "FALLBACK"}
        return _parse_ai_response_text(text)
    except Exception as e:
        print(f"ask_ollama error: {e}")
        if gemini_client:
            print("Ollama unavailable, falling back to Gemini for SQL generation.")
            return ask_gemini(question)
        return {"action": "FALLBACK"}


def _parse_ai_response_text(text: str) -> dict:
    if not text:
        return {"action": "FALLBACK"}
    upper = text.upper()
    if upper.startswith("SQL:"):
        sql = text[4:].strip()
        sql = re.sub(r'^```[a-zA-Z]*\n?', '', sql)
        sql = re.sub(r'```$', '', sql).strip()
        if sql.upper().startswith("SELECT"):
            return {"action": "SQL", "sql": sql}
        return {"action": "FALLBACK"}
    if upper.startswith("DENY:"):
        return {"action": "DENY", "reason": text[5:].strip()}
    return {"action": "FALLBACK"}


def _extract_json_object(text: str) -> str:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text


def _parse_classification_response(text: str) -> dict:
    """Parse AI classification results from a JSON response."""
    payload = _extract_json_object(text)
    try:
        parsed = json.loads(payload)
        return {
            "category": parsed.get("category", "db_query"),
            "rewrite": parsed.get("rewrite", "").strip(),
            "reason": parsed.get("reason", "")
        }
    except Exception:
        return {"category": "db_query", "rewrite": "", "reason": "fallback"}


def ask_gemini_classification(question: str, history: list | None = None) -> dict:
    if not gemini_client:
        return {"category": "db_query", "rewrite": question, "reason": "Gemini unavailable"}

    model = AI_GOOGLE_MODEL
    history_lines = ""
    if history:
        history_lines = "\nHistory:\n"
        for h in history[-3:]:
            history_lines += f"Q: {h['q']}\nSQL: {h['sql']}\n"

    prompt = (
        f"{CLASSIFICATION_SYSTEM_PROMPT}\n"
        f"{history_lines}\n"
        f"User input: \"{question}\"\n"
        "Reply with JSON only."
    )

    try:
        response = gemini_client.models.generate_content(
            model=model,
            contents=prompt
        )
        text = _safe_text(response)
        if not text:
            return {"category": "db_query", "rewrite": question, "reason": "empty response"}
        return _parse_classification_response(text)
    except Exception as e:
        print(f"ask_gemini_classification error: {e}")
        return {"category": "db_query", "rewrite": question, "reason": "error"}


def ask_openrouter_classification(question: str, history: list | None = None) -> dict:
    if AI_PROVIDER != "openrouter" or not OPENROUTER_API_KEY:
        return {"category": "db_query", "rewrite": question, "reason": "OpenRouter unavailable"}

    model = AI_OPENROUTER_MODEL
    history_lines = ""
    if history:
        history_lines = "\nHistory:\n"
        for h in history[-3:]:
            history_lines += f"Q: {h['q']}\nSQL: {h['sql']}\n"

    prompt = (
        f"{CLASSIFICATION_SYSTEM_PROMPT}\n"
        f"{history_lines}\n"
        f"User input: \"{question}\"\n"
        "Reply with JSON only."
    )

    try:
        response = _openrouter_request({
            "model": model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 300,
        })
        response.raise_for_status()
        body = response.json()
        text = ""
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = (msg.get("content") or "").strip()
        if not text:
            return {"category": "db_query", "rewrite": question, "reason": "empty response"}
        return _parse_classification_response(text)
    except Exception as e:
        print(f"ask_openrouter_classification error: {e}")
        if gemini_client:
            print("OpenRouter classification unavailable, falling back to Gemini classification.")
            return ask_gemini_classification(question, history)
        return {"category": "db_query", "rewrite": question, "reason": "error"}


def ask_ollama_classification(question: str, history: list | None = None) -> dict:
    """Classify user intent using a locally running Ollama model."""
    model = AI_OLLAMA_MODEL
    history_lines = ""
    if history:
        history_lines = "\nHistory:\n"
        for h in history[-3:]:
            history_lines += f"Q: {h['q']}\nSQL: {h['sql']}\n"

    prompt = (
        f"{CLASSIFICATION_SYSTEM_PROMPT}\n"
        f"{history_lines}\n"
        f"User input: \"{question}\"\n"
        "Reply with JSON only."
    )

    try:
        response = _ollama_request({
            "model": model,
            "messages": [
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
        })
        body = response.json()
        text = ""
        if isinstance(body, dict):
            choices = body.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = (msg.get("content") or "").strip()
        if not text:
            return {"category": "db_query", "rewrite": question, "reason": "empty response"}
        return _parse_classification_response(text)
    except Exception as e:
        print(f"ask_ollama_classification error: {e}")
        if gemini_client:
            print("Ollama classification unavailable, falling back to Gemini classification.")
            return ask_gemini_classification(question, history)
        return {"category": "db_query", "rewrite": question, "reason": "error"}


def ask_classification(question: str, history: list | None = None) -> dict:
    if AI_PROVIDER == "ollama":
        return ask_ollama_classification(question, history)
    if AI_PROVIDER == "openrouter":
        return ask_openrouter_classification(question, history)
    return ask_gemini_classification(question, history)


def ask_ai(question: str) -> dict:
    if AI_PROVIDER == "ollama":
        return ask_ollama(question)
    if AI_PROVIDER == "openrouter":
        return ask_openrouter(question)
    return ask_gemini(question)


TABLE_INFO = None
TABLE_FKS = None
TABLE_SAMPLES = None
TABLE_KEY_VALUES = None


def invalidate_schema_cache() -> None:
    """Force re-analysis on next schema access."""
    global TABLE_INFO, TABLE_FKS, TABLE_SAMPLES, TABLE_KEY_VALUES, SCHEMA_EMBEDDINGS_CACHE, TABLE_DESCRIPTIONS_CACHE
    TABLE_INFO = None
    TABLE_FKS = None
    TABLE_SAMPLES = None
    SCHEMA_EMBEDDINGS_CACHE = None
    TABLE_DESCRIPTIONS_CACHE = None
    TABLE_KEY_VALUES = None


def is_valid_db_filename(filename: str) -> bool:
    return bool(filename and filename == secure_filename(filename)
                and filename.lower().endswith((".db", ".sqlite", ".sqlite3")))


def list_available_databases() -> list:
    if not os.path.isdir(DATABASES_DIR):
        return []
    return sorted(
        f for f in os.listdir(DATABASES_DIR)
        if os.path.isfile(os.path.join(DATABASES_DIR, f)) and is_valid_db_filename(f)
    )


def get_current_database_name() -> str:
    return os.path.basename(DB_PATH)


def set_current_database(filename: str) -> None:
    global DB_PATH, TABLE_INFO
    if not is_valid_db_filename(filename):
        raise ValueError("Invalid database filename.")
    path = os.path.join(DATABASES_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError("Database not found.")
    DB_PATH = path
    invalidate_schema_cache()
    # Pre-initialize Schema-RAG embeddings for the new database
    if SCHEMA_RAG != "off":
        _initialize_schema_embeddings()


def get_database_status() -> dict:
    files = list_available_databases()
    default = os.path.basename(DEFAULT_DB_PATH) if os.path.exists(DEFAULT_DB_PATH) else (files[0] if files else "")
    return {
        "current": get_current_database_name(),
        "files": files,
        "default": default,
    }


def get_table_info(force_refresh: bool = False):
    """Get table schema info. Cached globally; use force_refresh to bypass cache."""
    global TABLE_INFO
    if TABLE_INFO is not None and not force_refresh:
        return TABLE_INFO
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]
    info = {}
    for t in tables:
        cursor.execute('PRAGMA table_info("{}")'.format(t))
        cols = cursor.fetchall()
        info[t] = [{"name": c[1], "type": c[2]} for c in cols]
    conn.close()
    TABLE_INFO = info
    return info


# ── NL-to-SQL Engine ───────────────────────────────────────────────────

# Table aliases / keywords mapping
TABLE_ALIASES = {
    "order": "Orders", "orders": "Orders", "purchase": "Orders", "purchases": "Orders",
    "customer": "Customers", "customers": "Customers", "client": "Customers", "clients": "Customers",
    "company": "Customers", "companies": "Customers",
    "product": "Products", "products": "Products", "item": "Products", "items": "Products",
    "category": "Categories", "categories": "Categories",
    "supplier": "Suppliers", "suppliers": "Suppliers", "vendor": "Suppliers", "vendors": "Suppliers",
    "employee": "Employees", "employees": "Employees", "staff": "Employees", "worker": "Employees",
    "shipper": "Shippers", "shippers": "Shippers",
    "region": "Regions", "regions": "Regions",
    "territory": "Territories", "territories": "Territories",
    "order detail": "Order Details", "order details": "Order Details",
    "order_detail": "Order Details",
}

COLUMN_ALIASES = {
    "name": {"Customers": "CompanyName", "Products": "ProductName",
             "Categories": "CategoryName", "Suppliers": "CompanyName",
             "Employees": "FirstName || ' ' || LastName", "Shippers": "CompanyName"},
    "price": "UnitPrice", "prices": "UnitPrice", "cost": "UnitPrice", "costs": "UnitPrice",
    "stock": "UnitsInStock", "quantity": {"Order Details": "Quantity",
                                           "Products": "UnitsInStock"},
    "total": {"Order Details": "Quantity * UnitPrice", "Orders": "Freight"},
    "revenue": "Quantity * UnitPrice",
    "city": "City", "country": "Country", "address": "Address",
    "phone": "Phone", "contact": "ContactName",
    "date": "OrderDate", "dates": "OrderDate",
    "freight": "Freight", "shipping": "Freight",
    "discount": "Discount",
    "id": "ID",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def detect_table(question):
    """Detect the most likely target table for the question using attached schema."""
    q_tokens = tokenize_text(question)
    info = get_table_info()
    if not info:
        return None

    table_scores = {}
    for table, cols in info.items():
        score = 0
        table_tokens = tokenize_text(table)
        score += len(q_tokens & table_tokens) * 3
        for col in cols:
            score += len(q_tokens & tokenize_text(col["name"]))
        if table.lower() in question.lower():
            score += 5
        table_scores[table] = score

    # Fallback based on schema keywords if exact matches are missing
    if all(score == 0 for score in table_scores.values()):
        for alias, table in TABLE_ALIASES.items():
            if alias in question.lower() and table in info:
                return table

    best_table = max(table_scores, key=table_scores.get)
    if table_scores[best_table] == 0:
        return next(iter(info.keys()))
    return best_table


def extract_number_conditions(question):
    """Extract numeric comparisons like 'over 50', 'more than 100', etc."""
    conditions = []
    patterns = [
        (r'(?:over|more\s+than|greater\s+than|above|>)\s*\$?(\d+(?:\.\d+)?)', '>'),
        (r'(?:under|less\s+than|fewer\s+than|below|<)\s*\$?(\d+(?:\.\d+)?)', '<'),
        (r'(?:at\s+least|minimum|>=?)\s*\$?(\d+(?:\.\d+)?)', '>='),
        (r'(?:at\s+most|maximum|<=?)\s*\$?(\d+(?:\.\d+)?)', '<='),
        (r'(?:equal\s+to|exactly|=)\s*\$?(\d+(?:\.\d+)?)', '='),
    ]
    for pattern, operator in patterns:
        matches = re.findall(pattern, question.lower())
        for m in matches:
            conditions.append((operator, float(m)))
    return conditions


def extract_text_conditions(question, table):
    """Extract text-based conditions, schema-aware (works with ANY database)."""
    conditions = []
    q_lower = question.lower()
    info = get_table_info()
    if table not in info:
        return conditions

    # Find best name/text columns from the actual schema
    name_cols = get_preferred_text_columns(table, info)

    # ── Name prefix / contains patterns (works for ANY table) ───────────
    starts_with = re.search(r'(?:name|names)\s+starts?\s+with\s+(?:a\s+)?([a-z])\b', q_lower)
    contains = re.search(r'(?:name|names)\s+(?:contains|has|includes?)\s+(?:a\s+)?([a-z])\b', q_lower)
    in_name = re.search(r'with\s+(?:a\s+)?([a-z])\s+(?:in|inside)\s+their\s+name\b', q_lower)
    # Broader pattern for "with [word(s)] in the/their name" (handles multi-character values)
    with_in_name = re.search(r'with\s+(?:a\s+)?([a-z][a-z\s]*?)\s+in\s+(?:the\s+)?(?:their\s+)?name\b', q_lower) if not (starts_with or contains or in_name) else None

    if (starts_with or contains or in_name or with_in_name) and name_cols:
        if starts_with:
            like_val = starts_with.group(1).upper() + '%'
        elif contains:
            like_val = '%' + contains.group(1).upper() + '%'
        elif in_name:
            like_val = '%' + in_name.group(1).upper() + '%'
        else:
            # with_in_name: extract just the first word (skip "a " prefix)
            val = with_in_name.group(1).strip()
            val = re.sub(r'^a\s+', '', val)  # Remove leading "a " if present
            like_val = '%' + val.upper() + '%'
        conditions.append((f'"{table}"."{name_cols[0]}"', "LIKE", f"'{like_val}'"))

    # ── Geography column matching (city, country, etc.) ────────────────
    geo_col_names = {"city", "country", "state", "region", "province", "shipcity", "shipcountry"}
    for col in info[table]:
        col_key = col["name"].lower().replace(" ", "").replace("_", "")
        if col_key in geo_col_names:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute(f'SELECT DISTINCT "{col["name"]}" FROM "{table}" WHERE "{col["name"]}" IS NOT NULL ORDER BY 1')
                values = [r[0] for r in cursor.fetchall() if r[0]]
                conn.close()
                for val in values:
                    if val and val.lower() in q_lower:
                        conditions.append((f'"{table}"."{col["name"]}"', "=", quote_sql_value(val)))
                        break
            except Exception:
                conn.close()

    # ── Named value matching (only if question mentions a likely value) ─
    if name_cols and any(w in q_lower for w in ["show", "find", "list", "get", "named", "called"]):
        # Skip if we already have a LIKE condition for this column (avoid redundant filters)
        has_like = any(c[1] == "LIKE" and name_cols[0].lower() in c[0].lower() for c in conditions)
        if not has_like:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute(f'SELECT DISTINCT "{name_cols[0]}" FROM "{table}" WHERE "{name_cols[0]}" IS NOT NULL')
                values = [r[0] for r in cursor.fetchall() if r[0]]
                conn.close()
                for val in values:
                    # Use word boundary check to avoid false positives like "IT" matching inside "whITe"
                    if val and re.search(r'\b' + re.escape(val.lower()) + r'\b', q_lower):
                        conditions.append((f'"{table}"."{name_cols[0]}"', "=", quote_sql_value(val)))
                        break
            except Exception:
                conn.close()

    return conditions


def extract_date_conditions(question):
    """Extract date-related conditions."""
    conditions = []
    q_lower = question.lower()

    # Year
    years = re.findall(r'\b(20\d\d)\b', question)
    for year in years:
        conditions.append(("OrderDate", ">=", "'{}-01-01'".format(year)))
        conditions.append(("OrderDate", "<", "'{}-01-01'".format(int(year) + 1)))

    # Month + Year, e.g. "orders in January 2017"
    for month_name, month_num in MONTHS.items():
        if month_name in q_lower:
            for year in re.findall(r'\b(20\d\d)\b', question):
                conditions.append((
                    "OrderDate", ">=",
                    "'{}-{:02d}-01'".format(year, month_num)
                ))
                if month_num == 12:
                    end = "{}-01-01".format(int(year) + 1)
                else:
                    end = "{}-{:02d}-01".format(year, month_num + 1)
                conditions.append(("OrderDate", "<", "'{}'".format(end)))
                break
            break

    # "last month", "this month", "this year", "last year"
    import datetime
    now = datetime.datetime.now()
    if "last month" in q_lower:
        first_of_last = (now.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        first_of_this = now.replace(day=1)
        conditions.append(("OrderDate", ">=", "'{}'".format(first_of_last.strftime('%Y-%m-%d'))))
        conditions.append(("OrderDate", "<", "'{}'".format(first_of_this.strftime('%Y-%m-%d'))))
    elif "this month" in q_lower:
        first_of_this = now.replace(day=1)
        next_month = (first_of_this + datetime.timedelta(days=32)).replace(day=1)
        conditions.append(("OrderDate", ">=", "'{}'".format(first_of_this.strftime('%Y-%m-%d'))))
        conditions.append(("OrderDate", "<", "'{}'".format(next_month.strftime('%Y-%m-%d'))))
    elif "this year" in q_lower:
        first_of_year = now.replace(month=1, day=1)
        next_year = first_of_year.replace(year=first_of_year.year + 1)
        conditions.append(("OrderDate", ">=", "'{}'".format(first_of_year.strftime('%Y-%m-%d'))))
        conditions.append(("OrderDate", "<", "'{}'".format(next_year.strftime('%Y-%m-%d'))))
    elif "last year" in q_lower:
        first_of_last = now.replace(year=now.year - 1, month=1, day=1)
        first_of_this = now.replace(year=now.year, month=1, day=1)
        conditions.append(("OrderDate", ">=", "'{}'".format(first_of_last.strftime('%Y-%m-%d'))))
        conditions.append(("OrderDate", "<", "'{}'".format(first_of_this.strftime('%Y-%m-%d'))))

    # recent N (days/orders)
    recent_match = re.search(r'(?:recent|last|past)\s+(\d+)\s+(day|days|week|weeks|month|months)', q_lower)
    if recent_match:
        num = int(recent_match.group(1))
        unit = recent_match.group(2)
        if unit.startswith("day"):
            delta = datetime.timedelta(days=num)
        elif unit.startswith("week"):
            delta = datetime.timedelta(weeks=num)
        else:
            delta = datetime.timedelta(days=num * 30)
        cutoff = now - delta
        conditions.append(("OrderDate", ">=", "'{}'".format(cutoff.strftime('%Y-%m-%d'))))

    # "in 2017", "during 2016"
    in_year = re.search(r'\b(in|during)\s+(20\d\d)\b', q_lower)
    if in_year and not any("OrderDate" in c for c in conditions):
        year = in_year.group(2)
        conditions.append(("OrderDate", ">=", "'{}-01-01'".format(year)))
        conditions.append(("OrderDate", "<", "'{}-01-01'".format(int(year) + 1)))

    return conditions


def detect_order_by(question):
    """Detect ORDER BY clause."""
    q_lower = question.lower()

    # "top N" or "N most" or "N highest"
    top_match = re.search(r'(?:top|first)\s+(\d+)', q_lower)
    if top_match:
        return "DESC", int(top_match.group(1))

    # "bottom N" or "N lowest" or "N least"
    bottom_match = re.search(r'(?:bottom|last)\s+(\d+)', q_lower)
    if bottom_match:
        return "ASC", int(bottom_match.group(1))

    # "most recent" / "newest" -> order by date DESC
    if re.search(r'(most\s+)?recent|newest|latest', q_lower):
        return "DESC", None

    # "oldest" / "earliest"
    if re.search(r'oldest|earliest', q_lower):
        return "ASC", None

    # "highest" / "largest" / "most expensive"
    if re.search(r'highest|largest|most\s+expensive|maximum', q_lower):
        return "DESC", None

    # "lowest" / "cheapest" / "smallest"
    if re.search(r'lowest|cheapest|smallest|minimum|least\s+expensive', q_lower):
        return "ASC", None

    return None, None


def natural_language_to_sql(question):
    """Convert a natural language question to SQL."""
    q_lower = question.lower()
    table = detect_table(question)
    info = get_table_info()

    # Determine if this is a COUNT query
    is_count = bool(re.search(r'\b(count|how many|how much|total number|number of)\b', q_lower))

    # Determine columns to select
    columns = []

    if is_count:
        # "count of orders by customer" needs GROUP BY
        if re.search(r'(?:by|per|for each|group by)\s+(customer|product|category|country|city|employee|supplier)', q_lower):
            by_match = re.search(r'(?:by|per|for each)\s+(customer|product|category|country|city|employee|supplier)', q_lower)
            group_col = by_match.group(1)

            group_table_map = {
                "customer": ("Customers", "CompanyName"),
                "product": ("Products", "ProductName"),
                "category": ("Categories", "CategoryName"),
                "country": (table, "ShipCountry" if table == "Orders" else "Country"),
                "city": (table, "ShipCity" if table == "Orders" else "City"),
                "employee": ("Employees", "FirstName || ' ' || LastName"),
                "supplier": ("Suppliers", "CompanyName"),
            }

            if group_col in group_table_map:
                gt, gc = group_table_map[group_col]
                select_expr = "{}.{} AS {}".format(gt, gc, gc.split("||")[0].strip().replace("'", "").strip())
                return build_count_group_by_sql(question, table, select_expr, gt, gc)
        else:
            # Simple count
            return build_simple_count_sql(question, table)

    # Detect columns mentioned
    if table == "Orders":
        if re.search(r'freight|shipping cost|shipping|ship', q_lower):
            columns.append("Orders.Freight")
        if re.search(r'date|when|order date|shipped date|required', q_lower):
            columns.append("Orders.OrderDate")
        if re.search(r'customer|company|client', q_lower):
            columns.append("Customers.CompanyName")
        if re.search(r'employee|who|staff|worker', q_lower):
            columns.append("Employees.FirstName || ' ' || Employees.LastName AS Employee")
    elif table == "Products":
        if re.search(r'stock|inventory|available|units\s+in\s+stock', q_lower):
            columns.append("Products.UnitsInStock")
        if re.search(r'price|cost|\$', q_lower):
            columns.append("Products.UnitPrice")
        if re.search(r'category|categories', q_lower):
            columns.append("Categories.CategoryName")
        if re.search(r'supplier|vendor', q_lower):
            columns.append("Suppliers.CompanyName AS Supplier")
        if re.search(r'discontinued', q_lower):
            columns.append("Products.Discontinued")
    elif table == "Customers":
        if re.search(r'country|city|address|location', q_lower):
            columns.append("Customers.Country")
            columns.append("Customers.City")
        if re.search(r'contact|phone|fax', q_lower):
            columns.append("Customers.ContactName")
            columns.append("Customers.Phone")

    return build_general_select_sql(question, table, columns)


def build_simple_count_sql(question, table):
    """Build a simple COUNT query."""
    conditions = extract_number_conditions(question)

    sql = 'SELECT COUNT(*) AS Count FROM "{}"'.format(table)

    joins = []
    where_clauses = []

    # Check if we need to join for conditions
    if table == "Products" and any("CategoryName" in str(c) for c in conditions):
        joins.append('JOIN Categories ON Products.CategoryID = Categories.CategoryID')

    # Add numeric conditions
    for op, val in conditions:
        if table == "Orders":
            where_clauses.append('Freight {} {}'.format(op, val))
        elif table == "Products":
            where_clauses.append('UnitPrice {} {}'.format(op, val))
        elif table == "Order Details":
            where_clauses.append('UnitPrice {} {}'.format(op, val))

    # Add text conditions
    text_conditions = extract_text_conditions(question, table)
    for col, op, val in text_conditions:
        where_clauses.append('{} {} {}'.format(col, op, val))

    if joins:
        sql = 'SELECT COUNT(*) AS Count FROM "{}" {}'.format(table, ' '.join(joins))

    if where_clauses:
        sql += ' WHERE ' + ' AND '.join(where_clauses)

    return sql


def build_count_group_by_sql(question, table, select_expr, group_table, group_col):
    """Build a COUNT with GROUP BY query."""
    conditions = extract_number_conditions(question)

    # Build the SQL
    sql = 'SELECT {}, COUNT(*) AS Count '.format(select_expr)

    if table == group_table:
        sql += 'FROM "{}"'.format(table)
    else:
        sql += 'FROM "{}"'.format(table)

    joins = []

    # Add necessary joins
    if table == "Orders" and group_table == "Customers":
        joins.append('JOIN Customers ON Orders.CustomerID = Customers.CustomerID')
    elif table == "Orders" and group_table == "Employees":
        joins.append('JOIN Employees ON Orders.EmployeeID = Employees.EmployeeID')
    elif table == "Order Details" and group_table == "Products":
        joins.append('JOIN Products ON "Order Details".ProductID = Products.ProductID')
    elif table == "Products" and group_table == "Categories":
        joins.append('JOIN Categories ON Products.CategoryID = Categories.CategoryID')
    elif table == "Products" and group_table == "Suppliers":
        joins.append('JOIN Suppliers ON Products.SupplierID = Suppliers.SupplierID')
    elif table == "Orders" and group_table == "Order Details":
        joins.append('JOIN "Order Details" ON Orders.OrderID = "Order Details".OrderID')

    if joins:
        sql += ' ' + ' '.join(joins)

    where_clauses = []
    text_conditions = extract_text_conditions(question, table)
    for col, op, val in text_conditions:
        where_clauses.append('{} {} {}'.format(col, op, val))

    if where_clauses:
        sql += ' WHERE ' + ' AND '.join(where_clauses)

    sql += ' GROUP BY {}'.format(group_col)
    sql += ' ORDER BY Count DESC'

    return sql


def build_general_select_sql(question, table, extra_columns):
    """Build a general SELECT query using schema metadata."""
    info = get_table_info()
    if table not in info:
        table = next(iter(info.keys())) if info else table

    all_columns = extra_columns[:] if extra_columns else []
    q_lower = question.lower()

    # Use schema-aware default columns if none requested
    if not all_columns:
        cols = [c["name"] for c in info.get(table, [])]
        if cols:
            all_columns = [f'"{table}"."{col}"' for col in cols[:6]]
        else:
            all_columns = [f'"{table}".*']

    # If specific column-like terms are present, prefer matching schema names
    for token in tokenize_text(question):
        for col in info.get(table, []):
            if token == normalize_text(col["name"]):
                col_name = col["name"]
                qualified = f'"{table}"."{col_name}"'
                if qualified not in all_columns:
                    all_columns.append(qualified)

    sql = 'SELECT {} FROM "{}"'.format(', '.join(all_columns), table)
    joins = []
    where_clauses = []

    # Add simple text matching WHERE clauses for columns found in the schema
    for col in info.get(table, []):
        col_name = col["name"]
        if re.search(rf'\b{re.escape(col_name.lower())}\b', q_lower):
            if re.search(rf'\b{re.escape(col_name.lower())}\s+(?:is|equals|=|contains|like)\s+([\w\s]+)', q_lower):
                match = re.search(rf'\b{re.escape(col_name.lower())}\s+(?:is|equals|=|contains|like)\s+([\w\s]+)', q_lower)
                if match:
                    value = match.group(1).strip()
                    where_clauses.append(f'"{table}"."{col_name}" = ' + quote_sql_value(value))

    # Add pattern matching conditions only for explicit value phrases
    explicit_match = re.search(r'\b(?:named|called|make|makes|from|in|about|of)\s+([a-z0-9 &"\'\-]+)', q_lower)
    if explicit_match:
        value = explicit_match.group(1).strip()
        if value and not re.match(r'^(what|who|show|list|find|give|give me)\b', value):
            preferred_cols = get_preferred_text_columns(table, info)
            if preferred_cols:
                col_name = preferred_cols[0]
                where_clauses.append(f'"{table}"."{col_name}" LIKE ' + quote_sql_value(f'%{value}%'))

    extra_conditions = extract_text_conditions(question, table)
    for col, op, val in extra_conditions:
        if '.' in col:
            clause = f'{col} {op} {val}'
        else:
            clause = f'"{table}"."{col}" {op} {val}'
        if clause not in where_clauses:
            where_clauses.append(clause)

    if where_clauses:
        sql += ' WHERE ' + ' AND '.join(sorted(set(where_clauses)))

    order_dir, limit = detect_order_by(question)
    if order_dir:
        sql += ' ORDER BY 1 ' + order_dir
        if limit:
            sql += ' LIMIT {}'.format(limit)
    elif not is_summary_query(question):
        sql += ' LIMIT 100'

    return sql


def quote_sql_value(value: str) -> str:
    escaped = value.replace("'", "''").strip()
    return f"'{escaped}'"


def is_summary_query(question):
    """Check if this is a summary/aggregate query that shouldn't be limited."""
    q_lower = question.lower()
    return bool(re.search(r'\b(count|how many|how much|total|average|avg|sum|max|min|group\s+by|per\s+|for\s+each)\b', q_lower))


def generate_sql(question):
    """Main entry point for NL-to-SQL conversion."""
    try:
        sql = natural_language_to_sql(question)
        sql = re.sub(r'\s+', ' ', sql).strip()
        if not sql.upper().startswith('SELECT'):
            first_table = next(iter(get_table_info().keys()), None)
            if first_table:
                sql = f'SELECT * FROM "{first_table}" LIMIT 50'
            else:
                sql = 'SELECT 1'
        return sql
    except Exception:
        first_table = next(iter(get_table_info().keys()), None)
        if first_table:
            return f'SELECT * FROM "{first_table}" LIMIT 50'
        return 'SELECT 1'


def execute_sql(sql):
    """Execute SQL query against the database and return results."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return columns, rows
    except Exception as e:
        conn.close()
        raise e


@app.route("/databases", methods=["GET"])
def databases():
    return jsonify(get_database_status())


@app.route("/databases/upload", methods=["POST"])
def upload_database():
    if "db_file" not in request.files:
        return jsonify({"error": "Missing 'db_file' in request."}), 400

    db_file = request.files["db_file"]
    filename = secure_filename(db_file.filename or "")
    if not is_valid_db_filename(filename):
        return jsonify({"error": "Invalid database filename. Use .db, .sqlite, or .sqlite3."}), 400

    save_name = filename
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(DATABASES_DIR, save_name)):
        save_name = f"{base}_{counter}{ext}"
        counter += 1

    target_path = os.path.join(DATABASES_DIR, save_name)
    db_file.save(target_path)
    set_current_database(save_name)

    return jsonify({"message": "Database uploaded and selected.", **get_database_status()})


@app.route("/databases/select", methods=["POST"])
def select_database():
    data = request.get_json() or {}
    filename = secure_filename(data.get("filename", ""))
    if not is_valid_db_filename(filename):
        return jsonify({"error": "Invalid database filename."}), 400

    if filename == get_current_database_name():
        return jsonify(get_database_status())

    try:
        set_current_database(filename)
    except FileNotFoundError:
        return jsonify({"error": "Database not found."}), 404

    return jsonify(get_database_status())


@app.route("/databases/<filename>", methods=["DELETE"])
def delete_database(filename):
    safe_name = secure_filename(filename)
    if safe_name != filename or not is_valid_db_filename(safe_name):
        return jsonify({"error": "Invalid database filename."}), 400

    if safe_name == get_current_database_name():
        return jsonify({"error": "Cannot delete the active database. Select another database first."}), 400

    files = list_available_databases()
    if len(files) <= 1:
        return jsonify({"error": "At least one database must remain available."}), 400

    target_path = os.path.join(DATABASES_DIR, safe_name)
    if not os.path.exists(target_path):
        return jsonify({"error": "Database not found."}), 404

    os.remove(target_path)
    return jsonify(get_database_status())


# ── Flask Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/query", methods=["POST"])
def query():
    global _conversation_history
    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "Missing 'question' in request body"}), 400

    question = data["question"].strip()
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    # Stage 1: relevance check
    relevance = check_relevance(question, _conversation_history)
    if not relevance["relevant"]:
        return jsonify({
            "is_relevant": False,
            "reason": relevance["reason"],
            "sql": None,
            "results": [],
            "columns": [],
        })

    # Stage 2: classify the intent and handle non-query inputs.
    classification = ask_classification(question, _conversation_history)
    category = classification.get("category", "db_query")

    # If the AI says irrelevant but the question looks like a short follow-up with
    # conversation history, override to db_query so the local rewrite and SQL
    # generation can handle it. This handles cases like "and white?" after a
    # previous query about "companies with cheese in the name".
    if category == "irrelevant" and _conversation_history and _looks_like_followup(question):
        category = "db_query"
        classification["category"] = "db_query"

    if category == "irrelevant":
        return jsonify({
            "is_relevant": False,
            "reason": classification.get("reason", "The question is unrelated to the database."),
            "sql": None,
            "results": [],
            "columns": [],
        })
    if category == "greeting":
        return jsonify({
            "is_relevant": True,
            "sql": None,
            "results": [],
            "columns": [],
            "message": "Hello! I can help you query your attached SQLite database using natural language."
        })
    if category == "showcase":
        return jsonify({
            "is_relevant": True,
            "sql": None,
            "results": [],
            "columns": [],
            "message": "I am a professional assistant for your attached SQLite database. Ask about tables, rows, and values present in the schema."
        })

    # Stage 3: rewrite follow-up and then check data availability
    if category == "followup" and classification.get("rewrite"):
        question = classification["rewrite"].strip()
    else:
        question = rewrite_followup_question(question, _conversation_history)
    availability = check_data_availability(question)
    if not availability["available"]:
        return jsonify({
            "is_relevant": False,
            "reason": availability["reason"],
            "sql": None,
            "results": [],
            "columns": [],
        })

    # Use configured AI provider and fall back to rule-based SQL generation when needed.
    result = ask_ai(question)
    if result["action"] == "DENY":
        return jsonify({
            "is_relevant": False,
            "reason": result["reason"],
            "sql": None,
            "results": [],
            "columns": [],
        })

    sql = result.get("sql") if result["action"] == "SQL" else None
    if not sql:
        sql = generate_sql(question)

    try:
        columns, results = execute_sql(sql)
        # Save to history for follow-up questions
        _conversation_history.append({"q": question, "sql": sql})
        if len(_conversation_history) > MAX_HISTORY:
            _conversation_history.pop(0)
        return jsonify({
            "is_relevant": True,
            "sql": sql,
            "results": results,
            "columns": columns,
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "is_relevant": True,
            "sql": None,
            "results": []
        }), 500


@app.route("/schema", methods=["GET"])
def schema():
    """Return the database schema for reference."""
    info = get_table_info()
    return jsonify(info)


if __name__ == "__main__":
    # Initialize schema cache
    get_table_info()
    PORT = int(os.environ.get("PORT", "5005"))
    HOST = os.environ.get("HOST", "0.0.0.0")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=DEBUG, host=HOST, port=PORT)
