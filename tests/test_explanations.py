import json
import re
from pathlib import Path
from unittest import TestCase

QUIZ = Path(__file__).resolve().parents[1] / "quiz"


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


class PublishedQuizTests(TestCase):
    def test_text_only_questions_do_not_repeat(self):
        deck = json.loads((QUIZ / "deck.json").read_text(encoding="utf-8"))
        seen = {}
        for card in deck["cards"]:
            if card["issues"] or card["image"] or card["clip"]:
                continue
            if any(choice.get("image") for choice in card["choices"]):
                continue
            choices = [normalized(choice["text"]) for choice in card["choices"]]
            key = (
                normalized(card["prompt"]),
                tuple(sorted(choices)),
                choices[card["answer"]],
            )
            self.assertNotIn(key, seen, f"{card['id']} duplicates {seen.get(key)}")
            seen[key] = card["id"]

    def test_flagged_questions_have_no_gradeable_answer(self):
        deck = json.loads((QUIZ / "deck.json").read_text(encoding="utf-8"))
        for card in deck["cards"]:
            with self.subTest(card=card["id"]):
                if card["issues"]:
                    self.assertIsNone(card["answer"])
                else:
                    self.assertIn(card["answer"], range(len(card["choices"])))

    def test_every_media_reference_resolves_inside_the_published_site(self):
        deck = json.loads((QUIZ / "deck.json").read_text(encoding="utf-8"))
        for card in deck["cards"]:
            references = [card["image"], card["clip"], card["evidence"]]
            references.extend(choice.get("image") for choice in card["choices"])
            for reference in filter(None, references):
                with self.subTest(card=card["id"], reference=reference):
                    media = (QUIZ / reference).resolve()
                    self.assertTrue(media.is_relative_to(QUIZ / "media"))
                    self.assertTrue(media.is_file())

    def test_every_published_card_has_a_bilingual_explanation(self):
        deck = json.loads((QUIZ / "deck.json").read_text(encoding="utf-8"))
        explanations = json.loads(
            (QUIZ / "explanations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(explanations["source"], deck["source"])
        self.assertEqual(
            set(explanations["cards"]), {card["id"] for card in deck["cards"]}
        )
        self.assertEqual(
            set(explanations["cards"].values()), set(explanations["rules"])
        )

        for rule_id, entry in explanations["rules"].items():
            with self.subTest(rule=rule_id):
                self.assertTrue(entry["en"].strip())
                self.assertRegex(entry["zh-Hans"], r"[\u4e00-\u9fff]")
                self.assertRegex(entry["pages"], r"^\d+(?:–\d+)?(?:, \d+(?:–\d+)?)*$")
                self.assertIn(entry.get("status"), {None, "context", "conflict"})
