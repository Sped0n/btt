from unittest import TestCase

from PIL import Image

from btt.video import SCAN_HEIGHT, SCAN_WIDTH, stable_intervals


class ScanTests(TestCase):
    def test_prompt_change_splits_questions_with_similar_headers_and_choices(self):
        first = Image.new("L", (SCAN_WIDTH, SCAN_HEIGHT), 255)
        second = first.copy()
        second.paste(20, (40, 45, 160, 47))

        self.assertEqual(
            stable_intervals([first] * 10 + [second] * 10), [(0.0, 2.0), (2.0, 4.0)]
        )

    def test_motion_in_prompt_media_does_not_split_question(self):
        first = Image.new("L", (SCAN_WIDTH, SCAN_HEIGHT), 255)
        second = first.copy()
        second.paste(20, (225, 35, 280, 67))

        self.assertEqual(stable_intervals([first] * 10 + [second] * 10), [(0.0, 4.0)])
