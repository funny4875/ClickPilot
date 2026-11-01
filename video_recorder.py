"""Record a selected Chrome tab and convert the chosen region to MP4."""
import http.server
import json
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
overlay.addEventListener('pointerup',e=>{if(!start)return; e.preventDefault();e.stopPropagation();const x=Math.min(start[0],e.clientX),y=Math.min(start[1],e.clientY),w=Math.abs(e.clientX-start[0]),h=Math.abs(e.clientY-start[1]); if(w<4||h<4){start=null;box.style.display='none';return;} end({x:x/window.innerWidth,y:y/window.innerHeight,w:w/window.innerWidth,h:h/window.innerHeight});});'''

PAGE = r'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>ClickPilot 錄影</title><body style="font:18px sans-serif;padding:2em">
<h2>ClickPilot 分頁錄影</h2><p>請在分享視窗選擇剛才框選的 Chrome 分頁，並勾選「分享分頁音訊」。</p><button id="start">選擇分頁並開始錄影</button><p id="status">等待選擇分頁</p>
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

class TabVideoRecorder:
    def __init__(self, driver, stop_event):
        self.driver, self.stop_event = driver, stop_event
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

    def start(self):
        if self.state == 'paused':
            self._helper_call('window.captureResume()')
            self.state = 'recording'
            return
        if self.state != 'idle':
            raise RuntimeError('已有進行中的分頁錄影。')
        self.target = self.driver.current_window_handle
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
        self.region = region
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
            while not self.stop_event.is_set():
                state = self.driver.execute_script('return window.captureState')
                if state == 'recording': break
                if state == 'error': raise RuntimeError(self.driver.execute_script('return window.captureError()'))
                time.sleep(.2)
            else:
                raise RuntimeError('已停止等待分頁分享。')
            self._switch(self.target)
            self.state='recording'
        except Exception:
            self.cleanup(); raise

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
        output_dir = Path.home() / 'Videos' / 'ClickPilot'
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
