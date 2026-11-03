import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import qq_command_agent as q

BOT = "987654321"
OWNER = "123456789"
TARGET = "234567890"
STRANGER = "345678901"

class FakeAPI:
    def __init__(self):
        self.sent = []
        self.sent_segments = []
        self.friends = {TARGET}
        self.token = "fake-token"
        self.raise_on_send = False
    async def send(self, target, text):
        if self.raise_on_send and str(target) == TARGET:
            raise q.GuardError("simulated unknown delivery")
        self.sent.append((str(target), str(text)))
        return "fake-receipt"
    async def send_segments(self, target, segments):
        self.sent_segments.append((str(target), list(segments)))
        return "fake-receipt-seg"
    async def friend_ids(self):
        return self.friends

def ev(sender=OWNER, text="/ping", mid=1, kind="private", subtype="friend"):
    return {"post_type": "message", "message_type": kind, "sub_type": subtype,
            "user_id": int(sender), "self_id": int(BOT), "message_id": mid,
            "message": [{"type": "text", "data": {"text": text}}]}

class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.db = q.new_db(self.path)
        self.api = FakeAPI()
        self.model_calls = []
        def model(alias, text):
            self.model_calls.append((alias, text))
            return "你好，请问明天下午方便交流吗？"
        self.chat_calls = []
        def chat(messages):
            self.chat_calls.append(messages)
            return "你好！我是虾爬子，今天想聊些什么？"
        self.agent = q.Agent(self.db, BOT, model, chat)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def bind(self):
        q.set_meta(self.db, "owner", OWNER)

    def add(self):
        self.db.execute("INSERT OR IGNORE INTO contacts VALUES (?,?,?)",
                        (TARGET, "测试好友", int(time.time())))

    async def test_nonowner_message_silent(self):
        self.bind()
        status = await self.agent.incoming(ev(STRANGER, "/ping", 10), self.api)
        self.assertEqual(status, "ignored")
        self.assertEqual(self.api.sent, [])

    async def test_unbound_silent_except_binding(self):
        status = await self.agent.incoming(ev(OWNER, "/ping", 11), self.api)
        self.assertEqual(status, "ignored")
        self.assertFalse(self.api.sent)

    async def test_pair_code_from_local_console(self):
        code = q.pair_create(self.db, now=1000)
        status = await self.agent.incoming(ev(OWNER, "/绑定 " + code, 12), self.api, now=1003)
        self.assertEqual(status, "paired")
        self.assertEqual(q.meta(self.db, "owner"), OWNER)
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)

    async def test_pair_wrong_code_rejected(self):
        q.pair_create(self.db, now=1000)
        result = await self.agent.incoming(ev(STRANGER, "/绑定 " + "A"*12, 13), self.api, now=1002)
        self.assertEqual(result, "rejected-pair")
        self.assertFalse(q.meta(self.db, "owner"))
        self.assertEqual(self.api.sent, [])

    async def test_pair_expired(self):
        code = q.pair_create(self.db, now=1000)
        result = await self.agent.incoming(ev(OWNER, "/绑定 " + code, 14), self.api, now=3000)
        self.assertEqual(result, "rejected-pair")
        self.assertEqual(self.api.sent, [])

    async def test_group_never_talks(self):
        self.bind()
        result = await self.agent.incoming(ev(OWNER, "/ping", 15, kind="group"), self.api)
        self.assertEqual(result, "ignored")
        self.assertFalse(self.api.sent)

    async def test_owner_plain_text_receives_natural_chat(self):
        self.bind()
        result = await self.agent.incoming(ev(OWNER, "你好", 16), self.api)
        self.assertEqual(result, "processed")
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)
        self.assertEqual(len(self.chat_calls), 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0], 2)

    async def test_ping_and_dedup(self):
        self.bind()
        once = await self.agent.incoming(ev(OWNER, "/ping", 17), self.api)
        twice = await self.agent.incoming(ev(OWNER, "/ping", 17), self.api)
        self.assertEqual((once, twice), ("processed", "duplicate"))
        self.assertEqual(len(self.api.sent), 1)

    async def test_friend_authorization_requires_friendship(self):
        self.bind()
        self.api.friends = set()
        result = await self.agent.incoming(ev(OWNER, "/授权 " + TARGET + " 测试好友", 18), self.api)
        self.assertEqual(result, "processed")
        self.assertFalse(self.db.execute("SELECT 1 FROM contacts").fetchone())
        self.assertIn("未执行", self.api.sent[0][1])

    async def test_authorize_friend(self):
        self.bind()
        await self.agent.incoming(ev(OWNER, "/授权 " + TARGET + " 测试好友", 19), self.api)
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM contacts").fetchone())
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)

    async def test_draft_only_sends_owner_notification(self):
        self.bind(); self.add()
        status = await self.agent.incoming(ev(OWNER, "/发 测试好友 问他明天下午有空吗", 20), self.api)
        self.assertEqual(status, "processed")
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)
        self.assertEqual(len(self.model_calls), 1)
        draft = self.db.execute("SELECT state FROM drafts").fetchone()
        self.assertEqual(draft["state"], "draft")

    async def test_natural_directive_drafts(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "帮我给测试好友发消息：问他明天下午有空吗", 21), self.api)
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)

    async def test_confirm_not_without_saved_draft(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "/确认 ABCDE123", 22), self.api)
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0][0], OWNER)

    async def test_confirm_sends_to_target_exactly_once(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "/发 测试好友 问候一下", 23), self.api)
        code=self.db.execute("SELECT code FROM drafts").fetchone()[0]
        self.api.sent.clear()
        result=await self.agent.incoming(ev(OWNER, "/确认 " + code, 24), self.api)
        self.assertEqual(result, "processed")
        self.assertEqual([x[0] for x in self.api.sent], [TARGET, OWNER])
        again=await self.agent.incoming(ev(OWNER, "/确认 " + code, 25), self.api)
        self.assertEqual(again, "processed")
        self.assertEqual([x[0] for x in self.api.sent], [TARGET, OWNER, OWNER])
        self.assertEqual(self.db.execute("SELECT state FROM drafts").fetchone()[0], "sent")

    async def test_unknown_send_result_fails_closed(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "/发 测试好友 询问情况", 26), self.api)
        code=self.db.execute("SELECT code FROM drafts").fetchone()[0]
        self.api.raise_on_send = True
        await self.agent.incoming(ev(OWNER, "/确认 " + code, 27), self.api)
        self.assertEqual(self.db.execute("SELECT state FROM drafts").fetchone()[0], "unknown")
        self.api.raise_on_send=False
        self.api.sent.clear()
        await self.agent.incoming(ev(OWNER, "/确认 " + code, 28), self.api)
        self.assertEqual([x[0] for x in self.api.sent], [OWNER])

    async def test_cancel_inhibits_sending(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "/发 测试好友 询问一下", 29), self.api)
        code=self.db.execute("SELECT code FROM drafts").fetchone()[0]
        await self.agent.incoming(ev(OWNER, "/取消", 30), self.api)
        self.api.sent.clear()
        await self.agent.incoming(ev(OWNER, "/确认 " + code, 31), self.api)
        self.assertEqual([x[0] for x in self.api.sent], [OWNER])
        self.assertEqual(self.db.execute("SELECT state FROM drafts").fetchone()[0], "cancelled")

    async def test_persistent_owner_and_draft(self):
        self.bind();self.add()
        await self.agent.incoming(ev(OWNER, "/发 测试好友 问一下时间", 32), self.api)
        db2=q.new_db(self.path)
        try:
            self.assertEqual(q.meta(db2, "owner"), OWNER)
            self.assertEqual(db2.execute("SELECT COUNT(*) FROM drafts").fetchone()[0],1)
            self.assertEqual(db2.execute("SELECT COUNT(*) FROM contacts").fetchone()[0],1)
        finally:
            db2.close()

    async def test_max_five_per_hour(self):
        self.bind();self.add()
        now=int(time.time())
        for i in range(5):
            self.db.execute("INSERT INTO drafts(code,recipient,alias,body,state,created,attempt_at) VALUES (?,?,?,?,?,?,?)",
                            (f"USED{i}", TARGET, "测试好友", "test", "sent", now-300, now-300))
        self.db.execute("INSERT INTO drafts(code,recipient,alias,body,state,created) VALUES (?,?,?,?,?,?)",
                        ("NEWCODE0", TARGET, "测试好友", "test", "draft", now))
        with self.assertRaises(q.GuardError):
            q.mark_attempt(self.db,"NEWCODE0",now)
        self.assertEqual(self.db.execute("SELECT state FROM drafts WHERE code='NEWCODE0'").fetchone()[0],"draft")

    async def test_self_message_not_triggered(self):
        self.bind()
        result=await self.agent.incoming(ev(BOT, "/ping", 33), self.api)
        self.assertEqual(result,"ignored")
        self.assertFalse(self.api.sent)

    def _fake_image(self, name="shot.png"):
        p = self.path.parent / name
        p.write_bytes(b"\x89PNG\r\n\x1a\n-fake-bytes-")
        return p

    async def test_inbound_image_routed_to_claude(self):
        self.bind()
        q.set_meta(self.db, "mode", "claude")
        img = self._fake_image()
        captured = []
        async def fake_reply(db, prompt):
            captured.append(prompt)
            return "我看完了这张图。"
        with mock.patch.object(q.code_bridge, "reply_async", new=fake_reply):
            event = ev(OWNER, "帮我看看这张图", 40)
            event["message"].append({"type": "image", "data":
                                    {"path": str(img), "file": "file:///" + img.as_posix(),
                                     "name": "shot.png"}})
            result = await self.agent.incoming(event, self.api)
        self.assertEqual(result, "processed")
        self.assertEqual(len(captured), 1)
        self.assertIn("主人随消息发来了 1 张图片", captured[0])
        self.assertIn(str(img), captured[0])
        self.assertEqual(self.api.sent, [(OWNER, "我看完了这张图。")])

    async def test_inbound_image_only_not_ignored(self):
        self.bind()
        q.set_meta(self.db, "mode", "claude")
        img = self._fake_image("only.png")
        captured = []
        async def fake_reply(db, prompt):
            captured.append(prompt)
            return "描述完成。"
        with mock.patch.object(q.code_bridge, "reply_async", new=fake_reply):
            event = ev(OWNER, "", 41)
            event["message"].append({"type": "image", "data": {"path": str(img)}})
            result = await self.agent.incoming(event, self.api)
        self.assertEqual(result, "processed")
        self.assertEqual(len(captured), 1)
        self.assertIn("主人随消息发来了 1 张图片", captured[0])
        self.assertIn(str(img), captured[0])

    async def test_outbound_image_marker_sent(self):
        self.bind()
        q.set_meta(self.db, "mode", "claude")
        out = self._fake_image("out.png")
        async def fake_reply(db, prompt):
            return "截图已生成\nQQ_SEND_IMAGE:" + str(out)
        with mock.patch.object(q.code_bridge, "reply_async", new=fake_reply):
            result = await self.agent.incoming(ev(OWNER, "把页面截图发我", 42), self.api)
        self.assertEqual(result, "processed")
        self.assertEqual(self.api.sent, [])
        self.assertEqual(len(self.api.sent_segments), 1)
        target, segments = self.api.sent_segments[0]
        self.assertEqual(target, OWNER)
        self.assertEqual(segments[0], {"type": "text", "data": {"text": "截图已生成"}})
        self.assertEqual(segments[1]["type"], "image")
        self.assertTrue(segments[1]["data"]["file"].startswith("file:///"))
        self.assertTrue(segments[1]["data"]["file"].endswith("out.png"))
        self.assertNotIn("QQ_SEND_IMAGE", segments[0]["data"]["text"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
