#!/bin/bash
#================================================================
# Smart3W Wrapper - fetch.sh
#
# 封装 smart3w 的 fetch.sh，保留原有用法，同时支持本项目的扩展
# 
# 用法：
#   ./scripts/fetch.sh search "关键词" [数量]
#   ./scripts/fetch.sh smart "URL" [输出文件]
#   ./scripts/fetch.sh get "URL" [输出文件]
#   ./scripts/fetch.sh stealthy "URL" [输出文件]
#   ./scripts/fetch.sh fetch "URL" [输出文件]  # 动态页面
#
# 环境变量：
#   SEARXNG_INSTANCE  SearXNG 实例地址
#   SMART3W_PATH      smart3w 安装路径（可选，用于调用原生实现）
#================================================================

set -e

# 配置
SEARXNG_INSTANCE="${SEARXNG_INSTANCE:-https://searxng.hqgg.top:59826}"
SMART3W_PATH="${SMART3W_PATH:-}"  # 如果有 smart3w 安装路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_deps() {
    local missing=()

    command -v curl >/dev/null 2>&1 || missing+=(curl)
    command -v python3 >/dev/null 2>&1 || missing+=(python3)

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "缺少依赖: ${missing[*]}"
        log_info "安装命令: apt install ${missing[*]}"
        exit 1
    fi
}

# SearXNG 搜索
do_search() {
    local query="$1"
    local limit="${2:-10}"

    log_info "SearXNG 搜索: $query"

    local response
    response=$(curl -s -G "${SEARXNG_INSTANCE}/search" \
        --data-urlencode "q=${query}" \
        --data-urlencode "format=json" \
        --data-urlencode "engines=" \
        --data-urlencode "categories=general" \
        --max-time 30)

    if [ -z "$response" ]; then
        log_error "搜索请求失败"
        return 1
    fi

    # 格式化输出
    echo "$response" | python3 -c "
import sys, json

try:
    data = json.load(sys.stdin)
    results = data.get('results', [])
    print(f'找到 {len(results)} 条结果:\n')
    for i, r in enumerate(results[:${limit}], 1):
        title = r.get('title', 'N/A')
        url = r.get('url', 'N/A')
        content = r.get('content', r.get('description', 'N/A'))[:150]
        print(f'{i}. {title}')
        print(f'   URL: {url}')
        print(f'   {content}...')
        print()
except Exception as e:
    print(f'解析失败: {e}')
    print(sys.stdin.read()[:500])
" 2>/dev/null || echo "$response"
}

# 智能抓取（默认）
do_smart() {
    local url="$1"
    local output="${2:-}"

    log_info "智能抓取: $url"

    # 调用 Python 实现
    python3 "${PROJECT_ROOT}/src/main.py" fetch "$url" --topic "quick-fetch" >/dev/null 2>&1 || true

    # 如果有 smart3w 原生脚本，优先使用
    if [ -n "$SMART3W_PATH" ] && [ -f "${SMART3W_PATH}/scripts/fetch.sh" ]; then
        "${SMART3W_PATH}/scripts/fetch.sh" smart "$url" "$output"
    else
        do_get "$url" "$output"
    fi
}

# 普通 HTTP 抓取
do_get() {
    local url="$1"
    local output="${2:-}"

    log_info "HTTP 抓取: $url"

    if [ -z "$output" ]; then
        # 输出到 stdout
        curl -s -L -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
            --max-time 30 "$url"
    else
        curl -s -L -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
            --max-time 30 "$url" -o "$output"
        log_info "已保存到: $output"
    fi
}

# 动态页面抓取（浏览器渲染）
do_fetch() {
    local url="$1"
    local output="${2:-}"

    log_warn "动态页面抓取需要 playwright/selenium，当前使用降级方案"

    if [ -z "$output" ]; then
        do_get "$url" ""
    else
        do_get "$url" "$output"
    fi
}

# stealthy 模式（绕过反爬）
do_stealthy() {
    local url="$1"
    local output="${2:-}"

    log_info "Stealthy 抓取: $url"

    # 调用 Python 实现
    if [ -n "$SMART3W_PATH" ] && [ -f "${SMART3W_PATH}/scripts/fetch.sh" ]; then
        "${SMART3W_PATH}/scripts/fetch.sh" stealthy "$url" "$output"
    else
        log_warn "stealthy 模式需要 smart3w 原生支持，使用降级方案"
        do_get "$url" "$output"
    fi
}

# 帮助信息
show_help() {
    cat << EOF
Research Tool - fetch.sh

用法:
    $0 search "关键词" [数量]     SearXNG 搜索
    $0 smart "URL" [输出文件]     智能抓取（自动选择最佳方式）
    $0 get "URL" [输出文件]      普通 HTTP 抓取
    $0 stealthy "URL" [输出文件]  绕过反爬抓取
    $0 fetch "URL" [输出文件]    动态页面抓取

环境变量:
    SEARXNG_INSTANCE  SearXNG 实例地址（默认: https://searxng.hqgg.top:59826）
    SMART3W_PATH      smart3w 安装路径（用于调用原生实现）

示例:
    $0 search "AVAS 低速提示音" 10
    $0 get "https://example.com" /tmp/page.html
    $0 smart "https://example.com/article" /tmp/article.md
EOF
}

# 主逻辑
main() {
    check_deps

    local command="${1:-}"

    case "$command" in
        search)
            do_search "${2:-}" "${3:-10}"
            ;;
        smart)
            do_smart "${2:-}" "${3:-}"
            ;;
        get)
            do_get "${2:-}" "${3:-}"
            ;;
        stealthy)
            do_stealthy "${2:-}" "${3:-}"
            ;;
        fetch)
            do_fetch "${2:-}" "${3:-}"
            ;;
        -h|--help|help)
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

main "$@"
