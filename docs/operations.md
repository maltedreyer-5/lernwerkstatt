# Operations

## Security model

LernWerkstatt is built for a **trusted group of users behind access
control**, for instance staff of a university on its own network or behind
single sign-on. It is not built for the open internet.

What that means in practice:

- **No user accounts.** Anyone who reaches the interface can create jobs,
  upload material and use your LLM quota. Restrict access in front of it
  (see [installation](installation.md#behind-a-reverse-proxy)).
- **Jobs are separated by pickup codes, not by users.** Every job gets a
  random 12-character code when it is created; it is shown once. Loading or
  deleting a job needs that code. Only a SHA-256 hash of the code is
  stored, so it cannot be read back from the register. There is no list of
  jobs in the interface.
- **Model output is treated as untrusted.** Simulator code written by the
  model runs, at generation time, in an isolated Node.js context without
  host objects, with code generation from strings disabled and, from
  Node.js 20 on, under the Node permission model (no file writes, no child
  processes, no workers). In the delivered unit it runs in a sandboxed
  iframe without access to the page. Widgets (raw HTML blocks) run in a
  sandboxed iframe as well. Generated HTML is reduced to an allowlist of
  tags and attributes before it is assembled.
- **Delivered units make no network requests.** All libraries are embedded,
  unless the image was built with `ALLOW_CDN_FALLBACK=1`.

Report vulnerabilities as described in [SECURITY.md](../SECURITY.md).

## What is stored, and where

Everything lives in the work directory (`WORK_DIR`, `/app/work` in the
container):

```text
work/
├── jobs.sqlite                      job register
└── job-0001-<title-slug>/           one folder per job
    ├── state.json                   pipeline state, for resuming
    ├── run-status.json              status of the server-side run
    ├── 00-learner-profile.md
    ├── 00-material-full-text.txt    text extracted from the uploads
    ├── 01-outline-plan.md           the checkpoint: derivation and chapters
    ├── 01b-teaching-script.md       common thread and concept graph
    ├── 01c-material-coverage.md     with an embedder only
    ├── 02-detail-plan-c<n>.json     per chapter
    ├── 03-script-c<n>.html          per chapter
    ├── 04-fact-check.md             with an embedder only
    ├── terminology.json             fixed terms and candidates
    ├── terminology-blocklist.json   replaced coinages
    ├── 99-technical-report.json/md  usage and content figures
    ├── 99-discarded-blocks.json     only if blocks were downgraded
    ├── content/unit.json            the unit, the editable source
    └── dist/                        the generated unit (HTML), handout (MD, DOCX)
```

The register holds only number, title, status, folder and the hash of the
pickup code. **The job folders hold the full text of uploaded material**
and everything derived from it. Plan the work directory accordingly: back
it up if jobs must survive a loss of the server, and do not put it on
storage that others can read.

Uploaded files themselves are deleted right after their text has been
extracted. Gradio keeps its own cache of uploads and of files offered for
download; entries older than a day are removed hourly.

Files in the job folders are written in the interface language that was
active when the job was created. The unit itself is written in the language
chosen for it.

The delivered unit stores a learner's progress (visited lessons, quiz
results, written answers) only in that learner's browser (`localStorage`, key `lw:<unit id>`).

## Deleting jobs

In the interface: step 1, "Continue or delete a job", pickup code, tick the
confirmation, "Delete job". This removes the register row and the folder. A
job that is still running is asked to stop first; delete it again after a
few seconds.

On the server, `scripts/cleanup.py` maintains the work directory:

```bash
python scripts/cleanup.py              # remove register rows whose folder is gone
python scripts/cleanup.py --list       # show all jobs
python scripts/cleanup.py --delete 12 13
python scripts/cleanup.py --all        # delete everything, counter back to 1
python scripts/cleanup.py --code 12    # issue a new pickup code for job 12
```

In the container, prefix the commands with
`docker compose -f deploy/docker-compose.example.yml exec lernwerkstatt`.
`--code` is the way to help a user who has lost a code: the old code stops
working, and the new one is printed once.

Deleting a job folder by hand works too; the next `cleanup.py` run removes
the orphaned register row.

## Running jobs

Production runs on the server, not in the browser: a user can close the
window and load the job later with its pickup code. Up to `JOBS_PARALLEL`
jobs compute at the same time; further jobs wait in a queue, show their
position and start automatically.

Running jobs end when the application restarts. Their progress is not lost:
it is saved after each phase of each chapter and after each lesson of the
block phase, and loading the job with its code continues from there.

## Logs

The application logs to standard output. At start-up it prints a
diagnosis of Node.js, the Mermaid and KaTeX probes, the embedder and the
reranker (see [installation](installation.md#checking-the-installation)).
During production it logs each step, repairs and their outcome, discarded
blocks and the reasons, and the usage figures. Prompts are not logged. Model
answers are not logged either, with one exception: if an answer cannot be
parsed as JSON, its first 200 characters are, so that the cause can be found.
That excerpt can contain content derived from uploaded material.

## Known limits

- **Resumption** continues inside a chapter: an interrupted script phase
  runs again; in the block phase, lessons already created are kept and only
  the missing ones are produced.
- **Pipelined chapters** log in bundles: the block phase of chapter *k*
  reports after the script phase of chapter *k+1*. The log lines carry the
  chapter number.
- **Terminology control** finds new term candidates only in German text
  (see [architecture](architecture.md#terminology-control)).
- **The Word handout** has two export routes; if both fail, the handout is
  delivered as Markdown only. The fallback route knows headings, paragraphs
  and emphasis, nothing more.
- **Without an embedder** there is no fact check and no coverage report;
  the material reaches the model as excerpts, and the interface says so.

## Model quality

The pipeline checks and repairs what can be checked deterministically:
format, structure, references between lessons, concept coverage, simulator
behaviour, diagram syntax, language mixing. It does not prove that the
content is correct. The fact check compares lessons with the uploaded
material only if an embedder is configured; without material there is
nothing to compare against.

Every unit says so in its provenance note. Have units reviewed before they
are used for teaching.

`scripts/benchmark.py` runs five reference cases against your configured
models and reports, per case, errors and warnings after at most one repair.
Run it when you change models.
