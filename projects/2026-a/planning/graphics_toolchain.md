# 本机绘图工具入口

本文件供项目内部调用与维护使用，不属于队友讲解稿、论文附录或官方提交包。2026-09-12 按用户要求补齐工具，并按随后明确指令卸载了商店版 Inkscape。

## 已接通的工具

| 职责 | 工具及状态 |
|---|---|
| 数值图、坐标轴、等值线 | 项目 Python / Matplotlib，继续读取既有计算数据 |
| 矢量母版、精细拼版、PNG/PDF 导出 | 官方便携版 Inkscape 1.4.4；版本、中文、公式、渐变、裁切和导出已实测 |
| 三维几何与渲染 | 现有 Three.js 0.180.0 + Node 24.19.0 + Playwright 1.62.1 + Edge 152.0.4191.66，已渲染 1600×1200 程序化圆柱，页面错误为零 |
| 公式排版、PDF 页面检查 | 本机 XeLaTeX 与 Poppler，沿用已有路径 |
| 备用数值与绘图软件 | 找到 MATLAB R2025b 主程序；本次没有验证其许可证或绘图运行，不标记为已接通 |

统一配置为 [graphics_toolchain.json](graphics_toolchain.json)，统一 Inkscape 调用入口为 [graphics_tools.py](../scripts/graphics_tools.py)。代码会优先使用配置中的便携版，也允许通过进程环境变量 `INKSCAPE_PATH` 指定新的 `inkscape.com` 路径；不依赖全局 PATH。

便携版主程序位置：`<未收录-下载缓存>/graphics_tools/inkscape-1.4.4/inkscape/bin/inkscape.exe`；自动化使用同目录 `inkscape.com`。配置、近期文件与缓存重定向到项目 `<未收录-下载缓存>/graphics_tools/`，不会要求修改用户全局设置。该目录是可重建的工具缓存，不进入正式材料包。

## 调用方式

在项目根目录的 PowerShell 中检查工具：

```powershell
.venv/Scripts/python.exe -B scripts/graphics_tools.py doctor
```

从 SVG 母版导出，下面的输入和输出路径按实际图件替换：

```powershell
.venv/Scripts/python.exe -B scripts/graphics_tools.py export "输入母版.svg" -o "阅读图.png" --dpi 300
.venv/Scripts/python.exe -B scripts/graphics_tools.py export "输入母版.svg" -o "论文图.pdf"
```

SVG 原文件保持可编辑。PDF 若要消除字体依赖，可加 `--text-to-path`，但这样 PDF 中的文字不能按文字检索；不应将转路径 PDF 反向作为编辑母版。已有输出默认不覆盖，确需更新时加 `--overwrite`。单次导出设有 120 秒超时，失败会保留原有目标文件。

Windows 访问权限修复：临时导出目录会限制访问，直接将其中的文件移动到最终位置会保留该限制，导致桌面软件无法读取。现改为在目标父目录独占创建普通暂存文件，仅复制完整字节，关闭并刷新后原子替换目标；由目标目录提供正常的继承权限。导出检查除格式与渲染外，还需核对最终文件的普通用户读取权限。该处理不修改全局权限，也不改变图件内容。

导出验证覆盖了：1890×827 像素的 300 dpi PNG、单页 PDF、中文与上下标文本提取、文字转路径 PDF，以及本项目已有物性曲面 SVG 的实际 PDF 导出。测试图和 PDF 只放在系统临时目录，未加入正式选图。该检查证明工具可调用，不代表先前样图的构图质量已经达标。

## 来源与恢复

Inkscape 来自[官方便携包](https://inkscape.org/gallery/item/59503/inkscape-1.4.4_2026-05-05_dcaf3e7-x64_mHK170m.7z)，最终下载主机为 `media.inkscape.org`。压缩包 110359970 字节，下载文件 SHA-256 为 `c4dbd64a92628abe7d7316c43f9325396e4d48417866027ee3d993d4f5b54c6a`。解压前检查了全部 12955 个条目的路径，实际版本输出为 `Inkscape 1.4.4 (dcaf3e7, 2026-05-05)`。

若工具缓存被清理，按配置中的官方地址重新取得压缩包，核对上述下载身份后解压至 `<未收录-下载缓存>/graphics_tools/inkscape-1.4.4/`，使内部路径仍为 `inkscape/bin/inkscape.com`，再运行 `doctor`。软件版本变化时重新核对导出效果，不直接复用旧验证记录。

原商店版通过桌面快捷方式定位，包名为 `25415Inkscape.Inkscape_1.4.40.0_x64__9waqn51p1ttv2`；当前自动化环境直接调用失败。便携版导出成功后，按用户明确要求使用 Windows `Remove-AppxPackage` 正常卸载。复查当前用户同名包为零，原桌面与开始菜单快捷方式均已自动移除；没有手工修改 WindowsApps 权限或删除系统包目录。

## 后续绘图的工具分工

数值曲线、等值线和色场由真实数据生成；SVG 负责组合图的面板比例、字体、标注和留白；确有空间几何需求时复用已有 Three.js 渲染链。当前工具已经能支持这三层，不需要先安装 PyVista 或 Blender 才开始改图。正式图仍须按项目 skill 完成内容与实际页面视觉审阅。
