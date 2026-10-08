# 抖音视频与音频 Skill

接收抖音分享文本、视频链接或本地视频，输出校验通过的视频、MP3/WAV 和 `result.json`。支持明确指定的多条链接；音频是完整音轨，不是单独背景音乐或人声。

下载有两个后端：默认的 yt-dlp 本机下载器，以及 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) v5 自部署服务。服务适配器按上游实际接口实现解析、任务轮询、媒体下载和文件取回；不复制其签名算法，也不自动部署服务器。

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

2026-10-08：24 项测试通过。本地视频与音频处理、DTK HTTP 接入和异常处理通过；真实抖音下载仍未成功。用户授权的 Edge 会话先遇到数据库占用，完全退出后台进程后遇到 DPAPI 解密失败。skill 已分别报告 browser_cookie_access、browser_decryption、browser_profile 和平台 session_required；恢复路径为正常导出的仅抖音域 Cookie 文件。没有实测连接用户自部署的 DTK 服务。详细证据见 [验证报告](VALIDATION.md)。
