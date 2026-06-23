# CookAgent

CookAgent 是一个面向烹饪与饮食管理场景的智能助手项目。它由 FastAPI 后端和 React 前端组成，支持基于 HowToCook 菜谱知识库的 RAG 问答、个人知识文档、饮食计划与饮食日志、图像识别记录饮食、Agent 工具调用、MCP 服务管理、LLM 调用统计和 RAG 评估。

## 功能概览

- 菜谱与烹饪问答：基于 HowToCook 全局知识库，提供查询改写、意图识别、元数据过滤、混合检索、重排和答案生成。
- 个人知识库：用户可上传、查询、更新和删除个人文档，个人文档写入独立的 Milvus collection。
- 饮食管理：支持周计划、餐次管理、饮食日志、自然语言或图片解析饮食记录、每日和每周分析。
- 多模态能力：支持图片分析，并可用于饮食日志解析等业务场景。
- Agent 能力：提供 Agent Chat、工具列表、MCP Server 管理、会话管理和 Subagent 管理。
- 用户体系：注册、登录、JWT 鉴权、用户资料、登录失败锁定和可选限流。
- 观测与评估：提供 LLM usage 统计、按模块/模型/工具分布、RAG 评估统计、趋势、告警和健康检查。

## 技术栈

后端：

- Python 3.12+
- FastAPI / Uvicorn
- SQLAlchemy async / asyncpg
- LangChain / LangGraph
- Milvus / langchain-milvus
- Redis
- PostgreSQL
- Pydantic v2

前端：

- React 19
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Recharts

基础设施：

- PostgreSQL: 业务数据、用户数据、会话、文档元数据
- Redis: 缓存、限流、登录安全辅助状态
- Milvus: 全局菜谱向量库与个人文档向量库
- MinIO + etcd: Milvus standalone 依赖

## 项目结构

```text
app/
  api/                 FastAPI 路由
  agent/               Agent、工具、MCP、Subagent
  config/              config.yml 和 .env 配置加载
  conversation/        对话、意图识别、查询改写
  database/            数据库模型、Repository、连接初始化
  diet/                饮食计划、日志、分析
  llm/                 LLM Provider、结构化 JSON 输出、调用统计
  rag/                 RAG 检索、重排、元数据过滤、向量库
  services/            业务服务层
  vision/              多模态图片分析
frontend/             React 前端
scripts/              数据同步与 HowToCook 导入脚本
deployments/          Docker Compose 基础设施
tests/                后端测试
config.yml            非敏感配置
.env.example          环境变量模板
```

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
```

至少需要填写：

- `JWT_SECRET_KEY`: 后端启动必需，建议 32 字符以上。
- `DATABASE_PASSWORD`: PostgreSQL 密码，需要与 Docker Compose 使用的密码一致。
- `LLM_API_KEY`: 主模型 API Key。
- `FAST_LLM_API_KEY`: 快速模型 API Key，可与主模型一致。
- `VISION_API_KEY`: 图片分析使用。
- `RERANKER_API_KEY`: 检索重排使用。

可选能力需要额外配置：

- `WEB_SEARCH_API_KEY`: Tavily Web Search。
- `OPENAI_IMAGE_API_KEY`: 图片生成。
- `AMAP_API_KEY`: 高德地图 MCP 工具。

非敏感配置放在 `config.yml` 中，包括模型名称、API base URL、数据库 host/port、Milvus collection、RAG 检索参数、缓存参数和数据路径。

### 2. 启动基础设施

```bash
docker compose -f deployments/docker-compose.yml --env-file .env up -d
```

默认服务端口：

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- Milvus: `localhost:19530`
- Milvus HTTP: `localhost:9091`
- MinIO: `localhost:9001`

### 3. 安装后端依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 初始化全局 HowToCook 知识库

先检查本地数据是否能正常解析：

```bash
python -m scripts.howtocook_loader --dry-run
```

正式导入：

```bash
python -m scripts.howtocook_loader
```

导入脚本会：

- 如果 `data/HowToCook` 不存在，自动同步 HowToCook 数据。
- 删除 PostgreSQL 中 `data_source="recipes"` 的全局文档。
- 写入新的全局菜谱文档元数据。
- 重建 Milvus 的 `recipes` collection，并写入 chunks。
- 不刷新后端进程内的文档元数据缓存。

如果后端已经在运行，导入完成后需要重启后端，让启动流程重新执行元数据缓存初始化。

常用参数：

```bash
python -m scripts.howtocook_loader --sync      # 导入前强制同步 HowToCook
python -m scripts.howtocook_loader --no-sync   # 不自动同步，本地数据缺失时报错
python -m scripts.howtocook_loader --dry-run   # 只解析并输出 document/chunk 数
```

可用下面的命令检查 PostgreSQL 是否写入全局文档：

```bash
docker exec -it cookagent_postgres psql -U cookagent -d cookagent -c "select data_source, count(*) from knowledge_documents group by data_source;"
```

### 5. 启动后端

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后访问：

- API 根路径: `http://localhost:8000/`
- OpenAPI 文档: `http://localhost:8000/docs`
- API 前缀: `/api/v1`

后端启动时会初始化数据库表、Agent 模块、MCP 服务、文档元数据缓存、Redis 缓存和限流器。

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev
```

Vite 开发服务器会把 `/api` 代理到 `http://localhost:8000`，因此前端默认可以直接访问本地后端。

`http://localhost:5173` 访问 CookAgent。

## 主要 API 模块

所有业务 API 默认挂载在 `/api/v1` 下。

- 认证：`/auth/register`、`/auth/login`
- 用户资料：`/user/profile`
- 对话：`/conversation`
- 个人知识库：`/knowledge/personal-docs`、`/knowledge/metadata-options`
- Agent：`/agent/chat`、`/agent/tools`、`/agent/mcp-servers`、`/agent/sessions`、`/agent/subagents`
- 饮食管理：`/diet/plans/*`、`/diet/meals/*`、`/diet/logs/*`、`/diet/analysis/*`、`/diet/preferences`
- RAG 评估：`/evaluation/*`
- LLM 统计：`/llm-stats/*`

更完整的请求和响应结构以 `http://localhost:8000/docs` 为准。

## 配置说明

`config.yml` 管理非敏感配置，`.env` 管理密钥和部署环境变量。

常见配置位置：

- LLM 分层配置：`llm.fast`、`llm.normal`、`llm.vision`
- RAG 数据源：`rag.data_source.howtocook`
- Milvus collection：`rag.vector_store.collection_names`
- Embedding 模型：`rag.embedding`
- 检索和重排：`rag.retrieval`、`rag.reranker`
- 缓存：`rag.cache`
- MCP：`mcp`
- 图片生成和图片存储：`image_generation`、`image_storage`

敏感值不要写入 `config.yml`，应通过 `.env` 注入。


## 开发备注

- 全局菜谱文档使用 `data_source="recipes"`。
- 个人文档使用 `data_source="personal"`，不受全局 HowToCook 导入脚本影响。
- 全局向量库 collection 默认是 `cook_agent_recipes`。
- 个人文档向量库 collection 默认是 `cook_agent_personal_docs`。
- 模型 JSON 输出统一通过 `LLMInvoker.ainvoke_json(..., PydanticSchema)` 处理，内部包含 Structured Output、JSON 提取兜底、错误反馈重试和降级策略。

## 贡献指南
[CookHero](https://github.com/Decade-qiu/CookHero) - 原项目
