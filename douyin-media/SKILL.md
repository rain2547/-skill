---
name: douyin-media
description: 获取指定抖音视频或从本地视频提取完整音轨，支持分享文本、明确指定的链接列表、本机下载器和已配置的下载服务，并校验交付文件；生成转写或正文后由 AI 自动总结。
---

# 抖音视频与音频

完整运行包使用包根目录的 `run.cmd` 或包内 Python 调用 `scripts/media_workflow.py`，完成下载、音轨提取与离线转写；只获取媒体时使用 `scripts/fetch_media.py`。默认单条输入输出视频和 MP3；音频为视频的完整音轨。只处理用户指定的作品，不扩展到主页、合集或直播。背景音乐获取和人声分离属于另外的处理流程。

## 路由与执行

1. 接受本地视频路径、一个抖音视频链接或一段含单个链接的分享文本。多项任务重复 `--url` 或 `--input`；每个参数只放一个链接。
2. 确定输出目录及 `--mode video|audio|both`、`--audio-format mp3|wav`。先执行 `--check`，需要的 Python 下载依赖见 `requirements.txt`；FFmpeg 安装须提供 ffmpeg、ffprobe。工具不在 PATH 时传 `--ffmpeg-dir`。
3. 本地输入直接用 `--input`。链接默认用 yt-dlp；用户已指定或配置 Evil0ctal v5 服务时用 `--backend dtk`，并读取 [服务接口说明](references/backends.md)。后端失败时不隐式把输入或会话发送到另一服务。
4. 完整工作流检查 `workflow.json`：媒体成功后自动离线转写，正文保存为 TXT/SRT/JSON，并生成 `summary-input.md`。AI 读取每项完整正文、完成下方总结要求，将 `summary.status=pending` 的待办处理完再交付。单独媒体脚本检查 `result.json`。脚本保留媒体容器原扩展名；如果用户明确需要 MP4，再完成兼容的封装或转码并重新校验。
5. 任务生成转写、字幕整理或其他正文后，按下方“自动总结生成的文本”完成全文阅读与总结，无需用户另行要求摘要。
6. 交付结果清单中确实存在的文件链接。退出码 0 表示全部成功，1 表示失败或部分成功，2 表示参数、环境或输出错误。无音轨时可交付已校验的视频。音轨较视频短是可能的，不补造声音。

示例（脚本路径替换为本 skill 实际路径）：

```text
python scripts/fetch_media.py --url "抖音分享文本" --mode both --output "输出目录"
python scripts/fetch_media.py --input "视频.mp4" --mode audio --audio-format wav --output "输出目录"
python scripts/fetch_media.py --backend dtk --url "抖音链接" --output "输出目录"
```

## 自动总结生成的文本

当本流程生成可用正文文本时，执行 skill 的 AI 必须读取完整文本并自动生成总结。收到本流程已有的转写或正文时，直接处理这份文字，不重复获取已有材料。

- 根据全文组织简短概要、关键要点和结论；原文包含明确建议或操作步骤时，再提取行动项。长度随内容复杂度调整。
- 总结忠实于原文，保留关键事实、数字及作者明确表达的观点；对转写不清或原文未说明的内容标注不确定性，不补造信息。
- 保留完整正文，另存同目录的 `<正文文件名>-总结.md`；批量内容按来源分别总结，便于追溯。
- 交付时同时提供完整正文与总结文件的链接，并在回复中给出简短总结。用户无需再次提出“请总结”。
- 读取到可用正文并确认总结文件存在、可读后，才报告总结完成。正文缺失或总结失败时说明文字处理状态，并交付其他已验证的产物。

该要求由执行 skill 的 AI 在文字处理阶段完成。`fetch_media.py` 的结果清单记录媒体处理状态，`media_workflow.py` 记录媒体、转写和总结的分阶段状态。CLI 的待总结状态表示还需执行 skill 的 AI 读取正文并完成总结；交付时核对真实产物再说明状态。

## 会话与失败处理

只有用户授权使用其会话后，才传 `--cookies-browser chrome|edge|firefox` 或 `--cookies-file`。已有授权的 Netscape Cookie 文件时优先使用 `--cookies-file`，该流程已在真实抖音视频上验证；Windows 上可避免直接读取浏览器数据库时的占用与 DPAPI 兼容性问题。API key 通过 `DTK_API_KEY` 环境变量提供。凭证及原始媒体签名 URL 不进入结果清单或交付内容。服务模式可能在指定服务器保存媒体，这应符合用户选择的保存位置。

每项默认处理时限 300 秒、源媒体上限 1 GiB，可按任务调整。HTTP 传输有 socket 时限，脚本在读取块和阶段边界检查剩余时间。下载器仅对暂时性网络错误有限重试；遇到 `session_required`、登录、验证码或权限不足时使用正常授权路径，停止自动重试。

出现失败时读取 [排错说明](references/troubleshooting.md)。报告实际测试范围：本机 HTTP 测试服务验证的是接入协议，不能证明抖音实网下载成功。以当前任务的真实结果为准。

将浏览器读取和解密错误与平台拒绝分开处理。browser_cookie_access 可在浏览器完全退出后重试一次；browser_decryption 切换为正常导出的仅抖音域 Netscape Cookie 文件（--cookies-file），不继续反复关闭浏览器或修改其加密保护。文件放在仓库外，仅把文件路径用于任务，不把会话内容写入聊天或报告。
