# 抖音视频与音频 Skill

接收抖音分享文本、视频链接或本地视频，输出校验通过的视频、MP3/WAV 和 `result.json`。支持明确指定的多条链接；音频是完整音轨，不是单独背景音乐或人声。工作流生成转写或正文后，AI 自动总结，并同时保留完整文本与独立的总结文件。

下载有两个后端：默认的 yt-dlp 本机下载器，以及 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) v5 自部署服务。服务适配器按上游实际接口实现解析、任务轮询、媒体下载和文件取回；不复制其签名算法，也不自动部署服务器。

## 完整 Windows x64 运行包

GitHub Release 提供完整 ZIP：Python 3.13.16、锁定的 Python 依赖、FFmpeg/ffprobe、CPU 语音转写模型、微软 VC++ 官方离线安装器和许可证/对应源材料。Windows 10/11 x64 使用；视频下载需要网络，离线模型处理不需要联网。AI 总结由调用 skill 的 AI 完成。

解压后在包目录运行：

```text
run.cmd --check
run.cmd --url "抖音链接" --cookies-file "本机已授权的 cookies.txt" --output "输出目录"
run.cmd --input "本地视频.mp4" --output "输出目录"
```

完整流程输出媒体、transcript.txt、transcript.srt、transcript.json、workflow.json 和 summary-input.md。AI 自动读取生成正文，再另存总结；完整正文保留。

如果当前 Windows 未安装 VC++ 运行库，使用包内 runtime/prerequisites/vc_redist.x64.exe 按微软安装界面提示完成安装；包内已有安装文件。Cookie 必须由用户另行提供，包内不带 Cookie、浏览器配置、历史会话或个人运行结果。

## 安装与检查

需要 Python 3.10+。在仓库目录执行：

```text
python -m pip install -r requirements.txt
python douyin-media/scripts/fetch_media.py --check
```

另安装 [FFmpeg](https://www.ffmpeg.org/download.html)，确保 `ffmpeg`、`ffprobe` 在 PATH 中，或者每次传入 `--ffmpeg-dir "工具所在的 bin 目录"`。DTK 后端和本地文件处理仅使用 Python 标准库与 FFmpeg；yt-dlp 是本机下载所需依赖。

使用 Codex 时，将整个 `douyin-media` 文件夹放入个人的 `~/.codex/skills/`，或者项目的 `.agents/skills/`，再通过 `$douyin-media` 调用。也可以直接使用脚本。

## 本机下载和音频提取

```text
python douyin-media/scripts/fetch_media.py --url "抖音链接或分享文本" --mode both --output ./media
python douyin-media/scripts/fetch_media.py --input "video.mp4" --mode audio --audio-format wav --output ./media
python douyin-media/scripts/fetch_media.py --url "链接一" --url "链接二" --output ./media
```

只有显式指定时才读取浏览器会话或 Cookie 文件：

```text
python douyin-media/scripts/fetch_media.py --url "抖音链接" --cookies-browser edge --output ./media
python douyin-media/scripts/fetch_media.py --url "抖音链接" --cookies-file "已授权的 cookies.txt" --output ./media
```

可传 `--proxy http://127.0.0.1:7897` 使用本机下载器代理。代理端口由实际环境决定。`--cookies-file` 使用一次性副本，原文件保持不变。

Windows 上若已有用户授权的 Netscape Cookie 文件，优先使用 `--cookies-file`。文件只保留本机，不放入 Git 仓库；无需为了读取文件再次关闭浏览器。该方式已用于本项目的真实视频验证。

## AI 自动总结文本

在 AI 执行 skill 的流程中，一旦生成转写、字幕整理或文字稿，AI 会读取全文并自动给出概要、关键要点和结论；有明确建议时提取行动项，无需再次请求总结。

完整正文保留，另存同目录的 `<正文文件名>-总结.md`，交付时提供两份文件。批量内容分别总结；转写含糊之处标注不确定性。

这是一项 AI 执行要求。`media_workflow.py` 先完成媒体与离线转写，生成 `summary-input.md` 供 AI 读取全文并总结；总结状态初始为 pending，ready=true 仅表示有可供总结的正文；CLI 的成功状态只确认媒体和转写完成。执行 skill 的 AI 应完成总结并交付独立文件，实际总结文件存在后才能报告总结完成。包不包含本地大语言模型，也不自动调用收费 AI API。

## 自部署服务后端

先按上游文档部署 v5 服务，启用媒体下载组件，并创建有 `douyin:read`、`media:read`、`media:write` 权限的 API key。这个后端会在指定服务的媒体卷上保存视频，再把视频下载到当前机器。

PowerShell 示例；API key 应通过环境变量或凭证管理器设置，避免进入提交或聊天记录：

```powershell
$env:DTK_BASE_URL = 'http://127.0.0.1:8000'
# 通过安全方式设置 DTK_API_KEY 环境变量
python douyin-media/scripts/fetch_media.py --backend dtk --url "抖音链接" --output ./media
```

远程服务使用 HTTPS。Cookie、代理和平台登录在服务器端配置。详见 [服务接口说明](douyin-media/references/backends.md)。

## 输出与限制

每次运行创建独立目录，逐项保存文件并更新结果清单。清单包含状态、错误代码、文件大小、时长和 SHA-256；视频扩展名取决于源文件，脚本不把所有格式强行改名为 MP4。

退出码：`0` 全部成功，`1` 至少一项失败或部分成功，`2` 参数、依赖或输出目录错误。无音轨时保留已校验的视频；批量任务继续处理后续项。每项默认时限 300 秒、源媒体上限 1 GiB，可用 `--timeout`、`--max-bytes` 调整。网络读取有独立的 socket 时限；超时检查在读取块和阶段边界执行。

只处理有权保存的指定媒体。平台可要求有效会话，下载能力不等于任意链接都能成功；图集、主页、合集和直播不属于本 skill 的处理范围。

## 验证

```text
python -m unittest discover -s tests -v
```

需要 FFmpeg 才能跑全部测试；非 PATH 安装可先设置 `MEDIA_FFMPEG_DIR` 为 bin 目录。测试实际生成视频并调用 FFmpeg/ffprobe，DTK 协议测试使用本机 HTTP 测试服务。

2026-10-09：当前完整 Windows 包共 40 项自动测试通过，包内 Python 和依赖隔离导入、small/base 离线 CPU 转写、中文路径、缺失模型处理与混合批量流程验证通过。完整包可运行 `run-tests.cmd` 重现测试；8 项 DTK 协议测试需要允许本机回环连接。CLI 生成全文和 `summary-input.md` 后，总结状态仍为 pending，由执行 skill 的 AI 自动完成独立总结文件。详见[验证报告](VALIDATION.md)和[完整包脱敏验证记录](validation/windows-full-bundle.json)。

2026-10-08 的抖音实网流程已用 Netscape Cookie 文件成功获取作品 7692971496985218304，视频与 MP3 均约 360.63 秒，独立复核文件大小、SHA-256 和媒体结构通过；本次完整包验证没有重新下载该作品。Edge 直接导入可能受后台占用或 DPAPI 解密影响，Windows 上已有授权 Cookie 文件时推荐使用文件输入。自部署 DTK 服务的实网下载尚未验证。见[历史脱敏成功记录](validation/douyin-7692971496985218304.json)。
