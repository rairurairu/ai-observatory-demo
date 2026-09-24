# AI Observatory

**LLM 品牌推荐洞察平台** · 本地研究平台

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

AI Observatory 是一个本地研究平台，用于开展受控的提示词与模型实验、保存原始回答、提取品牌观察并查看描述性趋势。仓库附带真实实验数据；应用不会在数据或服务提供方缺失时生成替代回答。

## 界面截图

![AI Observatory 总览：筛选自 SQLite 快照中的真实手机推荐实验](docs/images/live-overview.png)

*总览：来自仓库 SQLite 实验数据库的真实实验记录。*

![回答浏览器：真实 MiniMax、DeepSeek 回答及记录的失败尝试](docs/images/live-response-explorer.png)

*回答浏览器：实验数据库中的服务提供方原始输出、提取观察结果和失败尝试。*

## 架构

- **前端：** TypeScript、React 和 Vite，提供分析视图、筛选、创建实验、查看回答、CSV/JSON 导出和人工审核。
- **API：** FastAPI 与 Pydantic；文档位于 `http://localhost:8000/docs`。
- **数据库：** 默认使用 SQLite 和 SQLAlchemy。安装 PostgreSQL 驱动后，可用 `DATABASE_URL` 配置 PostgreSQL。
- **研究流程：** 提示词/模型/重复次数 → 运行记录 → 原始回答 → 版本化提取 → 标准品牌观察 → 分析或人工标注。
- **附带数据：** 仓库包含截图使用的 SQLite 快照。API 启动时只初始化品牌参考数据，不会合成回答。

本地执行器适用于研究演示，不是持久化分布式执行系统。实时执行支持 OpenAI、Anthropic、Google Gemini、MiniMax 和 DeepSeek API，以及运行 API 的电脑上已登录的 Claude Code、Codex 和 GitHub Copilot CLI。请求按顺序执行，需要明确确认，提供方错误也会保存。搜索工具/引用、自动调度和价格估算尚未实现；实时执行会禁用搜索，费用显示为不可用。

## 安装与启动（Windows PowerShell）

建议使用 Python 3.11 或更高版本。在此目录运行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\initialize_database.py
```

安装前端依赖：

```powershell
cd frontend
npm install
cd ..
```

在两个终端分别启动 API 和前端：

```powershell
# 终端 1
uvicorn backend.main:app --reload
```

```powershell
# 终端 2
npm --prefix frontend run dev
```

打开 `http://localhost:5173`。Vite 会将 API 请求代理到 8000 端口的 FastAPI。健康检查和交互式 API 文档位于 `http://localhost:8000/health` 和 `/docs`。

## 附带的实验快照

仓库中的 `data/ai_observatory.db` 是一个时间点快照，仪表板打开后即可查看真实实验记录。快照包含五个小型实验的 16 次提供方请求：实时回答、记录的提供方/模型失败，以及一条因无法确认解析后模型而排除的 Copilot Auto 回答。没有合成回答。实时研究只使用一个智能手机提示词，适合描述性查看，不构成具有统计说服力的模型比较。数据库不含 API 密钥；凭据应保存在本地且被 Git 忽略的 `.env` 文件中。

该快照已提交到仓库，之后的本地实验不会自动发布。分享新记录前，请先确认数据库不包含私人数据或密钥，再明确提交更新。

`.env.example` 设置 `APP_MODE=live` 并指向快照数据库。无需 API 密钥即可浏览已保存的回答。只有需要收集新的实时回答时才添加凭据；启动时不会调用模型。

如需使用实时 API，将一个或多个密钥填入 `.env`（`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`MINIMAX_API_KEY` 或 `DEEPSEEK_API_KEY`），然后重启后端。MiniMax 和 DeepSeek 使用兼容 OpenAI 的 Chat Completions API；可通过对应设置调整基础 URL 和模型 ID。实验室会检测已登录的 Claude Code 和 Codex CLI。只有在 `COPILOT_CLI_MODEL_IDS` 明确列出模型 ID 时才会提供 Copilot；Auto 路由已禁用，因为无法记录实际解析的模型。模型可用性取决于 Copilot 计划、CLI 版本和组织策略；不可用请求会保留为失败记录，不计入推荐结果。目前登录的 Copilot CLI 账户只提供 Auto，因此具名模型开放前 Copilot 会保持禁用。应用不会通过浏览器登录连接 Gemini Enterprise。Claude Pro 和 ChatGPT Plus 通过各自的本地 CLI 使用，并受对应服务的订阅条款管理。CLI 用量或额度由相应服务管理。

创建实时实验后，先查看计划请求数量，并勾选明确确认项再运行。目前未配置 API 定价，因此不提供费用估算；API 请求可能产生费用。单个提供方请求失败会保存为失败记录，不会阻止其他请求继续。如果实时执行期间 API 进程中断，重启并再次运行该实验即可从已保存的请求继续。请勿公开 `.env`。快照数据库在修改或替换前应先备份。

## 给编程代理的提示

如需编程代理在本地克隆并打开已保存的研究数据，请直接发送以下提示：

```text
请克隆 https://github.com/rairurairu/ai-observatory-demo.git，并协助我在本地运行 AI Observatory。先阅读 README.md 并遵循安装步骤。使用仓库附带的 data/ai_observatory.db 作为实验历史，不要生成合成回答。不要读取、打印、复制或上传任何 .env 文件或 API 密钥。不要发送实时服务提供方请求、替换数据库或推送更改。启动后端和前端，然后告诉我本地网址以及如何停止两个服务。
```

## 五分钟导览

1. 打开 **Overview**，查看实时数据标记、分母、回答级提及率以及领域/模型筛选器。
2. 打开 **Experiment Lab**，查看 MiniMax/DeepSeek 配对运行，以及 CLI 和 Copilot 可用性记录。
3. 打开 **Response Explorer**，比较真实提供方回答、提取观察、提及顺序和明确排名。
4. 查看 **Model Comparison**、**Prompt Sensitivity** 和 **Historical Trends**。当前样本较小，比例仅用于描述。
5. 打开 **Data Quality** 查看证据，再用 **System Monitor** 查看请求/失败数量及目前不可用的 Token/费用信息。

## 测试

```powershell
pytest -q
```

测试涵盖 API 启动、提取与明确排名处理、限定领域的比例汇总、隔离的合成测试数据、实时/演示来源隔离和标注保存。合成数据仅供测试；正常启动会加载附带的真实数据，不会新增虚构回答。

## 范围与限制

- **已实现：** 规范化持久化结构；附带实时实验历史；受控实验 CRUD/执行；实验/运行/回答 ID；OpenAI、Anthropic、Gemini、MiniMax、DeepSeek API 适配器；Claude Code、Codex、GitHub Copilot CLI 适配器；实时费用确认；逐请求保存失败；字典式品牌提取、别名和产品关联；带证据的提及记录；回答级品牌比例；模型比较；历史趋势；提示词变体比例；人工审核标注；运行日志；回答导出；CSV/JSON；TypeScript/React 前端。
- **尚未实现：** SDK 重试之外的提供方限流、实时价格估算、持久化异步任务队列、提供方搜索/引用、自动调度、高级分层推断、统计漂移检验和 Parquet 快照。漂移视图需要足够的观测数据，且仅为描述性信息，不能证明服务版本发生变化。
- 情感和属性提取使用保守的关键词规则。结果只是研究辅助，并非经过验证的 NLP 测量；无法明确判断时会保留未知值。

## 数据库说明

SQLite 结构由 SQLAlchemy `create_all` 创建。仓库中的 `data/ai_observatory.db` 仅包含实时实验历史：五个小型实验的 16 次提供方请求，包括成功回答、失败记录和一条排除的 Copilot Auto 回答。数据库不含 API 密钥。长期研究请在结构演进前加入 Alembic 迁移，并配置 PostgreSQL 驱动。原始回答和既有提取记录都会保留；提取版本记录在 `extraction_runs.pipeline_version` 中。
