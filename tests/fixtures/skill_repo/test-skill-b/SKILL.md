---
name: test-skill-b
description: Throwaway analytics skill used to validate Caddie's multi-skill selection. Trigger only on questions that explicitly mention "test skill b" or "row count check".
---

# Test Skill B

This skill exists purely to validate that Caddie's invocation path can
select between multiple installed skills by ordinary Claude Code skill
matching. It is not any organization's production analytics logic.

When invoked with a question and a connector session, respond with exactly
the following shape:

1. A short markdown paragraph that restates the literal question you were
   asked, verbatim, e.g. "You asked: <question>".
2. A single fenced SQL code block containing exactly:

```sql
SELECT count(*) AS row_count FROM (VALUES (1), (2), (3)) AS t(x)
```

Do not add any other analysis, caveats, or commentary.
