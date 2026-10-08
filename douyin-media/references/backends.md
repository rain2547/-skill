# 下载后端

## yt-dlp

默认后端。固定测试版本在本 skill 的 requirements.txt 中，平台支持变化后按上游发布记录升级并用真实链接回归测试。调用时忽略用户全局下载配置、禁用播放列表、使用本次任务独立目录，下载后用 ffprobe 校验。

`session_required` 表示需要当前可用的授权会话。Cookie 文件使用临时副本，保留原文件；浏览器读取受浏览器和系统凭证机制影响，传入参数本身不保证成功。

项目：https://github.com/yt-dlp/yt-dlp

## Evil0ctal v5 服务

适配器使用 Python 标准库调用 REST API。用户先配置服务；客户端不安装或运行上游的服务器代码。按上游安装文档启用媒体下载组件，创建有 douyin:read、media:read、media:write 权限的 API key。

配置：DTK_BASE_URL 为服务 origin（不带 /api/v1 路径）；DTK_API_KEY 为 API key。允许本机 HTTP，远程服务要求 HTTPS。客户端不跟随服务重定向，不将 API key 发送到媒体 CDN。

顺序：

1. POST /api/v1/parse，body 为 {"url":"抖音链接"}。
2. 如果返回 data.task_id，轮询 GET /api/v1/tasks/{id}；done 时取 data.data，failed/cancelled 时终止。
3. 从解析结果取 platform 和 content_id，POST /api/v1/downloads，设置 skip_existing=true。
4. 按 data.download_id 轮询 GET /api/v1/downloads/{id}。done/partial 时选择 kind=video、state=done 的单个文件。
5. GET /api/v1/downloads/{id}/files/{name} 下载媒体字节。校验字节上限、Content-Length 与服务提供的 SHA-256，再交给共同处理流程。

JSON 响应使用 success/data/error/meta 信封；文件响应为实际字节。服务无媒体组件会返回 501，客户端报告 service_not_configured。API key 失败报告 service_auth/service_permission。解析和下载任务只轮询已有任务，客户端不反复创建新任务。

这条路径会在指定服务器的媒体卷保存视频，并取回本机副本。客户端取消或超时不等于服务器任务取消；客户端不会删除服务上的媒体或修改其配置。

协议核查基于上游 commit `4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2`：

- [请求 schema](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/api/routes/schemas.py)
- [下载与文件取回](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/api/routes/downloads.py)
- [任务状态和结果](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/api/routes/tasks.py)

v4 与 v5 接口不兼容，本适配器不支持 v4。升级服务后核查相同接口的实际 schema，并运行 HTTP 接入测试和一条真实链接。
