# Local Caption · 本地悬浮字幕

在 Windows 上把英语麦克风或系统声音转成英文字幕，并在本机翻译为简体中文。紧凑半透明置顶窗口、带时间戳的中英字幕、本地 TXT 保存、实时积压提示，支持 Hy-MT2 和 NLLB 对比。

当前是可安装的源码试用版，不是免安装 EXE。Windows 10/11 x64、CPU 为当前验证目标；另有 [Apple Silicon macOS 实验移植说明](docs/macos.md)，已完成单机安装与示例流程验证，真实麦克风仍待验证，且未实现 macOS 系统声音采集。Linux、Windows ARM 和整堂课连续运行尚未验证。

## 安装

准备 **Python 3.11 64 位（含 Tkinter）**。已有 Miniconda 可以在 Anaconda Prompt 中运行：

```bat
conda create -n local-caption python=3.11
conda activate local-caption
cd /d "你的目录\local-caption"
setup.cmd
```

安装程序仅创建项目内 `translation/.venv`，安装固定版本依赖，并下载校验固定版本模型和运行时。默认安装 Hy-MT2；不要求 NVIDIA 显卡、PyTorch 或虚拟声卡。模型及引擎约下载 1.9 GB，保留下载缓存，建议预留至少 6 GB 磁盘。16 GB 内存是目前验证机器的配置，不是已验证的最低配置。

可选安装 NLLB 或两个模型：

```bat
setup.cmd --backend nllb
setup.cmd --backend both
```

NLLB 是可选的非商业模型，先看 [第三方许可](THIRD_PARTY.md)。未安装模型会在菜单中禁用。

网络断开时重新运行同一命令，下载会尝试续传；完成后核对 SHA-256。Hugging Face 直连不可用时，可自行选择 HTTPS 镜像，例如通过 `--hf-endpoint https://你的镜像域名` 指定；程序不会悄悄切换下载来源。

## 使用

双击 **start.cmd**，无需再次激活 Conda。启动前检查依赖和资源；失败信息留在控制台。双击 **doctor.cmd** 自检，`doctor.cmd --verify` 额外核对所有资源哈希。

1. 菜单 `···` 选择“麦克风”或“系统声音”，再点击“开始”。系统声音采集默认扬声器/耳机的混音，包含该设备上的所有应用声音。
2. 点击“停止”结束采集并处理末尾。字幕和译文自动保存到 `transcripts`；“保存”可另存为，“复制”可复制中英全文。

“自动保存字幕（不含录音）”只保存识别文字和译文。已完成的识别段会累计保留，实时修订只更新当前段；窗口为节省显示开销只展示最近部分，TXT 保存完整会话文字。旧版本已经被覆盖且没有备份的内容，升级后不能自动恢复。

Windows 可在 ··· 菜单独立勾选“保存原始音频（下次开始生效）”，默认关闭，适用于麦克风和系统声音。它保存增强及单声道混音之前的设备音频，以设备采样率、原声道数转换为 PCM16 WAV，和字幕同名放在 `transcripts`。录制中是 `.partial.wav`，停止并完成写盘后改成 `.wav`；字幕末尾也会显示音频路径。该选项独立于字幕自动保存，不会补回开启前或软件停止采集后的音频；不是原始浮点采样的无损副本。异常中断可能留下 `.partial.wav`，应保留并检查，不能直接认定完整。48 kHz 双声道约 11.5 MB/分钟。macOS 音频保存暂未接入。
3. 菜单切换翻译模型；旧模型结果会另存，新模型重新翻译当前文本。冷启动需等待模型加载。
4. 字幕积压时，早期片段可能保留英文并标为“待补译”。停止后可选择“补译待译片段”。翻译异常也会明确保留英文。
5. 拖动工具栏空白移动窗口，右下角调整大小；菜单设置置顶和透明度。透明度作用于整个窗口，包括文字。

系统声音依赖默认输出设备；更换耳机或默认设备后停止再开始。没有识别时先确认正确输入、播放器正在发声，并在 Windows 自行检查麦克风权限。运行中不上传声音或文字；首次安装需要联网下载。Hy-MT2 服务器只监听本机回环地址，退出时释放。

会话 TXT、系统声音指标和偏好保存在本目录。请放在有写权限的普通文件夹。移动目录、重装 Python 或发给朋友时，重新运行 setup；不要复制虚拟环境。分享使用 `scripts/package_source.py`，它只打包白名单源码，不含模型、字幕、日志、偏好或录音。

## 当前效果与边界

### 开发机实测

2026-09-16，**Core Ultra 5 125H（14 核 / 18 线程）、16 GB 内存、Windows 11**；全程 CPU 推理，翻译 4 线程。

| 用途 / 模型 | 主权重大小 | 本机速度（翻译为热运行平均 / 中位数） |
|---|---:|---:|
| 识别：Nemotron EN 0.6B Q8_0 | 667 MiB | 119.98 秒音频用时 60.92 秒，约 1.97 倍实时速度 |
| 翻译：Hy-MT2 1.8B Q4_K_M | 1081 MiB | 1.726 / 1.760 秒每段 |
| 翻译：NLLB 600M INT8 | 594 MiB | 0.576 / 0.617 秒每段 |

翻译统计为相同 21 段中排除首次加载后的 20 段；ASR 是另一轮文件转写，不能当成实时字幕延迟。

**正在运行的 Hy-MT2 + 麦克风会话，旁路观察约 121 秒：**

| 指标 | 本次观测 |
|---|---:|
| Hy-MT2 推理，20 次请求 | 平均 1.71 秒；P95 2.30 秒；最长 2.97 秒 |
| 最早未译文字等待 | 采样平均 10.94 秒；峰值 17.62 秒 |
| 待译词数 | 平均 18.9；峰值 33；结束时 16（仍在录音） |
| 新增延后补译 / 翻译异常 | 0 / 0 |
| 整套应用进程树工作集 | 平均 1.75 GiB；采样峰值 1.75 GiB |
| 整套应用私有提交内存 | 平均 4.79 GiB |
| 整套应用平均 CPU | 25.7%（整机 18 逻辑处理器满载为 100%） |

当时系统可用内存最低约 142 MiB，存在明显内存压力；工作集会受分页/内存回收影响，不能把 1.75 GiB 当成最低内存要求。等待包含断句和排队，不能与纯模型推理耗时混用。以上均为单机小样本，不保证其他硬件、语言或整堂课表现；尚无 Mac 实测。详见 [完整统计、测量口径和复现方式](docs/performance.md)。

英语识别使用 Nemotron Speech Streaming EN 0.6B Q8；Hy-MT2 1.8B Q4_K_M / llama.cpp CPU，NLLB 600M INT8 / CTranslate2 CPU，翻译默认 4 线程。只有英语识别和英语到简体中文经过本项目验证。

已有同一两分钟系统声音实测：Hy-MT2 待译峰值 31 词、最早等待 24.35 秒；NLLB 28 词、20.26 秒。两者停止后均清空；NLLB 有 3 段异常保留英文，Hy-MT2 为 0。不是准确率或长期稳定性保证，等待也不是纯推理耗时。

口语硬切片、术语、否定和 ASR 错字仍可能产生漏译/误译；近似时间戳不是逐字音频对齐。[首轮 overlapping 对照](docs/overlap-experiment.md)已运行，出现前文重复和额外开销，尚未作为正式功能启用。字幕不应作为需要逐字准确的唯一记录。

## 开发与验证

```bat
translation\.venv\Scripts\python.exe -m unittest discover -s tests -p test_translation_flow.py
translation\.venv\Scripts\python.exe tests\test_quick_stop.py
translation\.venv\Scripts\python.exe tests\test_stream_translation.py
translation\.venv\Scripts\python.exe tests\test_system_audio.py
```

最后一个会实际播放示例并采集系统声音；翻译集成测试需要 NLLB。测试生成的诊断和字幕不进入源码包。纯逻辑测试的 CI 不代表音频硬件验证。

[验证记录与维护经验](docs/verification.md) · [第三方许可与来源](THIRD_PARTY.md)

欢迎 [提交 Issue](https://github.com/WYI1223/local-caption/issues) 或 fork 后发起 PR，macOS 优化可单独提交。流程见 [贡献说明](CONTRIBUTING.md)。

后续：在另一台 Windows 机器验证安装；长时间回放与设备切换；overlapping 对照实验；再考虑免 Python 安装器、签名、升级与多系统支持。
