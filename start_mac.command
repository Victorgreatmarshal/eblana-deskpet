#!/bin/bash
# 在 macOS 上从源码运行：双击这个文件即可（首次运行会自动准备环境）
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "没有找到 python3。请先安装 Python 3.10 或更新版本：https://www.python.org/downloads/"
  read -r -n 1 -p "按任意键退出…"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "首次运行，正在创建虚拟环境并安装依赖，大约需要一两分钟…"
  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt || {
    echo "依赖安装失败，请检查网络后重试。"
    read -r -n 1 -p "按任意键退出…"
    exit 1
  }
fi

./.venv/bin/python main.py
