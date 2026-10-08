---
name: douyin-media
description: 获取用户指定的抖音视频或从本地视频提取完整音轨，支持单条链接及明确指定的链接列表，校验文件并交付视频、音频和结果清单。
---

# 抖音视频与音频

使用 scripts/fetch_media.py 执行任务。下载后端为 yt-dlp，音频处理使用 FFmpeg；平台支持需以实际执行结果为准。

## 输入和执行

接受分享文本、抖音视频链接或本地媒体路径。默认 mode=both、audio-format=mp3。音频指完整音轨，包括人声、音乐和音效；背景音乐获取或人声分离是另外的任务。

1. 检查 python、yt-dlp、ffmpeg、ffprobe。使用 python scripts/fetch_media.py --check 检查环境。缺依赖时按用户环境安装；Python 依赖为 yt-dlp，FFmpeg 安装须同时提供 ffprobe。
2. 对每个指定链接使用 --url，对本地文件使用 --input。批量任务可重复 --url 或 --input。选择 --mode video、audio 或 both，并设置 --output 为用户指定输出目录。
3. 下载仅针对指定视频，不扩展到账号或播放列表。分享短链由后端解析；用户可先提供展开后的完整视频链接以排查短链问题。
4. 查看进程退出码和 result.json。退出码 0 为全部成功，1 为至少一项失败，2 为环境或参数错误。部分成功时仍交付已校验文件。
5. 返回实际生成文件的可点击链接和失败原因。音频提取失败时保留成功下载的视频。

示例：

```text
python scripts/fetch_media.py --url "抖音分享文本或链接" --mode both --audio-format mp3 --output "输出目录"
python scripts/fetch_media.py --input "本地视频.mp4" --mode audio --audio-format wav --output "输出目录"
```

## 会话与停止条件

默认不读取浏览器会话。只有用户授权使用其会话后，才传入 --cookies-browser chrome 等参数。凭证不写入结果清单；不要在交付内容中包含原始诊断日志或媒体签名直链。

脚本对网络下载最多重试两次，每项有总超时。登录要求、验证码、权限不足或内容不可用时，报告原因并使用正常授权路径，不自动反复尝试。现有文件不覆盖，每次执行输出独立运行目录。

出现解析或依赖错误时阅读 references/troubleshooting.md。
