# 排错

- --check 失败：确认当前 Python 可导入 yt_dlp，ffmpeg 与 ffprobe 在 PATH 中。Python 依赖可通过 python -m pip install yt-dlp 安装。
- 解析失败：记录当前 yt-dlp 版本，核查上游 Douyin 问题；更新后对同一链接实测。不要把通用下载器支持等同于当前链接必定可下载。
- 登录或 Cookie 要求：取得用户授权后，使用 --cookies-browser 指定浏览器。浏览器凭证读取可能受系统加密或文件占用影响；停止并说明具体错误。
- 短链失败：请求或取得对应的 www.douyin.com/video/<id> 完整链接，重试一次。
- 无音轨：音频任务失败；视频任务可以独立成功。
- FFmpeg 转码失败：查看本地诊断，确认编码器可用及磁盘空间足够。交付校验通过的视频。
- 超时：单项默认为 300 秒，可用 --timeout 调整。批量任务会继续处理后续项目。

## 上游来源

下载器：https://github.com/yt-dlp/yt-dlp
FFmpeg：https://www.ffmpeg.org/ffmpeg.html
可选服务后端：https://github.com/Evil0ctal/Douyin_TikTok_Download_API

当前实现直接调用 yt-dlp，不依赖 Evil0ctal 服务。未来接入服务时应新增适配器，按固定版本核实 API 或 MCP 工具及响应；不要复用不同主版本的接口示例。
