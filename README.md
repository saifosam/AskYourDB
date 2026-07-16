# AskYourDB

> **Natural Language → SQL → Database Results**  
> Ask questions in plain English and get answers from your SQLite databases — powered by AI.

---

## Overview

AskYourDB is a web application that converts natural language questions into SQL queries and executes them against SQLite databases. It uses a **multi-stage AI pipeline** — combining rule-based checks with LLM-powered classification and SQL generation — to ensure accurate, relevant results.

### The Pipeline

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

---

## Features

- **Natural Language Queries** — Ask questions like *"Show me all customers from Germany"* or *"What are the top 5 most expensive products?"*
- **Multi‑Provider AI Support** — Works with **Google Gemini**, **OpenRouter**, or a local **Ollama** model
- **Automatic Schema Discovery** — Analyzes your SQLite database and extracts tables, columns, foreign keys, and sample data
- **Smart Fallback** — If the AI provider is unavailable, a rule‑based NL‑to‑SQL engine generates the query
- **Relevance Checking** — Filters out irrelevant questions (weather, news, jokes, etc.)
- **Conversation History** — Supports follow‑up questions with context awareness
- **Database Manager** — Upload, select, and delete SQLite databases through the UI
- **Dark‑mode UI** — Clean, modern chat interface with collapsible SQL blocks and results tables

---

## Architecture

### Tech Stack

| Layer        | Technology                          |
|--------------|-------------------------------------|
| Backend      | Python + Flask                      |
| Frontend     | HTML, CSS (vanilla)                 |
| Database     | SQLite                              |
| AI Providers | Google Gemini, OpenRouter, Ollama   |
| HTTP Client  | `requests`                          |

### Key Files

```
AskYourDB/
├── app.py              # Flask backend — all routes, AI logic, NL-to-SQL engine
├── templates/
│   └── index.html      # Chat UI frontend
├── static/
│   └── style.css       # Dark‑mode styling
├── databases/          # Uploaded SQLite databases
│   ├── northwind.db
│   ├── default.db
│   └── Chinook_Sqlite_AutoIncrementPKs.sqlite
├── test_app_logic.py   # Unit tests (59 tests)
├── requirements.txt    # Python dependencies
├── .env                # API keys (GEMINI_API_KEY, OPENROUTER_API_KEY)
├── LICENSE             # MIT License
└── README.md           # This file
```

---

## Setup

### Prerequisites

- Python 3.10+
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd AskYourDB
   ```

2. **Install dependencies**
   ```bash
   pip install flask python-dotenv google-genai requests werkzeug
   ```

3. **Configure AI provider**

   Edit the provider settings in `app.py`:
   ```python
   AI_PROVIDER = "ollama"   # "google" | "openrouter" | "ollama"
   ```

   Or set API keys in a `.env` file:
   ```
   GEMINI_API_KEY=your_gemini_key_here
   OPENROUTER_API_KEY=your_openrouter_key_here
   ```

4. **Start the app**
   ```bash
   python app.py
   ```

5. **Open in browser** → [http://localhost:5005](http://localhost:5005)

### AI Provider Options

| Provider     | Requires API Key | Model (configurable)        | Notes                           |
|-------------|-----------------|----------------------------|----------------------------------|
| **Ollama**   | ❌ No           | `qwen2.5-coder:7b`         | Default; runs locally            |
| **Google**   | ✅ `GEMINI_API_KEY` | `gemini-2.0-flash-lite` | Free tier available              |
| **OpenRouter** | ✅ `OPENROUTER_API_KEY` | `gpt-4o-mini`         | Access to many models            |

The app auto‑fallbacks to another provider if the selected one's API key is missing.

---

## Usage

### Asking Questions

Just type your question in natural language and press **Enter** (or click the send button).

**Example questions** (with the Northwind database):
- *"Show me all customers from Germany"*
- *"What are the top 5 most expensive products?"*
- *"How many orders were placed in 2017?"*
- *"List all employees and their countries"*
- *"Who are the suppliers in the USA?"*

### Follow‑up Questions

After asking a question, you can ask follow‑ups like:
- *"What about France?"* (after asking about Germany)
- *"And those starting with C?"* (referring to the previous list)
- *"Now show me the suppliers"* (after seeing customers)

### Managing Databases

Click **Manage DB** in the header to:
- **Upload** a new SQLite database (.db, .sqlite, .sqlite3)
- **Select** an existing database to query
- **Delete** a database (at least one must remain)

---

## How It Works (Detailed Flow)

### 1. Relevance Check (`check_relevance()`)

A fast, rule‑based filter runs before any AI call:
- Checks for **irrelevant keywords** (weather, news, jokes, politics, etc.)
- Compares question tokens against **schema tokens** (table/column names)
- Detects **question words** (what, who, where, show, find, list, etc.)

If the question passes, it moves to AI classification.

### 2. AI Classification (`ask_classification()`)

The configured AI provider classifies the input into one of:
- **`greeting`** — Returns a friendly welcome message
- **`showcase`** — Returns a description of the assistant's capabilities
- **`followup`** — Rewrites the question into a standalone query using conversation history
- **`db_query`** — Proceeds to SQL generation
- **`irrelevant`** — Returns a denial message

### 3. Schema Extraction (`_build_schema_prompt()`)

The app extracts rich metadata from the connected SQLite database:
- **Table names and column names + types** (via `PRAGMA table_info`)
- **Foreign key relationships** (via `PRAGMA foreign_key_list`)
- **Sample rows** (first 3 rows from each table)
- **Key column value previews** (distinct values from name/title/company/city columns)
- All content is **auto‑sized** to fit within a 3000‑token budget using a compact format

### 4. AI SQL Generation (`ask_ai()`)

The schema context is sent to the AI provider with the user's question. The AI responds with either:
- **`SQL: <query>`** — A valid SQLite SELECT statement
- **`DENY: <reason>`** — If the question cannot be answered from the schema

**Fallback chain**: If the AI provider fails (or returns invalid SQL), the app falls back to:
1. A different AI provider (if available)
2. A **rule‑based NL‑to‑SQL engine** (`generate_sql()`) that handles:
   - Table detection (schema‑aware)
   - Column aliases (name → ProductName/CompanyName, etc.)
   - COUNT queries with GROUP BY
   - Numeric conditions (over $50, at least 10, etc.)
   - Text conditions (contains, starts with, geography matching)
   - Date conditions (year, month, "last month", "recent 7 days")
   - ORDER BY and LIMIT detection (top N, most recent, cheapest, etc.)

### 5. Execute SQL (`execute_sql()`)

The generated SQL runs against the database and returns results as:
- **columns**: Array of column names
- **results**: Array of row objects

Results are displayed in a **collapsible SQL block** + **results table** in the chat UI.

---

## Testing

```bash
python -m pytest test_app_logic.py -v
```

The test suite covers:
- ❌ Irrelevant prompts are denied (weather, nonsense)
- ❌ Money queries denied when no financial data exists
- ✅ Valid queries allowed (people names, country questions)
- ✅ Follow‑up question rewriting
- ✅ Data availability checks
- ✅ NL‑to‑SQL engine unit tests
- ✅ AI response parsing, follow‑up rewriting, and edge cases

---

## Configuration

### Environment Variables (`.env`)

| Variable             | Description                    |
|----------------------|--------------------------------|
| `GEMINI_API_KEY`     | Google Gemini API key          |
| `OPENROUTER_API_KEY` | OpenRouter API key             |
| `DB_PATH`            | Custom database file path      |

### Provider Configuration (`app.py`)

```python
AI_PROVIDER       = "ollama"       # google | openrouter | ollama
AI_GOOGLE_MODEL   = "gemini-2.0-flash-lite"
AI_OPENROUTER_MODEL = "gpt-4o-mini"
AI_OLLAMA_MODEL   = "qwen2.5-coder:7b"
AI_OLLAMA_BASE_URL = "http://localhost:11434/v1"
```

---

## API Endpoints

| Method | Endpoint               | Description                       |
|--------|------------------------|----------------------------------|
| GET    | `/`                    | Serve the chat interface           |
| POST   | `/query`               | Submit a natural language query    |
| GET    | `/schema`              | Get the current database schema    |
| GET    | `/databases`           | List available databases           |
| POST   | `/databases/upload`    | Upload a new SQLite database       |
| POST   | `/databases/select`    | Switch the active database         |
| DELETE | `/databases/<filename>`| Delete an uploaded database        |

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Saif. You are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software.

