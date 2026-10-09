# 第三方软件、模型与分发说明

本项目的 Windows 完整运行包包含独立的 Python 解释器、FFmpeg 工具、Python 依赖和本地语音识别模型。各组件的版权归原作者所有，各自的原始许可证独立适用。本文是来源与分发义务说明；随包保存的原始 LICENSE、NOTICE 和 THIRD-PARTY-PROGRAMS 文件保留完整授权条款。

## Python

Python 由 Python Software Foundation 等原始版权人提供。官方授权允许分发源代码和二进制，但要求保留 PSF License Agreement 和版权声明；修改 Python 时还应附修改摘要。[Python 官方许可证](https://docs.python.org/3.13/license.html)

完整包保留官方嵌入式 Python 发行版的 `runtime/python/LICENSE.txt`。解释器二进制未修改；本项目的便携模块搜索路径配置与应用启动脚本是本项目的打包配置。Python 所包含的第三方组件仍适用其附属许可。

## FFmpeg 及 PyAV 的 FFmpeg 库

FFmpeg 的基础授权为 LGPL；启用 GPL 组件会使该 FFmpeg 构建适用 GPL。本地原始 BtbN 构建 `N-127233-g452820cba6-20261007` 启用了 `--enable-gpl --enable-version3`，并包含 x264/x265 等静态依赖，因此不能按普通 LGPL 构建处理。[FFmpeg 官方法律说明](https://ffmpeg.org/legal.html)、[BtbN 构建变体说明](https://github.com/BtbN/FFmpeg-Builds/blob/9acad4a9ef1583096af7836cc1e9c8cbcb4d3950/README.md)

本项目通过独立进程调用 `ffmpeg.exe` / `ffprobe.exe`。GPLv3 第 5 节对独立作品组成的 aggregate 有明确说明；将独立程序放在同一压缩包不自动使其他独立组件也适用 GPL。这不免除被分发 FFmpeg 二进制的源码与许可义务。PyAV 则直接绑定 FFmpeg 库，其附带库也必须单独核对。[GPLv3 第 5、6 节](https://www.gnu.org/licenses/gpl-3.0.html)、[PyAV 官方源代码](https://github.com/PyAV-Org/PyAV/tree/v19.0.1)

分发 GPL 二进制时，需要提供机器可读的 Corresponding Source，覆盖构建该二进制所需的源码、相关库、适用补丁及控制构建/安装的脚本。GPLv3 第 6(d) 节允许源码置于另一个服务器，但需要在二进制下载处明确指向可同等获取的源码，并持续确保其可用。通用主页、浮动 `master` 链接或仅 FFmpeg 主仓库源码不能代替全部对应源。[GPLv3 第 1、6 节](https://www.gnu.org/licenses/gpl-3.0.html)

原 BtbN 二进制对应的发行标签为 [`autobuild-2026-10-07-13-07`](https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-07-13-07)，构建仓库提交为 `9acad4a9ef1583096af7836cc1e9c8cbcb4d3950`。该发行版自动生成的 “Source code” ZIP 是构建仓库快照，不能单独视为所有 FFmpeg/依赖的 Corresponding Source。依赖的版本与补丁见该提交的构建脚本，例如 [x264](https://github.com/BtbN/FFmpeg-Builds/blob/9acad4a9ef1583096af7836cc1e9c8cbcb4d3950/scripts.d/50-x264.sh)、[x265](https://github.com/BtbN/FFmpeg-Builds/blob/9acad4a9ef1583096af7836cc1e9c8cbcb4d3950/scripts.d/50-x265.sh)。

PyAV `19.0.1` 使用的上游构建记录指向 [`PyAV-Org/pyav-ffmpeg` 的 `9.0.2-1`](https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/9.0.2-1)。该构建记录列明 FFmpeg 和外部库版本，并包含 x264/x265；PyAV 的 BSD 许可证不替代其附带 FFmpeg 的许可证。[精确构建配置](https://github.com/PyAV-Org/PyAV/blob/v19.0.1/scripts/ffmpeg-latest.json)、[外部库版本清单](https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/README.md)

精确来源和获取方式保存在 [THIRD_PARTY_SOURCES.json](THIRD_PARTY_SOURCES.json)。清单包含固定的 FFmpeg 提交、BtbN 构建快照中 127 个配方的源码获取超集、Git/SVN 固定版本、子模块获取说明，以及 librsvg/rav1e 原始 Cargo.lock 中 577 个去重 Rust 源码包的版本与 SHA256。源码包访问及下载校验记录也随清单保存。

运行包的 `sources/` 目录保存 BtbN 与 PyAV 的原始构建快照、两个 Rust 锁文件及适用补丁；`THIRD_PARTY_LICENSES/ffmpeg-btbn/` 和 `THIRD_PARTY_LICENSES/ffmpeg-rust-sources/` 保留从固定源码取得的原始许可证/版权材料。源码清单包含未参与 Windows 构建的可选、开发和其他平台组件，作为不遗漏实际运行时源码的超集；这些条目不表示其二进制都随包分发。

本发行采用 GPLv3 第 6(d) 节的对应源码访问方式：在二进制下载处直接指向上述精确源码清单，接收者可通过相同的公开网络方式获取原始源码及构建补丁。重新分发者仍应持续确保这些源码可取得；若来源消失，应补充镜像。清单不声称与原编译器逐字节复现二进制。rav1e 使用的 `cc` 位于其 `[build-dependencies]`，是未修改的通用 C 编译调用工具；GPLv3 第 1 节对这种未成为作品一部分的一般免费构建工具有明确排除。[固定 rav1e 配置](https://github.com/xiph/rav1e/blob/31435de9d76fddd38f6dcc31d4014574cebb2092/Cargo.toml)、[Cargo 保守更新说明](https://doc.rust-lang.org/cargo/commands/cargo-update.html)

## Whisper 模型与转换工具

OpenAI 官方说明明确将 Whisper 代码和模型权重以 MIT License 发布。分发权重时需要保留 OpenAI 的版权与许可声明；无需把模型训练数据一起分发。[Whisper 官方许可说明](https://github.com/openai/whisper#license)、[原始 MIT License](https://github.com/openai/whisper/blob/main/LICENSE)

本应用的本地 ASR 路径使用 `faster-whisper` 和 CTranslate2 加载 CT2 格式模型。small 来自 `Systran/faster-whisper-small` 提交 `536b0662742c02347bc0e980a01041f333bce120`，base 来自 `Systran/faster-whisper-base` 提交 `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`；对应文件 SHA256 保存在源码来源清单中，OpenAI 原始 MIT License 保存在每个模型目录及 `THIRD_PARTY_LICENSES/whisper-models/LICENSE`。模型格式转换不移除原始权重的版权声明。`faster-whisper` 与 CTranslate2 的授权还分别适用于其代码。[faster-whisper](https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1)、[CTranslate2 `v4.8.2` MIT License](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/LICENSE)

## Python 依赖与本机运行库

保留 `runtime/site-packages` 中所有分发包的 `*.dist-info` 元数据以及其中的许可文件。依赖版本以随包元数据和构建来源清单为准。常用主组件的原始来源如下：

| 组件 | 主要许可及来源 |
| --- | --- |
| yt-dlp | 其发行包自带 LICENSE；[官方许可文件](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) |
| faster-whisper 1.2.1 | MIT；[官方 LICENSE](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/LICENSE) |
| CTranslate2 4.8.2 | MIT；[官方 LICENSE](https://github.com/OpenNMT/CTranslate2/blob/v4.8.2/LICENSE) |
| PyAV 19.0.1 | BSD-3-Clause；[官方 LICENSE](https://github.com/PyAV-Org/PyAV/blob/v19.0.1/LICENSE.txt)；附带 FFmpeg 库另行适用其授权 |
| FlatBuffers 25.12.19 | Apache-2.0；[官方 LICENSE](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE) |
| tokenizers 0.23.2 | Apache-2.0；[官方 LICENSE](https://github.com/huggingface/tokenizers/blob/v0.23.2/LICENSE) |
| packaging 25.0 | Apache-2.0 或 BSD-2-Clause；保留该发行包的 LICENSE、LICENSE.APACHE、LICENSE.BSD |
| NumPy、ONNX Runtime 及其他依赖 | 保留各自分发包中的许可证和附属版权声明；原包元数据列明来源 |

CTranslate2 的 Windows wheel 还包含静态 oneDNN 与 Intel OpenMP 运行库。已经补充的原始许可资料放在完整包中：

- `THIRD_PARTY_LICENSES/ctranslate2/LICENSE`
- `THIRD_PARTY_LICENSES/flatbuffers/LICENSE`
- `THIRD_PARTY_LICENSES/tokenizers/LICENSE`
- `THIRD_PARTY_LICENSES/onednn-3.1.1/LICENSE`
- `THIRD_PARTY_LICENSES/onednn-3.1.1/THIRD-PARTY-PROGRAMS`
- `THIRD_PARTY_LICENSES/intel-openmp-2025.3.0/` 中的 LICENSE 和 third-party-programs 原文件

oneDNN 的 Apache-2.0 许可及其第三方声明来自 [oneDNN `v3.1.1`](https://github.com/oneapi-src/oneDNN/tree/v3.1.1)。Intel OpenMP 资料来自 [Intel 官方发布的 `intel-openmp 2025.3.0` wheel](https://pypi.org/project/intel-openmp/2025.3.0/)；仅从该包提取原始许可材料，没有用另一版 DLL 替换应用运行库。Apache-2.0 组件的许可副本、适用 NOTICE 和修改声明应按其第 4 节保留。[Apache-2.0 原文](https://www.apache.org/licenses/LICENSE-2.0)

Windows 应用运行还需 Microsoft Visual C++ Runtime。使用 Microsoft 官方 Redistributable 安装器时，应保留安装器及其随附授权，不把 Windows 本机安装目录当作可任意复制的 DLL 来源。[Microsoft 官方 Redistributable 说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)

许可证文本、版权及源代码访问条件仍以各组件实际发行版所附原文为准。
