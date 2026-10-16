#!/usr/bin/env bash
# ==============================================================================
# LiveSnip - 银河麒麟 (Kylin OS V10 / Debian / Ubuntu) 一键安装部署脚本
# ==============================================================================

set -e

# 确保以 root / sudo 权限运行系统级安装
if [ "$EUID" -ne 0 ]; then
    echo "============================================================"
    echo "[提示] 安装到银河麒麟系统菜单需要管理权限，请使用 sudo 运行："
    echo "       sudo ./install_kylin.sh"
    echo "============================================================"
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/livesnip"
BIN_LINK="/usr/local/bin/livesnip"
DESKTOP_FILE="/usr/share/applications/livesnip.desktop"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
PIXMAPS_DIR="/usr/share/pixmaps"

echo "============================================================"
echo "    正在将 LiveSnip 安装到银河麒麟 (Kylin Linux) 系统..."
echo "============================================================"

# 1. 安装基础系统库 (X11 / Qt 运行环境)
if command -v apt-get &>/dev/null; then
    echo "[1/5] 检查并安装系统级运行时依赖库..."
    apt-get update -qq || true
    apt-get install -y -qq python3 python3-pip libgl1-mesa-glx libegl1 \
        libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
        libxcb-xinerama0 libxcb-xfixes0 libx11-xcb1 || true
fi

# 2. 复制程序文件至 /opt/livesnip
echo "[2/5] 部署应用文件至 ${INSTALL_DIR} ..."
mkdir -p "${INSTALL_DIR}"
cp -rf "${SRC_DIR}/"* "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/run_kylin.sh"

# 3. 安装桌面图标与菜单项
echo "[3/5] 注册系统图标与开始菜单快捷方式..."
mkdir -p "${ICON_DIR}" "${PIXMAPS_DIR}"
if [ -f "${SRC_DIR}/app.png" ]; then
    cp -f "${SRC_DIR}/app.png" "${ICON_DIR}/livesnip.png"
    cp -f "${SRC_DIR}/app.png" "${PIXMAPS_DIR}/livesnip.png"
fi

if [ -f "${SRC_DIR}/livesnip.desktop" ]; then
    cp -f "${SRC_DIR}/livesnip.desktop" "${DESKTOP_FILE}"
    chmod 644 "${DESKTOP_FILE}"
fi

# 4. 创建系统命令软链接
echo "[4/5] 创建命令行启动软链接 ${BIN_LINK} ..."
ln -sf "${INSTALL_DIR}/run_kylin.sh" "${BIN_LINK}"

# 5. 安装 Python 核心依赖
echo "[5/5] 配置 Python 依赖组件 (PySide6, RapidOCR, Pynput)..."
pip3 install -r "${INSTALL_DIR}/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple || {
    echo "[提示] pip3 安装部分包失败，如果已使用系统包或虚拟环境可忽略此提示。"
}

# 刷新桌面与图标数据库
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi

echo "============================================================"
echo "🎉 LiveSnip 银河麒麟系统安装完成！"
echo ""
echo "启动方式："
echo "  1. 银河麒麟【开始菜单】->【工具软件】/【常用应用】-> 点击【LiveSnip 截图贴图】"
echo "  2. 在任何终端中直接输入：livesnip"
echo "  3. 全局默认快捷键：【F1】屏幕截图  |  【F3】贴图悬浮"
echo "============================================================"
