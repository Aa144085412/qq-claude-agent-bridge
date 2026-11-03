# 虾爬子 QQ → Claude Code CLI 独立会话桥接

## 设计
- 普通主人 QQ 消息交由独立 Claude Code CLI 处理，支持会话恢复；Claude 桥接调用 127.0.0.1:18082（Desktop 控制器通道，支持思考协议，`MAX_THINKING_TOKENS=1024`）；原 /模式 聊天 轻量通道保持 18081 不变。
- 不是直接把消息打进已打开的 Claude Desktop Code 标签页；Desktop 尚无受支持的外部入站会话 API。
- QQ 原有主人绑定、消息去重、白名单和手动确认发信均保留。

## QQ 命令
/模式 Claude —— 将普通主人私聊交给 Claude Code
/Claude 请分析项目结构 —— 任意模式中显式调用 Claude Code
/Claude状态 —— 查看 QQ 专用 Claude Code 会话状态
/Claude重置 —— 重置 QQ 专用 Claude 会话，不影响 Desktop 会话
/模式 Agent —— 原受控电脑工具模式
/模式 聊天 —— 原 IQ3_S 轻量聊天
/模式 自动 —— 原轻量对话与受控工具
/发 收件人 要求 —— 拟稿，不直接联系第三方
/确认 草稿码 —— 主人审核后发信
/电脑状态 —— 直接查询本机，不经过 Claude Code

## 权限
- Claude Code 以 bypassPermissions 运行，启用 Read、Glob、Grep、Bash；不启用 Edit、Write，不给模型 OneBot Token。
- 主人 QQ 消息只能请求"运行某命令/脚本"，不能改写 claude.exe 路径或 argv；Native claude.exe 固定绝对路径，subprocess shell=False。
- 命令级审计：%LOCALAPPDATA%\QQ-Small-Agent-Pilot\claude-exec-audit.jsonl。每执行一条 Bash 命令记一条 bash_command（含命令与描述，截断 500 字，不含任何凭据/Token）；每轮结束记一条 final。**没有 bash_command 即本轮未真正执行任何命令。**
- 已知局限：本地 IQ3_S 调用 Bash 工具并不稳定，偶发"复述命令输出而并不执行"。事后以审计日志核对——有 bash_command 才是真实执行，否则按未执行处理。
- 本地模型地址由程序硬编码，移除进程内代理环境变量；模型智能仍取决于 IQ3_S。
- 每条输入最多 4000 字，回复最多约 2200 字；Claude Code 最多 20 个执行轮次，子进程超时 240 秒。
- QQ 后端长期保持为原 QQ-Small-Agent-V2 Windows 任务，不新建调度器。

## 文件
Claude 桥接：C:\claude_code_project\qq-small-agent\qq_claude_bridge.py
QQ 路由：C:\claude_code_project\qq-small-agent\qq_command_agent.py
数据：%LOCALAPPDATA%\QQ-Small-Agent-Pilot\command-agent.sqlite3
日志：%LOCALAPPDATA%\QQ-Small-Agent-Pilot\command-agent-service.log

降级：主人 QQ 发送 /模式 Agent 或 /模式 聊天。

## 2026-11-03 实际修复
- 真正根因：Claude Code 原先只给 3 个执行轮次，复杂项目分析触发 error_max_turns 并以退出码 1 结束；并不是 NInfer 或 Claude Code 安装问题。
- 提升至 16 轮次，超限按错误子类型准确回报；原始 QQ 架构分析请求已在真实 Claude Code + IQ3_S 中成功。
- 接收器改为计划任务直接管理 Python，使用 Windows 文件锁确保只存在一个 QQ WebSocket 消费者；任务停止不会留下孤儿 Python 进程。
- 该时点仍维持只读项目分析、主人专属路由与第三方发送审批；同日稍后升级为命令执行能力（见文末）。


## 2026-11-03 13:36: HTTP 403 诊断与防护
- NInfer 的 /health、/v1/chat/completions 和 /v1/messages 均能返回 HTTP 200，尚不能证明 403 来自 NInfer。
- 原始项目分析请求经真实 Claude Code CLI 复测成功，错误并非稳定复现。
- 对新建的只读 Claude Code 会话，HTTP 403 自动最多重试一次，使用新的会话 ID；已有多轮会话不自动重放。
- 追加安全诊断元数据到 %LOCALAPPDATA%\QQ-Small-Agent-Pilot\claude-cli-bridge-errors.jsonl，不记录原文、回复、Token。
- 90/90 项自动化测试通过，原始问题通过真实模型与测试 QQ 回复器验收，未向真实 QQ 发测试消息。
- 13:36 重启后唯一 Python 接收器和一条 WS 3001 连接，主人绑定、claude 模式及数据库完整性正常。
- 真人 QQ 收到修复后回复尚待用户实际测试。


## 2026-11-03 13:56 -- Scheduled Task HTTP 403 root cause resolved
- Native Claude Code debug showed HTTP 403 CONTROLLER_LANE_UNAUTHORIZED.
- Desktop user settings intentionally use 127.0.0.1:18082 and a separate ANTHROPIC_AUTH_TOKEN. Windows Task Scheduler Claude child inherited those settings instead of selecting QQ's explicit 18081 endpoint.
- Isolated task profile removed 403 but surfaced HTTP 400: thinking.display='omitted' is not supported by NInfer.
- QQ Claude child environment now explicitly sets CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1 and CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1, sets HOME from USERPROFILE and clears inherited CLAUDE_CONFIG_DIR.
- Same-user Task Scheduler execution of the ORIGINAL QQ architecture-analysis question succeeded: Claude Code process exit 0 and 937 characters of actual analysis; no HTTP API errors. The separate native CLI smoke also exited 0.
- 90/90 offline owner/permissions/bridge tests passed. Production QQ-Small-Agent-V2 task restarted at 13:56 with exactly one Python receiver and one WebSocket 3001 client. Owner remained bound, routing mode claude, DB integrity ok.
- Backup of bridge prior to this fix: claude-provider-routing-fix-20261103-135408.
- No Desktop settings, NInfer service, QQ login or third-party contacts were changed. No actual QQ messages were sent by test.
- Owner needs to send a fresh QQ question to complete the final live QQ reply acceptance.


## 2026-11-03 能力升级：命令执行（bypassPermissions + Bash + 命令级审计）
- 应主人要求，QQ 会话从只读分析升级为可执行本地命令：`--permission-mode bypassPermissions`，`--tools Read,Glob,Grep,Bash`，`--output-format stream-json --verbose`。
- 桥接改为解析 stream-json 事件流：每出现一次 Bash tool_use 即追加一条命令级审计（bash_command，命令+描述，截断 500 字），每轮追加 final（会话 ID + 结果状态）。审计文件 %LOCALAPPDATA%\QQ-Small-Agent-Pilot\claude-exec-audit.jsonl，不含凭据/Token。
- 保留的安全机制不变：主人专属绑定、第三方白名单+草稿码+手动 /确认、固定 claude.exe 绝对路径、subprocess shell=False、QQ 不能指定可执行文件或改 argv、不向 QQ 泄露 stderr/凭据。
- 已知局限（已实测确认）：本地 IQ3_S 调用 Bash 工具并不稳定——同一"运行 echo X"提示连续 3 个全新会话，1 次未调用工具而是复述输出（审计无 bash_command），2 次真实执行（审计有 bash_command）。桥接无法自动判断模型是否在"演"；以审计日志事后核对。
- 主人已选择"接受现状 + 用审计核对"：每次 QQ 命令执行后，查看 claude-exec-audit.jsonl 是否新增 bash_command 记录以确认是否真实执行。
- 验证：`python -m py_compile qq_claude_bridge.py` 通过；真实模型 smoke 跑通 stream-json 解析，真实调用 Bash 时写入 bash_command + final，未调用时只写 final。
- 未改动 Desktop 设置、NInfer 服务、QQ 登录或第三方联系人。生产任务 QQ-Small-Agent-V2 待重启加载新代码。


## 2026-11-03 15:14 -- 根因定位：长会话漂移导致 Bash 不执行（已修复）
- 现象：主人连续 3 条 QQ 命令全部"成功"返回文字但审计无 bash_command（均未真正执行）。
- 根因：生产长会话 0e6bbad2 是 bypassPermissions 升级前建立，累积了"我是只读、无执行权限"的旧上下文，覆盖了新工具授权。同一"查系统时间"提示：全新会话调用 Bash（date，审计有 bash_command），resume 该会话则回"没有执行命令的权限"、不调 Bash（审计无 bash_command）。
- 修复：删除 meta 的 claude_cli_session 与 claude_cli_turns（下一条 QQ 消息自动开全新会话）；已先做 DB 一致性备份 command-agent.sqlite3.bak-20261103-151413。主人绑定 81xx、claude 模式均未变；服务进程未重启。
- 诊断脚本：smoke_utf8.py / smoke_nl.py / smoke_resume.py / reset_stale_session.py（均一次性）。
- 使用提示：若日后命令又变"只回文字不执行"，QQ 发 /Claude重置 即可开启新会话恢复 Bash。


## 2026-11-03 升级 A：思考预算 + 系统提示 + 截断放宽
- Claude 桥接从 18081 切换到 18082（Desktop 控制器通道），启用 `MAX_THINKING_TOKENS=1024` 思考预算；18082 要求控制器凭据，桥接在运行时从 `%USERPROFILE%\.claude\settings.json` 的 `env.ANTHROPIC_AUTH_TOKEN` 读取（不硬编码、不打印）。CLI 优先发送 `x-api-key`，因此 `ANTHROPIC_API_KEY` 与 `ANTHROPIC_AUTH_TOKEN` 必须同时写入同一通道凭据，占位符会导致 403 CONTROLLER_LANE_UNAUTHORIZED。
- 系统提示重写：明确模型身份为"本机 Qwen3.8 (30B GGUF) 在 Claude Code CLI 内运行"，声明工作目录、Git Bash 环境、主人 QQ 授权、中文 ≤1200 字回复与硬安全边界（不泄露凭据/Token、不发 QQ 消息、不安装/持久改动）；消除"自认我是 Claude"与误以为自己是 Desktop GUI 会话的问题。
- 截断放宽：输入 1700→4000 字（QQ 路由正则同步），回复 950→2200 字，执行轮次 16→20，超时 180→240 秒。
- 会话机制适配 npm claude-code 2.1.283：新会话不再传 `--session-id`（该 CLI 版本将其当作不存在的会话恢复而报错），改由 CLI 自生成会话 ID 并从 stream-json 的 result 事件取回；续会话用 `--resume`；403 重试仅对新会话生效且为原样重跑。
- 验证：py_compile 通过；25/25 桥接测试通过；真实 18082 全新会话 smoke（Bash date，14.1s，审计 bash_command 落盘）与 resume 续会话 smoke（同 ID 3.7s、正确记得上下文）均通过。
- 生产任务 QQ-Small-Agent-V2 已重启加载新代码，唯一 Python 监听进程确认。升级 A 之前的备份：qq_claude_bridge.py.bak-20261103-upgradeA。
- 待办：主人从 QQ 实测一条命令（如锁屏），核对回复与审计新增 bash_command。
