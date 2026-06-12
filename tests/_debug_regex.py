"""Debug regex matching."""
import re

ql = "what infrastructure types exist in the data?"

_LIST_UNIQUE_KEYWORDS = [
    "list all", "what are the", "list the", "list every",
    "list each", "list unique", "list the unique", "all the unique",
    "all unique", "enumerate", "all of the", "all the different",
    "unique values of", "unique names of",
    "what types of", "what kinds of", "what categories of",
    "what type of", "what kind of",
]

_LIST_UNIQUE_REGEX = [
    r"what\s+\w+\s+(?:exist|are\s+there|are\s+found|are\s+present|can\s+be\s+found|do\s+we\s+have)",
    r"what\s+(?:different|various|kinds?\s+of|types?\s+of|categories?\s+of)",
]

print(f"Question: {ql}")
print()
print("Substring matches:")
for kw in _LIST_UNIQUE_KEYWORDS:
    if kw in ql:
        print(f"  ✅ '{kw}'")

print()
print("Regex matches:")
for p in _LIST_UNIQUE_REGEX:
    m = re.search(p, ql)
    if m:
        print(f"  ✅ '{p}' → matched '{m.group()}'")
    else:
        print(f"  ❌ '{p}'")

# Fix: the pattern needs to handle "types" as the word before "exist"
print()
print("Fixed regex:")
fixed = r"what\s+\w+\s+(?:types?\s+)?(?:exist|are\s+there)"
m = re.search(fixed, ql)
print(f"  Pattern: {fixed}")
print(f"  Match: {m.group() if m else 'NO MATCH'}")
