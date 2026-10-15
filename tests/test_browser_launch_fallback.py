import unittest
from types import SimpleNamespace
from unittest.mock import patch

from XianyuAutoAsync import XianyuLive


class BrowserLaunchFallbackTests(unittest.TestCase):
    def test_missing_bundled_browser_uses_installed_mac_chrome(self):
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = 'test'
        playwright = SimpleNamespace(chromium=SimpleNamespace(executable_path='/missing/chromium'))
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        with patch('os.path.exists', side_effect=lambda path: path == chrome):
            options = live._get_playwright_launch_options(playwright, [], '商品详情')
        self.assertEqual(options['executable_path'], chrome)
        self.assertNotIn('channel', options)
