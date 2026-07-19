"""Fix remaining issues in app.py"""
import sys

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Change COALESCE(SUM(...), 0) back to bare SUM(...)
content = content.replace('COALESCE(SUM("', 'SUM("')
content = content.replace('"), 0) AS Revenue', '") AS Revenue')
print("Fix 1: Replaced COALESCE(SUM) with bare SUM")

# Fix 2: Add directive to CLASSIFICATION_SYSTEM_PROMPT
old = (
    '    "The \'--- Available tables\' section below lists EVERY valid query target. "\n'
    '    "If the user mentions a table name listed there, or an everyday synonym "\n'
    '    "for one of those tables, it IS a valid db_query \xe2\x80\x94 do NOT mark it irrelevant."\n'
    ')'
)
new = (
    '    "The \'--- Available tables\' section below lists EVERY valid query target. "\n'
    '    "If the user mentions a table name listed there, or an everyday synonym "\n'
    '    "for one of those tables, it IS a valid db_query \xe2\x80\x94 do NOT mark it irrelevant."\n'
    '    "--- Common-sense rule ---\\n"\n'
    '    "Common sense: if the question describes something conceptually related to "\n'
    '    "ANY table or its data (e.g. a \'movie\' relates to a table about films/videos; "\n'
    '    "\'weather\' does not), treat it as db_query, not irrelevant. "\n'
    '    "When in doubt, prefer db_query over irrelevant.\\n"\n'
    '    "The user is asking about the ATTACHED database. If the question could "\n'
    '    "conceivably be answered by querying tables in the schema, it is db_query.\\n"\n'
    '    "Only mark something irrelevant if it is TRULY unrelated (e.g. politics, weather, news, math)."\n'
    ')'
)

if old in content:
    content = content.replace(old, new)
    print("Fix 2: Updated CLASSIFICATION_SYSTEM_PROMPT with common-sense directive")
else:
    print("WARN: Could not find old prompt end")
    idx = content.find("Available tables' section below")
    if idx >= 0:
        print(f"Found at {idx}: {repr(content[idx:idx+400])}")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done writing app.py")
