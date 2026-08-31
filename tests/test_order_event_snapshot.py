import unittest
from unittest.mock import Mock, patch

from XianyuAutoAsync import XianyuLive


class OrderEventSnapshotTests(unittest.TestCase):
    def test_extracts_supported_transaction_status(self):
        message = {
            "1": {
                "10": {
                    "reminderContent": "[我已付款，等待你发货]",
                },
            },
        }

        self.assertEqual(
            XianyuLive._extract_order_event_status(message),
            "pending_ship",
        )

    def test_delivery_reminder_marks_order_pending_ship(self):
        message = {
            "1": {
                "10": {
                    "reminderContent": "[记得及时发货]",
                    "redReminder": "等待卖家发货",
                },
            },
        }

        self.assertEqual(
            XianyuLive._extract_order_event_status(message),
            "pending_ship",
        )

    def test_flattened_paid_event_extracts_status_and_context(self):
        message = {
            "1": "4274724498753.PNM",
            "2": "66007031665@goofish",
            "4": {
                "reminderContent": "[已付款，待发货]",
                "reminderUrl": (
                    "fleamarket://message_chat?itemId=1069825745099"
                    "&peerUserId=2207390817379&sid=66007031665"
                ),
                "senderUserId": "2207390817379",
                "senderNick": "买家",
            },
            "5": 1788191496000,
        }

        self.assertEqual(XianyuLive._extract_order_event_status(message), "pending_ship")
        context = XianyuLive._extract_order_event_context(message)
        self.assertEqual(context["buyer_id"], "2207390817379")
        self.assertEqual(context["item_id"], "1069825745099")
        self.assertEqual(context["chat_id"], "66007031665")
        self.assertEqual(context["create_time"], 1788191496000)

    def test_peer_user_id_has_priority_over_sender_user_id(self):
        message = {
            "1": "4274724498753.PNM",
            "2": "66007031665@goofish",
            "4": {
                "senderUserId": "system-or-self",
                "reminderUrl": (
                    "fleamarket://message_chat?itemId=1069825745099"
                    "&peerUserId=2207390817379"
                ),
            },
        }

        context = XianyuLive._extract_order_event_context(message)
        self.assertEqual(context["buyer_id"], "2207390817379")

    def test_new_rating_prompt_marks_order_completed(self):
        message = {
            "1": {
                "10": {
                    "reminderContent": "快给ta一个评价吧～",
                },
            },
        }

        self.assertEqual(XianyuLive._extract_order_event_status(message), "completed")

    def test_red_reminder_marks_order_completed(self):
        message = {
            "1": {
                "10": {
                    "reminderContent": "[我完成了评价]",
                    "redReminder": "交易成功",
                },
            },
        }

        self.assertEqual(XianyuLive._extract_order_event_status(message), "completed")
        self.assertTrue(XianyuLive._is_rate_completion_event(message))

    def test_rating_prompt_is_not_completion_receipt(self):
        message = {"1": {"10": {"reminderContent": "快给ta一个评价吧～"}}}
        self.assertFalse(XianyuLive._is_rate_completion_event(message))

    def test_saves_snapshot_when_order_detail_is_unavailable(self):
        fake_db = Mock()
        fake_db.get_item_info.return_value = {"item_price": "¥0.01"}
        fake_db.get_order_by_id.return_value = None
        fake_db.insert_or_update_order.return_value = True
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = "2217097925130"
        message = {
            "1": {
                "2": "65134820995@goofish",
                "10": {
                    "reminderContent": "[我已拍下，待付款]",
                },
            },
        }

        with patch("app.db_manager.db_manager", fake_db):
            saved = live._save_order_event_snapshot(
                order_id="3315714027267035666",
                message=message,
                item_id="1070863591807",
                buyer_id="2214686388912",
            )

        self.assertTrue(saved)
        fake_db.insert_or_update_order.assert_called_once_with(
            order_id="3315714027267035666",
            item_id="1070863591807",
            buyer_id="2214686388912",
            quantity="1",
            amount="0.01",
            order_status="processing",
            cookie_id="2217097925130",
            created_at=None,
            chat_id="65134820995",
        )

    def test_existing_order_details_are_not_overwritten_by_snapshot_defaults(self):
        fake_db = Mock()
        fake_db.get_item_info.return_value = {"item_price": "80"}
        fake_db.get_order_by_id.return_value = {
            "item_id": "item-1",
            "buyer_id": "buyer-1",
            "quantity": "3",
            "amount": "72",
            "created_at": "2026-08-05 18:47:41",
        }
        fake_db.insert_or_update_order.return_value = True
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = "seller"

        with patch("app.db_manager.db_manager", fake_db):
            saved = live._save_order_event_snapshot(
                order_id="order-1",
                message={
                    "1": {
                        "2": "chat-1@goofish",
                        "10": {"reminderContent": "[你已发货]"},
                    },
                },
                item_id="item-1",
                buyer_id="buyer-1",
            )

        self.assertTrue(saved)
        fake_db.insert_or_update_order.assert_called_once_with(
            order_id="order-1",
            item_id=None,
            buyer_id=None,
            quantity=None,
            amount=None,
            order_status="shipped",
            cookie_id="seller",
            created_at=None,
            chat_id="chat-1",
        )

    def test_saves_flattened_paid_event_snapshot(self):
        fake_db = Mock()
        fake_db.get_item_info.return_value = {"item_price": "7.99"}
        fake_db.get_order_by_id.return_value = None
        fake_db.insert_or_update_order.return_value = True
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = "seller"
        message = {
            "1": "4274724498753.PNM",
            "2": "66007031665@goofish",
            "4": {
                "reminderContent": "[已付款，待发货]",
                "reminderUrl": "fleamarket://message_chat?itemId=1069825745099",
                "senderUserId": "2207390817379",
            },
            "5": 1788191496000,
        }

        with patch("app.db_manager.db_manager", fake_db):
            saved = live._save_order_event_snapshot(
                order_id="3316391978143007163",
                message=message,
                item_id="1069825745099",
                buyer_id="2207390817379",
            )

        self.assertTrue(saved)
        call = fake_db.insert_or_update_order.call_args.kwargs
        self.assertEqual(call["order_status"], "pending_ship")
        self.assertEqual(call["chat_id"], "66007031665")
        self.assertEqual(call["item_id"], "1069825745099")
        self.assertEqual(call["buyer_id"], "2207390817379")

    def test_ignores_non_transaction_messages(self):
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = "seller"

        self.assertFalse(
            live._save_order_event_snapshot(
                order_id="order-1",
                message={"1": {"10": {"reminderContent": "你好"}}},
            )
        )


if __name__ == "__main__":
    unittest.main()
