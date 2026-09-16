# 验证与维护记录

## 2026-09-16：从本机原型整理为独立仓库

范围：只复制应用、翻译适配器和回归测试源码。未复制私人课堂录音、转写、偏好、运行日志、Python 环境或本机快捷方式到源码包。原安装未修改。模型和运行时由安装器独立部署，不进入 Git 或分享 ZIP。

实际安装入口：Python 3.11.16 执行 `scripts/setup.py --backend both --from-existing <原安装>`，创建新 venv，pip 实际下载安装依赖；模型和 Windows 引擎使用之前已下载的固定资产，经哈希验证后复制。该过程验证了从本地缓存安装，不等同于验证朋友网络上的全新模型下载。安装后的 `scripts/doctor.py --verify` 对两种模型及原生资源全量哈希检查通过。

Windows：8 项切句/时间线/积压逻辑测试、2 项分发边界测试通过；真实 ASR worker 在 0/0.1/0.5 秒停止均正常退出，耗时 0.297/0.078/0.031 秒。实际 `start.cmd` 启动独立 venv 的 GUI，点击示例，走本地 WAV → 原生 ASR → Hy-MT2 worker → 两段中英字幕 → 自动保存；回读 TXT 两段完整且没有“未完成”标记。原型已知的 JFK 否定误译仍出现，集成成功不代表翻译准确。独立环境中 `test_stream_translation.py --unknown` 在 4.66 秒完成，验证 NLLB 异常保留英文后继续翻译下一句；该测试模拟 ASR 输入边界，不代表硬件采音验收。新仓库本轮没有重跑真实系统声音硬件测试，旧原型的两分钟数据仅作背景。

macOS：从 GitHub b11005 / v0.1.0 下载 arm64 归档，SHA-256 与 release digest 一致，检查了真实归档布局和文件摘要。NeMo 包有 `nemo-speech/` 顶层，llama 包有 `llama-b11005/` 顶层，必须保留对应路径及动态库布局。已准备 POSIX 进程信号和 shell 启动入口，但没有 Mac 真机或 macOS CI 执行证据；系统声音后端未实现。不要将静态检查记录为 Mac 可用性验收。

## 可复用经验

- 快速停止需区分 ASR 加载中和已开始 listening；加载中终止，已开始则先发中断让引擎 flush。Windows worker 使用专属隐藏控制台；不能广播给 GUI 或其他终端。
- Windows venv 常有启动器及真实 Python 两级进程；关闭 stdin 让真实 worker 自行退出，超时清理专属进程树。macOS 翻译 worker 建独立进程组，超时时按组清理。
- 旧窗口卡死曾由 `Text.see` 引发；当前合并渲染、用比例滚动、限制可见字符数，完整字幕单独保留。不要只因模型进程还在就判断 UI 正常。
- Windows 系统声音 worker 的 stdin 停止检查用 PeekNamedPipe；此前阻塞读线程与 NumPy 导入在原机器上出现过死锁。该经验只在 Windows 路径得到复现和验证。
- 同一快照同时改词和新增文字时，新增词必须使用新时间；否则最早待译年龄虚高。相关逻辑回归见 `test_translation_flow.py`。
- 模型 `<unk>`、循环生成和正常排队是不同问题；保留英文降级可以让队列清空，但不能计为中文翻译成功。
- 分享用 `scripts/package_source.py` 的白名单，不要直接压缩整个工作目录。源码包不带 venv；朋友安装后再运行。

## 后续验收

另一台 Windows 完整联网安装、连续 30–60 分钟播放、设备切换和断开；Apple Silicon 真机安装/权限/窗口/麦克风/退出；macOS 系统声音后端。首轮 overlapping 固定样本 A/B 见 [实验记录](overlap-experiment.md)：前文泄漏没有触发输出保护，默认仍关闭；需进一步验证源范围回写与有界重译方案。
