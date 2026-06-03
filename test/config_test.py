import importlib
import sys

import pytest

from app.config.config_loader import (
    _load_config_data,
    load_database_config,
    load_llm_config,
    load_rag_config,
    load_web_search_config,
)


CONFIG_YAML = """
llm:
  fast:
    model_names:
      - "fast-model"
    base_url: "https://fast.example.com/v1"
    temperature: 0.2
    max_tokens: 1000
  normal:
    model_names:
      - "normal-model"
    base_url: "https://normal.example.com/v1"
    temperature: 0.7
    max_tokens: 2000
  vision:
    model_names:
      - "vision-model"
    base_url: "https://vision.example.com/v1"
    temperature: 0.3
    max_tokens: 3000

embedding:
  model_name: "test-embedding-model"

vector_store:
  type: "milvus"
  collection_names:
    recipes: "test_recipes"
    personal: "test_personal"

retrieval:
  top_k: 5
  score_threshold: 0.35
  ranker_type: "weighted"
  ranker_weights: [0.6, 0.4]

reranker:
  enabled: true
  type: "siliconflow"
  model_name: "test-reranker"
  base_url: "https://reranker.example.com/v1/rerank"
  temperature: 0.0
  max_tokens: 512
  score_threshold: 0.25

cache:
  enabled: true
  ttl: 600
  l2_enabled: false
  similarity_threshold: 0.8
  vector_collection: "test_cache"

web_search:
  enabled: true
  max_results: 3

database:
  postgres:
    host: "postgres.local"
    port: 5433
    database: "cookagent_test"
    user: "test_user"
    pool_size: 2
    max_overflow: 4
    pool_timeout: 10
    pool_recycle: 900
    echo: true
  redis:
    host: "redis.local"
    port: 6380
    db: 2
  milvus:
    host: "milvus.local"
    port: 19531

paths:
  base_data_path: "data/test"

data_source:
  howtocook:
    path_suffix: "test_dishes"
    tips_path_suffix: "test_tips"
    headers_to_split_on:
      - ["#", "header_1"]
      - ["##", "header_2"]
"""


SENSITIVE_ENV_VARS = [
    "LLM_API_KEY",
    "FAST_LLM_API_KEY",
    "VISION_API_KEY",
    "RERANKER_API_KEY",
    "DATABASE_PASSWORD",
    "REDIS_PASSWORD",
    "MILVUS_USER",
    "MILVUS_PASSWORD",
    "WEB_SEARCH_API_KEY",
]


@pytest.fixture
def config_workspace(tmp_path, monkeypatch):
    """Run each config test from an isolated directory with its own config.yml."""
    monkeypatch.chdir(tmp_path)
    for env_name in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    (tmp_path / "config.yml").write_text(CONFIG_YAML, encoding="utf-8")
    return tmp_path


def test_load_config_data_reads_config_yml(config_workspace):
    config_data = _load_config_data()

    assert config_data["llm"]["normal"]["model_names"] == ["normal-model"]
    assert config_data["database"]["postgres"]["host"] == "postgres.local"
    assert config_data["retrieval"]["top_k"] == 5


def test_load_llm_config_merges_yaml_and_environment(config_workspace, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "normal-secret")
    monkeypatch.setenv("FAST_LLM_API_KEY", "fast-secret")
    monkeypatch.setenv("VISION_API_KEY", "vision-secret")

    llm_config = load_llm_config()

    assert llm_config.normal.pick_default_model() == "normal-model"
    assert llm_config.normal.base_url == "https://normal.example.com/v1"
    assert llm_config.normal.api_key == "normal-secret"
    assert llm_config.fast.api_key == "fast-secret"
    assert llm_config.vision.api_key == "vision-secret"


def test_load_database_config_merges_yaml_and_environment(config_workspace, monkeypatch):
    # 临时设置环境变量
    monkeypatch.setenv("DATABASE_PASSWORD", "postgres-secret")
    monkeypatch.setenv("REDIS_PASSWORD", "redis-secret")
    monkeypatch.setenv("MILVUS_USER", "milvus-user")
    monkeypatch.setenv("MILVUS_PASSWORD", "milvus-secret")

    database_config = load_database_config()

    assert database_config.postgres.host == "postgres.local"
    assert database_config.postgres.port == 5433
    assert database_config.postgres.password == "postgres-secret"
    assert database_config.postgres.async_url == (
        "postgresql+asyncpg://test_user:postgres-secret"
        "@postgres.local:5433/cookagent_test"
    )
    assert database_config.redis.password == "redis-secret"
    assert database_config.milvus.user == "milvus-user"
    assert database_config.milvus.password == "milvus-secret"


def test_load_rag_config_maps_yaml_sections(config_workspace):
    rag_config = load_rag_config()

    assert rag_config.paths.base_data_path == "data/test"
    assert rag_config.embedding.model_name == "test-embedding-model"
    assert rag_config.vector_store.collection_names["recipes"] == "test_recipes"
    assert rag_config.retrieval.top_k == 5
    assert rag_config.retrieval.ranker_weights == [0.6, 0.4]
    assert rag_config.reranker.model_name == "test-reranker"
    assert rag_config.cache.ttl == 600
    assert rag_config.cache.l2_enabled is False
    assert rag_config.data_source.howtocook.path_suffix == "test_dishes"


def test_reranker_api_key_prefers_specific_environment(config_workspace, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "normal-secret")
    monkeypatch.setenv("RERANKER_API_KEY", "reranker-secret")

    rag_config = load_rag_config(load_llm_config())

    assert rag_config.reranker.api_key == "reranker-secret"


def test_reranker_api_key_falls_back_to_normal_llm_key(config_workspace, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "normal-secret")

    rag_config = load_rag_config(load_llm_config())

    assert rag_config.reranker.api_key == "normal-secret"


def test_load_web_search_config_uses_environment_api_key(config_workspace, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "web-search-secret")

    web_search_config = load_web_search_config()

    assert web_search_config.enabled is True
    assert web_search_config.max_results == 3
    assert web_search_config.api_key == "web-search-secret"


def test_settings_can_be_instantiated_from_project_config(monkeypatch):
    for env_name in SENSITIVE_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)

    sys.modules.pop("app.config.config", None)
    config_module = importlib.import_module("app.config.config")

    assert config_module.settings.PROJECT_NAME == "CookAgent"
    assert config_module.settings.llm.normal.model_names
    assert config_module.DefaultRAGConfig is config_module.settings.rag


def test_missing_config_file_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="config.yml not found"):
        _load_config_data()
