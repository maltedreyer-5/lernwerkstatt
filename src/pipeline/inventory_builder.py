"""
Inventory agent: splits source material into structured entries.

Sequence:
1. the LLM segments the material into semantic units
2. full texts are extracted by means of the markers
3. entries are embedded and stored in the index
"""

import logging
from src.core.limits import (
    INVENTORY_CHUNK_SIZE_CHARS,
    INVENTORY_SUMMARY_CHARS,
    INVENTORY_MAX_ENTRIES as _DEFAULT_INVENTORY_MAX,
    MATERIAL_INVENTORY_FALLBACK,
)
from src.llm.client import LLMClient
from src.pipeline.inventory import InventoryEntry, InventoryIndex
from src.prompts.inventorize import INVENTORY_PROMPT

logger = logging.getLogger(__name__)


async def build_inventory(
    material: str,
    document_name: str,
    llm: LLMClient,
    index: InventoryIndex,
    task_type_name: str = "",
    kind_types: list[str] | None = None,
    max_entries: int = _DEFAULT_INVENTORY_MAX,
    max_parallel_chunks: int = 5,
) -> list[InventoryEntry]:
    """Builds the inventory of a document: LLM segmentation → embedding → index.

    Args:
        material: full text of the document.
        document_name: file name for the assignment.
        llm: LLM client for the segmentation.
        index: InventoryIndex to store into.
        task_type_name: name of the task type (for the prompt).
        kind_types: expected kinds of unit (e.g. ["chapter", "section"]).
        max_entries: maximum number of entries.
        max_parallel_chunks: maximum parallelism of the chunk LLM calls
            (default 5). Speeds up large material considerably: 25 chunks
            * ~2 min sequentially -> 50 min; 5 in parallel -> ~10 min.

    Returns:
        List of the InventoryEntry objects created.
    """
    if not material or not material.strip():
        return []

    # For very short material: a single entry
    if len(material) < 500:
        entry = InventoryEntry(
            id="M01",
            document=document_name,
            title="Gesamtdokument",
            kind="Dokument",
            summary=material[:INVENTORY_SUMMARY_CHARS],
            full_text=material,
            position=0,
        )
        await index.add_entries([entry])
        return [entry]

    # Hint on the kinds of unit for the prompt
    if kind_types:
        kind_types_note = ", ".join(kind_types)
    else:
        kind_types_note = (
            ("chapter, section, paragraph, list, table "
             "(recognise automatically)")
        )

    # LLM segmentation.
    # Chunking as a safeguard against reverse-proxy timeouts; the primary model
    # may be configured with a longer timeout than the fast one.
    max_material_per_call = INVENTORY_CHUNK_SIZE_CHARS

    all_entries = []

    # Inventory large documents in parts
    chunks = []
    if len(material) <= max_material_per_call:
        chunks = [material]
    else:
        # Split at paragraph boundaries
        parts = material.split("\n\n")
        current_chunk = ""
        for part in parts:
            if len(current_chunk) + len(part) > max_material_per_call and current_chunk:
                chunks.append(current_chunk)
                current_chunk = part
            else:
                current_chunk += ("\n\n" if current_chunk else "") + part
        if current_chunk:
            chunks.append(current_chunk)

    logger.info(
        f"Inventory building: {len(material)} characters split into {len(chunks)} "
        f"chunk(s)"
    )

    # ── Phase 1: all chunk LLM calls IN PARALLEL ──────────────────────
    # Up to max_parallel_chunks at the same time (default 5). Sequentially, 25
    # chunks * ~2 min would mean 50 min of waiting; in parallel 25/5 = 5 waves
    # *
    # ~2 min = ~10 min.
    import asyncio
    sem = asyncio.Semaphore(max_parallel_chunks)

    async def _process_chunk(chunk_idx: int, chunk: str):
        async with sem:
            try:
                response = await llm.complete(
                    INVENTORY_PROMPT.format(
                        task_type_name=task_type_name or "general",
                        kind_types_note=kind_types_note,
                        material=chunk,
                    ),
                    json_mode=True,
                    thinking=False,
                )
                return (chunk_idx, chunk, response, None)
            except Exception as e:
                return (chunk_idx, chunk, None, e)

    chunk_results = await asyncio.gather(
        *[_process_chunk(i, c) for i, c in enumerate(chunks)],
        return_exceptions=False,
    )
    # Sort by chunk_idx (gather guarantees the order, but better safe than
    # sorry)
    chunk_results.sort(key=lambda r: r[0])

    # ── Phase 2: build entries SEQUENTIALLY (for consistent IDs) ──
    for chunk_idx, chunk, response, error in chunk_results:
        if error is not None:
            logger.error(f"inventory LLM error (chunk {chunk_idx+1}): {error}")
            entry = InventoryEntry(
                id=f"M{len(all_entries)+1:02d}", document=document_name,
                title=f"Section (chunk {chunk_idx+1})",
                kind="Dokument", full_text=chunk, position=len(all_entries),
            )
            all_entries.append(entry)
            continue

        # JSON parsen
        entries_raw = _parse_inventory_response(response)

        if not entries_raw:
            logger.warning(f"No entries extractable from chunk {chunk_idx+1}")
            entry = InventoryEntry(
                id=f"M{len(all_entries)+1:02d}", document=document_name,
                title=f"Section (chunk {chunk_idx+1})",
                kind="Dokument", full_text=chunk, position=len(all_entries),
            )
            all_entries.append(entry)
            continue

        # Create entries with full-text extraction
        for i, raw in enumerate(entries_raw):
            if len(all_entries) >= max_entries:
                break
            entry_id = f"M{len(all_entries)+1:02d}"

            # Extract the full text via the markers (within the chunk)
            full_text = _extract_full_text(
                chunk,
                raw.get("start_marker", ""),
                raw.get("end_marker", ""),
                position=i,
                total=len(entries_raw),
            )

            all_entries.append(InventoryEntry(
                id=entry_id,
                document=document_name,
                title=raw.get("title", f"Section {len(all_entries)+1}"),
                kind=raw.get("kind", "Section"),
                keywords=raw.get("keywords", []),
                summary=raw.get("summary", ""),
                full_text=full_text,
                position=len(all_entries),
            ))

    # Fallback if no entries were created at all
    if not all_entries:
        entry = InventoryEntry(
            id="M01", document=document_name,
            title="Gesamtdokument", kind="Dokument",
            full_text=material[:MATERIAL_INVENTORY_FALLBACK], position=0,
        )
        all_entries.append(entry)

    # Embed and store in the index
    await index.add_entries(all_entries)

    logger.info(
        f"Inventory building finished: {len(all_entries)} entries "
        f"from '{document_name}'"
    )
    return all_entries


def _parse_inventory_response(response: str) -> list[dict]:
    """Parses the LLM answer (JSON with an entries list)."""
    from src.llm.json_parser import parse_llm_json

    data = parse_llm_json(
        response,
        expected_keys=["entries"],
        context="inventory building",
        fallback={"entries": []},
    )
    if isinstance(data, dict):
        return data.get("entries", [])
    return []


def _extract_full_text(
    material: str,
    start_marker: str,
    end_marker: str,
    position: int = 0,
    total: int = 1,
) -> str:
    """Extracts the full text between start and end marker.

    Fallback: cut by position if the markers are not found.
    """
    if start_marker and end_marker:
        start_pos = material.lower().find(start_marker.lower())
        end_pos = material.lower().find(end_marker.lower())

        if start_pos >= 0 and end_pos >= 0 and end_pos > start_pos:
            # Include the end marker up to the end of the line
            line_end = material.find("\n", end_pos + len(end_marker))
            if line_end < 0:
                line_end = len(material)
            return material[start_pos:line_end].strip()

        # Only the start marker found
        if start_pos >= 0:
            chunk_size = len(material) // max(total, 1)
            end = min(len(material), start_pos + chunk_size + 500)
            return material[start_pos:end].strip()

    # Fallback: cut by position
    if total <= 1:
        return material

    chunk_size = len(material) // total
    start = position * chunk_size
    end = min(len(material), (position + 1) * chunk_size + 200)

    # Align with line boundaries
    if start > 0:
        nl = material.rfind("\n", max(0, start - 100), start)
        if nl >= 0:
            start = nl + 1
    if end < len(material):
        nl = material.find("\n", end)
        if nl >= 0 and nl < end + 200:
            end = nl

    return material[start:end].strip()
