import unittest
from types import SimpleNamespace

from services.ui import meal_html, notes_html, text


class MealFormattingTests(unittest.TestCase):
    def test_localized_structure_and_escaped_model_text(self):
        entry = SimpleNamespace(id=12, dish='<Rice> & beans', calories_kcal=320,
                                protein_g=10, fat_g=4, carbs_g=61)
        rendered = meal_html(entry, 'Russian')
        self.assertIn('#12\n\n<b>&lt;Rice&gt; &amp; beans</b>', rendered)
        self.assertIn('<b>320 ккал</b>', rendered)
        self.assertIn('Белки: 10.0 г · Жиры: 4.0 г · Углеводы: 61.0 г', rendered)
        self.assertIn('Protein:', meal_html(entry, 'English'))
        self.assertEqual(notes_html('<b>estimate</b> & detail'), '\n\n<i>&lt;b&gt;estimate&lt;/b&gt; &amp; detail</i>')
        self.assertEqual(notes_html('  '), '')

    def test_saved_reply_has_no_repeated_instruction(self):
        for language in ('Russian', 'English'):
            rendered = text(language, 'saved', entry='entry', notes='')
            self.assertNotIn('Ответь', rendered)
            self.assertNotIn('Reply', rendered)
            self.assertTrue(rendered.endswith('entry'))
