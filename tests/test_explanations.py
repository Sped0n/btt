import json
from pathlib import Path
from unittest import TestCase

QUIZ = Path(__file__).resolve().parents[1] / "quiz"


class PublishedQuizTests(TestCase):
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
