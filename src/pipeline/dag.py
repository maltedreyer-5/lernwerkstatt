"""
DAG executor: runs a plan of LLM tasks in dependency order.

The pipeline builds such a plan per chapter. Its tasks are organised in
phases; each task sees either a single part (in parallel, fast) or the
results of a whole phase (once, thoroughly):

    ┌─────────────────────────────────────────────────┐
    │   extract: one task per part (parallel)         │
    └──────┬────────────┬────────────┬────────┬───────┘
           ▼            ▼            ▼        ▼
    ┌─────────────────────────────────────────────────┐
    │   cross: 1 task, sees ALL extract results       │
    │   → terminology, cross-references, context      │
    └─────────────────────┬───────────────────────────┘
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
    ┌─────────────────────────────────────────────────┐
    │   process: one task per part + cross context    │
    │   (parallel)                                    │
    └──────┬───────────────┬───────────────┬──────────┘
           ▼               ▼               ▼
    ┌─────────────────────────────────────────────────┐
    │   finalize: 1 task, assembles and harmonises    │
    └─────────────────────────────────────────────────┘

Why phases instead of part after part: a part processed in sequence knows
only the parts before it. It cannot refer to what comes later, cross-cutting
requirements (consistent terminology) cannot be met, and later parts get
more context than earlier ones, so the quality varies systematically. With
phases every process task has the full context through the cross phase,
independent tasks run in parallel, and the quality-critical tasks (cross,
finalize) run on the primary model.

Tasks refer to the outputs of others with {dep:TASK_ID} and {deps:PHASE}
in their prompt; the executor fills these in at run time.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


# ── Datenmodelle ──────────────────────────────────────────────────


class DAGPlanError(Exception):
    """The plan violates the phase conventions.

    Raised by DAGPlan.validate_phase_conventions() if the plan does not
    match the documented conventions.
    """


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DAGTask:
    """A single task in the DAG.

    Fields:
        id:              unique ID (e.g. "extract:1", "cross", "process:3")
        phase:           phase in the phase model ("extract"|"cross"|"process"|"finalize")
        title:           human-readable title
        prompt:          complete LLM prompt (extended at run time)
        depends_on:      task IDs that must be finished before
        use_primary:     True = llm_primary, False = llm_fast
        max_tokens:      budget for this task (None = model default).
                         Blocks tasks need more than the default, because they
                         have to take over the script text completely.
        thinking:        None = coupled to use_primary, otherwise forced.
                         For very large outputs False pays off: otherwise the
                         budget goes into thinking and the answer stays empty.
        max_retries:     number of retries on error
        check_criteria:  quality criteria for the fulfilment check after execution

    Run-time fields (filled during execution):
        state:            current status
        output:           LLM output after success
        error:            error message after an error
        quality_score:    degree of fulfilment 1-5 (after the check)
        quality_feedback: feedback from the quality check
        started:          start time
        finished:         end time
    """
    id: str
    phase: str
    title: str
    prompt: str
    depends_on: list[str] = field(default_factory=list)
    use_primary: bool = False
    max_tokens: int | None = None
    thinking: bool | None = None
    max_retries: int = 1
    check_criteria: list[str] = field(default_factory=list)

    # Run time
    state: TaskState = TaskState.PENDING
    output: str = ""
    error: str = ""
    quality_score: int = 0
    quality_feedback: str = ""
    started: str = ""
    finished: str = ""


@dataclass
class DAGPlan:
    """A complete DAG plan.

    The plan contains all tasks with their dependencies.
    topological_order() returns the execution order as a list of layers
    (each layer contains tasks that can run in parallel).
    """
    title: str
    summary: str
    tasks: list[DAGTask]
    tone_guidance: str = ""
    quality_criteria: list[str] = field(default_factory=list)

    def topological_order(self) -> list[list[DAGTask]]:
        """Kahn's algorithm: topological sorting in layers.

        Returns:
            List of layers. Every layer contains tasks that can run in
            parallel (all dependencies met).

        Raises:
            ValueError: on cycles or missing dependencies.
        """
        task_by_id = {t.id: t for t in self.tasks}

        # Validation
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in task_by_id:
                    raise ValueError(
                        f"task '{task.id}' depends on non-existent task '{dep}'"
                    )

        # Count incoming edges
        in_degree = {t.id: len(t.depends_on) for t in self.tasks}
        remaining = set(in_degree.keys())
        layers: list[list[DAGTask]] = []

        while remaining:
            # Current layer: all tasks without open dependencies
            current = [
                task_by_id[tid] for tid in remaining
                if in_degree[tid] == 0
            ]
            if not current:
                raise ValueError(
                    f"Cycle in the DAG plan; remaining tasks: "
                    f"{remaining}"
                )

            layers.append(current)
            for task in current:
                remaining.discard(task.id)
                # Reduce edges to successors
                for other_id in remaining:
                    if task.id in task_by_id[other_id].depends_on:
                        in_degree[other_id] -= 1

        return layers

    def validate_phase_conventions(self, autofix: bool = True) -> list[str]:
        """Checks the plan against the phase conventions of the DAG model.

        Conventions:
        1. Exactly one finalize task.
        2. If cross tasks exist: they depend on ALL extract tasks.
        3. The finalize task depends on ALL process tasks.
        4. cross and finalize tasks have use_primary=True (autofix).
        5. Tasks other than finalize have check criteria (warning).

        Args:
            autofix: if True, convention violations that can be fixed with a
                     default value (e.g. use_primary=True for cross/finalize)
                     are corrected automatically. This is logged as a
                     warning.

        Returns:
            List of warnings (empty list = all fine).

        Raises:
            DAGPlanError: on hard violations (missing finalize, incomplete
                          cross/finalize dependencies).
        """
        warnings: list[str] = []
        by_phase: dict[str, list[DAGTask]] = {}
        for t in self.tasks:
            by_phase.setdefault(t.phase, []).append(t)

        # Convention 1: exactly one finalize task
        finalize_tasks = by_phase.get("finalize", [])
        if not finalize_tasks:
            raise DAGPlanError(
                "DAGPlan without finalize task is invalid"
            )
        if len(finalize_tasks) > 1:
            raise DAGPlanError(
                f"several finalize tasks found ({[t.id for t in finalize_tasks]}); exactly one is allowed"
            )
        finalize = finalize_tasks[0]

        # Convention 2: the cross phase depends on all extract tasks
        extract_ids = {t.id for t in by_phase.get("extract", [])}
        cross_tasks = by_phase.get("cross", [])
        if cross_tasks and extract_ids:
            for c in cross_tasks:
                missing = extract_ids - set(c.depends_on)
                if missing:
                    raise DAGPlanError(
                        f"cross task '{c.id}' does not depend on all extract tasks. Missing: {sorted(missing)}"
                    )

        # Convention 3: finalize depends on all process tasks
        process_ids = {t.id for t in by_phase.get("process", [])}
        if process_ids:
            missing = process_ids - set(finalize.depends_on)
            if missing:
                raise DAGPlanError(
                    f"finalize task does not depend on all process tasks. Missing: {sorted(missing)}"
                )

        # Convention 4: use_primary for cross/finalize
        for c in cross_tasks:
            if not c.use_primary:
                msg = (
                    f"Cross-Task '{c.id}' hat use_primary=False — "
                    f"Konvention verlangt True"
                )
                if autofix:
                    c.use_primary = True
                    logger.info(f"{msg} (autofix applied)")
                else:
                    warnings.append(msg)
        if not finalize.use_primary:
            msg = (
                f"Finalize-Task '{finalize.id}' hat use_primary=False — "
                f"Konvention verlangt True"
            )
            if autofix:
                finalize.use_primary = True
                logger.info(f"{msg} (autofix applied)")
            else:
                warnings.append(msg)

        # Convention 5: check criteria for non-finalize tasks (soft)
        for t in self.tasks:
            if t.phase != "finalize" and not t.check_criteria:
                warnings.append(
                    f"task '{t.id}' (phase {t.phase}) has no check criteria — quality check skipped"
                )

        # Convention 6: no placeholders in task prompts. LLMs imitate examples;
        # a plan with "[insert here]" produces empty tasks. It is rejected
        # outright here.
        import re as _re
        _placeholder_patterns = [
            (r"\[\s*(?:hier\s+)?(?:rohmaterial|material|text|abschnitt)?\s*"
            r"(?:einfuegen|einfügen|einsetzen|hier)\s*\]"
            # the same in English, now that the prompts are English
            r"|\[\s*(?:insert|paste|put)\s+(?:(?:raw\s+)?(?:material|text|section)\s+)?here\s*\]"),
            r"\[\s*(?:hier\s+einf(?:ue|ü)gen|insert\s+here)\s*\]",
            r"\[\s*\.\.\.\s*\]",  # bare ellipsis markers
        ]
        for t in self.tasks:
            if t.phase == "finalize":
                continue  # finalize uses {deps:process}, that is not a placeholder
            for pat in _placeholder_patterns:
                m = _re.search(pat, t.prompt or "", _re.IGNORECASE)
                if m:
                    raise DAGPlanError(
                        (f"task '{t.id}' (phase {t.phase}) contains placeholder "
                        f"'{m.group()}' in the prompt — the LLM imitated the example "
                        f"instead of embedding the material. The plan build "
                        f"must be repeated.")
                    )

        return warnings

    @property
    def phase_summary(self) -> str:
        """Summary of the phases for logging."""
        phases = {}
        for t in self.tasks:
            phases.setdefault(t.phase, []).append(t.id)
        return " → ".join(
            f"{phase}({len(ids)})"
            for phase, ids in phases.items()
        )


# ── DAG-Executor ──────────────────────────────────────────────────


class DAGExecutor:
    """Runs a DAGPlan layer by layer.

    Layers are determined by topological sorting. Within a layer all tasks
    run in parallel (limited by max_parallel).

    Features:
    - parallel execution with a semaphore
    - retry logic per task
    - skip on failed dependencies
    - stop support (clean abort after the current layer)
    - dependency output injection: tasks can access the outputs of their
      dependencies through {dep:TASK_ID} in the prompt
    - progress events as an AsyncIterator
    """

    def __init__(
        self,
        llm_primary,
        llm_fast=None,
        max_parallel: int = 5,
        enable_quality_checks: bool = True,
        stop_signal=None,
    ):
        from src.core.stop_signal import StopSignal
        self.llm_primary = llm_primary
        self.llm_fast = llm_fast or llm_primary
        self.max_parallel = max_parallel
        self.enable_quality_checks = enable_quality_checks
        # Shared StopSignal (can be passed in for shared pipelines). An own one
        # if None.
        self.stop_signal = stop_signal if stop_signal is not None else StopSignal()
        self._results: dict[str, DAGTask] = {}

    @property
    def _stop_requested(self) -> bool:
        return self.stop_signal.is_stopped

    @_stop_requested.setter
    def _stop_requested(self, value: bool):
        if value:
            self.stop_signal.request()
        else:
            self.stop_signal.reset()

    def request_stop(self):
        """Stops execution after the current layer."""
        self.stop_signal.request()

    async def execute(
        self,
        plan: DAGPlan,
    ) -> AsyncIterator[dict]:
        """Runs the DAGPlan.

        Yields progress events:
            {"event": "layer_start", "layer": 1, "total": 4, "tasks": [...]}
            {"event": "task_done", "task_id": "extract:1", "output": "..."}
            {"event": "task_failed", "task_id": "...", "error": "..."}
            {"event": "layer_done", "layer": 1, "done": 3, "failed": 0}
            {"event": "all_done", "total": 12, "done": 11, "failed": 1}
        """
        t0 = time.monotonic()
        layers = plan.topological_order()

        logger.info(
            f"DAGExecutor: {len(plan.tasks)} tasks in "
            f"{len(layers)} layers ({plan.phase_summary})"
        )

        self._results = {t.id: t for t in plan.tasks}
        semaphore = asyncio.Semaphore(self.max_parallel)

        for layer_idx, layer in enumerate(layers):
            if self._stop_requested:
                # Mark the remaining tasks as SKIPPED
                for remaining_layer in layers[layer_idx:]:
                    for task in remaining_layer:
                        if task.state == TaskState.PENDING:
                            task.state = TaskState.SKIPPED
                            task.error = "Aborted"
                yield {"event": "stopped", "layer": layer_idx + 1}
                break

            yield {
                "event": "layer_start",
                "layer": layer_idx + 1,
                "total_layers": len(layers),
                "tasks": [
                    {"id": t.id, "title": t.title, "phase": t.phase}
                    for t in layer
                ],
            }

            # Skip tasks with failed dependencies
            executable = []
            for task in layer:
                if self._deps_failed(task):
                    task.state = TaskState.SKIPPED
                    task.error = "Dependency fehlgeschlagen"
                    yield {
                        "event": "task_skipped",
                        "task_id": task.id,
                        "reason": task.error,
                    }
                else:
                    executable.append(task)

            # Parallel execution
            async def run_one(task: DAGTask):
                async with semaphore:
                    await self._execute_task(task, plan)

            if executable:
                await asyncio.gather(
                    *(run_one(t) for t in executable),
                    return_exceptions=True,
                )

            # Layer statistics
            done = sum(1 for t in layer if t.state == TaskState.DONE)
            failed = sum(1 for t in layer if t.state == TaskState.FAILED)
            skipped = sum(1 for t in layer if t.state == TaskState.SKIPPED)

            for task in layer:
                if task.state == TaskState.DONE:
                    event_data = {
                        "event": "task_done",
                        "task_id": task.id,
                        "title": task.title,
                        "phase": task.phase,
                        "output_preview": task.output[:200],
                    }
                    if task.quality_score > 0:
                        event_data["quality_score"] = task.quality_score
                        event_data["quality_feedback"] = task.quality_feedback
                    yield event_data
                elif task.state == TaskState.FAILED:
                    yield {
                        "event": "task_failed",
                        "task_id": task.id,
                        "title": task.title,
                        "error": task.error,
                    }

            yield {
                "event": "layer_done",
                "layer": layer_idx + 1,
                "done": done,
                "failed": failed,
                "skipped": skipped,
            }

            logger.info(
                f"Schicht {layer_idx + 1}/{len(layers)}: "
                f"{done} done, {failed} failed, {skipped} skipped"
            )

        # Gesamt-Statistik
        elapsed = time.monotonic() - t0
        total = len(plan.tasks)
        total_done = sum(1 for t in plan.tasks if t.state == TaskState.DONE)
        total_failed = sum(1 for t in plan.tasks if t.state == TaskState.FAILED)

        yield {
            "event": "all_done",
            "total": total,
            "done": total_done,
            "failed": total_failed,
            "elapsed_seconds": round(elapsed),
        }

    async def _execute_task(self, task: DAGTask, plan: DAGPlan):
        """Runs a single task with quality check and retry.

        Sequence:
        1. run the task (LLM call)
        2. if check criteria are present → quality check (fast, llm_fast)
        3. if score < 3 → retry WITH the feedback from the check
        4. at most 1 quality retry (in addition to the normal retries)
        """
        task.state = TaskState.RUNNING
        task.started = datetime.now().isoformat()

        # Extend the prompt: replace {dep:TASK_ID} by outputs
        base_prompt = self._inject_dependencies(task.prompt, plan)
        prompt = base_prompt

        llm = self.llm_primary if task.use_primary else self.llm_fast
        last_error = ""

        for attempt in range(task.max_retries + 1):
            try:
                output = await llm.complete(
                    prompt,
                    thinking=task.use_primary if task.thinking is None else task.thinking,
                    max_tokens=task.max_tokens,
                )
                task.output = output.strip()

                # Quality check (if criteria are present and the check is
                # enabled)
                if (self.enable_quality_checks
                        and task.check_criteria
                        and task.phase != "finalize"):
                    qc = await self._check_task_quality(task)
                    task.quality_score = qc.get("score", 5)
                    task.quality_feedback = qc.get("feedback", "")

                    if task.quality_score < 3 and attempt < task.max_retries:
                        # Retry with feedback
                        logger.info(
                            f"Task {task.id}: Score {task.quality_score}/5 "
                            f"→ retry with feedback"
                        )
                        prompt = (
                            (f"{base_prompt}\n\n"
                            f"--- QUALITY FEEDBACK (please take into account) ---\n"
                            f"Your previous attempt was rated {task.quality_score}/5. "
                            f"Feedback:\n"
                            f"{task.quality_feedback}\n\n"
                            f"Please revise your answer and take this "
                            f"feedback into account.")
                        )
                        continue  # → next attempt
                    elif task.quality_score < 3:
                        logger.warning(
                            f"Task {task.id}: score {task.quality_score}/5 (no further retries)"
                        )

                task.state = TaskState.DONE
                task.finished = datetime.now().isoformat()
                return

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"Task {task.id} attempt {attempt + 1}: {last_error}"
                )
                if attempt < task.max_retries:
                    await asyncio.sleep(1.5 * (attempt + 1))

        # Alle Retries verbraucht
        task.state = TaskState.FAILED
        task.error = last_error
        task.finished = datetime.now().isoformat()
        logger.error(f"Task {task.id} failed for good: {last_error}")

    async def _check_task_quality(self, task: DAGTask) -> dict:
        """Fast fulfilment check after a task has run.

        Checks the output against the task's check criteria. Uses llm_fast
        (fast and cheap).

        Returns:
            {"score": 1-5, "feedback": "...", "fulfilled": [...], "open": [...]}
        """
        criteria_text = "\n".join(
            f"  {i+1}. {k}" for i, k in enumerate(task.check_criteria)
        )

        # A generous window: with 4000 characters the checker would see only
        # the first quarter of a 15,000-character lesson and judge completeness
        # on a fragment. If it is cut nevertheless, it is told explicitly, so
        # that it does not judge the cut.
        CHECK_WINDOW = 16000
        output_ = task.output[:CHECK_WINDOW]
        shortened_note = (
            ("NOTE: for this check the output was cut off after "
            f"{CHECK_WINDOW} characters. Do NOT judge the "
            "completeness or the end of the output — only what you see.\n\n")
            if len(task.output) > CHECK_WINDOW else "")

        # The brief belongs in the check. Without it the checker sees only the
        # task title and has to count every criterion that needs context as
        # open — which produces scores of 1-2 systematically, regardless of the
        # quality of the output.
        job = (task.prompt or "")[:1800]
        check_prompt = (
            (f"Check whether the following output has fulfilled its task.\n\n"
            f"TASK: {task.title}\n\n"
            f"BRIEF (excerpt — the output is measured against it):\n{job}\n\n"
            f"CHECK CRITERIA:\n{criteria_text}\n\n"
            f"OUTPUT (to be checked):\n"
            f"{output_}\n\n")
            + (shortened_note)
            +
            (f"IMPORTANT — otherwise you judge the wrong thing:\n"
            f"  * Judge ONLY what you see here. Criteria that cannot be decided from "
            f"the brief and the output alone (because they "
            f"require source knowledge, a glossary or other chapters) "
            f"count as MET and must not lower the score.\n"
            f"  * An output that fulfils its brief gets at least "
            f"3 — even if it could be improved. Below 3 only if it is "
            f"wrong in content, unusable or misses the brief.\n\n"
            f"Rate on a scale of 1-5:\n"
            f"  1 = task missed / output unusable\n"
            f"  2 = essential criteria demonstrably not met\n"
            f"  3 = brief fulfilled, room for improvement\n"
            f"  4 = well fulfilled, minor flaws\n"
            f"  5 = completely and correctly fulfilled\n\n"
            f"Answer as JSON:\n"
            f'{{"score": 4, "feedback": "short rationale", '
            f'"fulfilled": ["criterion 1"], "open": ["criterion 3"]}}')
        )

        try:
            response = await self.llm_fast.complete(
                check_prompt,
                thinking=False,
            )
            from src.llm.json_parser import parse_llm_json
            return parse_llm_json(
                response,
                expected_keys=["score"],
                context=f"QualityCheck:{task.id}",
                fallback={"score": 3, "feedback": "(parse error)"},
            )
        except Exception as e:
            logger.warning(f"quality check for {task.id} failed: {e}")
            # Fallback: score 3 (basically fulfilled) — not 5, so that the task
            # does not count as perfect by mistake
            return {"score": 3, "feedback": f"(Check fehlgeschlagen: {e})"}


    def _inject_dependencies(self, prompt: str, plan: DAGPlan) -> str:
        """Replaces {dep:TASK_ID} placeholders by the outputs of the dependencies.

        Safety: after the injection, {dep:...} and {deps:...} patterns in the
        injected outputs are escaped, so that they are not resolved by the
        second regex pass (prevents unintended mixing of information through
        LLM outputs that happen to contain the dependency syntax).
        """
        import re

        def _escape_dep_syntax(text: str) -> str:
            """Escapes {dep:...} and {deps:...} in injected outputs.

            Uses safe placeholders that no regex matches (⟨dep: and ⟨deps:
            with a Unicode bracket).
            """
            text = text.replace("{dep:", "\u27E8dep:")
            text = text.replace("{deps:", "\u27E8deps:")
            return text

        # {dep:TASK_ID} → output of a single task
        def replace_dep(match):
            task_id = match.group(1)
            dep_task = self._results.get(task_id)
            if dep_task and dep_task.state == TaskState.DONE:
                return _escape_dep_syntax(dep_task.output)
            return f"(task '{task_id}' not available)"

        prompt = re.sub(r'\{dep:([^}]+)\}', replace_dep, prompt)

        # {deps:PHASE} → all outputs of a phase (with a length limit)
        def replace_deps_phase(match):
            phase = match.group(1)
            outputs = []
            for t in plan.tasks:
                if t.phase == phase and t.state == TaskState.DONE:
                    # Limit per task output: 3000 characters
                    output = t.output[:3000]
                    if len(t.output) > 3000:
                        output += "\n[... shortened]"
                    outputs.append(
                        f"### {t.title}\n\n"
                        f"{_escape_dep_syntax(output)}"
                    )
            return "\n\n---\n\n".join(outputs) if outputs else f"(no results for phase '{phase}')"

        prompt = re.sub(r'\{deps:([^}]+)\}', replace_deps_phase, prompt)

        return prompt

    def _deps_failed(self, task: DAGTask) -> bool:
        """Checks whether a dependency has failed."""
        for dep_id in task.depends_on:
            dep_task = self._results.get(dep_id)
            if dep_task and dep_task.state in (
                TaskState.FAILED, TaskState.SKIPPED
            ):
                return True
        return False

    def get_all_outputs(self, phase: Optional[str] = None) -> str:
        """Returns all outputs (optionally filtered by phase)."""
        parts = []
        for t in sorted(self._results.values(), key=lambda x: x.id):
            if t.state != TaskState.DONE:
                continue
            if phase and t.phase != phase:
                continue
            parts.append(f"## {t.title}\n\n{t.output}")
        return "\n\n---\n\n".join(parts)


# ── Plan formatting ─────────────────────────────────────────────


def format_dag_plan_markdown(plan: DAGPlan) -> str:
    """Formats a DAGPlan as readable Markdown."""
    layers = plan.topological_order()

    lines = [
        f"### 📋 Arbeitsplan: {plan.title}\n",
        f"{plan.summary}\n",
        f"**{len(plan.tasks)} Aufgaben in {len(layers)} Phasen:**\n",
    ]

    phase_icons = {
        "extract": "📖",
        "cross": "🔗",
        "process": "⚙️",
        "finalize": "✨",
    }

    for layer_idx, layer in enumerate(layers):
        phase = layer[0].phase if layer else "?"
        icon = phase_icons.get(phase, "▸")
        parallel = "parallel" if len(layer) > 1 else ""

        lines.append(
            f"\n**Schicht {layer_idx + 1}: "
            f"{icon} {phase.upper()}** "
            f"({len(layer)} {'Tasks' if len(layer) > 1 else 'Task'}"
            f"{', ' + parallel if parallel else ''})"
        )
        for t in layer:
            model = "🧠" if t.use_primary else "⚡"
            qc = f" ({len(t.check_criteria)} check criteria)" if t.check_criteria else ""
            lines.append(f"  - {model} {t.title}{qc}")

    if plan.quality_criteria:
        lines.append("\n**Quality criteria:**")
        for k in plan.quality_criteria:
            lines.append(f"  - {k}")

    return "\n".join(lines)
