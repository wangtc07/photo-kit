#!/usr/bin/env bash
# 取得腳本所在目錄
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 如果有虛擬環境，優先使用
if [ -d "$DIR/venv" ]; then
    source "$DIR/venv/bin/activate"
fi

# 執行啟動器
python3 "$DIR/run.py"
