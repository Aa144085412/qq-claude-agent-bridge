# QQ → Claude Code CLI 桥接阶段验收

项目 | 结果
---|---
Claude Desktop 与 CLI 确认本机安装 | PASS
Claude Code native CLI 通过本地 IQ3_S 推理 | PASS
Unicode 参数与 session-id / resume 双轮记忆 | PASS
原 65 项安全测试 | PASS
新增 22 项 CLI 桥接与异常分类测试（总计 87 项） | PASS
桥接完整函数调用 Claude CLI | PASS，原问题 16 轮正常完成
注入当前打开的 Desktop 窗口 | 不支持；这是独立的 CLI 会话
QQ 入站事件 → 真实 Claude Code → 测试 QQ 发送器 | PASS，原问题真实回包（不向 QQ 发消息）
真人 QQ 实际收到修复后的回复 | PASS（2026-11-03 14:08 主人确认收到；14:03/14:05/14:08 三条真实往返成功）
向第三方发送 QQ 消息 | 本轮未执行
修改本地文件、运行 Shell 或任意控制桌面 | 不允许

计划任务单实例验证 | PASS：旧包装器导致 3 个监听进程，已改为 Python 直接任务；停止后 0 个，启动后 1 个，1 条 WS 连接
本地模型 HTTP 健康 | PASS，HTTP 200
当前 QQ 模式 / 主人绑定 | claude / 保留


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


## 2026-11-03 14:08 -- Final live acceptance closed
- Live end-to-end test (live_acceptance_20261103.py): NapCat identity, owner binding (read-only DB), real Claude Code CLI read-only run, and real QQ reply to owner all PASS; NapCat confirmed message_id=2038737385.
- Inbound path: 14:03:14 and 14:05:06 owner events processed by the live receiver (EVENT_RESULT=processed); no bridge error entries after 13:56:48.
- Owner confirmed receipt on real QQ and sent "分析一下这个项目的架构"; production claude mode returned a correct architecture analysis with multi-turn memory (referenced earlier turns) and expected 950-char truncation.
- Final verdict: ACCEPTANCE_PASS. No code changes required in this round.


## 2026-11-03 能力变更：命令执行（bypassPermissions + Bash）
- 应主人要求，QQ 会话从"只读分析"升级为可执行本地命令：`--permission-mode bypassPermissions`，启用 Bash。上文表格"修改本地文件、运行 Shell 或任意控制桌面 | 不允许"仅适用于旧的只读阶段，新模式下运行命令已允许。
- 新增命令级审计：每执行一条 Bash 命令写入 %LOCALAPPDATA%\QQ-Small-Agent-Pilot\claude-exec-audit.jsonl 的 bash_command 记录；无记录即本轮未真正执行。
- 已实测确认本地 IQ3_S 调用 Bash 不稳定（同一"运行 echo X"提示 3 连测：1 次复述未执行、2 次真实执行）。主人选择"接受现状 + 用审计核对"。
- 保留机制：主人绑定、第三方白名单+草稿+确认、固定 claude.exe 路径、shell=False、QQ 不能指定可执行文件/改 argv。
- 验证：py_compile 通过；真实模型 smoke 确认 stream-json 解析正确（真实调用 Bash 时写 bash_command + final）。
- 生产任务 QQ-Small-Agent-V2 重启后加载新代码；主人真人 QQ 实测（含锁屏）待执行。


## 2026-11-03 15:14 -- 主人 3 连命令失败：根因与修复
- 主人报告"连续 3 条命令全部失败"。日志核实：3 条均被接收并 processed、CLI result_status=success、无报错，但审计 0 条 bash_command（均未真正执行）。
- 根因定位（对照实验）：同一"查系统时间"提示，全新会话调用 Bash（date，审计 bash_command=1）；resume 生产长会话 0e6bbad2 则回"没有执行命令的权限"、不调 Bash（bash_command=0）。即长会话累积的旧"只读"上下文覆盖了新的 Bash 授权。
- 修复：DB 备份后删除 claude_cli_session / claude_cli_turns，下一条 QQ 消息开全新会话。owner 绑定 81xx、claude 模式不变，服务未重启。
- 待办：主人从 QQ 实测一条命令（如锁屏），核对回复 + 审计新增 bash_command。日后若复发，QQ 发 /Claude重置。


## 2026-11-03 15:45 -- 升级 A：思考预算 + 系统提示 + 截断放宽
- Claude 桥接切换到 18082（Desktop 控制器通道），`MAX_THINKING_TOKENS=1024`；凭据运行时从 settings.json 读取，`ANTHROPIC_API_KEY` 与 `ANTHROPIC_AUTH_TOKEN` 同写（CLI 优先 x-api-key，占位符曾致 403）。
- 系统提示重写：身份改为"本机 Qwen3.8 在 Claude Code CLI 内"，含工作目录/环境/授权/安全边界；不再自认 Claude、不再误认 Desktop GUI 会话。
- 限制放宽：输入 4000 字 / 回复 2200 字 / 20 轮 / 240 秒（QQ 路由正则同步 4000）。
- 适配 npm claude-code 2.1.283：新会话不传 `--session-id`（CLI 自生成并在 result 事件回传），续会话 `--resume`；403 重试仅限新会话原样重跑。
- 验证：py_compile 通过；25/25 测试通过；真实 18082 smoke 两条——全新会话 Bash date 14.1s（审计 bash_command=1，final=success，会话 9d2fcdb5），resume 同 ID 3.7s 正确记得 `date`。
- QQ-Small-Agent-V2 重启后唯一 Python 监听进程；owner 绑定 81xx、claude 模式不变。升级前备份 qq_claude_bridge.py.bak-20261103-upgradeA。
- 待办：主人 QQ 实测 + 审计核对后，验收闭环。


## 2026-11-03 15:47 -- 升级 A 实机确认（无代码改动）
- 主人 15:44 从 QQ 发"你能控制我的电脑吗"（会话 682ddecc）。转录核实：模型先思考（thinking_tokens=170）后以中文正确作答，身份正确（"我运行在你这台 Windows 11 电脑上"，不再自认 Claude、不再误认 Desktop GUI）。
- 因是**问句而非命令**，模型正确地未调用 Bash，审计无 bash_command 属正常，非故障。
- 结论：18082 通道 + MAX_THINKING_TOKENS=1024 + 系统提示重写均已在生产生效并正常工作。
- 待办（最终闭环）：主人从 QQ 发一条**明确命令**（如"帮我锁屏"或"查一下系统时间"），核对审计是否新增 bash_command。


## 2026-11-03 15:54 -- 路由顺序修复：claude 模式直通 Claude 执行
- 现象：主人在 claude 模式发"打开edge"，却收到旧 Agent 帮助文案（"可以处理受控的本机任务……"），Claude 未执行。
- 根因：execute() 里 `pc.parse_action_name` / `pc.may_be_machine_request` 两道确定性守卫排在 `current_mode == "claude"` 分支**之前**。"edge" 不在 APP_ALIASES，parse 返回 None，落入 may_be_machine_request（以"打开"开头），直接回帮助文案，永远到不了 code_bridge.reply_async。
- 修复：把 `current_mode == "claude"` 分支前移到守卫之前。claude 模式下所有普通主人消息（含机器意图）直达 Claude Code（bypassPermissions + 真实 Bash）；agent/auto 模式仍保留受控工具 + /确认操作 审批流；chat 模式路径不变（轻聊天模型永远到不了 shell）。/确认操作、/发（外发）、未识别斜杠等守卫仍在此块之前处理，不受影响。
- 验证：py_compile 通过；test_qq_claude_bridge 25/25；test_qq_command_agent 20/20。
- 部署：QQ-Small-Agent-V2 停止旧进程后重启（唯一接收器 PID 33504），日志 QQ_AGENT_READY owner=bound_tail=81xx、WS 127.0.0.1:3001 已连，owner 绑定不变。改动前备份 qq_command_agent.py.bak-20261103-routing-claude。
- 待办（最终闭环）：主人从 QQ 发"打开edge"或"帮我锁屏"，核对 claude-exec-audit.jsonl 是否新增 bash_command。
