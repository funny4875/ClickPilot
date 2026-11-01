"""Script parsing, playback and browser recording for ClickPilot.

Recorder and clipboard handling adapted from funny4875/DocPilot script_engine.py.
"""
import ctypes
import json
import math
import time
import win32clipboard
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (StaleElementReferenceException,
    ElementClickInterceptedException, ElementNotInteractableException)

RECORDER = r'''(() => {
 if (window.__docRecorder) return;
 window.__docRecorder = true; window.__docRecording = true;
 function path(el) {
   if (el.id && document.querySelectorAll('[id="' + CSS.escape(el.id) + '"]').length === 1)
     return '//*[@id=' + JSON.stringify(el.id) + ']';
   let parts = [];
   while (el && el.nodeType === 1) {
     let n = 1, s = el.previousElementSibling;
     while (s) { if (s.tagName === el.tagName) n++; s = s.previousElementSibling; }
     parts.unshift(el.tagName.toLowerCase() + '[' + n + ']'); el = el.parentElement;
   }
   return '/' + parts.join('/');
 }
 function record(obj) { console.error('__DOC_ACTION__' + JSON.stringify(obj)); }
 document.addEventListener('click', e => {
   if (window.__docRecording && e.isTrusted && e.target instanceof Element) record({action:'click', xpath:path(e.target)});
 }, true);
 let saved = new WeakMap();
 if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) saved.set(document.activeElement, document.activeElement.value);
 document.addEventListener('focusin', e => {
   if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) saved.set(e.target, e.target.value);
 }, true);
 function saveInput(el) {
   if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) return;
   if (['checkbox','radio','file','button','submit'].includes(el.type)) return;
   if (saved.get(el) === el.value) return;
   saved.set(el, el.value);
   record({action:'clear', xpath:path(el)});
   record({action:'send_keys', xpath:path(el), value:el.type === 'password' ? '${PIN}' : el.value});
 }
 window.__docFlush = () => { if (window.__docRecording) saveInput(document.activeElement); };
 document.addEventListener('paste', e => {
   if (!window.__docRecording || !e.isTrusted || !(e.target instanceof Element)) return;
   const el = e.target;
   if (!e.clipboardData || !e.clipboardData.types.includes('text/plain')) {
     record({action:'paste', xpath:path(el), value:'', error:'剪貼簿沒有可錄製的純文字'});
     return;
   }
   if ((el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) && el.value && saved.get(el) !== el.value)
     saveInput(el);
   record({action:'paste', xpath:path(el), value:el.type === 'password' ? '${PIN}' : e.clipboardData.getData('text/plain')});
   el.addEventListener('input', () => { saved.set(el, el.value); }, {once:true});
 }, true);
 document.addEventListener('change', e => {
   if (window.__docRecording && e.isTrusted) saveInput(e.target);
 }, true);
 document.addEventListener('keydown', e => {
   if (window.__docRecording && e.isTrusted && e.key === 'Enter' && e.target instanceof Element)
     { saveInput(e.target); record({action:'key', xpath:path(e.target), value:'ENTER'}); }
 }, true);
})();'''


def paste_text(element, value):
    """Save clipboard data before temporarily replacing it with paste text."""
    user32 = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    kernel.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel.GlobalSize.restype = ctypes.c_size_t
    kernel.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = ctypes.c_void_p
    kernel.GlobalFree.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    backup = []
    win32clipboard.OpenClipboard()
    try:
        fmt = 0
        while True:
            fmt = win32clipboard.EnumClipboardFormats(fmt)
            if not fmt:
                break
            # GDI and metafile handles are not global memory and cannot be copied safely here.
            if fmt in (2, 3, 9, 14):
                raise RuntimeError('剪貼簿包含圖片或其他無法安全還原的格式；請先複製純文字再執行。')
            handle = user32.GetClipboardData(fmt)
            size = kernel.GlobalSize(handle) if handle else 0
            ptr = kernel.GlobalLock(handle) if size else None
            if not ptr:
                raise RuntimeError(f'無法備份剪貼簿格式 {fmt}，已停止貼上。')
            try:
                backup.append((fmt, ctypes.string_at(ptr, size)))
            finally:
                kernel.GlobalUnlock(handle)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(value, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    try:
        element.click()
        element.send_keys(Keys.CONTROL, 'v')
    finally:
        win32clipboard.OpenClipboard()
        try:
            unchanged = (win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT) and
                         win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) == value)
            if unchanged:
                win32clipboard.EmptyClipboard()
                for fmt, data in backup:
                    handle = kernel.GlobalAlloc(2, len(data))
                    if not handle:
                        raise RuntimeError('還原剪貼簿時記憶體不足。')
                    ptr = kernel.GlobalLock(handle)
                    if not ptr:
                        kernel.GlobalFree(handle)
                        raise RuntimeError('無法還原剪貼簿。')
                    ctypes.memmove(ptr, data, len(data))
                    kernel.GlobalUnlock(handle)
                    if not user32.SetClipboardData(fmt, handle):
                        kernel.GlobalFree(handle)
                        raise RuntimeError(f'無法還原剪貼簿格式 {fmt}。')
        finally:
            win32clipboard.CloseClipboard()


def parse_script(content):
    steps = []
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        try:
            step = json.loads(line)
            if not isinstance(step, dict) or step.get('action') not in ('click', 'clear', 'send_keys', 'paste', 'key', 'wait', 'wait_for', 'video_start', 'video_pause', 'video_stop'):
                raise ValueError('需指定有效的 action')
            action = step['action']
            if action not in ('wait', 'video_start', 'video_pause', 'video_stop') and (not isinstance(step.get('xpath'), str) or not step['xpath'].strip()):
                raise ValueError('需指定有效的 xpath')
            if 'name' in step and not isinstance(step['name'], str):
                raise ValueError('name 必須是文字')
            if step.get('error'):
                raise ValueError(str(step['error']))
            if action in ('send_keys', 'paste', 'key') and not isinstance(step.get('value'), str):
                raise ValueError('需指定文字 value')
            if action == 'key' and step['value'].upper() not in ('ENTER', 'TAB', 'ESCAPE'):
                raise ValueError('key 僅支援 ENTER、TAB、ESCAPE')
            for key in ('seconds', 'timeout'):
                if key in step:
                    val = step[key]
                    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0 or (key == 'timeout' and val == 0):
                        raise ValueError(f'{key} 必須是有效的非負秒數，timeout 須大於 0')
            if action == 'wait' and 'seconds' not in step:
                raise ValueError('wait 需指定 seconds')
            steps.append((number, step))
        except (ValueError, TypeError) as exc:
            raise ValueError(f'第 {number} 行格式錯誤：{exc}') from exc
    if not steps:
        raise ValueError('腳本沒有執行步驟。')
    return steps


class Stopped(Exception):
    pass


def run_script(driver, steps, count, variables, stop, progress):
    from video_recorder import TabVideoRecorder
    recorder = TabVideoRecorder(driver, stop)
    try:
        _run_script(driver, steps, count, variables, stop, progress, recorder)
        if recorder.state != 'idle':
            raise RuntimeError('腳本結束時分頁錄影尚未結束，請加入結束錄影指令。')
        return recorder.output
    finally:
        if recorder.state != 'idle':
            try:
                recorder.finish()
            except Exception:
                recorder.cleanup()


def _run_script(driver, steps, count, variables, stop, progress, recorder):
    for cycle in range(1, count + 1):
        for line, step in steps:
            if stop.is_set():
                raise Stopped()
            action = step['action']
            progress(cycle, line, step)
            try:
                if action == 'video_start':
                    recorder.start()
                    continue
                if action == 'video_pause':
                    recorder.pause()
                    continue
                if action == 'video_stop':
                    output = recorder.finish()
                    progress(cycle, line, {'name': f'影片已儲存：{output}'})
                    continue
                if action == 'wait':
                    if stop.wait(step['seconds']):
                        raise Stopped()
                    continue
                deadline = time.monotonic() + step.get('timeout', 5)
                value = step.get('value', '')
                for name, replacement in variables.items():
                    value = value.replace('${' + name + '}', replacement)
                while True:
                    if stop.is_set():
                        raise Stopped()
                    try:
                        elements = driver.find_elements(By.XPATH, step['xpath'])
                        element = next((e for e in elements if e.is_displayed() and e.is_enabled()), None)
                        if element is not None:
                            if action == 'wait_for': break
                            if action == 'click': element.click()
                            elif action == 'clear': element.clear()
                            elif action == 'send_keys': element.send_keys(value)
                            elif action == 'paste': paste_text(element, value)
                            elif action == 'key': element.send_keys(getattr(Keys, value.upper()))
                            break
                    except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
                        pass
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"等待可見且可操作的元件超過 {step.get('timeout', 5)} 秒：{step['xpath']}")
                    if stop.wait(min(.2, remaining)):
                        raise Stopped()

            except Stopped:
                raise
            except Exception as exc:
                raise RuntimeError(f"第 {cycle} 次、第 {line} 行（{step.get('name') or action}）失敗：{exc}") from exc


def start_recording(driver):
    identifier = driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': RECORDER})['identifier']
    try:
        driver.execute_script(RECORDER + '; window.__docRecording = true;')
        driver.get_log('browser')
    except Exception:
        driver.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': identifier})
        raise
    return identifier


def read_recording(driver):
    actions = []
    marker = '__DOC_ACTION__'
    for entry in driver.get_log('browser'):
        message = entry.get('message', '')
        if marker not in message:
            continue
        try:
            payload = json.loads(message[message.index('"' + marker):])
            action = json.loads(payload[len(marker):])
            action.setdefault('name', '')
            action.setdefault('timeout', 5)
            actions.append(action)
        except (ValueError, TypeError):
            continue
    return actions


def stop_recording(driver, identifier):
    driver.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': identifier})
    driver.execute_script('if (window.__docFlush) window.__docFlush(); window.__docRecording = false;')
