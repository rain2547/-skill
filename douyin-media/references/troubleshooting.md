# 排错

先看 result.json 中 error.code；原始工具输出可能含媒体签名或会话信息，不直接交付给用户。

| code | 处理 |
| --- | --- |
| session_required | 获取用户授权后使用浏览器会话或 Netscape Cookie 文件；不自动读取会话 |
| unavailable | 核实视频是否删除、私密或受权限限制 |
| download_failed/backend_response | 记录后端版本，核查上游问题；更新后对同一链接实测 |
| tool_missing | 安装 FFmpeg/ffprobe，或修正 --ffmpeg-dir |
| no_audio | 交付已校验的视频；该视频没有可提取音轨 |
| invalid_media/conversion_failed | 检查源媒体、编码器和空间；保留已交付视频 |
| timeout | 检查网络与服务任务状态，按需要调整 --timeout；服务任务可能仍在运行 |
| size_limit | 按用户允许的容量调整 --max-bytes；源文件和下载流都受此上限约束 |
| service_auth/service_permission | 检查 DTK_API_KEY 及 douyin:read、media:read、media:write 权限 |
| service_not_configured | 在用户服务中启用上游媒体下载组件 |
| checksum_mismatch/incomplete_download | 文件未通过完整性校验，本次不交付该文件；检查服务与网络 |
| service_redirect | 配置能直接处理 API 与媒体响应的服务 origin |

--check 只检查本机工具和服务配置是否存在，不测试服务连接或 API key 权限。批量任务逐项记录结果；有效输出在独立运行目录中，不覆盖以前的文件。
