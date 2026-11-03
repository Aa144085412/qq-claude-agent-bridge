# 虾爬子：QQ 主人专属双模式 Agent v3

## 双模式
普通聊天：已绑定主人直接私聊普通中文，调用本地 IQ3_S 自然回复，保留最近 12 条聊天上下文。最多保留 60 条，超过 7 天的内容清理。
指令执行：只有主人明确使用 / 指令或“帮我给某人发消息：……”时执行。联系好友先由模型拟稿，主人审核后使用 /确认 才能发送。

## 常用命令
/帮助、/模式、/状态、/ping
/聊天 内容 —— 明确使用对话模式
/清空记忆 —— 清空本机聊天历史，不改变主人绑定或白名单
/授权 QQ号 备注 —— 将真实好友加入白名单
/列表 —— 查看白名单
/发 备注或QQ号 你的要求 —— 拟稿，绝不自动发送
/草稿 —— 查看草稿
/确认 八位草稿码 —— 明确批准一次发信
/取消 —— 取消草稿
/撤销 QQ号 —— 从白名单移除

模糊的“帮我联系张三”等请求不会发信，会要求先使用 /发 指令。

## 服务和文件
任务名称：QQ-Small-Agent-V2（复用原任务，不建第二套）
主程序：C:\claude_code_project\qq-small-agent\qq_command_agent.py
本地模型：127.0.0.1:18081 / local-qwen38-gsq
OneBot HTTP：127.0.0.1:3000
OneBot WebSocket：127.0.0.1:3001
持久数据：%LOCALAPPDATA%\QQ-Small-Agent-Pilot\command-agent.sqlite3
日志：%LOCALAPPDATA%\QQ-Small-Agent-Pilot\command-agent-service.log

## 安全
- 非主人、群聊、自身消息、图片消息均不触发 AI。
- 模型只返回文字，不得直接调用 OneBot 发信接口，拿不到 Token。
- 发给第三方必须是机器人好友且白名单成员，必须草稿确认。
- 每小时最多 5 条第三方发信，两次发送至少间隔 30 秒；结果不明不自动重试。
- 没有开启群发、自动联系陌生人、Shell 或 VRLO/MCP 工具。
- Windows 任务重启不影响 QQ 主号和 NapCat 进程。
- 不记录来信原文到日志；聊天历史仅本机 SQLite 保存，可 /清空记忆。

## 运维
在 PowerShell 运行：
    cd C:\claude_code_project\qq-small-agent
    python qq_command_agent.py status
    Get-ScheduledTask QQ-Small-Agent-V2

停止接收器：
    Stop-ScheduledTask QQ-Small-Agent-V2
启动接收器：
    Start-ScheduledTask QQ-Small-Agent-V2

## 部署到另一台机器

clone 只得到纯代码（仓库内不含 token、owner 绑定、聊天记录），实际跑起来需要目标机器具备：

1. **Windows**：使用 ctypes 截图、headless Edge、PowerShell、msvcrt 文件锁。
2. **Python 3.13**（或较新 3.x）：`pip install -r requirements.txt`（唯一第三方库 `websockets`）。
3. **NapCat / OneBot v11** 同机运行并登录 QQ：
   - 事件 WS `ws://127.0.0.1:3001`、HTTP API `http://127.0.0.1:3000`（代码强制这两个地址，拒绝其他地址启动）。
   - OneBot token 运行时从 `%PROGRAMDATA%\NapCatQQ Desktop\config\bot.json` 读取，不在仓库内。
4. **模型通道**（按模式选其一）：
   - chat 模式：本地模型 `http://127.0.0.1:18081/v1/chat/completions`。
   - claude 模式：Claude Code CLI + 控制通道 `http://127.0.0.1:18082`，且 `%USERPROFILE%\.claude\settings.json` 内有有效 `env.ANTHROPIC_AUTH_TOKEN`（不在仓库内）。
5. **启动脚本路径**：`Start-QQ-Command-Agent.ps1` 里 `$root`、`$python` 是原机绝对路径，换机器需改成对应路径，或直接 `python qq_command_agent.py run` 运行。
6. **重新绑定主人**：owner 绑定存在本地 SQLite（`%LOCALAPPDATA%\QQ-Small-Agent-Pilot\`），新机器首次启动未绑定，需在本地控制台生成配对码，再在 QQ 私聊发 `/绑定 <code>`。
