# Apple Silicon macOS：实验性移植

已准备 arm64 原生引擎、安装脚本、窗口和进程管理适配。原始开发环境是 Windows；一台 arm64 Mac 已完成安装与示例流程验证，记录见文末，真实麦克风和长期使用仍待验收。当前仅提供麦克风/示例入口，**未实现 macOS 原生系统声音采集**；菜单不显示 Windows WASAPI 选项。Intel 和 Rosetta Python 不在此版本支持范围。

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

## 本地安装验证记录（2026-09-16）

macOS 15.7.4、Apple M4、16 GiB 内存、arm64，使用 uv 下载的 CPython 3.11.15（Tk 9.0）和默认 Hy-MT2 后端。Python 保存在项目的 `.tools/python`，虚拟环境仍为 `translation/.venv`。

- 修复安装器在 POSIX 上默认复制 Python 可执行文件的问题：此 Python 发行版的副本找不到 `@rpath/libpython3.11.dylib`，改为创建符号链接后正常启动。Windows 保持原有复制方式。
- `setup.command` 重用已安装的项目 Python，避免再次安装时误用系统 Python 3.9。
- 完成固定依赖、模型和引擎下载，安装器的 `doctor.py --verify` 全部通过（core / hymt；未安装 NLLB）。
- 通过真实 Tk 窗口运行内置 JFK 示例：英语识别、两段中文输出、自动保存及保存内容回读成功，约 23.45 秒完成；退出后翻译 worker 已结束。该时间为一次完整流程耗时，不是实时延迟测量，也不代表译文准确率验收。
- 示例中仍出现了 JFK “ask not” 的否定误译；本次验证只确认流程完成，没有修复模型翻译质量问题。
- `test_translation_flow.py` 的 8 项和 `test_distribution.py` 的 2 项测试通过。

启动：双击 `start.command` 或运行 `bash start.command`。此轮没有测试真实麦克风权限、麦克风录音或长时间运行，macOS 系统声音采集仍未实现。
