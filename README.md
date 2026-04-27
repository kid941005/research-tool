# Research Tool - 调研工具

基于 smart3w 架构的智能调研工具，集成 SearXNG 搜索、网页抓取、图片下载，输出结构化 Markdown 文档。

## 核心功能

- 🔍 **SearXNG 搜索** - 隐私友好的元搜索引擎
- 🌐 **智能网页抓取** - scrapling + readability-lxml 压缩
- 🖼️ **图片下载** - 自动下载正文图片并替换链接
- 📄 **结构化输出** - Markdown 格式，带元数据
- 🔄 **自动降级** - stealthy-fetch 应对反爬站点

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 搜索关键词
python src/main.py search "AVAS 电动汽车 低速提示音"

# 抓取单个 URL
python src/main.py fetch "https://example.com/article" --topic "汽车电子"

# 批量调研（从关键词列表）
python src/main.py batch --topics topics.txt

# 完整流程：搜索 → 抓取 → 下载图片 → 输出文档
python src/main.py research "AVAS 市场分析" --depth 10
```

## 项目结构

```
research-tool/
├── scripts/
│   └── fetch.sh          # smart3w 封装脚本
├── src/
│   ├── __init__.py
│   ├── main.py           # 主入口
│   ├── searcher.py        # SearXNG 搜索
│   ├── scraper.py         # 智能抓取（scrapling + readability）
│   ├── image_downloader.py # 图片下载
│   └── documentor.py      # 结构化文档输出
├── configs/
│   └── config.yaml        # 配置文件
├── output/                # 输出目录
│   ├── searches/          # 搜索结果
│   ├── pages/             # 抓取页面
│   └── reports/           # 最终报告
├── logs/                  # 日志目录
├── requirements.txt
└── README.md
```

## 配置

编辑 `configs/config.yaml`：

```yaml
searxng:
  instance: "https://searxng.hqgg.top:59826"  # 可替换为自建实例

scraping:
  compress: true          # 使用 readability 压缩
  timeout: 30             # 请求超时（秒）
  retry: 3                # 重试次数

images:
  download: true          # 是否下载图片
  output_dir: "output/images"
  max_size_mb: 10         # 单张图片最大大小
  formats: ["jpg", "png", "gif", "webp"]

output:
  format: "markdown"
  include_metadata: true
  include_images: true
```

## 技术架构

```
用户输入（关键词/URL）
       │
       ▼
┌─────────────────┐
│   SearXNG 搜索  │ ←── 返回标题/URL/摘要
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  智能抓取路由    │
├─────────────────┤
│ 1. scrapling    │
│    extract get  │── 成功 → readability 压缩
│                 │
│ 2. scrapling    │── 失败
│    stealthy-fetch│── 成功 → readability 压缩
│                 │
│ 3. 降级保底      │── 返回原始 HTML
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  图片下载        │ ←── 自动提取正文中图片
│  下载到本地      │ ←── 替换 Markdown 中的 URL
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  结构化文档输出   │
│  Markdown + YAML │
│  元数据头        │
└─────────────────┘
```

## 输出格式

生成的 Markdown 文档包含 YAML frontmatter：

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

![image description](../images/article-xxx-1.jpg)
```

## 依赖

- Python 3.9+
- scrapling (网页抓取)
- readability-lxml (正文提取压缩)
- requests (HTTP)
- PyYAML (配置)
- asyncio (并发下载)

## 参考

- smart3w: https://github.com/example/smart3w
- SearXNG: https://github.com/searxng/searxng
- scrapling: https://github.com/example/scrapling
