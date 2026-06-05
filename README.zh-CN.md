# RecallLens

本地优先的日常物品视觉记忆索引。拍照上传后，用自然语言搜索，快速找回物品。支持"我的钥匙在哪？""蓝色背包"等中英文查询。

## 技术栈

- 前端：React、Vite、TypeScript、PWA
- 后端：FastAPI、SQLite、本地图片存储
- 检索：本地 CLIP 嵌入，FAISS 可选加速
- 图像理解：CLIP 零样本语义标签，自动写入每张图片描述
- 测试/演示回退：确定性哈希嵌入，仅用于开发和测试

## 项目结构

```text
backend/
  app/          FastAPI 应用
  tests/        后端 API 与检索测试
frontend/
  src/          React PWA 源码
  public/       manifest、图标、Service Worker
static/         无构建回退 PWA，通过 /app/ 访问
data/           本地运行时数据，不纳入版本控制
```

## API

- `POST /api/images`：多部分上传，支持 `image` 字段和可选的 `note`、`capturedAt`、`latitude`、`longitude`、`locationLabel`；也接受 JSON `imageBase64` 用于回退界面。
- `GET /api/images`：按拍摄/上传时间倒序列出本地图片记录。
- `GET /api/images/{id}`：获取单张图片记录及媒体地址。
- `POST /api/search`：自然语言搜索，支持 `queryText`，可选 `limit`、`capturedFrom`、`capturedTo`、`locationText`。
- `GET /api/queries`：最近搜索历史，包含查询嵌入和结果 ID。
- `GET /api/tags`：自动生成的语义标签分组，方便浏览。
- `GET /api/health`：后端、嵌入服务和向量索引状态。

## 后端启动

```bash
uv sync --extra test
uv pip install -r requirements-clip.txt
uv run uvicorn backend.app.main:app --reload --port 8000
```

默认嵌入后端为本地 CLIP（通过 `open_clip_torch`）。首次上传或搜索时，如果模型权重未缓存，会自动下载。每张上传的图片会被嵌入并与内置标签库比对，`description` 字段会包含物体类型、场景、颜色等语义标签。

如果仅运行 API 测试而不安装 CLIP：

```bash
uv sync --extra test
```

照片包含 EXIF 元数据时，RecallLens 会从中提取拍摄时间和 GPS 坐标作为回退。用户手动输入或浏览器提供的值优先于 EXIF。

搜索支持从查询文本中自动推断日期范围。支持的短语包括 `today`、`yesterday`、`this week`、`last week`、`last 7 days`、`今天`、`昨天`、`本周`、`上周`、`最近 N 天`。

搜索排序采用混合策略：图片向量提供主要的语义匹配，文件名、用户笔记、语义标签和位置标签提供小幅加分。这使得"护照 抽屉"或"办公室 背包"等个人提示能有效发挥作用。

每次搜索会保存为查询记录，包含查询文本、嵌入向量、过滤条件和结果图片 ID。查询历史可通过 `GET /api/queries` 获取。

每张图片的响应还会暴露嵌入元数据（`embeddingModel`、`embeddingDimension`、`embeddingNorm`），方便审计使用的是哪个模型以及向量维度是否正确。

语义标签通过 `GET /api/tags` 自动分组；静态回退界面也包含标签视图，可按物体、场景、颜色标签快速浏览。

React 前端和静态回退界面均支持可选的语音查询输入（基于浏览器 Web Speech API）。不支持语音识别的浏览器可正常使用文字搜索。

常用环境变量：

```bash
RECALLLENS_DATA_DIR=./data
RECALLLENS_EMBEDDER=clip
RECALLLENS_CLIP_MODEL=ViT-B-32
RECALLLENS_CLIP_PRETRAINED=laion2b_s34b_b79k
```

不安装 CLIP 时的快速本地测试：

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

哈希后端是确定性的，适合测试上传/搜索流程，但不能替代 CLIP 的检索质量。

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。前端默认连接 `http://localhost:8000`，可通过环境变量覆盖：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## 无构建回退界面

在无法使用 npm 依赖时，使用静态回退界面：

```bash
RECALLLENS_EMBEDDER=hash uv run uvicorn backend.app.main:app --reload --port 8000
```

然后打开 `http://localhost:8000/app/`。也可以直接在浏览器中打开 `static/index.html`，将 API 地址设为 `http://localhost:8000`。

回退界面以 JSON/base64 方式上传图片，无需 `python-multipart`。安装正常依赖后，同一 `/api/images` 端点也支持多部分上传。

回退界面自带 manifest、图标和 Service Worker，可安装为小型 PWA，离线时仍可打开界面；上传、搜索、媒体和元数据仍需本地 FastAPI 后端运行。

## 演示数据

不安装 CLIP 权重即可快速体验完整的上传/索引/搜索流程：

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/seed_demo.py --data-dir data/demo
RECALLLENS_EMBEDDER=hash RECALLLENS_DATA_DIR=data/demo uv run uvicorn backend.app.main:app --reload --port 8000
```

打开 `http://localhost:8000/app/`，尝试搜索 `钥匙 玄关 架子`、`蓝色 背包`、`护照 抽屉` 或 `充电器 床头`。重复运行种子脚本会复用已有记录；仅在需要从零重建时才加 `--reset`。

## 测试

```bash
uv sync --extra test
RECALLLENS_EMBEDDER=hash uv run pytest
```

测试使用哈希嵌入后端，无需模型权重或网络连接。

不使用 pytest 的快速后端冒烟测试：

```bash
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_backend.py
RECALLLENS_EMBEDDER=hash uv run python scripts/smoke_api.py
```
