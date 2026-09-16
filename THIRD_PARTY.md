# 第三方组件与模型

源码包不包含第三方模型和引擎二进制。安装器按 `assets.json` 从指定来源下载，第三方组件继续适用其各自许可证。不要把应用源码许可当成模型许可。

| 组件 | 固定版本 / 来源 | 许可说明 |
|---|---|---|
| NeMo-Speech.cpp | [NVIDIA v0.1.0](https://github.com/NVIDIA/NeMo-Speech.cpp/releases/tag/v0.1.0) Windows x64 CPU | 查看发布包 `share/licenses`，安装保留整个归档 |
| Nemotron Speech EN 0.6B Q8 | [NVIDIA 模型](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b)，revision ebe59e5a817142986528bbbee5dba8db7b38ed50 | NVIDIA Open Model License |
| Hy-MT2 1.8B Q4_K_M | [腾讯 GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF)，revision a0c709d9fac510f2c807aa3af52872340dc37a4a | Apache-2.0 |
| llama.cpp | [b11005](https://github.com/ggml-org/llama.cpp/releases/tag/b11005) Windows CPU x64 | MIT，保留归档中的许可文件 |
| NLLB 200 distilled 600M | [Meta 原模型](https://huggingface.co/facebook/nllb-200-distilled-600M)，[OpenNMT 论坛转换教程](https://forum.opennmt.net/t/nllb-200-with-ctranslate2/5090)中的预转换文件 | CC-BY-NC-4.0，仅作为可选模型 |
| JFK 演讲示例 | NeMo-Speech.cpp v0.1.0 `test_files/asr/wav/test/jfk.wav` | 仅安装时从上游获取，未将课堂录音作为示例 |

Python 依赖见 `requirements.txt` 及安装后的各包许可信息。核心源码许可证见 `LICENSE`，不覆盖第三方组件。

校验来源：两个引擎 ZIP 与当时发布方摘要核对；ASR GGUF 与已验证缓存一致；Hy 模型哈希与此前镜像元数据一致，不能声称独立官方认证；NLLB 和配套 tokenizer 哈希标识本地验证过的下载，没有发布者独立摘要。归档内文件摘要来自这些固定归档。哈希用于确保后续安装字节与验证版本一致，不证明模型质量。
