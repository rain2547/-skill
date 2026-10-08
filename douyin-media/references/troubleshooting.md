# 排错

先看 result.json 中 error.code；原始工具输出可能含媒体签名或会话信息，不直接交付给用户。

| code | 处理 |
| --- | --- |
| session_required | 获取用户授权后使用浏览器会话或 Netscape Cookie 文件；不自动读取会话 |
| browser_cookie_access | 浏览器后台进程或文件权限阻止读取 Cookie 数据库；完全退出浏览器后重试一次。不要重复自动结束进程 |
| browser_decryption | Windows DPAPI 或浏览器加密兼容性阻止解密；关闭浏览器无助于这一阶段。使用浏览器正常导出的仅抖音域 Netscape Cookie 文件，或用户已有的可用 Firefox 会话 |
| browser_profile | 执行环境无法找到用户浏览器配置；检查运行用户及配置目录，沙盒目录可能与实际目录不同 |
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

## 正常导出的 Cookie 文件

文件必须是 Netscape 格式。只保存抖音域的会话，放在仓库外的临时位置，再用 --cookies-file 指向该文件。Cookie 内容不发进聊天、不进入 Git 或验证报告；本 skill 对输入文件制作一次性副本，原文件不会被 yt-dlp 改写。

可以使用 yt-dlp 官方 FAQ 列出的浏览器导出方式：https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp 。安装浏览器扩展涉及读取会话权限，由用户在自己的浏览器中决定并完成。只对网站正常可访问的媒体使用该会话。

不要把 --cookies-from-browser 与 --cookies 并用作为 DPAPI 失败的修复：它仍然会调用相同的浏览器数据库解密路径。
