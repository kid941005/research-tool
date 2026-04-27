# Research Tool - 架构设计文档

> 本文档定义调研工具的架构设计，作为开发与扩展的参考基准。

---

## 一、设计目标

| 目标 | 说明 |
|------|------|
| **隐私优先** | 使用 SearXNG 元搜索，不直接暴露查询意图给目标网站 |
| **Token 高效** | readability-lxml 自动压缩正文，节省 50-80% token |
| **降级兜底** | 多层抓取策略，任意一层失败自动回退到下一层 |
| **结构化输出** | Markdown + YAML frontmatter，便于后续分析 |
| **图片内嵌** | 自动下载图片并替换 URL，离线可查看 |

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Research Tool                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │  CLI     │───▶│  Searcher    │───▶│  Scraper    │───▶│  ImageDL     │  │
│  │ (main.py)│    │ (SearXNG)    │    │ (smart3w)   │    │ (aiohttp)    │  │
│  └──────────┘    └──────────────┘    └─────────────┘    └──────────────┘  │
│        │                                    │                   │           │
│        │                                    │                   ▼           │
│        │                                    │           ┌──────────────┐    │
│        │                                    └──────────▶│  Documentor  │    │
│        │                                                │  (Markdown)  │    │
│        │                                                └──────────────┘    │
│        │                                                      │             │
│        ▼                                                      ▼             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         output/                                      │   │
│  │   ├── searches/     # 搜索结果 JSON                                  │   │
│  │   ├── pages/        # 抓取页面 Markdown                             │   │
│  │   ├── reports/      # 汇总报告 Markdown                             │   │
│  │   └── images/       # 下载的图片                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块

### 3.1 Searcher（SearXNG 搜索）

**职责**：封装 SearXNG API，执行隐私友好的元搜索

**位置**：`src/searcher.py`

**类**：`SearXNGSearcher`

**接口**：
```python
class SearXNGSearcher:
    def __init__(self, instance_url: str, timeout: int = 10)
    def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]
    def batch_search(self, queries: List[str], delay: float = 1.0) -> Dict[str, List]
```

**数据流**：
```
query string
    │
    ▼
GET {searxng_instance}/search?q={query}&format=json
    │
    ▼
返回 JSON: { results: [{title, url, content}, ...] }
```

**SearXNG 实例**：
- 默认：`https://searxng.hqgg.top:59826`
- 可配置为自建实例（隐私性更强）

---

### 3.2 Scraper（智能网页抓取）

**职责**：基于 smart3w 架构的多层抓取 + 正文压缩

**位置**：`src/scraper.py`

**类**：`SmartScraper`

**抓取策略（优先级顺序）**：

| 优先级 | 方式 | 适用场景 | 失败时 |
|--------|------|----------|--------|
| 1 | `scrapling.DefaultFetcher` + `extract.get` | 普通网页 | 降至 2 |
| 2 | `scrapling.StealthyFetcher` + `fetch` | 反爬站点 | 降至 3 |
| 3 | `requests.Session`（降级保底） | 任意网站 | 返回原始 HTML |

**接口**：
```python
class SmartScraper:
    def __init__(self, compress: bool = True, timeout: int = 30, retry: int = 3)
    def fetch_smart(self, url: str) -> Dict  # 返回 {content, title, images, method, success}
    def _compress_content(self, html: str) -> Tuple[str, str]  # readability 压缩
    def _extract_images(self, html: str) -> List[str]  # 提取图片 URL
```

**readability-lxml 压缩效果**：
- 原始 HTML：约 512B
- 压缩后正文：约 126B
- 压缩率：约 24%（节省 76%）

---

### 3.3 ImageDownloader（图片下载）

**职责**：异步并发下载图片，替换 Markdown 中的 URL

**位置**：`src/image_downloader.py`

**类**：`ImageDownloader`

**接口**：
```python
class ImageDownloader:
    def __init__(self, output_dir: str, max_size_mb: int = 10, concurrency: int = 5)
    async def download_images(self, urls: List[str], prefix: str) -> Dict[str, str]
    def extract_images(self, content: str, base_url: str = "") -> List[str]
    def replace_images_in_markdown(self, content: str, url_to_local: Dict) -> str
```

**工作流程**：
```
Markdown 内容
    │
    ▼
正则提取图片 URL（![alt](url) 和 <img src="url">）
    │
    ▼
aiohttp 并发下载（semaphore 控制并发数）
    │
    ▼
保存到 output/images/{prefix}_{index}.{ext}
    │
    ▼
替换内容中的 URL 为本地相对路径
```

---

### 3.4 Documentor（结构化文档输出）

**职责**：生成带 YAML frontmatter 的 Markdown 文档

**位置**：`src/documentor.py`

**类**：`Documentor`

**输出格式**：
```markdown
---
topic: "AVAS 市场分析"
source: "https://example.com/article"
title: "文章标题"
fetched_at: "2026-04-27T21:00:00+08:00"
images_count: 5
---

# 文章标题

正文内容（readability 压缩后）...

![image description](../images/img_001.jpg)
```

**接口**：
```python
class Documentor:
    def save_search_results(self, query: str, results: List, topic: str) -> str
    def save_page(self, url: str, content: str, title: str, topic: str, images: List) -> str
    def save_report(self, topic: str, pages: List, summary: str) -> str
```

---

## 四、数据流

### 4.1 一键调研（research 命令）

```
用户输入：调研课题
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 搜索                                               │
│   SearXNG.search(课题) → List[title, url, snippet]        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 抓取（循环每个搜索结果）                            │
│   SmartScraper.fetch_smart(url)                             │
│     → content (readability 压缩)                           │
│     → images (URL 列表)                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 下载图片（可选）                                    │
│   ImageDownloader.download_images(urls)                     │
│     → url_to_local (URL → 本地路径)                        │
│   replace_images_in_markdown(content, url_to_local)        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 保存文档                                            │
│   Documentor.save_page(...) → output/pages/xxx.md           │
│   Documentor.save_search_results(...) → output/searches/    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: 生成报告                                            │
│   Documentor.save_report(pages) → output/reports/xxx.md    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
输出：结构化 Markdown 文档 + 本地图片
```

### 4.2 单页抓取（fetch 命令）

```
用户输入：URL
    │
    ▼
SmartScraper.fetch_smart(url)
    │
    ├─→ scrapling.extract.get
    │      成功 → readability 压缩 → 返回
    │
    ├─→ scrapling.stealthy-fetch（回退）
    │      成功 → readability 压缩 → 返回
    │
    └─→ requests（降级）
           成功 → readability 压缩 → 返回
           失败 → 返回空
    │
    ▼
ImageDownloader（可选）
    │
    ▼
Documentor.save_page() → output/pages/xxx.md
```

---

## 五、配置体系

### 5.1 config.yaml 结构

```yaml
searxng:
  instance: "https://searxng.hqgg.top:59826"  # SearXNG 实例
  result_count: 10                              # 默认搜索数量
  timeout: 10                                   # 请求超时（秒）

scraping:
  compress: true        # 是否使用 readability 压缩
  timeout: 30           # 抓取超时（秒）
  retry: 3             # 重试次数
  user_agent: "..."    # HTTP User-Agent

images:
  download: true        # 是否下载图片
  output_dir: "output/images"
  max_size_mb: 10      # 单张图片最大大小
  concurrency: 5       # 并发下载数

output:
  format: "markdown"
  include_metadata: true   # 包含 YAML frontmatter
  include_images: true    # 文档中引用图片
```

### 5.2 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SEARXNG_INSTANCE` | `https://searxng.hqgg.top:59826` | SearXNG 实例地址 |

---

## 六、CLI 接口

### 6.1 命令总览

| 命令 | 说明 | 示例 |
|------|------|------|
| `search` | 关键词搜索 | `python src/main.py search "AVAS"` |
| `fetch` | 抓取单个 URL | `python src/main.py fetch "https://..."` |
| `batch` | 批量调研 | `python src/main.py batch --topics file.txt` |
| `research` | 一键调研 | `python src/main.py research "AVAS 市场"` |

### 6.2 详细用法

```bash
# 搜索
python src/main.py search "关键词" [--limit 10] [--topic 课题]

# 抓取
python src/main.py fetch "URL" [--topic 课题]

# 批量调研
python src/main.py batch --topics topics.txt [--limit 5] [--depth 3]

# 一键调研
python src/main.py research "课题" [--depth 10]
```

---

## 七、扩展点

### 7.1 添加新的抓取方式

在 `SmartScraper` 中新增方法：

```python
async def _fetch_with_playwright(self, url: str) -> Tuple[Optional[str], str]:
    """使用 playwright 渲染 JavaScript"""
    # 实现...
    return content, "playwright"
```

然后在 `fetch_smart` 中添加优先级：

```python
# 在 stealthy 之后添加
if scrapling:
    content = self._fetch_with_playwright(url)
    if content:
        return self._compress_content(content, url)
```

### 7.2 添加新的输出格式

在 `Documentor` 中新增方法：

```python
def save_as_json(self, data: dict, topic: str) -> str:
    """输出为 JSON 格式"""
    # 实现...
```

### 7.3 集成向量数据库

可将 `Documentor.save_page()` 扩展为同时写入向量数据库：

```python
async def embed_and_store(self, content: str, metadata: dict):
    """使用 embedding 模型将内容向量化并存储"""
    # 调用嵌入 API
    # 存储到向量数据库
```

---

## 八、安全与合规

| 措施 | 说明 |
|------|------|
| **robots.txt 遵守** | 抓取前检查目标网站的 robots.txt |
| **请求频率控制** | 批量任务中加入延迟，避免对目标站造成压力 |
| **User-Agent 声明** | 使用真实 User-Agent，不伪装成搜索引擎 |
| **数据本地存储** | 图片和内容存储在本地，不上传第三方 |

---

## 九、技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| **语言** | Python 3.9+ | 生态丰富，易于扩展 |
| **搜索** | SearXNG | 隐私友好的元搜索 |
| **抓取** | scrapling | 自动降级，适配多种网站 |
| **正文提取** | readability-lxml | 专业 HTML 正文提取 |
| **HTTP** | requests + aiohttp | 同步 + 异步并发 |
| **配置** | PyYAML | 易于修改的配置格式 |

---

*文档版本：v0.1.0*
*最后更新：2026-04-27*
