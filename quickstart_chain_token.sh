#!/bin/bash
# 快速启动脚本 - 链和币种管理系统

set -e

echo "========================================="
echo "链和币种管理系统 - 快速启动"
echo "========================================="
echo ""

# 检查当前目录
if [ ! -f "pyproject.toml" ]; then
    echo "❌ 错误: 请在项目根目录运行此脚本"
    exit 1
fi

echo "步骤 1/3: 运行数据库迁移..."
uv run alembic upgrade head
echo "✓ 数据库迁移完成"
echo ""

echo "步骤 2/3: 初始化预设数据..."
uv run python -m src.scripts.init_chains_tokens
echo "✓ 数据初始化完成"
echo ""

echo "步骤 3/3: 启动服务..."
echo ""
echo "========================================="
echo "服务正在启动..."
echo "API 文档: http://localhost:8000/docs"
echo "========================================="
echo ""

uv run fastapi dev src/main.py
