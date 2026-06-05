[English](README.en.md)

# RecallLens

**本地优先的日常物品视觉记忆索引** — 拍照上传，用自然语言搜索，快速找回物品。

支持「我的钥匙在哪？」「蓝色背包」「护照 抽屉」等中英文查询。

## 功能亮点

- **本地 CLIP 语义检索** — 图片自动生成向量嵌入，支持自然语言搜索，无需云端 API
- **零样本语义标签** — 自动识别物体类型、场景、颜色，写入每张图片描述
- **混合排序** — 向量语义匹配 + 文件名/笔记/标签/位置文本加权，让个人提示词更有效
- **智能日期推断** — 从查询文本自动推断日期范围（今天、昨天、本周、最近 N 天）
- **PWA 离线可用** — React 前端 + 静态回退界面，均可安装为 PWA

## 系统架构

```mermaid
graph TB
    subgraph 前端
        A[React PWA]
        B[静态回退 UI]
    end

    subgraph 后端 FastAPI
        C[API 路由]
        D[RecallLens 服务层]
    end

    subgraph 数据层
        E[(SQLite)]
        F[本地图片存储]
        G[向量索引<br/>FAISS / NumPy]
    end

    subgraph AI 模型
        H[CLIP<br/>open_clip_torch]
        I[语义标签器]
    end

    A --> C
    B --> C
    C --> D
    D --> E
    D --> F
    D --> G
    D --> H
    H --> I
```

## 快速开始

```bash
# 安装依赖（含 CLIP）
uv sync --extra test
uv pip install -r requirements-clip.txt

# 启动后端
uv run uvicorn backend.app.main:app --reload --port 8000
```

打开 `http://localhost:8000/app/` 即可使用。

无需 CLIP 的快速体验：

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

## 上传流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant API as FastAPI
    participant S as 存储层
    participant E as CLIP 嵌入
    participant L as 语义标签器
    participant V as 向量索引
    participant DB as SQLite

    U->>API: POST /api/images（图片 + 可选元数据）
    API->>S: 保存原图 + 生成缩略图
    S->>DB: 写入图片记录（status: processing）
    S->>E: 编码图片向量
    E->>L: 生成语义标签（物体/场景/颜色）
    E->>V: 添加到向量索引
    V->>DB: 更新记录（status: indexed）
    API-->>U: 返回图片记录 + 元数据
```

## 搜索流程

```mermaid
flowchart TD
    A[用户输入查询文本] --> B[CLIP 编码查询向量]
    B --> C[向量索引 Top-K 检索]
    C --> D{解析过滤条件}
    D -->|显式指定| E[使用 capturedFrom / capturedTo / locationText]
    D -->|未指定| F[从查询文本推断日期范围]
    E --> G[候选集筛选]
    F --> G
    G --> H[混合评分]
    H --> I[向量语义匹配 × 0.65]
    H --> J[元数据加分<br/>文件名 / 笔记 / 标签 / 位置]
    I --> K[合并排序，返回 Top-N]
    J --> K
    K --> L[保存查询记录]
    L --> M[返回搜索结果]
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React, Vite, TypeScript, PWA |
| 后端 | FastAPI, SQLite, 本地图片存储 |
| 检索 | 本地 CLIP 嵌入，FAISS 可选加速 |
| 图像理解 | CLIP 零样本语义标签 |
| 测试/演示 | 确定性哈希嵌入（仅开发和测试） |

## 项目结构

```
backend/
  app/          FastAPI 应用
  tests/        后端 API 与检索测试
frontend/
  src/          React PWA 源码
  public/       manifest、图标、Service Worker
static/         无构建回退 PWA，通过 /app/ 访问
data/           本地运行时数据，不纳入版本控制
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/images` | 上传图片（multipart 或 JSON base64） |
| `GET` | `/api/images` | 按时间倒序列出图片 |
| `GET` | `/api/images/{id}` | 获取单张图片记录 |
| `POST` | `/api/search` | 自然语言搜索 |
| `GET` | `/api/queries` | 搜索历史 |
| `GET` | `/api/tags` | 语义标签分组 |
| `GET` | `/api/health` | 服务状态 |

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `RECALLLENS_DATA_DIR` | `./data` | 数据存储目录 |
| `RECALLLENS_EMBEDDER` | `clip` | 嵌入后端（`clip` 或 `hash`） |
| `RECALLLENS_CLIP_MODEL` | `ViT-B-32` | CLIP 模型名称 |
| `RECALLLENS_CLIP_PRETRAINED` | `laion2b_s34b_b79k` | CLIP 预训练权重 |

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`，默认连接 `http://localhost:8000`：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 演示数据

无需 CLIP 权重即可体验完整流程：

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/seed_demo.py --data-dir data/demo
RECALLLENS_EMBEDDER=hash RECALLLENS_DATA_DIR=data/demo uv run uvicorn backend.app.main:app --reload --port 8000
```

尝试搜索：`钥匙 玄关 架子`、`蓝色 背包`、`护照 抽屉`、`充电器 床头`

## 测试

```bash
uv sync --extra test
RECALLLENS_EMBEDDER=hash uv run pytest
```

快速冒烟测试：

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_backend.py
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_api.py
```
