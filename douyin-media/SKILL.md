---
name: douyin-media
description: 获取指定抖音视频或从本地视频提取完整音轨，支持分享文本、明确指定的链接列表、本机下载器和已配置的下载服务，并校验交付文件。
---

# 抖音视频与音频

使用本 skill 目录下 `scripts/fetch_media.py`。默认单条输入输出视频和 MP3；音频为视频的完整音轨。只处理用户指定的作品，不扩展到主页、合集或直播。背景音乐获取和人声分离属于另外的处理流程。

## 路由与执行

1. 接受本地视频路径、一个抖音视频链接或一段含单个链接的分享文本。多项任务重复 `--url` 或 `--input`；每个参数只放一个链接。
2. 确定输出目录及 `--mode video|audio|both`、`--audio-format mp3|wav`。先执行 `--check`，需要的 Python 下载依赖见 `requirements.txt`；FFmpeg 安装须提供 ffmpeg、ffprobe。工具不在 PATH 时传 `--ffmpeg-dir`。
3. 本地输入直接用 `--input`。链接默认用 yt-dlp；用户已指定或配置 Evil0ctal v5 服务时用 `--backend dtk`，并读取 [服务接口说明](references/backends.md)。后端失败时不隐式把输入或会话发送到另一服务。
4. 执行脚本，检查退出码及打印的 `result.json` 路径。脚本保留媒体容器原扩展名；如果用户明确需要 MP4，再完成兼容的封装或转码并重新校验。
5. 交付结果清单中确实存在的文件链接。退出码 0 表示全部成功，1 表示失败或部分成功，2 表示参数、环境或输出错误。无音轨时可交付已校验的视频。音轨较视频短是可能的，不补造声音。

示例（脚本路径替换为本 skill 实际路径）：

```text
python scripts/fetch_media.py --url "抖音分享文本" --mode both --output "输出目录"
python scripts/fetch_media.py --input "视频.mp4" --mode audio --audio-format wav --output "输出目录"
python scripts/fetch_media.py --backend dtk --url "抖音链接" --output "输出目录"
```

## 会话与失败处理

只有用户授权使用其会话后，才传 `--cookies-browser chrome|edge|firefox` 或 `--cookies-file`。已有授权的 Netscape Cookie 文件时优先使用 `--cookies-file`，该流程已在真实抖音视频上验证；Windows 上可避免直接读取浏览器数据库时的占用与 DPAPI 兼容性问题。API key 通过 `DTK_API_KEY` 环境变量提供。凭证及原始媒体签名 URL 不进入结果清单或交付内容。服务模式可能在指定服务器保存媒体，这应符合用户选择的保存位置。

每项默认处理时限 300 秒、源媒体上限 1 GiB，可按任务调整。HTTP 传输有 socket 时限，脚本在读取块和阶段边界检查剩余时间。下载器仅对暂时性网络错误有限重试；遇到 `session_required`、登录、验证码或权限不足时使用正常授权路径，停止自动重试。

出现失败时读取 [排错说明](references/troubleshooting.md)。报告实际测试范围：本机 HTTP 测试服务验证的是接入协议，不能证明抖音实网下载成功。以当前任务的真实结果为准。

将浏览器读取和解密错误与平台拒绝分开处理。browser_cookie_access 可在浏览器完全退出后重试一次；browser_decryption 切换为正常导出的仅抖音域 Netscape Cookie 文件（--cookies-file），不继续反复关闭浏览器或修改其加密保护。文件放在仓库外，仅把文件路径用于任务，不把会话内容写入聊天或报告。
