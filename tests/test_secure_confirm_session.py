import asyncio
import unittest
from unittest.mock import patch

from app.secure_confirm import SecureConfirm


class _FakeResponse:
    def __init__(self):
        self.headers = {}

    async def json(self):
        return {"ret": ["SUCCESS::调用成功"]}


class _FakeRequestContext:
    async def __aenter__(self):
        return _FakeResponse()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeSession:
    def __init__(self, loop, headers=None, timeout=None):
        self._loop = loop
        self.headers = headers or {}
        self.timeout = timeout
        self.closed = False
        self.post_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return _FakeRequestContext()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closed = True
        return False


class SecureConfirmSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_session_created_on_current_loop(self):
        session = _FakeSession(asyncio.get_running_loop(), {"cookie": "original"})
        confirm = SecureConfirm(
            session,
            "_m_h5_tk=token_123; sid=value",
            "seller",
        )

        result = await confirm.auto_confirm("order-1", "item-1")

        self.assertTrue(result["success"])
        self.assertEqual(len(session.post_calls), 1)
        self.assertFalse(session.closed)

    async def test_cross_loop_session_uses_temporary_session(self):
        source_session = _FakeSession(object(), {"User-Agent": "test", "cookie": "old"})
        temporary_sessions = []

        def create_temporary_session(headers=None, timeout=None):
            session = _FakeSession(asyncio.get_running_loop(), headers, timeout)
            temporary_sessions.append(session)
            return session

        confirm = SecureConfirm(
            source_session,
            "_m_h5_tk=token_123; sid=value",
            "seller",
        )

        with patch("app.secure_confirm.aiohttp.ClientSession", create_temporary_session):
            result = await confirm.auto_confirm("order-1", "item-1")

        self.assertTrue(result["success"])
        self.assertEqual(source_session.post_calls, [])
        self.assertEqual(len(temporary_sessions), 1)
        self.assertEqual(len(temporary_sessions[0].post_calls), 1)
        self.assertEqual(
            temporary_sessions[0].headers["cookie"],
            "_m_h5_tk=token_123; sid=value",
        )
        self.assertTrue(temporary_sessions[0].closed)


if __name__ == "__main__":
    unittest.main()
