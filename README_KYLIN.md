# LiveSnip 银河麒麟系统 (Kylin Linux OS) 适配与安装运行指南

LiveSnip 已针对 **银河麒麟操作系统 (Kylin OS V10 SP1/SP2/SP3 及 openKylin)** 完成系统适配，完全消除对 Windows 底层 API (`ctypes.windll`, `user32`, `kernel32`, `win32gui`) 的硬依赖，深度集成 UKUI 桌面环境与 X11/XWayland 图形栈。

---

## 一、适配银河麒麟特性

1. **跨平台原生适配**：
   - 全面解耦 Windows API，在 Linux 环境下自动无缝切换至 Qt 原生事件流与 Linux 标准机制。
   - 贴图穿透模式：采用 Qt 原生 `WA_TransparentForMouseEvents` 实现画板描图与无障碍鼠标穿透，无需依赖 Win32 分层窗口扩展样式。
2. **全局热键支持**：
   - 支持通过 `pynput` 监听 X11 全局快捷键（**F1 截图**、**F3 贴图**）。
   - 自动回退保护：若桌面环境安全限制全局监听，系统托盘图标支持一键唤起截图与贴图，绝不崩溃。
3. **UKUI 系统集成**：
   - 提供标准 FreeDesktop 规范的 `livesnip.desktop` 与高清矢量图标，自动注册进银河麒麟【开始菜单】->【常用应用】/【工具软件】。

---

## 二、使用方式

### 方式一：一键绿色运行（推荐，免安装）

直接解压便携包并运行启动脚本：
```bash
# 1. 解压便携包
tar -xzvf LiveSnip_v1.1.0_Linux_Kylin.tar.gz
cd LiveSnip_v1.1.0_Linux_Kylin

# 2. 赋予执行权限并一键启动
chmod +x run_kylin.sh
./run_kylin.sh
```
> `run_kylin.sh` 脚本会自动检测 Python3 运行环境并自动补齐缺失依赖。

---

### 方式二：一键安装进系统开始菜单与桌面

若希望像原生软件一样在银河麒麟系统的开始菜单和托盘中常驻：
```bash
cd LiveSnip_v1.1.0_Linux_Kylin

# 以管理员权限执行安装脚本
sudo ./install_kylin.sh
```
安装后：
- 在银河麒麟【开始菜单】中直接点击 **LiveSnip 截图贴图** 启动。
- 在任何终端中输入 `livesnip` 即可启动。
- 卸载非常干净：`sudo rm -rf /opt/livesnip /usr/share/applications/livesnip.desktop /usr/local/bin/livesnip`。

---

### 方式三：Debian / 银河麒麟 `.deb` 标准安装包

#### 1. 直接安装预编译好的 DEB 包：
```bash
sudo dpkg -i livesnip_1.1.0_amd64.deb
# 若系统提示缺少依赖库，一键自动修复补全：
sudo apt-get install -f -y
```

#### 2. 自行打包 DEB 包：
如果您需要针对特定架构（如飞腾 Phytium、鲲鹏 ARM64 等信创硬件）进行打包，在终端直接运行：
```bash
chmod +x build_deb.sh
./build_deb.sh
```
脚本将自动读取当前机器架构，一键生成适配当前 CPU 架构的 `livesnip_1.1.0_<架构>.deb`。

---

## 三、快捷键与操作速查

| 操作 | 快捷键 / 手势 | 说明 |
| :--- | :--- | :--- |
| **屏幕截图** | **F1** 或 点击托盘图标 | 启动全屏截取，支持窗口自动吸附侦测 |
| **贴图置顶** | **F3** 或 鼠标中键双击托盘 | 将剪贴板中的图片悬浮置顶在桌面 |
| **快速复制** | **Ctrl + C** | 框选截图区域后，直接按 Ctrl+C 完成复制并关闭 |
| **原地选词** | 鼠标左键拖拽划选 | 贴图悬浮后，自动执行高精度离线 OCR，可直接划词复制 |
| **智能即时翻译** | 点击工具栏【翻译】 | 自动判定源语种并即时双语对照呈现，毫秒级响应 |
| **矢量标注画板** | 截图时工具栏 / 贴图按【空格】 | 矩形、椭圆、箭头、画笔、马赛克、文字等 |
| **鼠标穿透 (描图)** | **F4** | 贴图可被鼠标穿透，辅助画师和工程师抄图/临摹 |
| **调整透明度** | 贴图上滑动鼠标滚轮 | 自由调节贴图透明度 (20% ~ 100%) |

---

## 四、常见问题排查 (FAQ)

1. **银河麒麟 Wayland 环境下截屏提示或黑屏？**
   - 银河麒麟 V10 桌面默认基于 X11，若切换到了纯 Wayland 会话，Qt 的截图接口需要 XWayland 桥接支持。
   - `run_kylin.sh` 已默认设置 `QT_QPA_PLATFORM=xcb`，确保在各类银河麒麟环境下均能获得最稳定的全屏截屏能力。
2. **快捷键无法触发？**
   - 部分银河麒麟版本可能将 F1 预分配给“系统帮助中心”。您可以随时通过系统托盘的 LiveSnip 小图标，左键点击直接启动截图，或者在“系统设置 -> 快捷键”中关闭系统默认的 F1 帮助占用。
3. **离线 OCR 引擎说明**：
   - LiveSnip 采用轻量高性能 `RapidOCR`，首次运行若未附带模型权重，会自动缓存至本地，后续断网环境完全 100% 离线可用。
