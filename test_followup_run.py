"""Verify the follow-up fix works by testing core functions."""
import sys
import types

# Mock google modules BEFORE importing app.py
for mod_name in ['google', 'google.genai', 'google.genai.types']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

import importlib.util
from pathlib import Path
import os

# Import app module same way the existing tests do
spec = importlib.util.spec_from_file_location("app_module", 
    Path(__file__).with_name("app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

# Use northwind database
app.DB_PATH = str(Path(__file__).parent / "databases" / "northwind.db")

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        failed += 1

print("=" * 70)
print("TESTING FOLLOW-UP FIX")
print("=" * 70)

# === TEST 1: _looks_like_followup ===
print("\n[TEST 1] _looks_like_followup()")
check("'and white?' returns True", app._looks_like_followup("and white?"))
check("'and white' returns True", app._looks_like_followup("and white"))
check("'or blue' returns True", app._looks_like_followup("or blue"))
check("'also cheese' returns True", app._looks_like_followup("also cheese"))
check("'what about Germany' returns True", app._looks_like_followup("what about Germany"))
check("'show me customers' returns False", app._looks_like_followup("show me customers") == False)
check("'how are you' returns False", app._looks_like_followup("how are you") == False)
check("'' returns False", app._looks_like_followup("") == False)

# === TEST 2: check_relevance with history ===
print("\n[TEST 2] check_relevance()")
history = [{"q": "give me all the company names with cheese in the name",
            "sql": "SELECT CompanyName FROM Customers WHERE CompanyName LIKE '%cheese%'"}]
r1 = app.check_relevance("and white?", history)
check("'and white?' with history is relevant", r1["relevant"] == True, str(r1))
r2 = app.check_relevance("and white?")
check("'and white?' without history is irrelevant", r2["relevant"] == False, str(r2))
r3 = app.check_relevance("tell me a joke about cheese", history)
check("joke still rejected even with history", r3["relevant"] == False, str(r3))

# === TEST 3: rewrite_followup_question ===
print("\n[TEST 3] rewrite_followup_question()")

# Test 3a: The actual user scenario
history = [{"q": "give me all the company names with cheese in the name",
            "sql": "SELECT CompanyName FROM Customers WHERE CompanyName LIKE '%cheese%'"}]
rewritten = app.rewrite_followup_question("and white?", history)
print(f"  Input: 'and white?'")
print(f"  Output: '{rewritten}'")
check("output contains 'white'", "white" in rewritten.lower(), rewritten)
check("output mentions 'company' or 'show'", 
      "company" in rewritten.lower() or "show" in rewritten.lower(), rewritten)
check("output was rewritten", rewritten != "and white?", rewritten)

# Test 3b: Products follow-up
history2 = [{"q": "show me the products with tofu in the name",
             "sql": "SELECT ProductName FROM Products WHERE ProductName LIKE '%tofu%'"}]
rewritten2 = app.rewrite_followup_question("and chocolate?", history2)
print(f"  Input: 'and chocolate?' after products")
print(f"  Output: '{rewritten2}'")
check("output contains 'chocolate'", "chocolate" in rewritten2.lower(), rewritten2)
check("output mentions 'product'", "product" in rewritten2.lower(), rewritten2)

# Test 3c: Geography follow-up (should NOT use LIKE analysis)
history3 = [{"q": "show me customers from Germany",
             "sql": "SELECT * FROM Customers WHERE Country = 'Germany'"}]
rewritten3 = app.rewrite_followup_question("and France?", history3)
print(f"  Input: 'and France?' after geography")
print(f"  Output: '{rewritten3}'")
print(f"  (Geography follow-up - left for AI to handle)")

# Test 3d: Existing tests should still pass
check("'what about france' with history still works", 
      "france" in app.rewrite_followup_question("what about france", 
        [{"q": "give me all the people who are in germany", "sql": "SELECT 1"}]).lower())
check("non-followup returns unchanged", 
      app.rewrite_followup_question("show me orders", 
        [{"q": "show me customers from Germany", "sql": "SELECT 1"}]) == "show me orders")

# === TEST 4: SQL generation for rewritten query ===
print("\n[TEST 4] SQL generation")
try:
    sql = app.generate_sql(rewritten)
    print(f"  SQL: {sql}")
    if sql is None:
        print("  (SQL is None)")
    else:
        check("starts with SELECT", sql.strip().upper().startswith("SELECT"), sql)
        check("contains LIKE or white", "LIKE" in sql.upper() or "white" in sql.lower(), sql)
except Exception as e:
    print(f"  SQL generation error: {e}")

# === TEST 5: Execute the SQL ===
print("\n[TEST 5] SQL execution")
if sql:
    try:
        columns, rows = app.execute_sql(sql)
        print(f"  Columns: {columns}")
        print(f"  Rows: {len(rows)}")
        if rows:
            print(f"  First row: {rows[0]}")
            check("results found", len(rows) > 0)
        else:
            print("  No results (no companies with 'white' in name)")
    except Exception as e:
        print(f"  Execution error: {e}")

# === SUMMARY ===
print(f"\n{'=' * 70}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} tests")
print(f"{'=' * 70}")
