"""Prompt for building the inventory of source material."""

INVENTORY_PROMPT = """Analyse the following document and split it
into semantic units (sections that each cover one topic).

TASK TYPE: {task_type_name}

EXPECTED KINDS OF UNIT for this task type:
{kind_types_note}

DOCUMENT:
--- BEGIN ---
{material}
--- END ---

Create an entry for EVERY unit recognised. Answer as JSON:
{{
  "entries": [
    {{
      "title": "short, concise title of the unit",
      "kind": "one of the expected kinds (e.g. chapter, section, definition)",
      "keywords": ["3-5 keywords"],
      "summary": "1-2 sentences of summary",
      "start_marker": "the first 5-10 words of the section in the original",
      "end_marker": "the last 5-10 words of the section in the original"
    }}
  ]
}}

RULES:
- Split along natural structural boundaries (headings,
  numbered sections, changes of topic)
- Each unit should cover 200-3000 words (fewer for shorter
  texts if necessary)
- For very long sections: subdivide sensibly
- Invent no content — only describe what is in the document
- start_marker and end_marker must occur EXACTLY in the original
  (they are used to extract the full text)
- Order: as in the document"""
