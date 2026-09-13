import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.analyzer import NoFoodIdentified, NutritionAnalyzer, parse_estimate


def response(data):
    message = SimpleNamespace(content=json.dumps(data))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


DATA = {"dish": "Toast", "calories_kcal": 210, "protein_g": 7, "carbs_g": 31,
        "fat_g": 6, "confidence": "medium", "notes": "Estimated portion"}


class AnalyzerTests(unittest.IsolatedAsyncioTestCase):
    def test_fiber_values_and_unknown(self):
        self.assertIsNone(parse_estimate(json.dumps(DATA)).fiber_g)
        for value in (None, 0, 4.2):
            self.assertEqual(parse_estimate(json.dumps({**DATA, 'fiber_g': value})).fiber_g, value)
        for value in (-1, 'NaN', 'Infinity', True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_estimate(json.dumps({**DATA, 'fiber_g': value}))

    def test_no_food_result_needs_no_nutrient_fields(self):
        with self.assertRaises(NoFoodIdentified):
            parse_estimate('{"identified": false}')

    def test_legacy_zero_estimate_is_not_food(self):
        with self.assertRaises(NoFoodIdentified):
            parse_estimate(json.dumps({**DATA, 'calories_kcal': 0}))

    def test_identified_zero_calorie_drink_is_valid(self):
        result = parse_estimate(json.dumps({**DATA, 'identified': True, 'dish': 'Water', 'calories_kcal': 0}))
        self.assertEqual(result.dish, 'Water')

    def setUp(self):
        self.service = NutritionAnalyzer("test-key", "gpt-test", "audio-test", "Italian")
        self.service.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=response(DATA)))),
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(text="toast")))),
        )

    async def test_text_boundary(self):
        result = await self.service.analyze("toast")
        self.assertEqual(result.calories_kcal, 210)
        kwargs = self.service.client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-test")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn("Write dish and notes in Italian", kwargs["messages"][0]["content"])

    async def test_per_request_language_does_not_mutate_default(self):
        await self.service.analyze('toast', language='Russian')
        prompt = self.service.client.chat.completions.create.await_args.kwargs['messages'][0]['content']
        self.assertIn('Write dish and notes in Russian', prompt)
        self.assertEqual(self.service.response_language, 'Italian')

    async def test_photo_boundary(self):
        await self.service.analyze("label", [(b"jpg", "image/jpeg")])
        content = self.service.client.chat.completions.create.await_args.kwargs["messages"][1]["content"]
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    async def test_audio_boundary(self):
        handle, path = tempfile.mkstemp(suffix=".ogg")
        os.close(handle)
        try:
            self.assertEqual(await self.service.transcribe(path), "toast")
            self.assertEqual(self.service.client.audio.transcriptions.create.await_args.kwargs["model"], "audio-test")
        finally:
            os.unlink(path)

    def test_rejects_empty_dish_and_nonfinite_nutrients(self):
        for changed in ({"dish": ""}, {"calories_kcal": "NaN"}, {"fat_g": "Infinity"}):
            data = {**DATA, **changed}
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                parse_estimate(json.dumps(data))
