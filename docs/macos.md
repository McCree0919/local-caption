# Apple Silicon macOS：实验性移植，待真机验收

已准备 arm64 原生引擎、安装脚本、窗口和进程管理适配。开发环境是 Windows，未在 Mac 上运行，不能称为可用性验收完成。当前仅提供麦克风/示例入口，**未实现 macOS 原生系统声音采集**；菜单不显示 Windows WASAPI 选项。Intel 和 Rosetta Python 不在此版本支持范围。

安装原生 arm64 Python 3.11.8+（3.11 系列，带 Tkinter）。已有 arm64 Miniconda 可新建 Python 3.11 环境；不要在 Rosetta 终端用 x86 Python。进入源码目录运行：

```bash
python3 -c 'import platform, tkinter; print(platform.machine())'
bash setup.command
bash start.command
```

第一行应输出 arm64。双击启动前可执行 `chmod +x setup.command start.command`。通过 bash 启动无需依赖压缩包的可执行权限。若 Tk 无法导入，先安装含 Tk 的 Python 环境，不要跳过自检。

默认 Hy-MT2；`bash setup.command --backend both` 额外安装 NLLB。两个模型都先使用 CPU，未启用 Metal 优化。NeMo 使用 v0.1.0 macOS aarch64 CPU 包，llama.cpp 使用 b11005 macOS arm64 包；下载摘要与 GitHub release digest 核对，归档结构已在 Windows 检查。

首次使用麦克风时由使用者按 macOS 系统提示授权；本项目不修改权限设置。如果界面启动但没声音，请在系统设置确认启动该程序的终端/Python 的麦克风访问权限。

系统声音需另做 macOS 采集后端。目前不能直接勾选系统声音；第三方虚拟音频设备可能作为默认输入供麦克风模式使用，但本项目尚未验证，不提供已可用保证。

朋友验收时请记录：macOS/Python 版本、芯片、setup 和 doctor 的结果、示例字幕及保存、麦克风开始/停止（包括立即停止）、关闭后进程释放。不要把私人录音或完整字幕提交到公开 issue。若系统阻止打开下载程序，保留完整提示供排查，不要求关闭系统安全保护。
