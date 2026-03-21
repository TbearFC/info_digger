# info_digger

AI 领域情报系统。自动抓取 GitHub、arXiv、HuggingFace 的最新动态，用 Claude 生成一句话摘要，在时间轴上聚合展示，并提供自然语言问答。

**核心理念：看到过去，才能看见未来。**

## Features

- **多源抓取**：GitHub 热门仓库、arXiv 论文（cs.AI / cs.LG / cs.CL）、HuggingFace 最新模型、X/Twitter（可选，默认关闭）
- **自动摘要**：每条条目由 Claude Haiku 生成一句话摘要
- **话题标签**：关键词匹配自动打标签（LLM Reasoning、RAG、Agents、Multimodal 等）
- **时间轴 UI**：按月分组、多源过滤、无限加载
- **活跃度曲线图**：各话题跨平台热度随时间变化的 SVG 折线图
- **研究助手**：`POST /api/ask`，用自然语言提问，系统用收集到的数据回答
- **健康监控**：`GET /admin/health`，查看各爬虫状态和 Claude API 成功率
- **Docker 支持**：一条命令启动，SQLite 数据持久化

## Quick Start

**方式一：bare 安装**

```bash
git clone https://github.com/TbearFC/info_digger
cd info_digger
pip install -r requirements.txt
cp .env.example .env      # 填入 ANTHROPIC_API_KEY
uvicorn main:app --reload
```

**方式二：Docker**

```bash
git clone https://github.com/TbearFC/info_digger
cd info_digger
cp .env.example .env      # 填入 ANTHROPIC_API_KEY
docker-compose up
```

打开 `http://localhost:8000`。首次启动会自动做 3 个月历史回填（arXiv 需要 30–90 分钟），之后每小时自动爬取一次。

## Configuration

复制 `.env.example` 为 `.env`，按需填写：

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ANTHROPIC_API_KEY` | ✅ | — | Claude API Key |
| `DB_PATH` | — | `./data/info_digger.db` | SQLite 路径 |
| `CLAUDE_MODEL` | — | `claude-haiku-4-5-20251001` | 摘要 + 问答用的模型 |
| `GITHUB_TOKEN` | — | — | 提升 GitHub 限速至 5000 req/hr |
| `HF_API_TOKEN` | — | — | 提升 HuggingFace 限速 |
| `TWITTER_ENABLED` | — | `false` | 设为 `true` 开启 Twitter 爬虫 |
| `NITTER_URL` | — | — | Twitter 启用时必填（nitter.net 已下线，需自备实例） |
| `TWITTER_ACCOUNTS` | — | `karpathy,ylecun,sama` | 跟踪的账号（逗号分隔） |
| `DB_BACKFILLED` | — | — | 设为 `1` 跳过历史回填 |

## API

| 接口 | 说明 |
|------|------|
| `GET /api/entries` | 获取条目，支持 `topic`、`source`、`limit`、`offset` 过滤 |
| `GET /api/topics` | 获取所有话题标签 |
| `GET /api/stats` | 各话题按月统计条目数（活跃度图数据源） |
| `POST /api/ask` | 自然语言问答，body: `{"question": "...", "topic": "..."}` |
| `GET /admin/health` | 爬虫状态 + Claude API 成功率 |

## Tech Stack

Python · FastAPI · SQLite (WAL) · APScheduler · httpx · feedparser · Anthropic Claude API · 原生 SVG · 零前端依赖
