# -*- coding: utf-8 -*-
"""LernWerkstatt wizard: five steps instead of a chat.

1 job → 2 briefing → 3 plan review (checkpoint, editable concept
inventory) → 4 production (chapter by chapter, on the server) → 5 result
(preview, download, check report).
"""
from __future__ import annotations

import html as html_mod
import logging
import traceback
from pathlib import Path

import gradio as gr

from src.config import WORK_DIR_PATH, load_config
from src.i18n import LANGUAGE_NAMES, LANGUAGES, Msg, default_language, render, tr
from src.core.jobs import JobRegister
from src.llm.client import LLMClient
from src.pipeline import gap_analysis as ga
from src.pipeline import teaching_script as lsk
from src.pipeline import job_runner as al
from src.unit import i18n
from src.pipeline.file_reader import read_uploaded_file
from src.pipeline.learning_pipeline import LearningPipeline
from src.ui.preview import for_preview as _for_preview

log = logging.getLogger(__name__)

REGISTER = JobRegister(WORK_DIR_PATH / "jobs.sqlite")

# Typing this into the class column removes a concept. The German word is
# accepted as well, because the column is edited by hand in either language.
REMOVE_MARKERS = {"DELETE", "STREICHEN"}


def best_language(accept_language: str | None) -> str:
    """Interface language for a request: APP_LANGUAGE if set, otherwise the
    first supported language in the browser's Accept-Language header."""
    import os
    if os.getenv("APP_LANGUAGE"):
        return default_language()
    for part in (accept_language or "").split(","):
        tag = part.split(";")[0].strip().lower().split("-")[0]
        if tag in LANGUAGES:
            return tag
    return default_language()


def _client_from(c) -> LLMClient:
    """Builds the client from an LLMConfig block (single arguments, no
    config object)."""
    if not (c.base_url and c.model):
        raise ValueError("LLM configuration incomplete: BASE_URL/MODEL missing — check .env (template: .env.example)")
    return LLMClient(
        base_url=c.base_url, api_key=c.api_key, model=c.model, family=c.family,
        thinking=c.thinking, max_tokens=c.max_tokens, temperature=c.temperature,
        timeout=c.timeout, max_concurrent=c.max_concurrent)


def _llms() -> tuple[LLMClient, LLMClient | None]:
    cfg = load_config()
    llm1 = _client_from(cfg.llm1)
    llm2 = _client_from(cfg.llm2) if getattr(cfg, "llm2", None) else None
    return llm1, llm2


def _inventory_index():
    """InventoryIndex only if an embedder is configured (EMBEDDER_*)."""
    cfg = load_config()
    emb = getattr(cfg, "embedder", None)
    if not (emb and getattr(emb, "base_url", "")):
        return None
    try:
        from src.pipeline.inventory import (EmbedderClient, InventoryIndex,
                                            RerankerClient)
        # Without a reranker wired in, the index would give only a ranking —
        # the relevance decision that material coverage relies on would be
        # missing. So it is passed in whenever RERANKER_BASE_URL is set.
        rer = getattr(cfg, "reranker", None)
        reranker = None
        if rer and getattr(rer, "base_url", ""):
            reranker = RerankerClient(rer.base_url, rer.api_key,
                                      getattr(rer, "model", ""))
        return InventoryIndex(
            EmbedderClient(emb.base_url, emb.api_key, emb.model), reranker)
    except Exception:  # noqa: BLE001 — grounding is an additional safety net
        return None


def _new_pipeline() -> LearningPipeline:
    llm1, llm2 = _llms()
    number = REGISTER.new_()
    p = LearningPipeline(llm1, llm2, work_dir=WORK_DIR_PATH, job_number=number,
                     notify_status=lambda st, n=number: REGISTER.update(n, status=st),
                     inventory_index=_inventory_index())
    return p


def _register_folder(pipeline) -> None:
    """Registers folder and title — as soon as both are known.

    The folder only comes into being AFTER the gap analysis, because its
    name contains the title. Express jobs must be registered here as well,
    otherwise they could not be loaded afterwards although they run and
    their folder is on disk.
    """
    if not (pipeline.job_number and pipeline.folder):
        return
    try:
        REGISTER.update(pipeline.job_number,
                              title=(pipeline.gap.title if pipeline.gap else None),
                              folder=str(pipeline.folder))
    except Exception:  # noqa: BLE001 — must never hold up the job
        log.warning("folder for job %s not registered",
                    pipeline.job_number, exc_info=True)


def _read_uploads(files) -> dict[str, str]:
    texts_: dict[str, str] = {}
    for d in files or []:
        path_ = Path(getattr(d, "name", d))
        try:
            text, _size = read_uploaded_file(str(path_))
            texts_[path_.name] = text
        except Exception as e:  # noqa: BLE001 — show upload errors, do not crash
            texts_[path_.name] = f"[file could not be read: {e}]"
        finally:
            # The original upload lives in Gradio's cache. Once its text has
            # been extracted it is no longer needed, so it is removed right
            # away instead of waiting for the periodic cache cleanup.
            try:
                path_.unlink(missing_ok=True)
            except OSError:
                log.warning("upload %s could not be removed", path_.name)
    return texts_


def _code_notice(number: int, code: str, lang: str) -> dict:
    """Shows the pickup code once. Only its hash is stored on the server."""
    return gr.update(visible=True, value=tr(
        "**Job #{number} — pickup code: `{code}`**\n\n"
        "Please write it down. With this code the job can be continued or "
        "deleted later. It is shown only now and cannot be recovered; the "
        "operator can issue a new one.", lang, number=number, code=code))


def _inventory_table(pipeline: LearningPipeline) -> list[list[str]]:
    return [[k.id, k.name, k.concept_class, k.rationale] for k in pipeline.gap.concepts]


def _plan_markdown(pipeline: LearningPipeline, proposal: str, hints: list, lang: str) -> str:
    g = pipeline.gap
    parts = [f"### {g.title}", g.description, "",
             tr("**Derivation:** {summary}", lang, summary=g.summary(lang)),
             tr("**Interference:** {level} — {rationale}", lang,
                level=tr(ga.INTERFERENCE_LABEL.get(g.interference, g.interference), lang),
                rationale=g.interference_rationale), "",
             tr("**Chapter plan:**", lang)]
    parts += [f"{i}. **{chap.title}** — {', '.join(chap.concepts)}"
              for i, chap in enumerate(g.chapters, 1)]
    if proposal:
        parts += ["", tr("**Prioritisation proposal (time budget):**", lang), str(render(proposal, lang))]
    if hints:
        parts += ["", tr("**Changes applied:**", lang) + " "
                  + "; ".join(h.render(lang) if hasattr(h, "render") else str(h) for h in hints)]
    return "\n".join(parts)


def build_ui() -> gr.Blocks:
    cfg = load_config()
    # delete_cache (on gr.Blocks below): Gradio keeps uploads and every file
    # it serves for download in its cache. Files older than a day are
    # removed hourly; uploaded originals are deleted right after reading.
    lang0 = default_language()
    translatable: list[tuple] = []          # (component, {property: English text})

    def ui_(factory, **kw):
        """Creates a component with its texts in the start language and
        registers the English source texts for switching languages later."""
        props = ["label", "placeholder", "info"]
        if factory in (gr.Markdown, gr.Button):
            props.append("value")
        texts = {k: kw[k] for k in props if isinstance(kw.get(k), str)}
        if isinstance(kw.get("headers"), list):
            texts["headers"] = kw["headers"]
        shown = {k: ([tr(x, lang0) for x in v] if isinstance(v, list) else tr(v, lang0))
                 for k, v in texts.items()}
        comp = factory(**{**kw, **shown})
        if texts:
            translatable.append((comp, texts))
        return comp

    with gr.Blocks(title=cfg.title, delete_cache=(3600, 86400)) as ui:
        with gr.Row():
            gr.Markdown(f"# {cfg.title}")
            ui_lang = gr.Radio(choices=[(LANGUAGE_NAMES[c], c) for c in LANGUAGES],
                               value=lang0, label="Language / Sprache", scale=0)
        ui_(gr.Markdown, value="From prior knowledge and a learning goal to an interactive "
                               "HTML learning unit — its scope derived, not set.")
        lang_state = gr.State(lang0)
        pickup_code_md = gr.Markdown(visible=False)
        state = gr.State({})

        # ── Step 1: job ──
        with gr.Column(visible=True) as s1:
            ui_(gr.Markdown, value="## 1 · Job")
            prior_knowledge = ui_(gr.Textbox, label="Where do you stand? (prior knowledge — one "
                                  "sentence or a full competence profile)", lines=4,
                                  placeholder="e.g. I administer servers and know Docker well …")
            learning_objective = ui_(gr.Textbox, label="What do you want to learn? (goal or "
                                     "knowledge gap)", lines=2,
                                     placeholder="e.g. understand and use Kubernetes")
            time_budget = ui_(gr.Number, label="Time budget in minutes (optional, 0 = none — a "
                              "constraint, never a silent cut)", value=None, precision=0)
            language = ui_(gr.Dropdown, label="Language of the unit",
                           choices=[(name, code) for code, name in i18n.CHOICES],
                           value=lang0 if lang0 in dict(i18n.CHOICES) else "en",
                           info="Sets the language of all content AND of the controls "
                                "of the generated unit.")
            uploads = ui_(gr.File, label="Your own material (optional: pdf, docx, pptx, md, "
                          "txt, csv, html)", file_count="multiple")
            with gr.Row():
                s1_next = ui_(gr.Button, value="Next →", variant="primary")
                s1_express = ui_(gr.Button, value="Build without follow-up questions ⏩")
            ui_(gr.Markdown, value="_The express route skips follow-up questions and the "
                                   "planning checkpoint: gap analysis and teaching script are "
                                   "generated and approved unchecked. The outline plan and the "
                                   "teaching script remain in the job folder and can be read "
                                   "there; single chapters can be corrected through rework._")
            s1_status = gr.Markdown()
            with ui_(gr.Accordion, label="Continue or delete a job", open=False):
                ui_(gr.Markdown, value="Production continues on the server even if this window "
                                       "is closed. To continue or delete a job, enter the pickup "
                                       "code that was shown when the job was created.")
                with gr.Row():
                    load_code = ui_(gr.Textbox, label="Pickup code", placeholder="XXXX-XXXX-XXXX",
                                    scale=2)
                    s1_laden = ui_(gr.Button, value="Load job", variant="primary")
                with gr.Row():
                    delete_ok = ui_(gr.Checkbox, label="Delete the job with all its files for "
                                    "good (material, intermediate results, result)")
                    s1_delete = ui_(gr.Button, value="Delete job", variant="stop")

        # ── Step 2: briefing ──
        with gr.Column(visible=False) as s2:
            ui_(gr.Markdown, value="## 2 · Briefing")
            briefing_questions = gr.Markdown()
            briefing_answer = ui_(gr.Textbox, label="Your answers (free text)", lines=4)
            s2_next = ui_(gr.Button, value="On to the gap analysis →", variant="primary")
            s2_status = gr.Markdown()

        # ── Step 3: plan review (checkpoint) ──
        with gr.Column(visible=False) as s3:
            ui_(gr.Markdown, value="## 3 · Plan review — the checkpoint")
            plan_md = gr.Markdown()
            ui_(gr.Markdown, value="**Concept inventory (editable).** Classes: V = full (derive, "
                                   "activate, practise) · K = compact · D = delta/pitfall · "
                                   "R = glossary only · DELETE = remove the concept")
            inventory = ui_(gr.Dataframe, headers=["ID", "Concept", "Class", "Rationale"],
                            datatype=["str", "str", "str", "str"], interactive=True, wrap=True)
            ui_(gr.Markdown, value="**Teaching script — common thread and concept graph.** It "
                                   "steers all following phases: every section learns from it "
                                   "which concept it may introduce and what it must not "
                                   "anticipate. Corrections here affect the whole production.")
            thread_md = gr.Markdown()
            teaching_script_tab = ui_(gr.Dataframe,
                                      headers=["ID", "Concept", "introduced in", "builds on (IDs, comma)"],
                                      datatype=["str", "str", "str", "str"], interactive=True, wrap=True)
            s3_approve = ui_(gr.Button, value="✓ Approve and start production", variant="primary")
            s3_new = ui_(gr.Button, value="Re-derive the gap analysis with the changes")
            s3_status = gr.Markdown()

        # ── Step 4: production ──
        with gr.Column(visible=False) as s4:
            ui_(gr.Markdown, value="## 4 · Production (chapter by chapter, on the server — the "
                                   "window may be closed)")
            progress = gr.Markdown()
            log_lines = ui_(gr.Textbox, label="Log", lines=16, interactive=False)
            s4_stop = ui_(gr.Button, value="Stop after the current layer", variant="stop")
            s4_continue = ui_(gr.Button, value="Continue production", variant="primary",
                              visible=False)

        # ── Step 5: result ──
        with gr.Column(visible=False) as s5:
            ui_(gr.Markdown, value="## 5 · Result")
            report = gr.Markdown()
            file = ui_(gr.File, label="Learning unit (single-file HTML) — main output")
            with gr.Row():
                s5_handout = ui_(gr.Button, value="Create script handout (MD + Word)")
                handout_files = ui_(gr.File, label="Script handout", file_count="multiple")
            with ui_(gr.Accordion, label="Rework: regenerate a single chapter", open=False):
                rework_chapter = ui_(gr.Number, label="Chapter no. (1 = first)", precision=0)
                rework_note = ui_(gr.Textbox, label="Note for the revision", lines=2)
                s5_rework = ui_(gr.Button, value="Regenerate chapter", variant="primary")
            with ui_(gr.Accordion, label="Technical report", open=False):
                technical_md = gr.Markdown()
                s5_log = ui_(gr.Textbox, label="Rework log", lines=8, interactive=False)
            preview = ui_(gr.HTML, label="Preview")

        # ── Interface language ──
        def h_language(lang):
            lang = lang if lang in LANGUAGES else lang0
            updates = [gr.update(**{k: ([tr(x, lang) for x in v] if isinstance(v, list) else tr(v, lang))
                                    for k, v in texts.items()})
                       for _, texts in translatable]
            return [lang, *updates]

        ui_lang.change(h_language, [ui_lang], [lang_state, *[c for c, _ in translatable]])

        def h_detect_language(request: gr.Request):
            header = request.headers.get("accept-language") if request else None
            return best_language(header)

        ui.load(h_detect_language, None, [ui_lang])

        # ────────────────── Handler ──────────────────

        async def h_job(pk, lo, tb, unit_lang, uploaded, st, lang):
            if not (pk or "").strip() or not (lo or "").strip():
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("Please state prior knowledge and learning goal.", lang),
                        gr.update(), gr.update(), st)
            try:
                pipeline = _new_pipeline()
                pipeline.ui_language = lang
                code = REGISTER.issue_code(pipeline.job_number)
                profile = await pipeline.collect_profile(
                    pk, lo, int(tb) if tb else None, _read_uploads(uploaded), unit_lang)
            except Exception as e:  # noqa: BLE001
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("Error: {error}", lang, error=e)
                        + f"\n```\n{traceback.format_exc(limit=3)}\n```",
                        gr.update(), gr.update(), st)
            st = {"pipeline": pipeline}
            questions = profile.get("open_questions") or []
            questions_md = (tr("The planning still needs some information:", lang) + "\n"
                            + "\n".join(f"- {f}" for f in questions)) if questions else \
                tr("No open questions — you can continue directly.", lang)
            return (gr.update(visible=False), gr.update(visible=True), "", questions_md,
                    _code_notice(pipeline.job_number, code, lang), st)

        async def h_express(pk, lo, tb, unit_lang, uploaded, st, lang):
            """Builds the unit without follow-up questions and without checkpoint.

            For jobs whose cut is known. The planning artefacts are still
            created and lie in the job folder — they are only not presented.
            Production then continues on the server as usual.
            """
            if not (pk or "").strip() or not (lo or "").strip():
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("Please state prior knowledge and learning goal.", lang),
                        gr.update(), gr.update(), gr.update(), st)
            try:
                pipeline = _new_pipeline()
                pipeline.ui_language = lang
                code = REGISTER.issue_code(pipeline.job_number)
                profile = await pipeline.collect_profile(
                    pk, lo, int(tb) if tb else None, _read_uploads(uploaded), unit_lang)
                open_ = profile.get("open_questions") or []
                if open_:
                    # Do not hide it: the questions go into the profile, so
                    # that the job folder shows what went into the planning
                    # unresolved.
                    pipeline.profile["skipped_follow_ups"] = open_
                await pipeline.analyse_gap()
                _register_folder(pipeline)     # from here on the job can be loaded
                await pipeline.create_teaching_script()
                hints = pipeline.approve([])
            except Exception as e:  # noqa: BLE001
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("Express route aborted: {error}", lang, error=e)
                        + f"\n```\n{traceback.format_exc(limit=3)}\n```",
                        gr.update(), gr.update(), gr.update(), st)

            st = {"pipeline": pipeline, "job_no": pipeline.job_number}
            n = len(pipeline.gap.chapters)

            async def work(run):
                run.notify(Msg("Job #{number} — express route, approved without follow-up "
                               "questions and without checkpoint. {hints} {skipped}",
                               {"number": pipeline.job_number, "hints": hints or "",
                                "skipped": Msg("Skipped follow-up questions: {n}.", {"n": len(open_)})
                                if open_ else ""}),
                           phase=Msg("Chapter {done}/{total}", {"done": 0, "total": n}), share=0.0)
                run.notify(Msg("Creating detail plans"), share=0.04)
                planned = await pipeline.plan_all_chapters()
                run.notify(Msg("Detail plans created: {n} chapters", {"n": len(planned)}), share=0.08)
                async for ev in pipeline.produce_all():
                    done_k = pipeline.next_chapter
                    run.notify(ev["text"], phase=Msg("Chapter {done}/{total}", {"done": done_k, "total": n}),
                               share=0.08 + 0.82 * done_k / max(n, 1))
                if not pipeline.stop_signal.is_stopped:
                    steps = 0
                    async for ev in pipeline.consolidate():
                        steps += 1
                        run.notify(ev["text"], phase=Msg("Consolidation"),
                                   share=0.90 + 0.07 * (1 - 0.75 ** steps))
                run.notify(Msg("Completion"), phase=Msg("Completion"), share=1.0)

            al.start(pipeline.job_number, pipeline.folder, pipeline, work)
            return (gr.update(visible=False), gr.update(visible=True),
                    tr("Chapter {done}/{total}", lang, done=0, total=n),
                    tr("Job #{number} is running on the express route. The window can be "
                       "closed.", lang, number=pipeline.job_number),
                    gr.Timer(active=True), _code_notice(pipeline.job_number, code, lang), st)

        s1_next.click(h_job, [prior_knowledge, learning_objective, time_budget, language, uploads, state,
                              lang_state],
                        [s1, s2, s1_status, briefing_questions, pickup_code_md, state])

        async def h_briefing(answers, st, lang):
            pipeline: LearningPipeline = st["pipeline"]
            pipeline.answer_briefing(answers or "")
            try:
                gap, proposal = await pipeline.analyse_gap()
            except Exception as e:  # noqa: BLE001
                return (gr.update(), gr.update(), "⚠️ " + tr("Gap analysis failed: {error}", lang, error=e),
                        gr.update(), gr.update(), gr.update(), gr.update(), st)
            st["proposal"] = proposal
            st["ls_findings"] = await pipeline.create_teaching_script()
            _register_folder(pipeline)
            return (gr.update(visible=False), gr.update(visible=True), "",
                    _plan_markdown(pipeline, proposal, [], lang),
                    _inventory_table(pipeline),
                    _thread_markdown(pipeline, st.get("ls_findings") or [], lang),
                    _teaching_script_table(pipeline), st)

        s2_next.click(h_briefing, [briefing_answer, state, lang_state],
                        [s2, s3, s2_status, plan_md, inventory,
                         thread_md, teaching_script_tab, state])

        def _teaching_script_table(pipeline: LearningPipeline):
            ls = pipeline.teaching_script
            if ls is None or pipeline.gap is None:
                return []
            names = {k.id: k.name for k in pipeline.gap.concepts}
            return [[cid, names.get(cid, cid), ls.nodes[cid].introduction or "",
                     ", ".join(ls.nodes[cid].requires) or "—"]
                    for cid in ls.sequence_order()]

        def _thread_markdown(pipeline: LearningPipeline, findings: list, lang: str) -> str:
            ls = pipeline.teaching_script
            if ls is None:
                return tr("_No teaching script created — production runs without a common thread._", lang)
            z = []
            if ls.guiding_question:
                z.append(tr("**Guiding question:** {q}", lang, q=ls.guiding_question))
            if ls.common_thread:
                z.append("\n".join(f"{i+1}. {x}" for i, x in enumerate(ls.common_thread)))
            if findings:
                z.append(tr("**Findings:**", lang) + " " + str(render(list(findings[:6]), lang)))
            return "\n\n".join(z)

        def _edits_from_table(pipeline: LearningPipeline, df) -> list[dict]:
            rows = df.values.tolist() if hasattr(df, "values") else (df or [])
            ist = {k.id: k.concept_class for k in pipeline.gap.concepts}
            edits = [{"id": str(z[0]).strip(), "concept_class": str(z[2]).strip().upper()}
                     for z in rows if len(z) >= 3]
            for e in edits:
                if e["concept_class"] in REMOVE_MARKERS:
                    e["concept_class"] = "DELETE"
            kept = {e["id"] for e in edits if e["concept_class"] != "DELETE"}
            edits += [{"id": cid, "concept_class": "DELETE"} for cid in ist
                      if cid not in kept and cid not in {e["id"] for e in edits}]
            return [e for e in edits if e["concept_class"] != ist.get(e["id"], "")]

        def h_rederive(df, st, lang):
            pipeline: LearningPipeline = st["pipeline"]
            hints = (ga.apply_edits(pipeline.gap, _edits_from_table(pipeline, df))
                        if pipeline.gap else [])
            return (_plan_markdown(pipeline, st.get("proposal", ""), hints, lang),
                    _inventory_table(pipeline), "", st)

        s3_new.click(h_rederive, [inventory, state, lang_state],
                     [plan_md, inventory, s3_status, state])

        # Start idle. If the ticker ran permanently, Gradio would re-render the
        # result outputs every two seconds as well — including the preview
        # iframe that carries the whole unit as srcdoc. That makes the preview
        # flicker and jump back while one looks at older units.
        ticker = gr.Timer(2.0, active=False)

        async def h_production(df, ls_df, st, lang):
            """Starts production as a server-side task and returns.

            Production keeps running when the window is closed; the
            interface only polls its state.
            """
            if not isinstance(st, dict) or "pipeline" not in st:
                return (gr.update(), gr.update(), tr("Session lost", lang),
                        tr("The session no longer exists (page reloaded or server "
                           "restarted). Please load the job again with its pickup code "
                           "in step 1.", lang),
                        gr.Timer(active=False), st if isinstance(st, dict) else {})
            pipeline: LearningPipeline = st["pipeline"]
            hints = pipeline.approve(_edits_from_table(pipeline, df))
            if pipeline.teaching_script is not None:
                row = ls_df.values.tolist() if hasattr(ls_df, "values") else (ls_df or [])
                hints += lsk.apply_edits(pipeline.teaching_script, row)
            n = len(pipeline.gap.chapters)

            async def work(run):
                run.notify(Msg("Job #{number} — approved. {hints}",
                               {"number": pipeline.job_number, "hints": hints or ""}),
                           phase=Msg("Chapter {done}/{total}", {"done": 0, "total": n}), share=0.0)
                run.notify(Msg("Creating detail plans"), share=0.04)
                planned = await pipeline.plan_all_chapters()
                run.notify(Msg("Detail plans created in parallel: {n} chapters", {"n": len(planned)}),
                           share=0.08)
                async for ev in pipeline.produce_all():
                    done_k = pipeline.next_chapter
                    run.notify(ev["text"], phase=Msg("Chapter {done}/{total}", {"done": done_k, "total": n}),
                               share=0.08 + 0.82 * done_k / max(n, 1))
                if not pipeline.stop_signal.is_stopped:
                    steps = 0
                    async for ev in pipeline.consolidate():
                        steps += 1
                        run.notify(ev["text"], phase=Msg("Consolidation"),
                                   share=0.90 + 0.07 * (1 - 0.75 ** steps))
                run.notify(Msg("Completion"), phase=Msg("Completion"), share=1.0)

            al.start(pipeline.job_number, pipeline.folder, pipeline, work)
            st["job_no"] = pipeline.job_number
            return (gr.update(visible=False), gr.update(visible=True),
                    tr("Chapter {done}/{total}", lang, done=0, total=n),
                    tr("Production started. The window can be closed — generation "
                       "continues.", lang),
                    gr.Timer(active=True), st)

        def h_status(st, lang):
            """Called by the timer; mirrors the run into the interface.

            Only a job that is running in the register or has just finished
            triggers anything here. For a LOADED older job there is no run —
            then the ticker must not touch anything, otherwise it overwrites
            the state that `h_load` has just built.
            """
            run = al.get_((st or {}).get("job_no"))
            if run is None:
                # A loaded older job or nothing at all: switch the ticker off.
                return gr.update(), gr.update(), gr.Timer(active=False), st
            if run.done and not st.get("done"):
                st["done"] = True
            # After the end one more pass, so that the result is produced —
            # then the ticker rests again.
            next_ = not run.done or not st.get("result_created")
            return (f"{render(run.phase, lang)} · {tr(al.STATUS_LABEL.get(run.status(), run.status()), lang)}",
                    run.log_text(lang),
                    gr.Timer(active=next_), st)

        def h_abort(st, lang):
            no = (st or {}).get("job_no")
            return (tr("Abort requested.", lang) if al.abort(no)
                    else tr("No running job.", lang))

        prod_ev = s3_approve.click(h_production, [inventory, teaching_script_tab, state, lang_state],
                                [s3, s4, progress, log_lines, ticker, state])
        # Express route: jumps from step 1 straight into production. Must come
        # after the ticker definition — Gradio handlers are local names and
        # must be bound at registration time.
        s1_express.click(h_express, [prior_knowledge, learning_objective, time_budget, language, uploads,
                                     state, lang_state],
                         [s1, s4, progress, log_lines, ticker, pickup_code_md, state])
        def h_stop(st):
            p = st.get("pipeline")
            if p:
                p.request_stop()
            return st
        s4_stop.click(h_stop, [state], [state])

        def h_result(st, lang=None):
            pipeline: LearningPipeline = st.get("pipeline")
            if not pipeline or not st.get("done") or st.get("result_created"):
                return (gr.update(), gr.update(), gr.update(), gr.update(),
                        gr.update(), st)
            if not (pipeline.unit.get("lessons") or []):
                return (gr.update(visible=True),
                        tr("### No lessons\n\nThis job has no generated unit "
                           "(`content/unit.json` is missing or empty). Production has to "
                           "run again.", lang),
                        gr.update(), gr.update(), gr.update(), st)
            # Set the lock only AFTER success. Set before, a single failure
            # would silence fetching the result for good: the error would
            # vanish in the Gradio stack, and every further attempt would
            # return only empty updates.
            try:
                finding, result = pipeline.finalise()
                technical = pipeline.technical_report(lang)
            except Exception as e:  # noqa: BLE001
                import traceback
                return (gr.update(visible=True),
                        tr("### The result could not be created", lang) + "\n\n"
                        f"`{type(e).__name__}: {e}`\n\n```\n"
                        + traceback.format_exc(limit=8) + "\n```",
                        gr.update(), gr.update(), gr.update(), st)
            st["result_created"] = True
            if result is None:
                md = (tr("### Final gate: NOT passed — no output can be created", lang)
                      + "\n\n```\n" + finding.report(lang) + "\n```")
                return (gr.update(visible=True), md, gr.update(), gr.update(),
                        technical, st)
            html = _for_preview(Path(result.path_).read_text(encoding="utf-8"))
            iframe = (f'<iframe sandbox="allow-scripts" style="width:100%;height:70vh;'
                      f'border:1px solid #ccc;border-radius:8px" '
                      f'srcdoc="{html_mod.escape(html)}"></iframe>')
            if getattr(result, "draft", False):
                md = (tr("### Final gate NOT passed — the DRAFT is below\n"
                         "**{name}** ({kb} KB) is clearly marked as a draft and can be viewed "
                         "and downloaded. Close the errors below (for instance through rework "
                         "per chapter) — the final file then replaces the draft.", lang,
                         name=result.path_.name, kb=result.kilobytes)
                      + "\n\n```\n" + finding.report(lang) + "\n```")
            else:
                md = (tr("### Done: {name} ({kb} KB, {mode})", lang, name=result.path_.name,
                         kb=result.kilobytes,
                         mode=tr("offline", lang) if result.offline else tr("CDN fallback", lang))
                      + "\n\n```\n" + finding.report(lang) + "\n```")
            return (gr.update(visible=True), md, str(result.path_), iframe,
                    technical, st)

        # The ticker keeps the display up to date and triggers the result as
        # soon as the server-side run is finished — whether or not the window
        # was open during production. Must come AFTER h_result: Gradio handlers
        # are local names and must be bound at call time, otherwise build_ui()
        # fails with UnboundLocalError.
        ticker.tick(h_status, [state, lang_state], [progress, log_lines, ticker, state]).then(
            h_result, [state, lang_state],
            [s5, report, file, preview, technical_md, state])

        # There is deliberately no list of jobs in the interface: every
        # visitor would see every other user's jobs. Operators get an overview
        # with `scripts/cleanup.py --list`.

        # ── Loading a job ──
        def h_load(code, st, lang):
            empty = (gr.update(),) * 7
            if not (code or "").strip():
                return (gr.update(), gr.update(), "⚠️ " + tr("Please enter the pickup code.", lang), st) + empty
            rec = REGISTER.find_by_code(code)
            if rec is None:
                # Same message for every failure, so the answer reveals
                # nothing about which jobs exist.
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("There is no job for this pickup code.", lang), st) + empty
            number = int(rec["number"])
            no = number
            folder = rec.get("folder")
            if not folder:
                # Fall back to the folder convention: jobs without a folder
                # entry in the register still have their folder on disk. The
                # folder name carries the title slug: job-0056-topic-xy. Hence
                # search for the PREFIX, not for the exact name.
                hits = sorted(WORK_DIR_PATH.glob(f"job-{number:04d}-*"))
                candidate = next((k for k in hits
                                 if (k / "state.json").exists()), None)
                if candidate:
                    folder = str(candidate)
                    try:
                        REGISTER.update(number, folder=folder)
                    except Exception:  # noqa: BLE001
                        pass
            if not folder or not (Path(folder) / "state.json").exists():
                return (gr.update(), gr.update(),
                        "⚠️ " + tr("Job #{number} has no saved state yet (planning was not "
                                   "finished).", lang, number=number),
                        st) + empty
            rec = dict(rec or {}, folder=folder)
            try:
                llm1, llm2 = _llms()
                # If the job is still running on the server, reuse its pipeline
                # — otherwise two instances would run on the same folder and
                # overwrite each other.
                active = al.get_(int(no))
                if active is not None and active.running:
                    pipeline = active.pipeline
                else:
                    pipeline = LearningPipeline.load(rec["folder"], llm1, llm2)
                pipeline.notify_status = (lambda s_, n_=pipeline.job_number:
                                         REGISTER.update(n_, status=s_))
                st["job_no"] = int(no)
            except Exception as e:  # noqa: BLE001
                return (gr.update(), gr.update(), "⚠️ " + tr("Loading failed: {error}", lang, error=e), st) + empty
            st = {"pipeline": pipeline}
            n = len(pipeline.gap.chapters) if pipeline.gap else 0
            info = tr("Job #{number} loaded: {title} — {done}/{total} chapters done.", lang,
                      number=pipeline.job_number, title=rec["title"],
                      done=pipeline.next_chapter, total=n)
            if pipeline.fully_produced:
                st["done"] = True
                s5v, bmd, dpf, vhtml, tmd, st = h_result(st, lang)
                return (gr.update(visible=False), gr.update(), "", st,
                        gr.update(visible=False), info, s5v, bmd, dpf, vhtml, tmd)
            return (gr.update(visible=False), gr.update(visible=True), "", st,
                    gr.update(visible=True), info + " " + tr("Continue with “Continue production”.", lang),
                    gr.update(), gr.update(), gr.update(), gr.update(), gr.update())

        async def h_continue(st, lang):
            pipeline: LearningPipeline = st["pipeline"]
            n = len(pipeline.gap.chapters)
            n_chap = len(pipeline.gap.chapters)

            async def work(run):
                run.notify(Msg("Continuing job #{number} from chapter {chapter}.",
                               {"number": pipeline.job_number, "chapter": pipeline.next_chapter + 1}),
                           phase=Msg("Chapter {done}/{total}", {"done": pipeline.next_chapter, "total": n_chap}))
                await pipeline.plan_all_chapters()
                async for ev in pipeline.produce_all():
                    done_k = pipeline.next_chapter
                    run.notify(ev["text"], phase=Msg("Chapter {done}/{total}", {"done": done_k, "total": n_chap}),
                               share=0.08 + 0.82 * done_k / max(n_chap, 1))
                if not pipeline.stop_signal.is_stopped:
                    async for ev in pipeline.consolidate():
                        run.notify(ev["text"], phase=Msg("Consolidation"), share=0.95)
                run.notify(Msg("Completion"), phase=Msg("Completion"), share=1.0)

            al.start(pipeline.job_number, pipeline.folder, pipeline, work)
            st["job_no"] = pipeline.job_number
            return (gr.update(visible=False),
                    tr("Chapter {done}/{total}", lang, done=pipeline.next_chapter, total=n_chap),
                    tr("Continuation running. The window can be closed.", lang),
                    gr.Timer(active=True), st)

        load_ev = s1_laden.click(
            h_load, [load_code, state, lang_state],
            [s1, s4, s1_status, state, s4_continue, progress,
             s5, report, file, preview, technical_md])

        def h_delete(code, confirmed, st, lang):
            """Deletes a job with everything it holds. Requires the pickup code."""
            if not (code or "").strip():
                return "⚠️ " + tr("Please enter the pickup code.", lang), False, st
            if not confirmed:
                return ("⚠️ " + tr("Please confirm the deletion explicitly (tick the box).", lang),
                        False, st)
            rec = REGISTER.find_by_code(code)
            if rec is None:
                return "⚠️ " + tr("There is no job for this pickup code.", lang), False, st
            number = int(rec["number"])
            active = al.get_(number)
            if active is not None and active.waiting and not active.running:
                al.abort(number)        # queued: removed at once
            elif active is not None and active.running:
                al.abort(number, immediately=True)
                return ("⚠️ " + tr("Job #{number} was still running and has been asked to stop. "
                                   "Please delete it again in a few seconds.", lang, number=number),
                        False, st)
            if not REGISTER.delete(number, with_folder=True):
                return "⚠️ " + tr("Job #{number} could not be deleted.", lang, number=number), False, st
            if (st or {}).get("job_no") == number or \
                    getattr((st or {}).get("pipeline"), "job_number", None) == number:
                st = {}
            return tr("Job #{number} was deleted with all its files.", lang, number=number), False, st

        s1_delete.click(h_delete, [load_code, delete_ok, state, lang_state],
                          [s1_status, delete_ok, state])
        s4_continue.click(h_continue, [state, lang_state],
                            [s4_continue, progress, log_lines, ticker, state])

        # ── Rework + script handout ──
        async def h_rework(chapter_no, note, st, lang):
            pipeline: LearningPipeline = st.get("pipeline")
            if not pipeline or not chapter_no or not (note or "").strip():
                yield ("⚠️ " + tr("Please give a chapter number and a note.", lang),
                       gr.update(), gr.update(), gr.update(), st)
                return
            ci = int(chapter_no) - 1
            if not (0 <= ci < len(pipeline.gap.chapters)):
                yield ("⚠️ " + tr("Chapter {n} does not exist.", lang, n=int(chapter_no)),
                       gr.update(), gr.update(), gr.update(), st)
                return
            rows = [tr("Rework of chapter {n} — note: {note}", lang, n=ci + 1, note=note)]
            async for ev in pipeline.regenerate_chapter(ci, note.strip()):
                rows.append(str(render(ev["text"], lang)))
                yield "\n".join(rows[-200:]), gr.update(), gr.update(), gr.update(), st
            _s5v, bmd, dpf, vhtml, _tmd, st = h_result(st, lang)
            yield ("\n".join(rows[-200:]) + "\n" + tr("Rework finished.", lang),
                   bmd, dpf, vhtml, st)

        def h_handout(st, lang):
            pipeline: LearningPipeline = st.get("pipeline")
            if not pipeline or not pipeline.scripts:
                return "⚠️ " + tr("No scripts available.", lang), gr.update(), st
            md_path, docx_path, message = pipeline.script_handout()
            files = [str(md_path)] + ([str(docx_path)] if docx_path else [])
            return str(render(message, lang)), files, st

        s5_rework.click(h_rework, [rework_chapter, rework_note, state, lang_state],
                            [s5_log, report, file, preview, state])
        s5_handout.click(h_handout, [state, lang_state], [s5_log, handout_files, state])

    return ui
