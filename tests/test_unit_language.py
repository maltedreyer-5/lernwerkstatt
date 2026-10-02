# -*- coding: utf-8 -*-
"""The language chosen for a unit decides its language, not the model.

The learner profile prompt asks the model for the language of the user's
input. That is not the language the unit is to be written in: someone may
describe an English course in German. The profile answer must not overwrite
the user's choice. The mock always answers "de", so a pipeline started with
"en" shows whether the choice survives.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.mock_llm import MockLLM  # noqa: E402
from src.pipeline.learning_pipeline import LearningPipeline  # noqa: E402


def test_chosen_language_survives_the_profile():
    with tempfile.TemporaryDirectory() as d:
        p = LearningPipeline(MockLLM("strong"), MockLLM("fast"), work_dir=Path(d))
        asyncio.run(p.collect_profile("Kennt Docker", "Kubernetes verstehen",
                                      language="en"))
        assert p.language == "en", f"unit language is {p.language!r}, chosen was 'en'"
    print("  ok   chosen unit language survives the learner profile")


def test_profile_answer_that_is_not_an_object():
    class Broken(MockLLM):
        async def complete(self, prompt, **kw):
            return "[]"
    with tempfile.TemporaryDirectory() as d:
        p = LearningPipeline(MockLLM("strong"), Broken("fast"), work_dir=Path(d))
        asyncio.run(p.collect_profile("x", "y", language="fr"))
        assert p.language == "fr"
    print("  ok   a profile answer that is not an object keeps the chosen language")


if __name__ == "__main__":
    test_chosen_language_survives_the_profile()
    test_profile_answer_that_is_not_an_object()
    print("UNIT LANGUAGE OK")
