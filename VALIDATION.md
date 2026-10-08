# 验证报告

日期：2026-10-08（Asia/Shanghai）

## 环境与证据

- Windows，Python 3.13。
- yt-dlp 2026.8.19；FFmpeg/ffprobe 9.0.2 essentials。
- Python 下载依赖与媒体工具放在工作区的测试目录中；未修改用户浏览器会话。
- Evil0ctal 服务适配器按上游 commit 4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2 的路由、schema 和服务实现核查。

## 自动验证

执行 `python -m unittest discover -s tests -v`，24 项测试全部通过（包含后续实网排错增加的回归测试）。

测试使用实际 FFmpeg 生成短视频（含音轨、静音、音轨比视频短），实际执行 MP3/WAV 提取并用 ffprobe 校验媒体流和时长，同时核验 SHA-256。

覆盖本地视频保存、音频单独输出、源文件保持不变、重复运行不覆盖、无音轨的部分成功、批量失败后继续处理、损坏文件、缺失输入、大小限制和超时。

DTK 接入测试使用本机 HTTP 测试服务，实际走 HTTP 请求、异步任务轮询、媒体字节下载、音频提取与文件校验；覆盖 API key 传递、授权失败、校验和不匹配、轮询超时、重定向拒绝、流式大小限制、异常错误结构和 chunked 传输中途断开后的批量继续执行。结果清单未包含测试 API key 或输入链接的 token 参数。

Skill 创建器的 quick_validate.py 验证通过，git diff --check 通过。独立检查核对了上游 v5 协议，并复现了异常响应结构和传输断开导致批量中断的问题；修复后相应回归测试通过。

## 抖音实网验证

通过本机代理调用最终脚本，输入 yt-dlp 上游测试作品链接：

`https://www.douyin.com/video/6961737553342991651`

工具返回需要新鲜 Cookie，最终脚本将其分类为 `session_required`，返回退出码 1、空文件列表和有效结果清单，未把平台拒绝误报为成功。

因此：本地媒体处理和 DTK 协议接入已验证；匿名抖音实网下载没有成功，使用有效授权会话的下载仍需实测。未部署或连接用户自己的 DTK 服务，HTTP 测试服务不是平台下载成功证据。

## 用户视频的后续验证

用户提供短链 https://v.douyin.com/GMp37b4x2pA/，解析为视频 7692971496985218304，标题为“消除信息差！看懂 GitHub 最常见的 6 种文件”。

用户授权使用 Edge 会话后，测试先遇到 Cookie 数据库占用。用户在正常本机终端结束 Edge 后台进程后，原诊断脚本报告 browser_decryption / Failed to decrypt with DPAPI。未取得媒体，视频保存和音频提取均不能认定通过。

核查本地及上游 Windows Cookie 实现发现：该版本只识别 v10，其他前缀转入传统 DPAPI，失败后整批退出。这说明当前浏览器导入路径失败；没有据此断言用户 Cookie 的具体加密版本，也没有修改浏览器加密设置。

新增回归测试用实际子进程输出本次观察到的错误文本，验证数据库占用、DPAPI 解密失败、配置目录缺失分别产生明确错误码，平台请求新鲜 Cookie 仍归类 session_required。修复前前三种情况失败，修复后通过；错误报告不含原始 Cookie 或密钥。

另尝试了正常网页播放器：浏览器能加载该视频，并显示 360.6 秒媒体；浏览器保存能力随后因 DNS/URL 策略错误未能导出文件。能播放网页不是已保存文件的证据。

下一步需由用户通过正常浏览器导出仅抖音域的 Netscape Cookie 文件，或使用另一已授权的可用会话，再走 --cookies-file 路径实测。仍未验证该恢复路径能成功获取此视频。

## 重现

安装 requirements.txt 和 FFmpeg/ffprobe。工具不在 PATH 时设置 MEDIA_FFMPEG_DIR，然后执行上述 unittest 命令。测试生成的媒体在临时目录中清理。

实网验证使用脚本的 --url、--proxy、--ffmpeg-dir 和 --timeout 参数，不需修改实现。有效会话可由用户显式提供 --cookies-browser 或 --cookies-file；结果以当次平台返回为准。
