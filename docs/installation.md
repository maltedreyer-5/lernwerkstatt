# Installation

LernWerkstatt is a web application. It needs:

- an **OpenAI-compatible LLM endpoint** (vLLM, TGI, a hosted API). One
  model is enough; a second, faster one is optional (see
  [configuration](configuration.md#the-two-models)).
- **Docker** (recommended), or **Python 3.12** and **Node.js 20** for a
  local installation.

Optionally, an embedding endpoint and a reranker make uploaded material
searchable and enable the fact check (see
[configuration](configuration.md#embedder-and-reranker)).

The interface has **no user accounts**. Anyone who can reach it can create
jobs and use your LLM quota. Run it on your own machine, or behind a reverse
proxy that controls access (see [below](#behind-a-reverse-proxy) and
[operations](operations.md#security-model)).

## With Docker Compose (recommended)

```bash
git clone https://github.com/maltedreyer-5/lernwerkstatt.git
cd lernwerkstatt
cp .env.example .env
# edit .env: at least LLM1_BASE_URL, LLM1_API_KEY (if needed), LLM1_MODEL
docker compose -f deploy/docker-compose.example.yml up -d --build
```

The interface is then at <http://127.0.0.1:7860/lernwerkstatt/>.
The example serves it under the path `/lernwerkstatt` because that is what a
reverse proxy usually needs. To serve it at the root, remove the
`APP_ROOT_PATH` line from `deploy/docker-compose.example.yml`.

What the example does:

- builds the image from the `Dockerfile` in the repository root;
- publishes port 7860 on the **loopback interface only**
  (`127.0.0.1:7860`), so nothing is reachable from the network until you put
  a reverse proxy in front;
- reads the configuration from `.env`;
- keeps the job register and all job folders in the named volume
  `lernwerkstatt-data`, mounted at `/app/work`. Jobs survive rebuilds;
  resuming a job with its pickup code depends on that.

To use a host directory instead of the named volume, make it writable for
the container user (UID 10001) first:

```bash
mkdir -p ./work && sudo chown 10001 ./work
```

and replace the volume line with `- ./work:/app/work`.

### What the image contains

- Python 3.12 on Debian 13 (trixie), which provides Node.js 20. Node.js 20
  has the permission model the simulator probe uses as a second sandbox
  layer; Debian 12 would bring Node.js 18, which has none.
- The Python packages from `requirements.txt`.
- The Node packages from `package-lock.json`, installed with `npm ci`, which
  checks every package against its recorded integrity hash.
- The renderer libraries (Chart.js, Mermaid, Vega, Vega-Lite, Vega-Embed),
  copied into `assets/vendor/`. They are embedded into every generated unit
  so that a unit works offline and learners' browsers never contact a
  third-party CDN.

The build **fails** if a renderer library is missing, or if the Mermaid and
KaTeX probes do not work. If CDN loading in the units is acceptable for you,
build with `--build-arg ALLOW_CDN_FALLBACK=1`; the units then load the
libraries from jsDelivr.

The container runs as an unprivileged user (UID 10001) and has a health
check against the interface.

### Without Compose

```bash
docker build -t lernwerkstatt .
docker run -d --name lernwerkstatt \
  -p 127.0.0.1:7860:7860 \
  --env-file .env \
  -v lernwerkstatt-data:/app/work \
  lernwerkstatt
```

This serves the interface at the root: <http://127.0.0.1:7860/>.

## Checking the installation

At start-up the application prints a diagnosis to the log:

```bash
docker compose -f deploy/docker-compose.example.yml logs lernwerkstatt | grep '\[startup\]'
```

```text
[startup] LernWerkstatt 1.0.0
[startup] node: v20.x
[startup] mermaid: operational
[startup] katex: operational
[startup] embedder: not configured — material reaches the model as excerpts only
[startup] reranker: not configured — retrieval ranks without a relevance cut
```

`embedder` and `reranker` say `operational` once they are configured and
reachable. Anything else names the cause.

If the LLM endpoint does not answer as expected, run the service check in
the container. It distinguishes a missing route, a rejected key and an
unknown model name:

```bash
docker compose -f deploy/docker-compose.example.yml exec lernwerkstatt \
  python scripts/check_services.py
```

## Behind a reverse proxy

`deploy/nginx-location.example.conf` contains the nginx locations for the
path `/lernwerkstatt`. Include them in an existing `server { … }` block and
set `APP_ROOT_PATH=/lernwerkstatt` (the Compose example already does).

Things to keep consistent:

- **Access control.** Add it in the proxy: your single sign-on,
  `auth_basic`, or `allow`/`deny` for your network.
- **Upload size.** `client_max_body_size` must be at least
  `APP_MAX_UPLOAD_MB` (default 50 MB).
- **Timeouts.** Production streams progress events; the example allows 600
  seconds between events. That limits idle time, not the length of a job.
- **Address.** If nginx runs in the same Docker network, replace
  `127.0.0.1:7860` with the container's name and port.

## Local installation without Docker

For development, or where Docker is not available. Tested on Linux with
Python 3.12 and Node.js 20 and 22.

```bash
git clone https://github.com/maltedreyer-5/lernwerkstatt.git
cd lernwerkstatt

python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

npm ci --omit=dev          # Node tools: probes and renderer libraries
node scripts/copy_vendor.mjs

cp .env.example .env       # fill in the LLM endpoint
python app.py
```

The interface is then at <http://127.0.0.1:7860/>. By default it listens on
the loopback interface only (`GRADIO_SERVER_NAME=127.0.0.1`).

Without Node.js the application still runs, with restrictions it reports at
start-up: simulators are not test-run, Mermaid diagrams are not
syntax-checked, and formulas are displayed in simple notation only (no
MathML). Without `node scripts/copy_vendor.mjs` the generated units load
their libraries from a CDN.

The job register and job folders go into `./work` (`WORK_DIR`), relative to
the directory you start the application from.

## Updating

```bash
git pull
docker compose -f deploy/docker-compose.example.yml up -d --build
```

The work volume is kept. Jobs created with an earlier version stay
loadable; see the [changelog](../CHANGELOG.md) for changes that affect
existing data.

## Removing

```bash
docker compose -f deploy/docker-compose.example.yml down
docker volume rm lernwerkstatt_lernwerkstatt-data   # deletes all jobs
```

The volume name carries the Compose project name as a prefix; `docker volume
ls` shows it.
