# 参与开发

欢迎通过 Issue 报告问题，通过 fork + Pull Request 提交改动。macOS 优化可以单独提交，无需同时完成 Windows 功能。

## Fork 与 PR

1. 在 GitHub fork 本仓库，clone 自己的 fork。
2. 从最新 `main` 创建分支，例如 `macos/audio-capture`。
3. 按 README 和 [macOS 说明](docs/macos.md)安装；修改后提交到自己的分支。
4. 向 `WYI1223/local-caption` 的 `main` 发起 PR，说明具体问题、改动和实际验证结果。

优先保持 `app/platform_support.py` 中的系统差异清晰；Windows WASAPI 后端在 `app/loopback_worker.py`，不要让 macOS 路径导入 Windows 专用依赖。新增 macOS 采集后端时应独立实现，再接到现有字幕与翻译流程。

## macOS 当前重点

- Apple Silicon 真机安装、Tk 窗口与麦克风权限。
- 原生系统声音采集，含权限拒绝、设备切换和无声状态。
- 开始后立即停止、正常停止时补齐尾部、退出时释放进程。
- 长时间字幕与翻译积压，以及 Metal 优化的质量/性能对比。

PR 请写明 macOS 版本、芯片、Python 版本、翻译模型和输入方式。通过真实入口验证“开始 → 字幕 → 停止 → 保存回读”，并区分纯逻辑测试、模拟输入、真实硬件测试。无法在另一系统验证时直说，不把未运行写成通过。

不加载模型的回归：

```bash
python -m unittest discover -s tests -p test_translation_flow.py
python -m unittest discover -s tests -p test_distribution.py
```

硬件及模型测试见 README；现有部分测试是 Windows 专用，不应直接作为 macOS 验收。修改平台边界时，尽量保留 Windows 行为，并在 PR 中标明需要维护者补测的部分。

## 提交内容

只提交源码、必要测试和文档。不提交模型、虚拟环境、私人录音、字幕、凭据或完整个人日志。复现问题优先用公开样例或人工构造的短文本；日志应只保留相关错误和版本信息。

新学到的可复用安装/排错方法更新到 `docs/verification.md` 或对应平台文档。模型和引擎仍遵守各自许可，新增来源需更新 `THIRD_PARTY.md` 与固定版本校验信息。
