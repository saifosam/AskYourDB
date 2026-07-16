# Architecture

AskYourDB uses a **multi-stage AI pipeline** — combining rule-based checks with LLM-powered classification and SQL generation.

## The Pipeline

```
[User sends a query]
       │
       ▼
┌─────────────────────────────────────────────┐
│ STAGE 1: Rule‑Based Relevance Check         │
│ check_relevance()                           │
│ • Keyword filtering (weather, news, etc.)   │
│ • Schema token matching                     │
│ • Question‑word detection (what, who, how)  │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ STAGE 2: AI Classification (AI.1)           │
│ ask_classification()                        │
│ • Categories: greeting, showcase, followup, │
│   db_query, irrelevant                      │
│ • Follow‑up rewrite into standalone query   │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ STAGE 3: Schema Extraction                  │
│ _build_schema_prompt()                      │
│ • Table names, column names & types         │
│ • Foreign key relationships                 │
│ • Sample rows (first 3)                     │
│ • Key column value previews                 │
│ • Auto‑sized to fit token budget            │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ STAGE 4: AI SQL Generation (AI.2)           │
│ ask_ai() → ask_gemini / ask_openrouter      │
│             / ask_ollama                    │
│ • Generates SQL: or DENY: response          │
│ • Falls back to rule‑based generate_sql()   │
│   if AI unavailable                         │
└─────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ STAGE 5: Execute SQL                        │
│ execute_sql()                               │
│ • Runs the generated SELECT query           │
│ • Returns columns + rows as JSON            │
└─────────────────────────────────────────────┘
       │
       ▼
[Results displayed in the chat UI]
```

## Stage Details

### Stage 1: Relevance Check

A fast, rule-based filter that runs before any AI call:

- Checks for **irrelevant keywords** (weather, news, jokes, politics, etc.)
- Compares question tokens against **schema tokens** (table/column names)
- Detects **question words** (what, who, where, show, find, list, etc.)

If the question passes, it moves to AI classification.

### Stage 2: AI Classification

The configured AI provider classifies the input into one of:

- **`greeting`** — Returns a friendly welcome message
- **`showcase`** — Returns a description of the assistant's capabilities
- **`followup`** — Rewrites the question into a standalone query using conversation history
- **`db_query`** — Proceeds to SQL generation
- **`irrelevant`** — Returns a denial message

### Stage 3: Schema Extraction with Schema-RAG

Schema extraction provides the AI with rich context about the database:

- **Table names and column names + types** (via `PRAGMA table_info`)
- **Foreign key relationships** (via `PRAGMA foreign_key_list`)
- **Sample rows** (first 3 rows from each table)
- **Key column value previews** (distinct values from name/title/company/city columns)

**Schema-RAG** (Retrieval-Augmented Generation) enhances this stage:

- Each table's schema is embedded as a vector using Ollama or Google's embedding API
- When a question arrives, it's embedded and compared against table embeddings via cosine similarity
- Only the top-5 most relevant tables are included in the prompt, dramatically reducing token usage
- Embeddings are cached to disk, so they persist across restarts

### Stage 4: AI SQL Generation

The schema context is sent to the AI provider with the user's question. The AI responds with either:

- **`SQL: <query>`** — A valid SQLite SELECT statement
- **`DENY: <reason>`** — If the question cannot be answered from the schema

**Fallback chain**: If the AI provider fails (or returns invalid SQL), the app falls back to:

1. A different AI provider (if available)
2. A **rule-based NL-to-SQL engine** (`generate_sql()`) that handles:
   - Table detection (schema-aware)
   - Column aliases (name → ProductName/CompanyName, etc.)
   - COUNT queries with GROUP BY
   - Numeric conditions (over $50, at least 10, etc.)
   - Text conditions (contains, starts with, geography matching)
   - Date conditions (year, month, "last month", "recent 7 days")
   - ORDER BY and LIMIT detection (top N, most recent, cheapest, etc.)

### Stage 5: Execute SQL

The generated SQL runs against the database and returns results as:

- **columns**: Array of column names
- **results**: Array of row objects

Results are displayed in a collapsible SQL block + results table in the chat UI.

## Tech Stack

| Layer        | Technology                          |
|-------------|-------------------------------------|
| Backend      | Python + Flask                      |
| Frontend     | HTML, CSS (vanilla)                 |
| Database     | SQLite                              |
| AI Providers | Google Gemini, OpenRouter, Ollama   |
| HTTP Client  | `requests`                          |
| Schema-RAG   | Vector embeddings via Ollama/Google |

## Key Files

```
AskYourDB/
├── app.py              # Flask backend — all routes, AI logic, NL-to-SQL engine
├── templates/
│   └── index.html      # Chat UI frontend (dark mode, collapsible SQL, results table)
├── static/
│   └── style.css       # Dark‑mode styling
├── databases/          # Uploaded SQLite databases
├── test_app_logic.py   # Unit tests (59+ tests)
├── requirements.txt    # Python dependencies
├── .env                # API keys (GEMINI_API_KEY, OPENROUTER_API_KEY)
└── README.md           # Full documentation
```
