# Prompt Catalog Schema

This directory contains prompt assets written as **markdown files with YAML
frontmatter**. The catalog is the source of truth for which prompt maps to
which agent.

## Markdown file layout

```
---
id: director_init
version: 2.0
role: director
changelog:
  - v2.0 - 2026-06-15 - tighten premise length
default_variant: standard
variants:
  standard:
    description: standard planning
    patch: |
      extra text appended to the main body
---

Main body. This is the system prompt that goes verbatim into the LLM call.
Markdown formatting (headers, code blocks, lists) is preserved.
```

### Required frontmatter fields

- `id` — unique prompt identifier; matches the agent's call site
- `version` — semver string
- `role` — agent role (director, actor, narrator, ...)
- `changelog` — non-empty list of strings

### Optional frontmatter fields

- `default_variant` — which variant the catalog picks when no override
- `variants.<name>.description` — human description
- `variants.<name>.patch` — text appended after the main body
- `user_template_vars` — list of variable names used in the user message
- `notes` — free-form notes for human readers

## Catalog (`catalog.json`)

A JSON file mapping each agent to its available prompts:

```json
{
  "schema_version": 1,
  "agents": {
    "director": {
      "primary": "director_init",
      "prompts": [
        { "id": "director_init" },
        { "id": "director_intervention" }
      ]
    }
  }
}
```

The catalog is validated on every reload. Every `id` referenced must
resolve to a `.md` file on disk.

## Adding a new prompt (4 steps)

1. Create `prompts/<role>/<your_prompt>.md` with frontmatter + body.
2. (Optional) add an entry under the matching role in `catalog.json`.
3. The loader picks it up on the next call (hot reload via mtime).
4. Run `make test-backend` to confirm.
