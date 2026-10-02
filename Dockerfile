# Debian 13 (trixie) is pinned on purpose: it ships Node.js 20, which offers
# the permission model the simulator probe uses as a second sandbox layer.
# Debian 12 (bookworm) ships Node.js 18, which has none.
FROM python:3.12-slim-trixie

# Node.js : simulator probe, Mermaid syntax probe and LaTeX-to-MathML at
#           generation time (nothing of it runs in the learner's browser)
# curl    : container health check
# Not pinned to Debian package versions: point releases replace them, and a
# pinned version would break the build at the next security update.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    GRADIO_SERVER_NAME=0.0.0.0 \
    WORK_DIR=/app/work

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Exact versions from package-lock.json; npm verifies each package against
# the integrity hash recorded there. A failure here fails the build.
#
# jsdom stays on major version 24: from 25 on it calls
# `webidl.util.markAsUncloneable`, which Node.js provides only from 22 on.
# With a newer jsdom the DOM for the Mermaid probe cannot be set up, and
# Mermaid fails with "DOMPurify.addHook is not a function".
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY . .

# The renderer libraries are embedded into every generated unit. Units are
# standalone files that leave the server (download, offline use, passing
# on); only with embedded libraries do learners' browsers never contact a
# third-party CDN. A missing file therefore fails the build. Set
# ALLOW_CDN_FALLBACK=1 only if CDN loading in the units is acceptable.
ARG ALLOW_CDN_FALLBACK=0
RUN if node scripts/copy_vendor.mjs; then :; \
    elif [ "$ALLOW_CDN_FALLBACK" = "1" ]; then \
        echo "WARNING: renderer libraries missing — units will load them from a CDN"; \
    else exit 1; fi

# Prove that the probes actually run. printf instead of echo: the shell here
# is dash, whose echo turns the "\n" inside the JSON into a real line break,
# which makes the input invalid and the probe fail although it works.
# The check looks at the RESULT, not only at the exit code: a probe given
# input under a key it does not read returns an empty result and exit code 0.
# hadolint ignore=DL4006
RUN printf '%s' '{"diagrams":["flowchart LR\n A-->B"]}' | node assets/mermaid_probe.mjs \
        | grep -q '"ok":true' \
    && printf '%s' '{"formulas":["x^2"]}' | node assets/mathml_probe.mjs | grep -q '<math' \
    && echo "probes: mermaid and katex operational"

# Run unprivileged. Only the work directory is writable; mount a volume
# there. A host directory mounted there must be writable for UID 10001.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/work && chown app /app/work
USER 10001

EXPOSE 7860
# Shell form on purpose: APP_ROOT_PATH is expanded when the check runs.
# hadolint ignore=DL3025
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:7860${APP_ROOT_PATH:-}/" > /dev/null || exit 1
CMD ["python", "app.py"]
