"""
Central limits of the inventory building.

Constants that must stay consistent across module boundaries.
"""

# ── Material budgets (characters, not tokens) ─────────────────────
MATERIAL_INVENTORY_FALLBACK = 15_000  # fallback for inventory building


# ── Inventar ─────────────────────────────────────────────────────
INVENTORY_MAX_ENTRIES = 200            # max inventory entries in total
INVENTORY_SUMMARY_CHARS = 200       # summary for very small material
INVENTORY_CHUNK_SIZE_CHARS = 30_000    # per LLM call during inventory building
