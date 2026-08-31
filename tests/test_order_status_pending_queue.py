import time
import unittest
from unittest.mock import Mock

from app.order_status_handler import OrderStatusHandler


class OrderStatusPendingQueueTests(unittest.TestCase):
    def test_unrelated_pending_status_is_not_applied_by_fifo(self):
        handler = OrderStatusHandler()
        stale_message = {"1": {"10": {"reminderContent": "[退款成功，钱款已原路退返]"}}}
        handler._pending_system_messages["seller"] = [{
            "message": stale_message,
            "send_message": "[退款成功，钱款已原路退返]",
            "cookie_id": "seller",
            "msg_time": "2026-08-31 22:10:08",
            "new_status": "cancelled",
            "temp_order_id": "temp-old",
            "message_hash": hash(str(sorted(stale_message.items()))),
            "timestamp": 1,
        }]
        handler.update_order_status = Mock(return_value=True)
        new_order_message = {"1": "4274724498753.PNM", "2": "new-chat@goofish"}

        handler.on_order_id_extracted("new-order", "seller", new_order_message)

        handler.update_order_status.assert_not_called()
        self.assertEqual(len(handler._pending_system_messages["seller"]), 1)

    def test_matching_sid_buyer_and_item_can_bind_without_same_hash(self):
        handler = OrderStatusHandler()
        pending_message = {
            "1": "old.PNM",
            "2": "66007031665@goofish",
            "4": {
                "reminderContent": "[退款成功，钱款已原路退返]",
                "reminderUrl": (
                    "fleamarket://message_chat?itemId=1069825745099"
                    "&peerUserId=2207390817379"
                ),
            },
        }
        context = handler._extract_pending_match_context(pending_message)
        handler._pending_system_messages["seller"] = [{
            "message": pending_message,
            "send_message": "[退款成功，钱款已原路退返]",
            "cookie_id": "seller",
            "msg_time": "2026-09-01 10:00:00",
            "new_status": "cancelled",
            "temp_order_id": "temp-related",
            "message_hash": context["message_hash"],
            "sid": context["sid"],
            "buyer_id": context["buyer_id"],
            "item_id": context["item_id"],
            "timestamp": time.time(),
        }]
        handler.update_order_status = Mock(return_value=True)
        order_message = {
            "1": "new.PNM",
            "2": "66007031665@goofish",
            "4": {
                "reminderContent": "[已付款，待发货]",
                "reminderUrl": (
                    "fleamarket://message_chat?itemId=1069825745099"
                    "&peerUserId=2207390817379"
                ),
            },
        }

        handler.on_order_id_extracted("order-1", "seller", order_message)

        handler.update_order_status.assert_called_once()
        self.assertNotIn("seller", handler._pending_system_messages)


if __name__ == "__main__":
    unittest.main()
