import uuid
from datetime import date, datetime

import pytest

from app.diet.database.models import DataSource
from app.diet.service import DietLogItemOutput, DietLogParseOutput, DietService
from app.utils.structured_json import extract_first_valid_json


class FakeLogItem:
    def __init__(self, *, log_id, user_id, log_date, meal_type, notes, item):
        self.log_id = log_id
        self.user_id = user_id
        self.log_date = log_date
        self.meal_type = meal_type
        self.notes = notes
        self.plan_meal_id = None
        self.created_at = datetime(2026, 6, 22, 12, 0, 0)
        self.item = item

    def to_dict(self):
        return {
            "id": str(uuid.uuid4()),
            "log_id": str(self.log_id),
            "food_name": self.item["food_name"],
            "weight_g": self.item.get("weight_g"),
            "unit": self.item.get("unit"),
            "calories": self.item.get("calories"),
            "protein": self.item.get("protein"),
            "fat": self.item.get("fat"),
            "carbs": self.item.get("carbs"),
            "source": self.item.get("source"),
            "confidence_score": self.item.get("confidence_score"),
            "created_at": self.created_at.isoformat(),
        }


class FakeRepository:
    def __init__(self):
        self.created_items = None

    async def create_log_items(
        self,
        user_id,
        log_date,
        meal_type,
        items,
        notes=None,
        plan_meal_id=None,
        log_id=None,
    ):
        self.created_items = items
        log_uuid = log_id or uuid.uuid4()
        return [
            FakeLogItem(
                log_id=log_uuid,
                user_id=user_id,
                log_date=log_date,
                meal_type=meal_type,
                notes=notes,
                item=item,
            )
            for item in items
        ]


class FakeInvoker:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def ainvoke_json(self, messages, schema, **kwargs):
        self.calls.append((messages, schema, kwargs))
        if self.error:
            raise self.error
        return self.result


class FakeProvider:
    create_invoker_kwargs = None
    invoker = None

    def __init__(self, config):
        pass

    def create_invoker(self, **kwargs):
        self.__class__.create_invoker_kwargs = kwargs
        return self.__class__.invoker


def test_extract_first_valid_json_accepts_common_llm_shapes():
    direct = '{"meal_type": "lunch", "items": []}'
    trailing = '{"meal_type": "lunch", "items": []}\n以上是解析结果'
    fenced = '```json\n{"meal_type": "lunch", "items": []}\n```'

    assert extract_first_valid_json(direct)["meal_type"] == "lunch"
    assert extract_first_valid_json(trailing)["meal_type"] == "lunch"
    assert extract_first_valid_json(fenced)["meal_type"] == "lunch"


@pytest.mark.asyncio
async def test_log_from_text_records_items_from_structured_output(monkeypatch):
    FakeProvider.invoker = FakeInvoker(
        result=DietLogParseOutput(
            meal_type="lunch",
            items=[
                DietLogItemOutput(food_name="双层芝士汉堡", unit="个", calories=450),
                DietLogItemOutput(food_name="中薯条", unit="份", calories=320),
                DietLogItemOutput(food_name="无糖可乐", unit="杯", calories=0),
                DietLogItemOutput(food_name="混沌", unit="碗", calories=350),
                DietLogItemOutput(food_name="茶叶蛋", unit="个", calories=140),
            ],
        )
    )
    monkeypatch.setattr("app.llm.provider.LLMProvider", FakeProvider)
    repository = FakeRepository()
    service = DietService(repository=repository)

    result = await service.log_from_text(
        user_id="user-1",
        text="今天中午在kfc吃了一个双层芝士汉堡、一份中薯条、一杯无糖可乐，晚上吃了一碗混沌加两个茶叶蛋",
        log_date=date(2026, 6, 22),
    )

    assert FakeProvider.create_invoker_kwargs == {
        "llm_type": "normal",
        "temperature": 0.0,
    }
    assert FakeProvider.invoker.calls[0][1] is DietLogParseOutput
    assert result["meal_type"] == "lunch"
    assert [item["food_name"] for item in result["items"]] == [
        "双层芝士汉堡",
        "中薯条",
        "无糖可乐",
        "混沌",
        "茶叶蛋",
    ]
    assert {item["source"] for item in repository.created_items} == {
        DataSource.AI_TEXT.value
    }


@pytest.mark.asyncio
async def test_log_from_text_falls_back_to_raw_text_when_structured_output_fails(
    monkeypatch,
):
    FakeProvider.invoker = FakeInvoker(error=ValueError("bad json"))
    monkeypatch.setattr("app.llm.provider.LLMProvider", FakeProvider)
    repository = FakeRepository()
    service = DietService(repository=repository)

    result = await service.log_from_text(
        user_id="user-1",
        text="今天吃了一些东西",
        log_date=date(2026, 6, 22),
    )

    assert result["meal_type"] == "snack"
    assert repository.created_items == [
        {
            "food_name": "今天吃了一些东西",
            "source": DataSource.AI_TEXT.value,
        }
    ]


class FakeVisionProvider:
    is_enabled = True

    def __init__(self):
        self.calls = []

    async def analyze_json(self, text, images, schema, **kwargs):
        self.calls.append((text, images, schema, kwargs))
        return DietLogParseOutput(
            meal_type="dinner",
            items=[DietLogItemOutput(food_name="牛肉面", unit="碗", calories=520)],
        )


@pytest.mark.asyncio
async def test_log_from_text_uses_vision_structured_output_for_images(monkeypatch):
    fake_vision = FakeVisionProvider()
    FakeProvider.invoker = FakeInvoker(error=AssertionError("text LLM should not run"))
    monkeypatch.setattr("app.llm.provider.LLMProvider", FakeProvider)
    monkeypatch.setattr("app.vision.provider.vision_provider", fake_vision)
    repository = FakeRepository()
    service = DietService(repository=repository)

    result = await service.log_from_text(
        user_id="user-1",
        text="晚餐",
        log_date=date(2026, 6, 22),
        images=[{"data": "abc", "mime_type": "image/jpeg"}],
    )

    assert result["meal_type"] == "dinner"
    assert fake_vision.calls[0][2] is DietLogParseOutput
    assert repository.created_items == [
        {
            "food_name": "牛肉面",
            "weight_g": None,
            "unit": "碗",
            "calories": 520.0,
            "protein": None,
            "fat": None,
            "carbs": None,
            "source": DataSource.AI_IMAGE.value,
        }
    ]
