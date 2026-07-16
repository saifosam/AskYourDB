# Getting Started

## 1. Prerequisites

- Python 3.10+
- pip

## 2. Clone & Install

```bash
git clone <repository-url>
cd AskYourDB

pip install flask python-dotenv google-genai requests werkzeug
```

## 3. Configure AI Provider

Edit the provider settings in `app.py`:

```python
AI_PROVIDER = "ollama"   # "google" | "openrouter" | "ollama"
```

Or set API keys in a `.env` file:

```
GEMINI_API_KEY=your_gemini_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

### Provider Options

| Provider     | Requires API Key | Model                     | Notes                       |
|-------------|-----------------|---------------------------|-----------------------------|
| **Ollama**   | ❌ No           | `qwen2.5-coder:7b`        | Default; runs locally       |
| **Google**   | ✅ `GEMINI_API_KEY` | `gemini-2.0-flash-lite` | Free tier available         |
| **OpenRouter** | ✅ `OPENROUTER_API_KEY` | `gpt-4o-mini`          | Access to many models       |

The app auto-fallbacks to another provider if the selected one's API key is missing.

## 4. Start the App

```bash
python app.py
```

Open your browser to **`http://localhost:5005`**

## 5. Ask Your First Question

With the Northwind sample database loaded, try typing:

> *"Show me all customers from Germany"*

The app will:
1. Check if your question is relevant to the database
2. Classify it as a database query
3. Extract the schema context
4. Generate a SQL query via AI
5. Execute it and display the results

## Key Concepts

- **Natural Language Input** — Just type what you want to know, in plain English
- **Conversation History** — Ask follow-ups like *"What about France?"* and the app remembers context
- **Collapsible SQL** — Click to view or hide the generated SQL for any response
- **Database Manager** — Upload, select, and delete SQLite databases through the UI

## Sample Databases

The project includes three sample databases to get started:

- **`northwind.db`** — Classic Northwind trading company (customers, orders, products, suppliers)
- **`Chinook_Sqlite_AutoIncrementPKs.sqlite`** — Digital media store (artists, albums, tracks, invoices)
- **`default.db`** — Custom starter database

Upload your own `.db`, `.sqlite`, or `.sqlite3` files anytime.
