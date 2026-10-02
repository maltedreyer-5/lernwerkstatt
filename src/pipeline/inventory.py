"""
Inventory: structures source material into semantically searchable entries.

Uses an embedder and an optional reranker (both OpenAI-compatible HTTP
endpoints, configured through EMBEDDER_* and RERANKER_*) for semantic
retrieval.
"""

import logging
import math
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


# ── Datenstrukturen ──────────────────────────────────────────────


def _headers(api_key: str, json_body: bool = False) -> dict[str, str]:
    """Request headers; no Authorization header without a key.

    Local embedding and rerank services (TEI, for instance) usually run
    without authentication. An empty key would give "Authorization: Bearer "
    with nothing after it, which httpx rejects as an illegal header value
    before the request is even sent.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers

@dataclass
class InventoryEntry:
    """A single inventory entry (a structured section of the material)."""
    id: str                          # "M01", "M02", ...
    document: str                    # file name
    title: str
    kind: str                         # e.g. "chapter", "section"
    keywords: list[str] = field(default_factory=list)
    summary: str = ""
    full_text: str = ""
    embedding: list[float] = field(default_factory=list)
    position: int = 0                # order in the source document

    @property
    def display_label(self) -> str:
        kind_icons = {
            "TOP": "📋", "Beschluss": "✅", "Auftrag": "📌",
            "Kapitel": "📖", "Codeblock": "💻", "Kriterium": "🔍",
            "Preisangabe": "💰", "Frist": "📅", "Zitat": "💬",
        }
        icon = kind_icons.get(self.kind, "📄")
        return f"{icon} {self.id}: {self.title}"


# ── Embedder-Client ──────────────────────────────────────────────

class EmbedderClient:
    """Client for the OpenAI-compatible embeddings endpoint.

    Detects the endpoint path automatically:
    - /embeddings (OpenAI standard)
    - /embed (TEI / Hugging Face Text Embeddings Inference)
    - /v1/embeddings (if base_url contains no /v1)
    """

    def __init__(self, base_url: str, api_key: str, model: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=60.0)
        self._endpoint: str | None = None  # detected on the first call
        self._unavailable = False     # after unsuccessful detection

    async def _model_list(self) -> list[str]:
        """Queries /v1/models — tells what the server offers at all.

        A 404 on /v1/embeddings only means that the route is missing. Only
        the model list shows whether an embedding model runs there at all or
        whether the base URL points to the wrong service.
        """
        basis = self.base_url.rstrip("/")
        if not basis.endswith("/v1"):
            basis += "/v1"
        try:
            resp = await self._client.get(
                f"{basis}/models",
                headers=_headers(self.api_key))
            if resp.status_code != 200:
                return []
            data_ = resp.json().get("data") or []
            return [m.get("id", "?") for m in data_ if isinstance(m, dict)]
        except Exception:  # noqa: BLE001
            return []

    async def _detect_endpoint(self) -> str | None:
        """Detects the right endpoint path.

        None means: no endpoint found. Keeping the first candidate in that
        case would let every following call run into the same 404 and flood
        the log while the cause stays unexplained.
        """
        if self._endpoint:
            return self._endpoint
        if self._unavailable:
            return None

        basis = self.base_url.rstrip("/")
        without_v1 = basis[:-3].rstrip("/") if basis.endswith("/v1") else basis
        candidates_ = []
        for url in (f"{basis}/embeddings", f"{basis}/embed",
                    f"{without_v1}/v1/embeddings", f"{without_v1}/embeddings",
                    f"{without_v1}/embed"):
            if url not in candidates_:
                candidates_.append(url)

        headers = _headers(self.api_key, json_body=True)
        test_payload = {"model": self.model, "input": ["test"]}

        # Distinguish status codes. Counting EVERY status except 404 as success
        # would book a 401 (wrong key) or 400 (unknown model name) as "endpoint
        # detected", and every real call afterwards would fail without naming
        # the cause.
        findings: list[str] = []
        for url in candidates_:
            try:
                resp = await self._client.post(url, json=test_payload, headers=headers)
            except Exception as e:  # noqa: BLE001
                findings.append(f"{url}: {type(e).__name__}")
                continue
            code = resp.status_code
            if code == 200:
                self._endpoint = url
                logger.info(f"Embedder endpoint detected: {url}")
                return url
            if code == 404:
                findings.append(f"{url}: 404 (route missing)")
                continue
            # The route exists, but the call was rejected — that is the most
            # useful information of all and must not get lost.
            body = ""
            try:
                body = str(resp.json())[:200]
            except Exception:  # noqa: BLE001
                body = (getattr(resp, "text", "") or "")[:200]
            if code in (401, 403):
                logger.error("embedder %s answers %s — check EMBEDDER_API_KEY. %s",
                             url, code, body)
            else:
                logger.error(("embedder %s answers %s — the route exists, the call was "
                              "rejected. Most common cause: EMBEDDER_MODEL does not "
                              "match the models offered"), url, code, body)
            findings.append(f"{url}: {code}")
            self._unavailable = True
            return None

        # Final: report once, with the model list as a hint, and stay silent
        # afterwards. The pipeline continues without an inventory.
        self._unavailable = True
        models = await self._model_list()
        note = (f"The server offers these models: {', '.join(models[:12])}"
                   if models else
                   "/v1/models does not answer either — does EMBEDDER_BASE_URL point to the right service?")
        logger.error(
            ("embedder not reachable. Findings per path: %s. %s "
             "Production continues without an inventory — uploaded material then "
             "reaches planning only as excerpts."),
            "; ".join(findings), note)
        return None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embeds a list of texts. Returns vectors."""
        if not self.base_url:
            logger.warning("embedder not configured — empty vectors")
            return [[] for _ in texts]

        endpoint = await self._detect_endpoint()
        if endpoint is None:
            return [[] for _ in texts]
        try:
            response = await self._client.post(
                endpoint,
                json={"model": self.model, "input": texts},
                headers={
                    **_headers(self.api_key),
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            # OpenAI-Format: data.data[i].embedding
            if "data" in data and isinstance(data["data"], list):
                embeddings = [item["embedding"] for item in data["data"]]
            # TEI-Format: direkt Liste von Vektoren
            elif isinstance(data, list) and data and isinstance(data[0], list):
                embeddings = data
            else:
                logger.warning(f"Unknown embedder answer format: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                return [[] for _ in texts]

            logger.debug(f"Embedded {len(texts)} texts, dim={len(embeddings[0])}")
            return embeddings
        except Exception as e:
            logger.error(f"embedder error: {e}")
            return [[] for _ in texts]

    async def embed_single(self, text: str) -> list[float]:
        """Embeds a single text."""
        results = await self.embed([text])
        return results[0]


# ── Reranker-Client ──────────────────────────────────────────────

class RerankerClient:
    """Client for the reranker endpoint."""

    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        # `base_url` is the COMPLETE endpoint URL — no path is appended.
        # `model` only if the service requires it (Cohere, Jina); TEI and vLLM
        # ignore it.
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=30.0)

    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5,
    ) -> list[int]:
        """Reranks documents by relevance. Returns sorted indices.

        For relevance decisions use `rerank_scored`, because the score is
        lost here.
        """
        hits = await self.rerank_scored(query, documents, top_k)
        if hits is None:
            return list(range(min(top_k, len(documents))))
        return [i for i, _ in hits]

    async def rerank_scored(
        self, query: str, documents: list[str], top_k: int = 5,
    ) -> list[tuple[int, float]] | None:
        """Reranks and returns (index, relevance score).

        The relevance score is the reason a reranker is suitable for a
        coverage statement and cosine similarity is not: it is comparable
        across different queries, because the model rates query and document
        together instead of comparing two independently created vectors.
        That makes a fixed threshold meaningful.

        None means EXPLICITLY "no statement possible" (not configured,
        failure, unexpected format). Falling back to the first N documents
        would be wrong here: it would make every concept look evidenced,
        even if the reranker never answered.
        """
        if not self.base_url or not documents:
            return None
        try:
            response = await self._client.post(
                self.base_url,
                json={"query": query, "documents": documents, "top_n": top_k,
                      # Cohere- and Jina-style services require a model name;
                      # TEI and vLLM ignore
                      # it.
                      **({"model": self.model} if getattr(self, "model", "") else {})},
                headers=_headers(self.api_key, json_body=True),
            )
            response.raise_for_status()
            results_ = response.json().get("results")
            if not isinstance(results_, list):
                logger.warning("Reranker: unexpected answer format")
                return None
            out: list[tuple[int, float]] = []
            for r in results_[:top_k]:
                idx = r.get("index")
                if not isinstance(idx, int) or not (0 <= idx < len(documents)):
                    continue
                value = r.get("relevance_score")
                if value is None:
                    value = r.get("score")
                out.append((idx, float(value) if value is not None else float("nan")))
            return out or None
        except Exception as e:  # noqa: BLE001
            logger.error(f"reranker error: {e}")
            return None


# ── Cosine-Similarity ────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Computes the cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Inventar-Index ───────────────────────────────────────────────

class InventoryIndex:
    """Manages inventory entries with semantic search.

    Usage:
        index = InventoryIndex(embedder, reranker)
        await index.add_entries(entries)   # with embedding
        results = await index.retrieve("annual report", top_k=3)
    """

    def __init__(
        self,
        embedder: EmbedderClient,
        reranker: RerankerClient | None = None,
    ):
        self.embedder = embedder
        self.reranker = reranker
        self._entries: list[InventoryEntry] = []

    @property
    def entries(self) -> list[InventoryEntry]:
        return list(self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def is_empty(self) -> bool:
        return len(self._entries) == 0

    async def add_entries(self, entries: list[InventoryEntry]) -> None:
        """Adds entries and embeds them (batch)."""
        if not entries:
            return

        # Texts for embedding: title + summary
        texts = [
            f"{e.title}. {e.summary}" for e in entries
        ]

        embeddings = await self.embedder.embed(texts)
        for entry, emb in zip(entries, embeddings):
            entry.embedding = emb
            self._entries.append(entry)

        logger.info(f"Inventory: {len(entries)} entries added (total: {self.count})")

    async def retrieve(
        self, query: str, top_k: int = 5,
    ) -> list[InventoryEntry]:
        """Semantic retrieval: finds the most relevant entries.

        Sequence:
        1. embed the query
        2. cosine similarity against all entries
        3. prefilter top N
        4. optional: reranker for a more precise order
        """
        if not self._entries:
            return []

        # 1. Query embedden
        query_emb = await self.embedder.embed_single(query)

        if not query_emb:
            # Fallback without an embedder: return by position
            logger.warning("No embedding possible — positional fallback")
            return self._entries[:top_k]

        # 2. Cosine-Similarity
        scored = []
        for entry in self._entries:
            if entry.embedding:
                sim = _cosine_similarity(query_emb, entry.embedding)
                scored.append((sim, entry))

        if not scored:
            return self._entries[:top_k]

        # 3. Prefilter top N (2x top_k as reranker input)
        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [entry for _, entry in scored[:top_k * 2]]

        # 4. Reranker (if available)
        if self.reranker and len(candidates) > top_k:
            docs = [f"{e.title}. {e.summary}" for e in candidates]
            reranked_indices = await self.reranker.rerank(
                query, docs, top_k=top_k,
            )
            result = [candidates[i] for i in reranked_indices if i < len(candidates)]
            return result

        return candidates[:top_k]

    async def retrieve_scored(
        self, query: str, top_k: int = 5, candidates_: int = 40,
    ) -> list[tuple["InventoryEntry", float, str]]:
        """Retrieval with a score. Returns (entry, score, source).

        `source` is "reranker" or "cosine" — the two values are NOT
        comparable and must not be checked against the same threshold. With
        a reranker there is a broad prefilter (candidates) and a precise
        decision; without it only the cosine ranking remains, which is too
        weak for a yes/no statement.
        """
        if not self._entries:
            return []
        query_emb = await self.embedder.embed_single(query)
        if not query_emb:
            return []
        scored = [(_cosine_similarity(query_emb, e.embedding), e)
                  for e in self._entries if e.embedding]
        if not scored:
            return []
        scored.sort(key=lambda p: -p[0])
        preselection = scored[:max(candidates_, top_k)]

        if self.reranker is not None:
            texts_ = [f"{e.title}\n{e.summary}\n{e.full_text[:1500]}"
                     for _, e in preselection]
            hits = await self.reranker.rerank_scored(query, texts_, top_k=top_k)
            if hits is not None:
                return [(preselection[i][1], value, "reranker")
                        for i, value in hits if 0 <= i < len(preselection)]
        return [(e, value, "cosine") for value, e in preselection[:top_k]]

    async def retrieve_for_section(
        self, section_title: str, section_instruction: str,
        top_k: int = 5,
    ) -> list[InventoryEntry]:
        """Retrieval for a pipeline section."""
        query = f"{section_title}. {section_instruction[:200]}"
        return await self.retrieve(query, top_k=top_k)

    def get_by_id(self, entry_id: str) -> InventoryEntry | None:
        """Finds an entry by ID (e.g. "M04")."""
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def reset(self):
        """Deletes all entries."""
        self._entries.clear()
