from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import howtocook_loader


class FakeDocumentRepository:
    deleted_sources = []
    created_batches = []

    @classmethod
    async def delete_by_data_source(cls, data_source):
        cls.deleted_sources.append(data_source)
        return 3

    @classmethod
    async def create_batch(cls, documents):
        cls.created_batches.append(documents)
        return [SimpleNamespace(**doc) for doc in documents]


def make_config(base_path: Path):
    return SimpleNamespace(
        rag=SimpleNamespace(
            paths=SimpleNamespace(base_data_path=str(base_path)),
            data_source=SimpleNamespace(
                howtocook=SimpleNamespace(
                    path_suffix="dishes",
                    tips_path_suffix="tips",
                    headers_to_split_on=[["#", "header_1"], ["##", "header_2"]],
                )
            ),
            vector_store=SimpleNamespace(
                collection_names={"recipes": "cook_agent_recipes"}
            ),
        ),
        database=SimpleNamespace(milvus=SimpleNamespace()),
    )


def write_recipe(base_path: Path):
    recipe_dir = base_path / "dishes" / "meat_dish"
    recipe_dir.mkdir(parents=True)
    (recipe_dir / "红烧肉.md").write_text(
        "# 红烧肉\n\n难度：★★\n\n## 做法\n\n炖煮。",
        encoding="utf-8",
    )
    tips_dir = base_path / "tips"
    tips_dir.mkdir()
    (tips_dir / "切菜.md").write_text("# 切菜\n\n保持稳定。", encoding="utf-8")


@pytest.mark.asyncio
async def test_import_global_howtocook_dry_run_does_not_write(tmp_path):
    base_path = tmp_path / "HowToCook"
    write_recipe(base_path)
    calls = {"init_db": 0, "embedding": 0, "vectorstore": 0, "sync": 0}

    result = await howtocook_loader.import_global_howtocook(
        config=make_config(base_path),
        document_repository=FakeDocumentRepository,
        init_db_fn=lambda: _count_async(calls, "init_db"),
        embedding_factory=lambda config: _count(calls, "embedding"),
        vector_store_factory=lambda **kwargs: _count(calls, "vectorstore"),
        sync_repo_fn=lambda: _count(calls, "sync"),
        dry_run=True,
        no_sync=True,
    )

    assert result["dry_run"] is True
    assert result["documents"] > 0
    assert result["chunks"] > 0
    assert FakeDocumentRepository.deleted_sources == []
    assert FakeDocumentRepository.created_batches == []
    assert calls == {"init_db": 0, "embedding": 0, "vectorstore": 0, "sync": 0}


@pytest.mark.asyncio
async def test_import_global_howtocook_no_sync_fails_when_data_missing(tmp_path):
    missing_base_path = tmp_path / "HowToCook"

    with pytest.raises(FileNotFoundError, match="HowToCook data directory not found"):
        await howtocook_loader.import_global_howtocook(
            config=make_config(missing_base_path),
            document_repository=FakeDocumentRepository,
            no_sync=True,
        )


@pytest.mark.asyncio
async def test_import_global_howtocook_empty_documents_do_not_delete_existing_data(tmp_path):
    base_path = tmp_path / "HowToCook"
    (base_path / "dishes").mkdir(parents=True)
    FakeDocumentRepository.deleted_sources = []

    with pytest.raises(RuntimeError, match="No HowToCook documents found"):
        await howtocook_loader.import_global_howtocook(
            config=make_config(base_path),
            document_repository=FakeDocumentRepository,
            no_sync=True,
        )

    assert FakeDocumentRepository.deleted_sources == []


async def _count_async(calls, key):
    calls[key] += 1


def _count(calls, key):
    calls[key] += 1
    return SimpleNamespace()
