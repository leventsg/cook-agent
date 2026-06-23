from app.diet.database.models import DietLogItemModel


def test_diet_log_item_indexes_have_unique_names():
    index_names = [index.name for index in DietLogItemModel.__table__.indexes]

    assert len(index_names) == len(set(index_names))
