#!/usr/bin/env bash
# ==============================================================================
# LiveSnip - 银河麒麟 (Kylin Linux) 专属一键启动脚本
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 检测 Python 3
if ! command -v python3 &>/dev/null; then
    echo "[LiveSnip 错误] 未找到 python3，请在终端执行：sudo apt update && sudo apt install -y python3 python3-pip"
    exit 1
fi

# 2. 优先使用本地虚拟环境 (如果存在)
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# 3. 兼容银河麒麟桌面 (UKUI / X11 / Wayland)
# 默认使用 xcb 确保屏幕截取、全局坐标与全局热键稳定工作
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export PYTHONUNBUFFERED=1

# 4. 检查核心依赖库，缺失时给出友好引导
if ! python3 -c "import PySide6" 2>/dev/null; then
    echo "============================================================"
    echo "【首次运行提示】检测到 Python 依赖未安装，准备自动安装..."
    echo "============================================================"
    python3 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || {
        echo "【提示】若 pip 权限受限，推荐运行：sudo ./install_kylin.sh"
    }
fi

# 5. 启动主程序
echo "[LiveSnip] 启动成功！快捷键：F1 截图 | F3 贴图 (也支持点击托盘图标操作)"
exec python3 main.py "$@"
