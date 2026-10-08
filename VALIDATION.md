# 验证报告

日期：2026-10-08（Asia/Shanghai）

## 环境与证据

- Windows，Python 3.13。
- yt-dlp 2026.8.19；FFmpeg/ffprobe 9.0.2 essentials。
- Python 下载依赖与媒体工具放在工作区的测试目录中；未修改用户浏览器会话。
- Evil0ctal 服务适配器按上游 commit 4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2 的路由、schema 和服务实现核查。

## 自动验证

执行 `python -m unittest discover -s tests -v`，23 项测试全部通过。

测试使用实际 FFmpeg 生成短视频（含音轨、静音、音轨比视频短），实际执行 MP3/WAV 提取并用 ffprobe 校验媒体流和时长，同时核验 SHA-256。

覆盖本地视频保存、音频单独输出、源文件保持不变、重复运行不覆盖、无音轨的部分成功、批量失败后继续处理、损坏文件、缺失输入、大小限制和超时。

DTK 接入测试使用本机 HTTP 测试服务，实际走 HTTP 请求、异步任务轮询、媒体字节下载、音频提取与文件校验；覆盖 API key 传递、授权失败、校验和不匹配、轮询超时、重定向拒绝、流式大小限制、异常错误结构和 chunked 传输中途断开后的批量继续执行。结果清单未包含测试 API key 或输入链接的 token 参数。

Skill 创建器的 quick_validate.py 验证通过，git diff --check 通过。独立检查核对了上游 v5 协议，并复现了异常响应结构和传输断开导致批量中断的问题；修复后相应回归测试通过。

## 抖音实网验证

通过本机代理调用最终脚本，输入 yt-dlp 上游测试作品链接：

`https://www.douyin.com/video/6961737553342991651`

工具返回需要新鲜 Cookie，最终脚本将其分类为 `session_required`，返回退出码 1、空文件列表和有效结果清单，未把平台拒绝误报为成功。

因此：本地媒体处理和 DTK 协议接入已验证；匿名抖音实网下载没有成功，使用有效授权会话的下载仍需实测。未部署或连接用户自己的 DTK 服务，HTTP 测试服务不是平台下载成功证据。

## 重现

安装 requirements.txt 和 FFmpeg/ffprobe。工具不在 PATH 时设置 MEDIA_FFMPEG_DIR，然后执行上述 unittest 命令。测试生成的媒体在临时目录中清理。

实网验证使用脚本的 --url、--proxy、--ffmpeg-dir 和 --timeout 参数，不需修改实现。有效会话可由用户显式提供 --cookies-browser 或 --cookies-file；结果以当次平台返回为准。
