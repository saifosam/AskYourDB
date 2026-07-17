"""Test the follow-up query fix by simulating the two-request flow."""
import importlib.util
from pathlib import Path
import json
import re

# Import the app module
spec = importlib.util.spec_from_file_location("app_module", 
    Path(__file__).with_name("app.py"))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

# Clear any existing conversation history
app_module._conversation_history = []

# Simulate the first question
q1 = "give me all the company names with cheese in the name"

print("=" * 60)
print(f"STEP 1: User asks: \"{q1}\"")
print("=" * 60)

# Stage 1: check relevance
rel1 = app_module.check_relevance(q1, app_module._conversation_history)
print(f"  Stage 1 (relevance): {rel1}")

# Stage 2: classify
cls1 = app_module.ask_classification(q1, app_module._conversation_history)
print(f"  Stage 2 (classification): {cls1}")

# Stage 3: rewrite (won't do much for first question)
cat1 = cls1.get("category", "db_query")
if cat1 == "followup" and cls1.get("rewrite"):
    q1_rewritten = cls1["rewrite"].strip()
else:
    q1_rewritten = app_module.rewrite_followup_question(q1, app_module._conversation_history)
print(f"  Stage 3 (rewrite): \"{q1_rewritten}\"")

# SQL generation
sql1 = app_module.generate_sql(q1_rewritten)
print(f"  Generated SQL: {sql1}")

# Execute
try:
    cols1, rows1 = app_module.execute_sql(sql1)
    print(f"  Results: {len(rows1)} rows")
    for r in rows1[:3]:
        print(f"    {r}")
except Exception as e:
    print(f"  Error: {e}")

# Save to history
app_module._conversation_history.append({"q": q1_rewritten, "sql": sql1})
print(f"\n  History saved: {len(app_module._conversation_history)} entry/entries")

print()

# Simulate the second question (follow-up)
q2 = "and white?"

print("=" * 60)
print(f"STEP 2: User asks: \"{q2}\"")
print("=" * 60)

# Stage 1: check relevance (with history)
rel2 = app_module.check_relevance(q2, app_module._conversation_history)
print(f"  Stage 1 (relevance): {rel2}")

if not rel2["relevant"]:
    print("  ❌ STAGE 1 REJECTED! Bug not fixed.")
else:
    print("  ✅ Stage 1 passed!")

    # Stage 2: classify
    cls2 = app_module.ask_classification(q2, app_module._conversation_history)
    cat2 = cls2.get("category", "db_query")
    print(f"  Stage 2 (classification): {cls2}")

    # Stage 2 override (the new fix)
    if cat2 == "irrelevant" and app_module._conversation_history and app_module._looks_like_followup(q2):
        print("  ⚡ Stage 2 override: irrelevant → db_query")
        cat2 = "db_query"

    if cat2 == "irrelevant":
        print("  ❌ STAGE 2 REJECTED as irrelevant!")
    else:
        # Stage 3: rewrite
        if cat2 == "followup" and cls2.get("rewrite"):
            q2_rewritten = cls2["rewrite"].strip()
            print(f"  Stage 3 (AI rewrite): \"{q2_rewritten}\"")
        else:
            q2_rewritten = app_module.rewrite_followup_question(q2, app_module._conversation_history)
            print(f"  Stage 3 (local rewrite): \"{q2_rewritten}\"")

        # Check if rewrite worked
        if q2_rewritten and q2_rewritten != app_module.rewrite_followup_question(q2, []):
            print(f"  ✅ Follow-up was rewritten!")
        elif q2_rewritten != q2:
            print(f"  ✅ Follow-up was rewritten!")
        else:
            print(f"  ⚠️  Question was NOT rewritten")

        # SQL generation
        sql2 = app_module.generate_sql(q2_rewritten)
        print(f"  Generated SQL: {sql2}")

        # Execute
        try:
            cols2, rows2 = app_module.execute_sql(sql2)
            print(f"  Results: {len(rows2)} rows")
            for r in rows2[:5]:
                print(f"    {r}")
            if len(rows2) > 0:
                print(f"  ✅ Final result: SUCCESS!")
            else:
                print(f"  ⚠️  No results (empty set)")
        except Exception as e:
            print(f"  ❌ SQL execution error: {e}")

print()
print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)
