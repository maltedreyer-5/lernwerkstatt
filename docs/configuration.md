# Configuration

All settings are environment variables. The application reads them from the
environment and from a file `.env` in the directory it is started from.
`.env.example` lists every variable the application reads, with its
default; a test (`tests/test_env_documented.py`) keeps the two in step.

Minimal configuration:

```ini
LLM1_BASE_URL=https://llm.example.org/v1
LLM1_API_KEY=…            # leave empty for endpoints without authentication
LLM1_MODEL=your-model-name
LLM1_FAMILY=generic
```

## The two models

LernWerkstatt makes many LLM calls per unit and routes them to two roles:

| Role | Variables | Used for |
|---|---|---|
| strong (required) | `LLM1_*` | gap analysis, detail plans, scripts of central concepts, chapter assembly, exercises, final test, critique and revision |
| fast (optional) | `LLM2_*` | learner profile, cross-context, simpler scripts, transformation into blocks, chapter metadata, quality checks, repair loop |

Without `LLM2_BASE_URL` **and** `LLM2_MODEL`, everything runs on LLM1.
`LLM2_API_KEY` and `LLM2_FAMILY` default to the LLM1 values.

Each role has the same set of variables:

| Variable | Default (LLM1 / LLM2) | Meaning |
|---|---|---|
| `…_BASE_URL` | — | OpenAI-compatible base URL, usually ending in `/v1` |
| `…_API_KEY` | empty | key; empty for endpoints without authentication |
| `…_MODEL` | — | model name as the endpoint expects it |
| `…_FAMILY` | `generic` | how reasoning is switched on and off (see below) |
| `…_THINKING` | `true` / `false` | reasoning by default for this role |
| `…_MAX_TOKENS` | `16000` / `8000` | output budget per call |
| `…_TEMPERATURE` | `0.3` / `0.2` | sampling temperature |
| `…_TIMEOUT` | `300` | seconds per request |
| `…_MAX_CONCURRENT` | `3` / `2` | concurrent requests per job |

### Model families and reasoning

Models that reason before answering ("thinking") are controlled differently
per family:

| `…_FAMILY` | Control | Reasoning by default |
|---|---|---|
| `qwen3` | `chat_template_kwargs.enable_thinking` | on |
| `kimi_k2` | `chat_template_kwargs.thinking` | on |
| `glm` | `chat_template_kwargs.enable_thinking` | on |
| `gemma4` | `chat_template_kwargs.enable_thinking` | off |
| `generic` | none (OpenAI, proxies, other servers) | as the endpoint decides |

An unknown family is rejected at start-up.

Two rules apply on top:

- **JSON mode switches reasoning off.** JSON answers use guided decoding; a
  model that reasons at the same time may be unable to emit its reasoning
  tokens and return nothing. Set `LLM_JSON_THINKING=true` only if your
  endpoint demonstrably handles both together.
- **With `generic`**, reasoning cannot be switched off through
  `chat_template_kwargs`. If the endpoint understands `reasoning_effort`, set
  `LLM_REASONING_EFFORT_OFF` to the value that means "off" (`low` or
  `none`, depending on the server).

If a call returns nothing although its budget was used up, the client
retries once with reasoning off. The technical report of each unit counts
truncated, empty and rescued answers.

## Application

| Variable | Default | Meaning |
|---|---|---|
| `APP_TITLE` | `LernWerkstatt` | name in the browser title and page heading |
| `APP_LANGUAGE` | unset | interface language, `en` or `de`; unset = the browser's language, English as the fallback |
| `APP_ROOT_PATH` | empty | path prefix behind a reverse proxy, e.g. `/lernwerkstatt` |
| `APP_MAX_UPLOAD_MB` | `50` | largest upload per file; a proxy needs at least the same limit |
| `GRADIO_SERVER_NAME` | `127.0.0.1` | interface address; the container image sets `0.0.0.0` |
| `GRADIO_SERVER_PORT` | `7860` | interface port |
| `WORK_DIR` | `work` | job register and job folders; relative to the start directory |

Users can switch the interface language at any time. The language of a
generated unit (German, English, French, Spanish, Italian) is chosen per job
and is independent of the interface language.

## Embedder and reranker

Both are optional. Without them, uploaded material reaches the model as
representative excerpts (beginning, outline, end) and no fact check runs.

| Variable | Default | Meaning |
|---|---|---|
| `EMBEDDER_BASE_URL` | empty | OpenAI-compatible embeddings endpoint |
| `EMBEDDER_API_KEY` | empty | key |
| `EMBEDDER_MODEL` | `default` | model name |
| `RERANKER_BASE_URL` | empty | **full** URL of the rerank endpoint |
| `RERANKER_API_KEY` | empty | key |
| `RERANKER_MODEL` | empty | only if the service requires a model name (Cohere, Jina) |

With an embedder, uploaded material is split into an inventory of
searchable sections. That index feeds three things: evidence for each
concept author, the material coverage report, and the fact check of each
lesson against the material.

The **reranker** turns a ranking into a decision: its relevance score is
comparable across queries, so a fixed threshold can tell "evidenced" from
"not evidenced". Without it the coverage report marks every assignment as
unchecked. Requests follow the Cohere/Jina/TEI form:

```text
request : {"query": …, "documents": [...], "top_n": n}
response: {"results": [{"index": i, "relevance_score": 0.87}, …]}
```

The embeddings client finds the route itself (`/embeddings`, `/embed` or
`/v1/embeddings`). `python scripts/check_services.py` reports what each
configured endpoint answers.

## Budgets and limits

| Variable | Default | Meaning |
|---|---|---|
| `BLOCKS_MAX_TOKENS` | `14000` | output budget of the block phase, the largest outputs of the pipeline |
| `BLOCKS_THINKING` | `false` | reasoning in the block phase; empty = as the task's model |
| `MAX_SCRIPT_CONTEXT` | `60000` | characters up to which a chapter script is passed in full to later steps |

A chapter script longer than `MAX_SCRIPT_CONTEXT` is not cut. It is
replaced by a labelled structural summary (outline, learning objectives,
content points), and the log says so. Adjust `BLOCKS_MAX_TOKENS` from the
technical report rather than by guessing: with models that take reasoning
tokens from the same budget, a higher value can even empty the output.

## Parallel operation

| Variable | Default | Meaning |
|---|---|---|
| `JOBS_PARALLEL` | `3` | jobs computing at the same time; further jobs wait in a queue |
| `LLM_GLOBAL_MAX_CONCURRENT` | unset | optional ceiling on concurrent requests across all jobs |

Every running job keeps its own per-role limits (`…_MAX_CONCURRENT`).
Waiting jobs show their queue position and start automatically. Leave
`LLM_GLOBAL_MAX_CONCURRENT` unset unless several jobs overload the endpoint:
a process-wide ceiling acts as a queue without fairness, in which the first
job takes the slots and later ones only follow as it drains.
