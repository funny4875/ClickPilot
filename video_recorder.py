"""Record a selected Chrome tab and convert the chosen region to MP4."""
import http.server
import json
import math
import os
import secrets
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import imageio_ffmpeg
from selenium.common.exceptions import JavascriptException
from selenium.webdriver.common.by import By

SELECT_REGION = r'''window.__clickpilotSelection = null; const done = value => { window.__clickpilotSelection = {value}; };
const old = document.getElementById('__clickpilot_selector'); if (old) old.remove();
const overlay = document.createElement('div'); overlay.id='__clickpilot_selector';
overlay.style.cssText='position:fixed;inset:0;z-index:2147483647;cursor:crosshair;background:rgba(0,0,0,.24);touch-action:none;';
const hint=document.createElement('div'); hint.textContent='拖曳選取錄影範圍，按 Esc 取消';
hint.style.cssText='position:fixed;top:10px;left:50%;transform:translateX(-50%);background:#222;color:white;padding:10px 18px;font:16px sans-serif;pointer-events:none';
const box=document.createElement('div'); box.style.cssText='position:fixed;border:2px solid #00d9ff;background:rgba(0,180,255,.15);display:none;pointer-events:none;box-sizing:border-box';
overlay.append(hint,box); document.documentElement.append(overlay);
let start=null;
function end(value){ document.removeEventListener('keydown',key,true); overlay.remove(); delete window.__clickpilotCancelSelection; done(value); }
window.__clickpilotCancelSelection=()=>end(null);
function key(e){if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();end(null);}}
document.addEventListener('keydown',key,true);
overlay.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();start=[e.clientX,e.clientY];overlay.setPointerCapture(e.pointerId);box.style.display='block';});
overlay.addEventListener('pointermove',e=>{if(!start)return;const x=Math.min(start[0],e.clientX), y=Math.min(start[1],e.clientY); Object.assign(box.style,{left:x+'px',top:y+'px',width:Math.abs(e.clientX-start[0])+'px',height:Math.abs(e.clientY-start[1])+'px'});});
overlay.addEventListener('pointerup',e=>{if(!start)return; e.preventDefault();e.stopPropagation();const x=Math.min(start[0],e.clientX),y=Math.min(start[1],e.clientY),w=Math.abs(e.clientX-start[0]),h=Math.abs(e.clientY-start[1]); if(w<4||h<4){start=null;box.style.display='none';return;} end({x:Math.round(x),y:Math.round(y),w:Math.round(w),h:Math.round(h)});});'''

PAGE = r'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>ClickPilot 錄影</title><body style="font:18px sans-serif;padding:2em">
<h2>ClickPilot 分頁錄影</h2><p>正在自動錄製第一個分頁的畫面與聲音。</p><button id="start">開始錄影</button><p id="status">準備錄影</p>
<script>
let stream, recorder, uploads=Promise.resolve(), failure=null; window.captureState='waiting';
const status=document.querySelector('#status');
function fail(e){failure=String(e);window.captureState='error';status.textContent=failure;}
window.captureError=()=>failure;
document.querySelector('#start').onclick=async()=>{
 try {
  stream=await navigator.mediaDevices.getDisplayMedia({video:{displaySurface:'browser',frameRate:{ideal:30,max:30}},audio:true,preferCurrentTab:false});
  const video=stream.getVideoTracks()[0];
  if(video.getSettings().displaySurface!=='browser') throw Error('請選擇 Chrome 分頁，不能選擇視窗或整個螢幕。');
  if(!stream.getAudioTracks().length) throw Error('未取得分頁音訊，請重新開始並勾選分享分頁音訊。');
  let mime=['video/webm;codecs=vp8,opus','video/webm'].find(x=>MediaRecorder.isTypeSupported(x));
  recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:5000000});
  recorder.ondataavailable=e=>{if(e.data.size) uploads=uploads.then(async()=>{const r=await fetch('chunk',{method:'POST',body:e.data});if(!r.ok)throw Error('錄影資料寫入失敗');}).catch(fail);};
  recorder.onerror=e=>fail(e.error||'錄影失敗');
  video.onended=()=>{if(window.captureState!=='stopping' && window.captureState!=='finished')fail('分頁分享已中斷');};
  recorder.start(1000); window.captureState='recording'; status.textContent='錄影中，請回到原分頁。';
 } catch(e) {if(stream)stream.getTracks().forEach(t=>t.stop());fail(e.message||e);}
};
window.capturePause=()=>{if(recorder && recorder.state==='recording'){recorder.pause();window.captureState='paused';}else throw Error('目前沒有正在錄製的影片');};
window.captureResume=()=>{if(recorder && recorder.state==='paused'){recorder.resume();window.captureState='recording';}else throw Error('目前沒有暫停的錄影');};
window.captureStop=()=>new Promise((resolve,reject)=>{
 if(!recorder||recorder.state==='inactive'){reject(Error(failure||'錄影已中斷'));return;}
 window.captureState='stopping'; recorder.onstop=async()=>{try{await uploads;if(failure)throw Error(failure);stream.getTracks().forEach(t=>t.stop());window.captureState='finished';resolve(true);}catch(e){reject(e);}};recorder.stop();
});
</script></body></html>'''

def region_path():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ClickPilot' / 'last_video_region.json'


def validate_region(region):
    if not isinstance(region, dict) or any(isinstance(region.get(k), bool) or not isinstance(region.get(k), (int, float)) or not math.isfinite(region[k]) for k in ('x', 'y', 'w', 'h')):
        raise ValueError('錄影範圍必須包含有效的 x、y、w、h 數字')
    if region['x'] < 0 or region['y'] < 0 or region['w'] < 4 or region['h'] < 4:
        raise ValueError('x、y 必須為非負數，w、h 至少為 4')
    return {k: region[k] for k in ('x', 'y', 'w', 'h')}


def video_output_dir():
    return Path.home() / 'Videos' / 'ClickPilot'

def load_region():
    try:
        value = json.loads(region_path().read_text(encoding='utf-8'))
        return validate_region(value)
    except (OSError, ValueError, TypeError):
        return None


def save_region(region):
    region = validate_region(region)
    path = region_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(region), encoding='utf-8')


class TabVideoRecorder:
    def __init__(self, driver, stop_event, on_region_changed=None):
        self.driver, self.stop_event = driver, stop_event
        self.on_region_changed = on_region_changed
        self.server = self.helper = self.target = self.tmp = None
        self.state = 'idle'
        self.output = None

    def _switch(self, handle):
        self.driver.switch_to.window(handle)

    def _helper_call(self, script, *args):
        self._switch(self.helper)
        try:
            return self.driver.execute_script(script, *args)
        finally:
            if self.target in self.driver.window_handles:
                self._switch(self.target)

    def start(self, reuse_region=False, region=None):
        if self.state == 'paused':
            self._helper_call('window.captureResume()')
            self.state = 'recording'
            return
        if self.state != 'idle':
            raise RuntimeError('已有進行中的分頁錄影。')
        self.target = getattr(self.driver, '_clickpilot_first_tab', None)
        marker = getattr(self.driver, '_clickpilot_capture_marker', None)
        if not self.target or self.target not in self.driver.window_handles or not marker:
            raise RuntimeError('找不到程式開啟的第一個分頁，請重新開啟 Chrome。')
        self._switch(self.target)
        viewport = self.driver.execute_script('return {w:window.innerWidth,h:window.innerHeight}')
        if region is not None:
            region = validate_region(region)
        elif reuse_region:
            region = load_region()
            if region is None:
                # Older versions saved ratios; convert them using the current viewport.
                try:
                    legacy = json.loads(region_path().read_text(encoding='utf-8'))
                    if any(isinstance(legacy.get(k), bool) or not isinstance(legacy.get(k), (int, float)) or not math.isfinite(legacy[k]) for k in ('x','y','w','h')) or legacy['x'] < 0 or legacy['y'] < 0 or legacy['w'] <= 0 or legacy['h'] <= 0 or legacy['x'] + legacy['w'] > 1 or legacy['y'] + legacy['h'] > 1:
                        raise ValueError('invalid legacy region')
                    region = validate_region({'x':round(legacy['x']*viewport['w']), 'y':round(legacy['y']*viewport['h']), 'w':round(legacy['w']*viewport['w']), 'h':round(legacy['h']*viewport['h'])})
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    raise RuntimeError('沒有可用的上次錄影範圍，請先取消勾選並框選一次。')
        else:
            self.driver.execute_script(SELECT_REGION)
            selection = None
            try:
                while not self.stop_event.is_set():
                    selection = self.driver.execute_script('return window.__clickpilotSelection')
                    if selection is not None: break
                    time.sleep(.15)
            finally:
                if selection is None:
                    self.driver.execute_script("window.__clickpilotCancelSelection?.()")
            region = selection['value'] if selection else None
            if not region:
                raise RuntimeError('已取消選取錄影範圍。')
            region = validate_region(region)
        viewport = self.driver.execute_script('return {w:window.innerWidth,h:window.innerHeight}')
        if region['x'] + region['w'] > viewport['w'] or region['y'] + region['h'] > viewport['h']:
            raise ValueError('錄影範圍超出目前分頁可視區域，請調整視窗或範圍。')
        save_region(region)
        if self.on_region_changed: self.on_region_changed(region.copy())
        self.region = {'x': region['x']/viewport['w'], 'y': region['y']/viewport['h'], 'w': region['w']/viewport['w'], 'h': region['h']/viewport['h']}
        original_title = self.driver.execute_script('const t=document.title; document.title=arguments[0]; return t;', marker)
        self.tmp = tempfile.TemporaryDirectory(prefix='clickpilot-video-')
        self.source = Path(self.tmp.name) / 'capture.webm'
        self.source.touch()
        token = secrets.token_urlsafe(32)
        owner = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if self.path != '/' + token + '/': self.send_error(404); return
                data = PAGE.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_POST(self):
                if self.path != '/' + token + '/chunk': self.send_error(404); return
                size = int(self.headers.get('Content-Length','0'))
                if size <= 0 or size > 32*1024*1024: self.send_error(400); return
                with owner.source.open('ab') as f:
                    remaining = size
                    while remaining:
                        data = self.rfile.read(min(remaining, 65536))
                        if not data: break
                        f.write(data); remaining -= len(data)
                if remaining: self.send_error(400); return
                self.send_response(204); self.end_headers()
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        try:
            self.driver.switch_to.new_window('tab'); self.helper=self.driver.current_window_handle
            self.driver.get(f'http://127.0.0.1:{self.server.server_port}/{token}/')
            self.driver.find_element(By.ID,'start').click()
            deadline = time.monotonic() + 30
            while not self.stop_event.is_set() and time.monotonic() < deadline:
                state = self.driver.execute_script('return window.captureState')
                if state == 'recording': break
                if state == 'error': raise RuntimeError(self.driver.execute_script('return window.captureError()'))
                time.sleep(.2)
            else:
                raise RuntimeError('自動選取第一個分頁失敗或已取消，請重新開啟 Chrome 後再試。')
            self._switch(self.target)
            self.driver.execute_script('if(document.title===arguments[0]) document.title=arguments[1]', marker, original_title)
            self.state='recording'
        except Exception:
            self.cleanup()
            try: self.driver.execute_script('if(document.title===arguments[0]) document.title=arguments[1]', marker, original_title)
            except Exception: pass
            raise

    def pause(self):
        if self.state != 'recording': raise RuntimeError('沒有進行中的分頁錄影。')
        self._helper_call('window.capturePause()')
        self.state='paused'

    def finish(self):
        if self.state not in ('recording','paused'): raise RuntimeError('沒有進行中的分頁錄影。')
        self._switch(self.helper)
        self.driver.set_script_timeout(120)
        result = self.driver.execute_async_script("const done=arguments[arguments.length-1]; window.captureStop().then(()=>done(null),e=>done(String(e)))")
        if result: raise RuntimeError(result)
        if self.target in self.driver.window_handles: self._switch(self.target)
        output_dir = video_output_dir()
        output_dir.mkdir(parents=True,exist_ok=True)
        self.output = output_dir / (time.strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(3) + '.mp4')
        r=self.region
        # even dimensions are required by yuv420p, coordinates use viewport ratios
        crop=f"crop=trunc(iw*{r['w']}/2)*2:trunc(ih*{r['h']}/2)*2:trunc(iw*{r['x']}/2)*2:trunc(ih*{r['y']}/2)*2"
        cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-i',str(self.source),'-vf',crop,'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(self.output)]
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if proc.returncode: raise RuntimeError('影片編碼失敗：'+proc.stderr.decode('utf-8',errors='replace')[-2000:])
        output=self.output
        self.cleanup()
        return output

    def cleanup(self):
        if self.helper:
            try:
                self._switch(self.helper)
                self.driver.close()
            except Exception: pass
            self.helper=None
        if self.target:
            try: self._switch(self.target)
            except Exception: pass
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.server=None
        if self.tmp:
            self.tmp.cleanup(); self.tmp=None
        self.state='idle'
