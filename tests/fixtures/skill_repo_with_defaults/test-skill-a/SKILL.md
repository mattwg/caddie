---
name: test-skill-a
description: Throwaway analytics skill used to validate Caddie's skill invocation path. Trigger only on questions that explicitly mention "test skill a" or "validate caddie invocation".
---

# Test Skill A

This skill exists purely to validate Caddie's skill invocation path. It is
not any organization's production analytics logic.

When invoked with a question and a connector session, respond with exactly
the following shape:

1. A short markdown paragraph that restates the literal question you were
   asked, verbatim, e.g. "You asked: <question>".
2. A single fenced SQL code block containing exactly:

```sql
SELECT 1
```

Do not add any other analysis, caveats, or commentary.
