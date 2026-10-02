# -*- coding: utf-8 -*-
"""MockLLM: answers every kind of prompt of the learning pipeline
deterministically and in the right format — so the ENTIRE workflow (including
the real DAG executor, quality checks, repair loop, critic revision) runs
without an endpoint. It tests the processing chain, not the quality of real
models (that is what scripts/benchmark.py is for).
"""
from __future__ import annotations

import json
import re


def _json_line(prompt: str, marker: str):
    for line in prompt.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker):].strip())
    raise ValueError(f"marker '{marker}' not found")


class MockLLM:
    def __init__(self, name: str, defect_first_transformation: bool = False,
                 defective_tasks: bool = False):
        # Usage counters as in the real client — the technical report evaluates
        # them.
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_truncated = 0
        self.total_empty = 0
        self.total_empty_rescued = 0
        self.model = f"mock-{name}"
        self.calls: list[str] = []
        self.defect_open = defect_first_transformation  # provokes the repair loop
        self.repairs = 0
        self.critic_defect_open = True                  # provokes 1 critic revision
        self.hallu_defect_open = True                   # provokes 1 fact revision
        self.tasks_defect_open = defective_tasks     # Alias-Feld + fehlendes Feld

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False,
                       max_tokens=None, temperature=None, thinking=None) -> str:
        self.total_calls += 1
        self.total_input_tokens += max(len(prompt) // 4, 1)
        self.calls.append(prompt.split("\n", 1)[0][:70])
        return self._response(prompt)

    # ── Prompt recognition (order matters) ──
    def _response(self, p: str) -> str:
        if p.startswith("Prüfe, ob die folgende Ausgabe"):
            return json.dumps({"score": 5, "feedback": "ok", "fulfilled": [], "open": []})
        if "Repair the following lesson" in p:
            self.repairs += 1
            assert "LANGUAGE RULE" in p, "the repair prompt must carry the language rule"
            lesson = json.loads(p.split("LESSON:\n", 1)[1].rsplit("Answer ONLY", 1)[0].strip())
            for b in lesson["blocks"]:
                if b.get("type") == "quiz":
                    b["questions"][0]["options"][0]["correct"] = True
                if b.get("type") == "text":
                    b["html"] = re.sub(r"[\u4e00-\u9fff]+", "Konfiguration", b["html"])
                if b.get("type") == "prediction" and not b.get("resolution"):
                    b["resolution"] = "<p>Idempotenz: keine Differenz, keine Handlung.</p>"
            return json.dumps(lesson, ensure_ascii=False)
        if "REVISE the following lesson" in p:
            lesson = json.loads(p.split("LESSON: ", 1)[1].strip())
            lesson["learning_objectives"] = (lesson.get("learning_objectives") or []) + ["Revision eingearbeitet"]
            return json.dumps(lesson, ensure_ascii=False)
        if "You check a teaching text AGAINST binding source material" in p:
            if self.hallu_defect_open:
                self.hallu_defect_open = False
                return json.dumps({"findings": [{"claim": "etcd liegt auf jedem Node",
                    "status": "contradicts", "evidence": "1",
                    "comment": "Quelle: etcd gehört zur Control Plane."}]},
                    ensure_ascii=False)
            return json.dumps({"findings": []})
        if "You are a didactic critic" in p:
            if self.critic_defect_open:
                self.critic_defect_open = False
                return json.dumps({"score": 3, "findings": [{
                    "criterion": "C3", "evidence": "Feedback zu knapp",
                    "correction": "Feedback erweitern"}]})
            return json.dumps({"score": 5, "findings": []})
        if "Normalise the input" in p:
            return json.dumps({
                "known_concepts": ["Docker", "Linux"], "unknown_concepts": ["Kubernetes"],
                "target_level": "apply", "context": "Admin im Hochschulumfeld", "language": "de",
                "open_questions": ["Welche Cluster-Version ist im Einsatz?"]})
        if "You carry out a gap analysis" in p:
            return json.dumps({
                "kind": "paradigm_shift", "interference": "high",
                "interference_rationale": "Imperative Reflexe aus der Docker-Welt.",
                "concepts": [
                    {"id": "k1", "name": "Desired State", "concept_class": "V", "rationale": "Kern"},
                    {"id": "k2", "name": "Deklaratives Arbeiten", "concept_class": "V", "rationale": "Kern"},
                    {"id": "k3", "name": "Architektur", "concept_class": "K", "rationale": "Verstehen genügt"},
                    {"id": "k4", "name": "kube-proxy", "concept_class": "D", "rationale": "Delta"},
                    {"id": "k5", "name": "CRI-Details", "concept_class": "R", "rationale": "Referenz"}],
                "chapters": [
                    {"title": "Denkmodell", "concepts": ["k1", "k2"],
                     "learning_objectives": ["Kann deklarativ von imperativ abgrenzen"], "prerequisites": []},
                    {"title": "Cluster", "concepts": ["k3", "k4"],
                     "learning_objectives": ["Kann die Architektur erklären"], "prerequisites": ["Denkmodell"]}],
                "unit_title": "Mock-Einheit Kubernetes", "description": "E2E-Testeinheit."})
        if "Create the detail plan" in p:
            chap = _json_line(p, "CHAPTER: ")
            concepts = _json_line(p, "CONCEPTS WITH CLASSES: ") if False else None
            lessons = [{"id": f"{cid}-lekt", "title": f"Lektion zu {cid}", "concepts": [cid],
                          "learning_objectives": [f"Kann {cid} anwenden"],
                          "content_points": ["Anker", "Mechanismus"],
                          "media_plan": ["text mit h3-Gliederung", "quiz"],
                          "check_criteria": ["Fehlvorstellung adressiert", "Beispiel vorhanden"]}
                         for cid in chap["concepts"] if cid != "k5"]
            return json.dumps({
                "lessons": lessons,
                "application_part": [{"type": "prediction", "concepts": [chap["concepts"][0]],
                                    "short_description": "Festlegen und prüfen"}],
                "case_task": {"concepts": chap["concepts"],
                                "short_description": "Integriert das Kapitel"}},
                ensure_ascii=False)
        if "coherence of a multi-part teaching text" in p:
            return "Terminologie: Desired State = Soll-Zustand. Bereits erklärt: siehe Vorkapitel."
        if "Write the script section" in p:
            concept = json.loads(re.search(r"CONCEPT: (\{.*?\}) \(treatment class", p).group(1))
            return (f"<h3>{concept['name']} verstehen</h3>"
                    f"<p>Sie kennen die Docker-Welt — neu ist {concept['name']}. "
                    "Man könnte meinen, ein Befehl genüge; tatsächlich beschreibt man einen "
                    "Zustand, und eine Regelschleife hält ihn. Das begründet Idempotenz und "
                    "Selbstheilung als logische Folgen desselben Prinzips.</p>"
                    "<p>Quizinhalt: Frage nach dem Soll-Zustand; korrekt ist die Regelungs-"
                    "Antwort; Distraktor ist die Befehls-Antwort mit erklärendem Feedback.</p>")
        if "assemble the coherent chapter script" in p:
            title = re.search(r'chapter script\n"(.*?)":', p).group(1)
            sections = p.split("SECTIONS:", 1)[1].split("Output:", 1)[0].strip()
            return (sections + f"\n=== GLOSSAR ===\n{title}-Begriff :: "
                    f"Zentraler Begriff des Kapitels {title}. :: x")
        if "Create the APPLICATION PART" in p:
            concepts = _json_line(p, "CONCEPTS: ")
            ids = [k["id"] for k in concepts]
            v_ids = [k["id"] for k in concepts if k.get("concept_class") == "V"] or ids[:1]
            defect = self.tasks_defect_open
            self.tasks_defect_open = False
            prediction = {"type": "prediction", "question": "<p>Was passiert bei zweimal apply?</p>",
                 "options": [{"text": "Zwei Pods", "correct": False, "feedback": "run-Logik."},
                              {"text": "Keine Wirkung", "correct": True, "feedback": "Idempotenz."}],
                 "resolution": "<p>Idempotenz: keine Differenz, keine Handlung.</p>",
                 "concepts": v_ids}
            if defect:                       # as observed with a real model:
                prediction.pop("resolution")  # required field missing → LLM repair
            return json.dumps({"exercises": [
                prediction,
                {"type": "error_analysis", "title": "Kaputtes Manifest",
                 **({"code": "apiVersion: apps/v1\nkind: Pod"} if defect   # Alias-Feldname
                    else {"material": "apiVersion: apps/v1\nkind: Pod"}),  # → normalisation
                 "question": "<p>Finden Sie den Fehler.</p>",
                 "sample_solution": "<p>Pod lebt unter v1. <em>Selbstprüfung:</em> begründet?</p>",
                 "concepts": ids[:1]},
                {"type": "task", "title": "Fallaufgabe: Migration",
                 "task": "<p>Begründetes Votum schreiben.</p>",
                 "sample_solution": "<p>Eher nein. <em>Selbstprüfung:</em> Kippbedingungen genannt?</p>",
                 "concepts": ids}]}, ensure_ascii=False)
        if "Summarise, for the coherence" in p:
            title = re.search(r'the chapter "(.*?)"', p).group(1)
            return json.dumps({"summary": f"Kapitel {title}: Kernidee eingeführt.",
                               "new_terms": [{"term": f"Meta-{title}",
                                                  "definition": "Aus der Zusammenfassung geerntet.",
                                                  "lesson": "x"}]}, ensure_ascii=False)
        if "Create the final test" in p:
            question = {"question": "Was gilt?", "multiple": False,
                     "options": [{"text": "A", "correct": True, "feedback": "Darum."},
                                  {"text": "B", "correct": False, "feedback": "Deshalb nicht."}]}
            return json.dumps({"title": "Abschlusstest", "questions": [question, question, question]},
                              ensure_ascii=False)
        if "Transform a script section" in p:
            skeleton = p.split("Produce JSON:", 1)[1].rsplit("Answer ONLY", 1)[0].strip()
            correct, foreign = True, ""
            if self.defect_open:              # deliver broken once → the repair loop applies
                self.defect_open, correct, foreign = False, False, " 配置很重要"
            blocks = [
                {"type": "text", "html": f"<h3>Abschnitt{foreign}</h3><p>Sie kennen Docker — neu ist der "
                 "deklarative Blick: beschreiben statt befehlen, und eine Regelschleife hält "
                 "den Zustand, weil Differenzen automatisch beseitigt werden.</p>"},
                {"type": "quiz", "questions": [{"question": "Kernprinzip?", "multiple": False,
                 "options": [{"text": "Regelung auf Soll-Zustand", "correct": correct,
                               "feedback": "Genau: Differenz → Handlung."},
                              {"text": "Befehlskette", "correct": False,
                               "feedback": "Das ist die imperative Welt."}]}]}]
            skeleton = skeleton.replace('"blocks": [ … ]', '"blocks": ' + json.dumps(blocks, ensure_ascii=False))
            json.loads(skeleton)  # Selbstkontrolle des Mocks
            return skeleton
        if "common thread of a learning unit" in p or "CONCEPT GRAPH" in p:
            ids = re.findall(r'"id":\s*"(k\d+)"', p)
            nodes = [{"id": cid, "introduction": f"l{i+1}",
                       "requires": ([ids[i-1]] if i else []),
                       "resumption": [], "contribution": f"Beitrag {cid}"}
                      for i, cid in enumerate(dict.fromkeys(ids))]
            return json.dumps({"guiding_question": "Wie funktioniert das?",
                               "common_thread": ["Kapitel 1: Grundlagen"],
                               "nodes": nodes}, ensure_ascii=False)
        if "enrich a finished lesson" in p or "new_blocks" in p:
            return json.dumps({"new_blocks": [
                {"after_block": 0, "rationale": "Ablauf zeigen statt beschreiben",
                 "block": {"type": "table", "caption": "Vergleich der beiden Ansaetze",
                           "header": ["Merkmal", "A", "B"],
                           "rows": [["Steuerung", "zentral", "verteilt"]]}}]},
                ensure_ascii=False)
        if "repeated explanations" in p:
            return json.dumps({"findings": []}, ensure_ascii=False)
        if "coinages" in p or "TERMS TO CHECK" in p:
            # Take candidates from the list and judge them deterministically:
            # everything with "-fuehrung"/"-gradient" counts as coined, the
            # rest as established. That way the E2E test covers both branches.
            terms = re.findall(r"^- (.+?) \(occurrence", p, re.M)
            verdicts = []
            for b in terms:
                shaped = any(s in b.lower() for s in ("führung", "gradient", "faktor"))
                verdicts.append({"term": b, "established": not shaped,
                                "evidence": "" if shaped else "Fachliteratur",
                                "definition": "" if shaped else "etablierter Begriff",
                                "substitute": "Regelkreis" if shaped else ""})
            return json.dumps({"verdicts": verdicts}, ensure_ascii=False)
        raise AssertionError("MockLLM: unknown kind of prompt:\n" + p[:200])
