import base64
import json
import math
from dataclasses import dataclass

from openai import AsyncOpenAI

SYSTEM_PROMPT = """Estimate nutrition for one consumed meal. Use text and every image.
Nutrition-label images are evidence; distinguish per-serving from consumed quantity.
A readable nutrition facts label plus a consumed amount identifies a food product
even when its name or ingredients are missing: set identified=true and use a generic
product description. Do not reject a valid label just because no dish name is visible.
If no dish, drink, or ingredients can be identified, return only identified=false.
Do not invent food from unrelated text or unrecognizable images. Otherwise return
JSON with identified=true, dish (string), calories_kcal, protein_g, carbs_g, fat_g
(numbers), confidence (low|medium|high), notes (short string). Use reasonable portions
when missing and say so in notes. Also return fiber_g: dietary fiber in grams for
the consumed portion, estimated from ingredients or the nutrition label. Use null
if fiber cannot reasonably be estimated (for example an unnamed label omitting it).
Never assume missing fiber is zero; zero is valid for foods known to contain none.
Never return ranges. Write dish and notes in {language}."""


class NoFoodIdentified(ValueError):
    """Input contains no identifiable food; nothing should be persisted."""


@dataclass(frozen=True)
class Estimate:
    dish: str
    calories_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    confidence: str
    notes: str
    fiber_g: float | None = None


class NutritionAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str,
        transcription_model: str,
        response_language: str = "English",
    ):
        self.client = AsyncOpenAI(api_key=api_key, timeout=60, max_retries=1)
        self.model = model
        self.transcription_model = transcription_model
        self.response_language = response_language

    async def analyze(self, text: str = "", images: list[tuple[bytes, str]] | None = None, language: str | None = None) -> Estimate:
        content: list[dict] = [{"type": "text", "text": text or "Estimate the pictured food."}]
        for raw, mime in images or []:
            encoded = base64.b64encode(raw).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(language=language or self.response_language)},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
        )
        return parse_estimate(response.choices[0].message.content)

    async def transcribe(self, path: str) -> str:
        with open(path, "rb") as audio:
            response = await self.client.audio.transcriptions.create(
                model=self.transcription_model, file=audio
            )
        return response.text.strip()


def parse_estimate(raw: str) -> Estimate:
    data = json.loads(raw)
    if data.get('identified') is False:
        raise NoFoodIdentified()
    dish = data.get('dish')
    if not isinstance(dish, str) or not dish.strip():
        raise NoFoodIdentified()
    dish = dish.strip()
    nutrients = {}
    for field in ("calories_kcal", "protein_g", "carbs_g", "fat_g"):
        value = float(data[field])
        if not math.isfinite(value):
            raise ValueError(f"{field} must be finite")
        nutrients[field] = max(0, value)
    if nutrients['calories_kcal'] == 0 and data.get('identified') is not True:
        raise NoFoodIdentified()
    confidence = str(data.get("confidence", "low")).lower()
    fiber = data.get('fiber_g')
    if fiber is not None:
        if isinstance(fiber, bool):
            raise ValueError('fiber_g must be a nonnegative finite number or null')
        fiber = float(fiber)
        if not math.isfinite(fiber) or fiber < 0:
            raise ValueError('fiber_g must be a nonnegative finite number or null')
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    return Estimate(
        dish=dish,
        calories_kcal=nutrients["calories_kcal"],
        protein_g=nutrients["protein_g"],
        carbs_g=nutrients["carbs_g"],
        fat_g=nutrients["fat_g"],
        confidence=confidence,
        notes=str(data.get("notes", "")).strip(),
        fiber_g=fiber,
    )
