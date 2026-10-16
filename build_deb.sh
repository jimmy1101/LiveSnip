#!/usr/bin/env bash
# ==============================================================================
# LiveSnip - 银河麒麟 / Debian / Ubuntu .deb 安装包构建脚本
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.1.0"
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
PKG_NAME="livesnip_${VERSION}_${ARCH}"
BUILD_ROOT="${SCRIPT_DIR}/build_deb_tmp/${PKG_NAME}"

echo "============================================================"
echo "    正在构建 LiveSnip ${VERSION} (${ARCH}) DEB 安装包..."
echo "============================================================"

# 清理旧构建目录
rm -rf "${SCRIPT_DIR}/build_deb_tmp"
mkdir -p "${BUILD_ROOT}/DEBIAN"
mkdir -p "${BUILD_ROOT}/opt/livesnip"
mkdir -p "${BUILD_ROOT}/usr/bin"
mkdir -p "${BUILD_ROOT}/usr/share/applications"
mkdir -p "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${BUILD_ROOT}/usr/share/pixmaps"

# 1. 写入 control 文件
cat <<EOF > "${BUILD_ROOT}/DEBIAN/control"
Package: livesnip
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: LiveSnip Team <https://github.com/jimmy1101/LiveSnip>
Depends: python3 (>= 3.8), python3-pip, libgl1-mesa-glx, libegl1, libxkbcommon-x11-0, libxcb-xinerama0, libxcb-cursor0
Description: LiveSnip - 现代化截图、贴图悬浮与划选OCR翻译工具
 LiveSnip 是一款轻量、丝滑且开箱即用的截图贴图工具。
 深度适配银河麒麟 (Kylin OS)、UOS 统信及各主流 Linux 桌面环境。
 支持 F1 屏幕截图、F3 贴图悬浮置顶、原地划选OCR识别、离线与在线即时翻译、矢量画板标注等核心功能。
EOF

# 2. 写入 postinst (安装后钩子)
cat <<'EOF' > "${BUILD_ROOT}/DEBIAN/postinst"
#!/bin/bash
set -e
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postinst"

# 3. 写入 postrm (卸载后钩子)
cat <<'EOF' > "${BUILD_ROOT}/DEBIAN/postrm"
#!/bin/bash
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -f /usr/bin/livesnip
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache -q /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "${BUILD_ROOT}/DEBIAN/postrm"

# 4. 拷贝程序代码与资源
echo "[1/4] 复制核心代码与资源..."
cp -r "${SCRIPT_DIR}/main.py" "${BUILD_ROOT}/opt/livesnip/"
cp -r "${SCRIPT_DIR}/core" "${BUILD_ROOT}/opt/livesnip/"
cp -r "${SCRIPT_DIR}/ui" "${BUILD_ROOT}/opt/livesnip/"
cp -r "${SCRIPT_DIR}/requirements.txt" "${BUILD_ROOT}/opt/livesnip/"
cp -r "${SCRIPT_DIR}/run_kylin.sh" "${BUILD_ROOT}/opt/livesnip/"
chmod +x "${BUILD_ROOT}/opt/livesnip/run_kylin.sh"

# 如果存在 PyInstaller 构建好的二进制 dist/LiveSnip/LiveSnip，则一同拷贝
if [ -d "${SCRIPT_DIR}/dist/LiveSnip" ]; then
    echo "[可选] 检测到 PyInstaller Linux 独立编译产物，打包独立可执行文件..."
    cp -r "${SCRIPT_DIR}/dist/LiveSnip/"* "${BUILD_ROOT}/opt/livesnip/"
fi

# 5. 桌面快捷方式与图标
echo "[2/4] 配置桌面入口与图标..."
cp -f "${SCRIPT_DIR}/livesnip.desktop" "${BUILD_ROOT}/usr/share/applications/"
if [ -f "${SCRIPT_DIR}/app.png" ]; then
    cp -f "${SCRIPT_DIR}/app.png" "${BUILD_ROOT}/usr/share/icons/hicolor/256x256/apps/livesnip.png"
    cp -f "${SCRIPT_DIR}/app.png" "${BUILD_ROOT}/usr/share/pixmaps/livesnip.png"
fi

# 6. /usr/bin/livesnip 软链接
echo "[3/4] 创建命令调用入口..."
ln -sf /opt/livesnip/run_kylin.sh "${BUILD_ROOT}/usr/bin/livesnip"

# 7. 打包 DEB
echo "[4/4] 正在调用 dpkg-deb 打包..."
dpkg-deb --build --root-owner-group "${BUILD_ROOT}" "${SCRIPT_DIR}/${PKG_NAME}.deb"

# 清理临时目录
rm -rf "${SCRIPT_DIR}/build_deb_tmp"

echo "============================================================"
echo "🎉 DEB 安装包构建成功: ${PKG_NAME}.deb"
echo "在银河麒麟系统中安装方法："
echo "   sudo dpkg -i ${PKG_NAME}.deb"
echo "   sudo apt-get install -f  # 若缺少依赖自动补全"
echo "============================================================"
