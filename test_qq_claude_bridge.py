"""Offline tests for QQ -> Claude Code CLI adapter. No actual CLI or QQ sends."""
import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

import qq_claude_bridge as bridge
import qq_command_agent as qa
from test_qq_command_agent import FakeAPI, ev, BOT, OWNER, STRANGER

class QQBridgeAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=qa.new_db(Path(self.folder.name)/"db.sqlite3")
        qa.set_meta(self.db,"owner",OWNER)
        self.api=FakeAPI()
        self.seq=7000
        self.agent=qa.Agent(self.db,BOT,lambda a,t:"拟稿",lambda messages:"普通聊天")

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    async def send(self,text,sender=OWNER,kind="private"):
        self.seq+=1
        return await self.agent.incoming(ev(sender,text,self.seq,kind=kind),self.api)

    async def test_switch_mode_claude(self):
        await self.send("/模式 Claude")
        self.assertEqual(qa.meta(self.db,"mode"),"claude")
        self.assertIn("Claude",self.api.sent[-1][1])

    async def test_plain_message_routes_to_code_without_original_chat(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock(return_value="Claude Code 结论")) as do:
            await self.send("请分析这个项目的架构")
        do.assert_awaited_once_with(self.db,"请分析这个项目的架构")
        self.assertEqual(self.api.sent,[(OWNER,"Claude Code 结论")])

    async def test_explicit_claude_command_in_chat_mode(self):
        qa.set_meta(self.db,"mode","chat")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock(return_value="已收到")) as do:
            await self.send("/Claude 请审查 Python 源码")
        do.assert_awaited_once_with(self.db,"请审查 Python 源码")
        self.assertEqual(self.api.sent[-1],(OWNER,"已收到"))

    async def test_stranger_never_invokes_claude(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            result=await self.send("你好",STRANGER)
        self.assertEqual(result,"ignored")
        do.assert_not_awaited()
        self.assertFalse(self.api.sent)

    async def test_stranger_slash_never_invokes_claude(self):
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            await self.send("/Claude 请运行脚本",STRANGER)
        do.assert_not_awaited()
        self.assertFalse(self.api.sent)

    async def test_group_never_invokes_claude(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            await self.send("请帮我写代码",kind="group")
        do.assert_not_awaited()
        self.assertFalse(self.api.sent)

    async def test_outgoing_qq_guard_still_priority(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            await self.send("帮我联系张三")
        do.assert_not_awaited()
        self.assertIn("/发",self.api.sent[-1][1])

    async def test_explicit_send_drafts_not_delegate(self):
        qa.set_meta(self.db,"mode","claude")
        self.db.execute("INSERT INTO contacts VALUES (?,?,?)",("234567890","测试好友",int(time.time())))
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            await self.send("/发 测试好友 你好")
        do.assert_not_awaited()
        self.assertEqual(self.db.execute("SELECT state FROM drafts").fetchone()[0],"draft")

    async def test_computer_approval_guard_remains_first(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as do:
            await self.send("/确认操作 00112233")
        do.assert_not_awaited()
        self.assertIn("未执行",self.api.sent[-1][1])

    async def test_claude_error_returns_safe_notice(self):
        qa.set_meta(self.db,"mode","claude")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock(side_effect=bridge.ClaudeBridgeError("本地模型暂时不可用"))):
            await self.send("帮我解释这个报错")
        self.assertIn("未执行",self.api.sent[-1][1])
        self.assertIn("本地模型",self.api.sent[-1][1])

    async def test_claude_status_and_reset_leave_owner(self):
        qa.set_meta(self.db,"claude_cli_session",str(uuid.uuid4()))
        qa.set_meta(self.db,"claude_cli_turns","5")
        await self.send("/Claude状态")
        self.assertIn("5",self.api.sent[-1][1])
        await self.send("/Claude重置")
        self.assertIsNone(qa.meta(self.db,"claude_cli_session"))
        self.assertEqual(qa.meta(self.db,"owner"),OWNER)

    async def test_switch_back_to_chat_no_code(self):
        await self.send("/模式 Claude")
        await self.send("/模式 聊天")
        with mock.patch.object(qa.code_bridge,"reply_async",new=mock.AsyncMock()) as code:
            await self.send("你好")
        code.assert_not_awaited()
        self.assertEqual(self.api.sent[-1][1],"普通聊天")


class CLIProcessSafetyTests(unittest.TestCase):
    def test_invalid_input_not_spawned(self):
        with mock.patch.object(bridge.subprocess,"run") as run:
            with self.assertRaises(bridge.ClaudeBridgeError):
                bridge._run_native("",None)
            run.assert_not_called()

    def test_invalid_resume_uuid_not_spawned(self):
        with mock.patch.object(bridge.subprocess,"run") as run:
            with self.assertRaises(bridge.ClaudeBridgeError):
                bridge._run_native("你好","dangerous-session-id")
            run.assert_not_called()

    def test_native_binary_owner_command_mode_and_authed_lane(self):
        sid=str(uuid.uuid4())
        fake=mock.Mock(returncode=0,stdout=json.dumps({"type":"result","is_error":False,"session_id":sid,"result":"只读检查成功"},ensure_ascii=False),stderr="")
        with mock.patch.object(bridge.subprocess,"run",return_value=fake) as run,\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            answer,got=bridge._run_native("请分析源码",sid)
        args=run.call_args.args[0]
        opts=run.call_args.kwargs
        self.assertEqual(answer,"只读检查成功")
        self.assertEqual(got,sid)
        self.assertEqual(args[0].lower().endswith(".exe"),True)
        self.assertIn("--bare",args)
        self.assertIn("--permission-mode",args)
        self.assertIn("bypassPermissions",args)
        self.assertIn("Read,Glob,Grep,Bash",args)
        self.assertNotIn("Write",args)
        self.assertNotIn("Edit",args)
        self.assertNotIn("--dangerously-skip-permissions",args)
        self.assertIn("--resume",args)
        self.assertNotIn("--session-id",args)
        self.assertFalse(opts["shell"])
        self.assertEqual(opts["env"]["ANTHROPIC_BASE_URL"],"http://127.0.0.1:18082")
        self.assertEqual(opts["env"]["CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST"],"1")
        self.assertNotIn("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",opts["env"])
        self.assertEqual(opts["env"]["MAX_THINKING_TOKENS"],"1024")
        self.assertNotIn("CLAUDE_CONFIG_DIR",opts["env"])
        self.assertEqual(opts["env"]["ANTHROPIC_AUTH_TOKEN"],"test-lane-token")
        # The CLI prefers ANTHROPIC_API_KEY as the credential; a placeholder
        # there made the 18082 lane answer 403 CONTROLLER_LANE_UNAUTHORIZED.
        self.assertEqual(opts["env"]["ANTHROPIC_API_KEY"],"test-lane-token")
        self.assertNotIn("HTTP_PROXY",opts["env"])
        self.assertNotIn("HTTPS_PROXY",opts["env"])

    def test_new_session_id_and_response_truncation(self):
        fake_response="字"*2600
        cli_sid=str(uuid.uuid4())
        def responder(args,**opts):
            # Fresh sessions must not pass --session-id (the current CLI
            # treats it as a resume of a nonexistent conversation); the
            # CLI generates its own ID and reports it in the result event.
            self.assertNotIn("--session-id",args)
            self.assertNotIn("--resume",args)
            return mock.Mock(returncode=0,stdout=json.dumps({"type":"result","result":fake_response,"is_error":False,"session_id":cli_sid}),stderr="")
        with mock.patch.object(bridge.subprocess,"run",side_effect=responder),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            txt,sid=bridge._run_native("写一段长说明",None)
        self.assertEqual(len(txt)<=bridge.MAX_REPLY_CHARS,True)
        self.assertIn("截断",txt)
        self.assertEqual(sid,cli_sid)

    def test_cli_error_cannot_leak_stderr(self):
        fake=mock.Mock(returncode=2,stdout="",stderr="SECRET_TOKEN_X")
        with mock.patch.object(bridge.subprocess,"run",return_value=fake),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            with self.assertRaises(bridge.ClaudeBridgeError) as cm:
                bridge._run_native("问问题",None)
        self.assertNotIn("SECRET_TOKEN_X",str(cm.exception))

    def test_max_turn_limit_error_is_actionable_not_installation(self):
        response={"type":"result","subtype":"error_max_turns",
                  "terminal_reason":"max_turns","is_error":True,
                  "errors":["Reached maximum number of turns (20)"]}
        fake=mock.Mock(returncode=1,stdout=json.dumps(response,ensure_ascii=False),
                       stderr="private-path-should-not-appear")
        with mock.patch.object(bridge.subprocess,"run",return_value=fake),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            with self.assertRaises(bridge.ClaudeBridgeError) as cm:
                bridge._run_native("请分析架构",None)
        self.assertIn("执行轮数上限",str(cm.exception))
        self.assertIn("20",str(cm.exception))
        self.assertNotIn("请检查本地 NInfer 与 Claude Code 安装",str(cm.exception))
        self.assertNotIn("private-path",str(cm.exception))

    def test_nonzero_http_error_is_classified(self):
        response={"type":"result","subtype":"error_during_execution",
                  "api_error_status":503,"is_error":True}
        fake=mock.Mock(returncode=1,stdout=json.dumps(response),stderr="")
        with mock.patch.object(bridge.subprocess,"run",return_value=fake),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            with self.assertRaises(bridge.ClaudeBridgeError) as cm:
                bridge._run_native("请解释代码",None)
        self.assertIn("HTTP 503",str(cm.exception))

    def test_403_fresh_session_retries_and_gets_fresh_cli_session(self):
        first=mock.Mock(returncode=1,stdout=json.dumps({
            "type":"result","subtype":"error_during_execution","api_error_status":403,"is_error":True
        }),stderr="SENSITIVE_STDERR")
        cli_sid=str(uuid.uuid4())
        called=[]
        def fake_run(args,**kwargs):
            called.append(list(args))
            self.assertNotIn("--session-id",args)
            self.assertNotIn("--resume",args)
            if len(called)==1:return first
            # Each CLI run of a fresh session self-generates its session
            # ID; the retry is a plain re-run and the result event carries
            # the new ID.
            return mock.Mock(returncode=0,stderr="",stdout=json.dumps({
                "type":"result","session_id":cli_sid,"is_error":False,"result":"正常回答"
            },ensure_ascii=False))
        with mock.patch.object(bridge.subprocess,"run",side_effect=fake_run),\
             mock.patch.object(bridge.time,"sleep"),\
             mock.patch.object(bridge,"_record_bridge_event"),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            response,sid=bridge._run_native("分析项目",None)
        self.assertEqual(response,"正常回答")
        self.assertEqual(len(called),2)
        self.assertEqual(called[0],called[1])
        self.assertEqual(sid,cli_sid)
        self.assertEqual(called[0][called[0].index("--tools")+1],"Read,Glob,Grep,Bash")

    def test_403_twice_fails_without_leaking_process_details(self):
        failed=mock.Mock(returncode=1,stdout=json.dumps({
            "type":"result","subtype":"error_during_execution","api_error_status":403,"is_error":True
        }),stderr="secret-password")
        with mock.patch.object(bridge.subprocess,"run",return_value=failed) as call,\
             mock.patch.object(bridge.time,"sleep"),\
             mock.patch.object(bridge,"_record_bridge_event"),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            with self.assertRaises(bridge.ClaudeBridgeError) as cm:
                bridge._run_native("分析代码",None)
        self.assertEqual(call.call_count,2)
        self.assertIn("HTTP 403",str(cm.exception))
        self.assertNotIn("secret-password",str(cm.exception))

    def test_resumed_session_403_never_replayed_automatically(self):
        failed=mock.Mock(returncode=1,stdout=json.dumps({
            "type":"result","subtype":"error_during_execution","api_error_status":403,"is_error":True
        }),stderr="")
        sid=str(uuid.uuid4())
        with mock.patch.object(bridge.subprocess,"run",return_value=failed) as call,\
             mock.patch.object(bridge,"_record_bridge_event"),\
             mock.patch.object(bridge,"_load_lane_token",return_value="test-lane-token"):
            with self.assertRaises(bridge.ClaudeBridgeError):
                bridge._run_native("继续分析",sid)
        call.assert_called_once()

    def test_response_persist_only_on_success(self):
        with tempfile.TemporaryDirectory() as work:
            db=qa.new_db(Path(work)/"state.sqlite")
            sid=str(uuid.uuid4())
            with mock.patch.object(bridge,"_run_native",return_value=("成功",sid)):
                self.assertEqual(bridge.reply(db,"QQ 问题"),"成功")
            self.assertEqual(qa.meta(db,"claude_cli_session"),sid)
            self.assertEqual(qa.meta(db,"claude_cli_turns"),"1")
            with mock.patch.object(bridge,"_run_native",side_effect=bridge.ClaudeBridgeError("网络错误")):
                with self.assertRaises(bridge.ClaudeBridgeError):
                    bridge.reply(db,"错误测试")
            self.assertEqual(qa.meta(db,"claude_cli_turns"),"1")
            db.close()

    def test_continuation_same_id(self):
        with tempfile.TemporaryDirectory() as work:
            db=qa.new_db(Path(work)/"state.sqlite")
            sid=str(uuid.uuid4())
            qa.set_meta(db,"claude_cli_session",sid)
            with mock.patch.object(bridge,"_run_native",return_value=("继续",sid)) as run:
                result=bridge.reply(db,"继续解释")
            run.assert_called_once_with("继续解释",sid)
            self.assertEqual(result,"继续")
            self.assertEqual(qa.meta(db,"claude_cli_session"),sid)
            db.close()

    def test_prompt_never_invokes_claude_desktop_automation(self):
        self.assertNotIn("claude://",bridge.PROMPT_POLICY)
        self.assertNotIn("bypassPermissions",bridge.PROMPT_POLICY)
        self.assertEqual(bridge.BASE_URL.startswith("http://127.0.0.1"),True)

if __name__=="__main__":
    unittest.main(verbosity=2)
