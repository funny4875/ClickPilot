import threading
import time
import unittest
from unittest.mock import patch
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import script_engine


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options = Options()
        options.add_argument('--headless=new')
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        cls.driver = WebDriver(options=options)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def setUp(self):
        self.driver.get('data:text/html,<input id="field"><button id="go">Go</button>')

    def test_record_input_before_enter_and_pause(self):
        ident = script_engine.start_recording(self.driver)
        field = self.driver.find_element(By.ID, 'field')
        field.click()
        field.send_keys('hello', Keys.ENTER)
        actions = script_engine.read_recording(self.driver)
        self.assertEqual([a['action'] for a in actions], ['click', 'clear', 'send_keys', 'key'])
        self.assertEqual(actions[2]['value'], 'hello')
        script_engine.stop_recording(self.driver, ident)
        field.send_keys('x', Keys.ENTER)
        self.assertEqual(script_engine.read_recording(self.driver), [])

    def test_stop_flushes_focused_input(self):
        ident = script_engine.start_recording(self.driver)
        field = self.driver.find_element(By.ID, 'field')
        field.click()
        field.send_keys('unfinished')
        script_engine.stop_recording(self.driver, ident)
        actions = script_engine.read_recording(self.driver)
        self.assertEqual([a['action'] for a in actions], ['click', 'clear', 'send_keys'])
        self.assertEqual(actions[-1]['value'], 'unfinished')

    def test_record_across_navigation(self):
        ident = script_engine.start_recording(self.driver)
        try:
            self.driver.find_element(By.ID, 'go').click()
            self.driver.get('data:text/html,<input id="second">')
            field = self.driver.find_element(By.ID, 'second')
            field.click()
            field.send_keys('next', Keys.ENTER)
            actions = script_engine.read_recording(self.driver)
            self.assertEqual([a['action'] for a in actions], ['click', 'click', 'clear', 'send_keys', 'key'])
            self.assertEqual(actions[3]['value'], 'next')
        finally:
            script_engine.stop_recording(self.driver, ident)

    def test_paste_dispatch_and_validation(self):
        content = '{"action":"paste","xpath":"//*[@id=\'field\']","value":"${TEXT}"}'
        with patch('script_engine.paste_text') as paste:
            script_engine.run_script(self.driver, script_engine.parse_script(content), 1, {'TEXT':'text'}, threading.Event(), lambda *a: None)
            self.assertEqual(paste.call_args.args[1], 'text')
        with self.assertRaisesRegex(ValueError, '第 1 行'):
            script_engine.parse_script('{"action":"send_keys","xpath":"//input"}')

    def test_wait_for_visible_enabled_and_actions(self):
        self.driver.execute_script("""document.body.innerHTML = `<input class="target" style="display:none"><input class="target" disabled><button id="result">Go</button>`; document.querySelector('#result').onclick = () => document.querySelector('#result').textContent = document.querySelectorAll('.target')[1].value; setTimeout(()=>document.querySelectorAll('.target')[1].disabled=false, 600);""")
        content = '''# comment
{"action":"wait_for","xpath":"//input[@class='target']","timeout":3}
{"action":"clear","xpath":"//input[@class='target']"}
{"action":"send_keys","xpath":"//input[@class='target']","value":"${TEXT}"}
{"action":"key","xpath":"//input[@class='target']","value":"TAB"}
{"action":"click","xpath":"//*[@id='result']"}
{"action":"wait","seconds":0.1}'''
        start = time.monotonic()
        script_engine.run_script(self.driver, script_engine.parse_script(content), 1, {'TEXT': 'hello'}, threading.Event(), lambda *a: None)
        self.assertGreater(time.monotonic()-start, .4)
        self.assertEqual(self.driver.find_element(By.ID, 'result').text, 'hello')

    def test_timeout_and_stop(self):
        steps = script_engine.parse_script('# heading\n{"name":"missing","action":"click","xpath":"//*[@id=\'missing\']","timeout":0.4}')
        with self.assertRaisesRegex(RuntimeError, '第 1 次、第 2 行（missing）失敗'):
            script_engine.run_script(self.driver, steps, 1, {}, threading.Event(), lambda *a: None)
        stop = threading.Event()
        threading.Timer(.3, stop.set).start()
        start = time.monotonic()
        with self.assertRaises(script_engine.Stopped):
            script_engine.run_script(self.driver, script_engine.parse_script('{"action":"wait","seconds":10}'), 1, {}, stop, lambda *a: None)
        self.assertLess(time.monotonic()-start, 2)

if __name__ == '__main__':
    unittest.main()
