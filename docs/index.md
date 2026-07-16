---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "AskYourDB"
  text: "Natural language questions into SQL queries"
  tagline: A Flask-based AI pipeline that converts plain English to SQL, executes it against SQLite databases, and returns results — all through a sleek chat interface.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/getting-started
    - theme: alt
      text: View Examples
      link: /examples
    - theme: alt
      text: GitHub
      link: https://github.com/saifosam/AskYourDB

features:
  - title: Natural Language Queries
    details: "Ask questions like \"Show me all customers from Germany\" or \"What are the top 5 most expensive products?\" — no SQL required."
  - title: Multi-Provider AI
    details: "Works with Google Gemini, OpenRouter, or a local Ollama model. Smart auto-fallback if your provider is unavailable."
  - title: Automatic Schema Discovery
    details: "Analyzes your SQLite database and extracts tables, columns, foreign keys, and sample data — no manual configuration."
  - title: Schema-RAG Vector Search
    details: "Embeds table schemas and retrieves only the most relevant tables for each query, keeping token usage low and accuracy high."
  - title: Smart Fallback Engine
    details: "If AI providers fail, a rule-based NL-to-SQL engine handles table detection, column aliases, numeric/text conditions, and date parsing."
  - title: Rich Chat UI
    details: "Dark-mode interface with collapsible SQL blocks, results tables, conversation history, and a built-in database manager."
---
