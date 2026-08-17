"""
自动确认发货模块。
用于处理订单的自动确认发货流程。
"""

import asyncio
import json
import time
import aiohttp
from contextlib import asynccontextmanager
from loguru import logger
from utils.xianyu_utils import generate_sign, trans_cookies


class SecureConfirm:
    """自动确认发货类"""

    def __init__(self, session, cookies_str, cookie_id, main_instance=None):
        """
        初始化确认发货实例

        Args:
            session: aiohttp会话对象
            cookies_str: Cookie字符串
            cookie_id: Cookie ID
            main_instance: 主实例对象（XianyuLive）
        """
        self.session = session
        self.cookies_str = cookies_str
        self.cookie_id = cookie_id
        self.main_instance = main_instance

        # 解析cookies
        self.cookies = trans_cookies(cookies_str) if cookies_str else {}

        # Token相关属性
        self.current_token = None
        self.last_token_refresh_time = 0
        self.token_refresh_interval = 3600  # 1小时

    def _safe_str(self, obj):
        """安全字符串转换"""
        try:
            return str(obj)
        except:
            return "无法转换的对象"

    async def _get_real_item_id(self):
        """从数据库中获取一个真实的商品ID"""
        try:
            from app.db_manager import db_manager
            
            # 获取该账号的商品列表
            items = db_manager.get_items_by_cookie(self.cookie_id)
            if items:
                # 返回第一个商品的ID
                item_id = items[0].get('item_id')
                if item_id:
                    logger.debug(f"【{self.cookie_id}】获取到真实商品ID: {item_id}")
                    return item_id
            
            # 如果该账号没有商品，尝试获取任意一个商品ID
            all_items = db_manager.get_all_items()
            if all_items:
                item_id = all_items[0].get('item_id')
                if item_id:
                    logger.debug(f"【{self.cookie_id}】使用其他账号的商品ID: {item_id}")
                    return item_id
            
            logger.warning(f"【{self.cookie_id}】数据库中没有找到任何商品ID")
            return None
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取真实商品ID失败: {self._safe_str(e)}")
            return None

    async def _update_config_cookies(self):
        """更新数据库中的Cookie配置"""
        try:
            from app.db_manager import db_manager
            # 更新数据库中的cookies
            db_manager.update_cookie_account_info(self.cookie_id, cookie_value=self.cookies_str)
            logger.debug(f"【{self.cookie_id}】已更新数据库中的Cookie")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】更新数据库Cookie失败: {self._safe_str(e)}")

    @asynccontextmanager
    async def _request_session(self):
        """在当前事件循环中提供可用的 HTTP session。

        账号运行时和 FastAPI 分别使用独立事件循环。手动完整发货
        可能从 FastAPI 循环调用账号实例，此时不能复用账号循环创建的
        aiohttp.ClientSession，否则 aiohttp 会报 timeout context 不在 task 中。
        """
        if not self.session:
            raise RuntimeError("Session未创建")

        current_loop = asyncio.get_running_loop()
        session_loop = getattr(self.session, "_loop", current_loop)
        session_closed = bool(getattr(self.session, "closed", False))

        if not session_closed and session_loop is current_loop:
            yield self.session
            return

        headers = dict(getattr(self.session, "headers", {}) or {})
        headers["cookie"] = self.cookies_str
        logger.warning(
            f"【{self.cookie_id}】HTTP Session不属于当前事件循环，"
            "本次确认发货使用独立Session"
        )
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as temporary_session:
            yield temporary_session


    async def auto_confirm(self, order_id, item_id=None, retry_count=0):
        """自动确认发货 - 使用真实商品ID刷新token"""
        if retry_count >= 4:  # 最多重试3次
            logger.error("自动确认发货失败，重试次数过多")
            return {"error": "自动确认发货失败，重试次数过多"}

        # 保存item_id供Token刷新使用
        if item_id:
            self._current_item_id = item_id
            logger.debug(f"【{self.cookie_id}】设置当前商品ID: {item_id}")

        # 确保session已创建
        if not self.session:
            raise Exception("Session未创建")

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.logistic.consign.dummy',
            'sessionOption': 'AutoLoginOnly',
        }

        data_val = '{"orderId":"' + order_id + '", "tradeText":"","picList":[],"newUnconsign":true}'
        data = {
            'data': data_val,
        }

        # 始终从最新的cookies中获取_m_h5_tk token（刷新后cookies会被更新）
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        if token:
            logger.info(f"已从Cookie读取签名令牌，长度: {len(token)}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            logger.info(f"【{self.cookie_id}】开始自动确认发货，订单ID: {order_id}")
            async with self._request_session() as request_session:
                async with request_session.post(
                    'https://h5api.m.goofish.com/h5/mtop.taobao.idle.logistic.consign.dummy/1.0/',
                    params=params,
                    data=data
                ) as response:
                    res_json = await response.json()

                    # 检查并更新Cookie
                    if 'set-cookie' in response.headers:
                        new_cookies = {}
                        for cookie in response.headers.getall('set-cookie', []):
                            if '=' in cookie:
                                name, value = cookie.split(';')[0].split('=', 1)
                                new_cookies[name.strip()] = value.strip()

                        # 更新cookies
                        if new_cookies:
                            self.cookies.update(new_cookies)
                            # 生成新的cookie字符串
                            self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                            # 更新数据库中的Cookie
                            await self._update_config_cookies()
                            logger.debug("已更新Cookie到数据库")

                    logger.info(f"【{self.cookie_id}】自动确认发货响应: {res_json}")

                    # 检查响应结果
                    if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                        logger.info(f"【{self.cookie_id}】✅ 自动确认发货成功，订单ID: {order_id}")
                        return {"success": True, "order_id": order_id}
                    else:
                        error_msg = res_json.get('ret', ['未知错误'])[0] if res_json.get('ret') else '未知错误'
                        logger.warning(f"【{self.cookie_id}】❌ 自动确认发货失败: {error_msg}")

                        return await self.auto_confirm(order_id, item_id, retry_count + 1)


        except Exception as e:
            logger.error(f"【{self.cookie_id}】自动确认发货API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)

            # 网络异常也进行重试
            if retry_count < 2:
                logger.info(f"【{self.cookie_id}】网络异常，准备重试...")
                return await self.auto_confirm(order_id, item_id, retry_count + 1)

            return {"error": f"网络异常: {self._safe_str(e)}", "order_id": order_id}
