---
name: EventPlannerSkill
description: Enables scheduling community events and setting up registration forms.
---

# Event Planner Skill

This skill allows the Agent to:
1. Parse event details (Title, Date, Description) from natural language.
2. Check the database via the Database MCP Server to prevent scheduling conflicts.
3. Commit new events via `insert_document` tool.
4. Create registration forms with a specific ticket fee via `insert_document` in the `form_schemas` collection.

## Usage Rules
- Standard ticket fee is £25.00 per adult if not specified.
- Children under 12 are always free.
- Keep titles concise and date formats clear.
