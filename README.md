# Research Tool - 调研工具

基于 smart3w 架构的智能调研工具，集成 SearXNG 搜索、网页抓取、图片下载，输出结构化 Markdown 文档。

## 核心功能

- 🔍 **SearXNG 搜索** - 隐私友好的元搜索引擎，自动过滤空 URL 并做基础去重
- 🧭 **来源过滤** - 支持按 `source_type` 最小过滤 `wechat / web / all`
- 🌐 **智能网页抓取** - scrapling + readability-lxml 压缩
- 🩺 **最小自检** - `smoke` 命令可快速验证基础抓取链路
- 🖼️ **图片下载** - 自动下载正文图片并替换链接
- 📄 **结构化输出** - Markdown 格式，带元数据
- 🧠 **规则分析报告** - 自动汇总执行摘要、高频关键词、来源分布、核心发现、抓取统计、抓取方式/警告与下一步建议
- 🟢 **公众号提取** - 自动识别微信文章并优先抽取 `js_content` 正文与插图
- 🚨 **微信错误页识别** - 识别“参数错误 / 内容已被删除 / 访问过于频繁 / weui-msg”等常见微信错误页
- 🧹 **微信尾部清理** - 对“推荐阅读 / 我们是谁 / 课程邀请 / 关注我们 / 点赞在看”等常见运营尾部做最小截断，并尽量保留 section 结构中的正文段落与插图
- 🧾 **微信来源汇总** - 在报告中单独列出微信公众号来源，便于快速识别微信证据链

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 搜索关键词
python src/main.py search "AVAS 电动汽车 低速提示音"

# 只看微信公众号来源
python src/main.py search "AVAS 电动汽车 低速提示音" --source-type wechat

# 抓取单个 URL
python src/main.py fetch "https://example.com/article" --topic "汽车电子"

# 最小自检（验证基础抓取链路）
python src/main.py smoke

# 批量调研（从关键词列表）
python src/main.py batch --topics topics.txt

# 完整流程：搜索 → 抓取 → 规则分析 → 输出调研报告
python src/main.py research "AVAS 市场分析" --depth 10 --output ./deliverables/

# 使用自定义配置（注意 --config 必须放在子命令前）
python src/main.py --config ./configs/config.yaml research "AVAS 市场分析" --depth 10

# 生成交付包（报告 + 搜索结果 + 页面原文）
python src/main.py research "AVAS 市场分析" --depth 10 --bundle-dir ./deliverables/avas_package

# 指定正式报告文件名
python src/main.py research "AVAS 市场分析" --depth 10 --report-name avas-market-report-q2.md --output ./deliverables/
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
┌──────────────────────────────┐
│  智能抓取路由                │
├──────────────────────────────┤
│ 1. scrapling.Fetcher().get() │── 成功 → 压缩/提取正文
│                              │
│ 2. scrapling:stealthy        │── 当前 CLI 运行时跳过
│                              │    记录 warning 后降至 3
│ 3. requests:fallback         │── 返回 HTML 并继续压缩/提取
└────────┬─────────────────────┘
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

生成的 Markdown 报告除来源与预览外，还会补充：
- 摘要
- 抓取统计
- 执行摘要
- 高频关键词
- 来源评估
- 来源分布
- 核心发现（附来源链接）
- 建议下一步
- 每个来源的抓取方式与 warning（如 fallback / skipped / 微信错误页提示）

交付相关：
- `research` / `batch` 支持 `--output` 指定最终报告交付路径（文件或目录）
- `research` / `batch` 支持 `--max-pages` 控制最终报告最多收录的页面数
- `research` / `batch` 支持 `--bundle-dir` 生成交付包目录，内含报告、搜索结果、页面原文和 `manifest.json`
- `research` / `batch` 支持 `--report-name` 指定正式交付时的报告文件名
- `manifest.json` 额外记录 `report_name`、`topic_slug`，便于归档与后续自动化处理
- 报告与 `manifest.json` 会记录最小抓取统计：`attempted_count`、`success_count`、`failed_count`
- 当前外部信息源以 `SearXNG 搜索结果 + 抓取网页正文` 为主；其中已优先支持微信公众号文章正文提取、常见尾部运营段最小清理、搜索结果中的微信链接显式标记，并在报告中单列微信公众号来源
- 搜索结果会做最小清洗：过滤空 URL，并按 URL 做基础去重
- `search` / `batch` / `research` 支持 `--source-type wechat|web|all` 做最小来源过滤
- 对微信公众号链接，当前还会识别常见微信错误页（如 `参数错误`、`内容已被删除`、`访问过于频繁`、`weui-msg`）并在 warning / error 中明确提示
- `--config` 是全局参数，必须写在子命令前，例如 `python src/main.py --config ./configs/config.yaml research "课题"`
- 当前 CLI 运行时会跳过 `scrapling:stealthy` 分支，并在降级时输出 warning 后继续走 `requests:fallback`

生成的页面 Markdown 文档包含 YAML frontmatter：

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

## 最小回归测试

建议按以下顺序验证：

```bash
python src/main.py smoke
pytest tests/test_wechat_extraction.py tests/test_documentor_report.py tests/test_searcher.py tests/test_main_filters.py tests/test_smoke.py
```

当前基线已验证通过：
- `python src/main.py smoke` → `SMOKE_OK`
- `pytest tests/test_wechat_extraction.py tests/test_documentor_report.py tests/test_searcher.py tests/test_main_filters.py tests/test_smoke.py` → `16 passed`
- `python src/main.py research 'example domain' --depth 1 --max-pages 1 --output ./tmp_e2e_verify` → 可完成搜索、抓取与报告落盘

当前最小测试基线覆盖：
- 微信 section 正文/图片保留与错误页识别
- 报告中的抓取统计、抓取方式、warning 输出
- 搜索结果空 URL 过滤与 URL 去重
- `--source-type wechat|web|all` 过滤逻辑

## 参考

- smart3w: https://github.com/example/smart3w
- SearXNG: https://github.com/searxng/searxng
- scrapling: https://github.com/example/scrapling
