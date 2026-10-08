# 抖音媒体 Skill

`douyin-media/` 包含 skill 入口、执行脚本与排错说明。

## 环境

Python 3.10+；安装 Python 下载依赖：

```text
python -m pip install -r requirements.txt
```

另外安装 FFmpeg，确保 ffmpeg 和 ffprobe 都在 PATH 中。

## 使用

```text
python douyin-media/scripts/fetch_media.py --check
python douyin-media/scripts/fetch_media.py --url "抖音链接或分享文本" --mode both --output ./media
python douyin-media/scripts/fetch_media.py --input "video.mp4" --mode audio --audio-format wav --output ./media
```

每次运行建立独立目录，生成 result.json 和媒体文件。退出码 0 表示成功，1 表示部分成功或失败，2 表示参数或环境问题。

默认不读取浏览器 Cookie。用户授权后可使用 --cookies-browser chrome、edge 或 firefox。平台解析支持可能随上游变化，实际下载需用真实链接验证。

音频为完整音轨，并非分离的背景音乐或人声。只处理有权保存和使用的媒体。

## 验证状态

脚本语法及输入校验已验证。当前机器未安装 yt-dlp、FFmpeg、ffprobe，尚未执行真实下载和媒体转码验证。
