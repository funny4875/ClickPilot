import json, os, queue, re, sys, threading, time, traceback, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC

JS = r'''if (!window.__recorder) {
 window.__recorder={events:[],active:true};
 const xp=e=>{let p=[]; while(e&&e.nodeType===1){let i=1,s=e; while(s=s.previousElementSibling) if(s.tagName===e.tagName)i++; p.unshift(e.tagName.toLowerCase()+'['+i+']'); e=e.parentElement} return '/'+p.join('/')};
 const name=e=>(e.innerText||e.getAttribute('aria-label')||e.placeholder||e.name||e.id||e.tagName).trim().slice(0,40);
 const add=(e,a,v)=>{if(!window.__recorder.active||!e.isTrusted)return; let x={name:name(e.target),action:a,xpath:xp(e.target),timeout:5}; if(v!==undefined)x.value=v; window.__recorder.events.push(x)};
 document.addEventListener('click',e=>add(e,'click'),true);
 document.addEventListener('change',e=>{if(e.target.matches('input,textarea')){add(e,'clear');add(e,'send_keys',e.target.type==='password'?'${PIN}':e.target.value)}},true);
 document.addEventListener('keydown',e=>{if(['Enter','Tab','Escape'].includes(e.key))add(e,'key',e.key.toUpperCase())},true);
} window.__recorder.active=arguments[0]; return window.__recorder.events.splice(0);'''

class App:
 def __init__(self, root):
  self.root=root; root.title('ClickPilot - Chrome 操作錄製器'); root.iconbitmap(str(Path(__file__).resolve().parent / 'assets' / 'icon.ico')); root.geometry('1100x700'); self.driver=None; self.state='idle'; self.q=queue.Queue(); self.stop_event=threading.Event()
  top=ttk.Frame(root,padding=8); top.pack(fill='x'); ttk.Label(top,text='網址').pack(side='left'); self.url=ttk.Entry(top); self.url.insert(0,'https://example.com'); self.url.pack(side='left',fill='x',expand=True,padx=6)
  self.buttons={}
  for text,cmd in [('開啟 Chrome',self.open_browser),('開始錄製',self.start),('暫停錄製',self.pause),('結束錄製',self.finish),('開啟腳本',self.load),('存檔',self.save)]:
   b=ttk.Button(top,text=text,command=cmd); b.pack(side='left',padx=2); self.buttons[text]=b
  bar=ttk.Frame(root,padding=(8,0)); bar.pack(fill='x'); self.runbtn=ttk.Button(bar,text='執行腳本',command=self.run); self.runbtn.pack(side='left'); self.count=ttk.Entry(bar,width=5); self.count.insert(0,'1'); self.count.pack(side='left',padx=5); ttk.Label(bar,text='次').pack(side='left'); self.stopbtn=ttk.Button(bar,text='停止執行',command=self.stop_event.set); self.stopbtn.pack(side='left',padx=10); self.status=ttk.Label(bar,text='準備就緒'); self.status.pack(side='left',padx=10)
  frame=ttk.Frame(root,padding=8); frame.pack(fill='both',expand=True); self.lines=tk.Text(frame,width=5,state='disabled',takefocus=0,bg='#eeeeee',wrap='none'); self.lines.grid(row=0,column=0,sticky='ns'); self.editor=tk.Text(frame,wrap='none',undo=True); self.editor.grid(row=0,column=1,sticky='nsew'); y=ttk.Scrollbar(frame,orient='vertical',command=self.scroll); self.ybar=y; y.grid(row=0,column=2,sticky='ns'); x=ttk.Scrollbar(frame,orient='horizontal',command=self.editor.xview); x.grid(row=1,column=1,sticky='ew'); self.editor.configure(yscrollcommand=self.yscroll,xscrollcommand=x.set); frame.rowconfigure(0,weight=1); frame.columnconfigure(1,weight=1); self.editor.bind('<<Modified>>',self.modified); self.refresh(); root.after(150,self.poll); root.protocol('WM_DELETE_WINDOW',self.close)
 def scroll(self,*args): self.editor.yview(*args); self.lines.yview(*args)
 def yscroll(self,*args): self.ybar.set(*args); self.lines.yview_moveto(args[0])
 def modified(self,event=None):
  if self.editor.edit_modified():
   n=int(self.editor.index('end-1c').split('.')[0]); self.lines.config(state='normal'); self.lines.delete('1.0','end'); self.lines.insert('1.0','\n'.join(map(str,range(1,n+1)))); self.lines.config(state='disabled'); self.editor.edit_modified(False)
 def refresh(self):
  connected=self.driver is not None
  for k,enabled in {'開啟 Chrome':self.state=='idle','開始錄製':connected and self.state in ('idle','paused'),'暫停錄製':self.state=='recording','結束錄製':self.state in ('recording','paused'),'開啟腳本':self.state=='idle','存檔':self.state in ('idle','paused')}.items(): self.buttons[k].config(state='normal' if enabled else 'disabled')
  self.buttons['開始錄製'].config(text='繼續錄製' if self.state=='paused' else '開始錄製'); self.runbtn.config(state='normal' if connected and self.state=='idle' else 'disabled'); self.stopbtn.config(state='normal' if self.state=='running' else 'disabled')
 def worker(self,fn): threading.Thread(target=fn,daemon=True).start()
 def open_browser(self):
  url=self.url.get().strip()
  if not re.match(r'^https?://',url): messagebox.showerror('網址錯誤','請輸入 http:// 或 https:// 網址'); return
  self.state='busy'; self.refresh()
  def work():
   try:
    if self.driver: self.driver.quit()
    self.driver=ChromeDriver(); self.driver.get(url); self.q.put(('state','idle','Chrome 已開啟'))
   except Exception as e: self.driver=None; self.q.put(('error',str(e)))
  self.worker(work)
 def start(self):
  self.state='recording'; self.refresh(); self.status.config(text='錄製中'); self.worker(self.record)
 def record(self):
  try:
   while self.state=='recording':
    events=self.driver.execute_script(JS,True)
    if events:self.q.put(('events',events))
    time.sleep(.2)
   events=self.driver.execute_script(JS,False)
   if events:self.q.put(('events',events))
  except Exception as e:self.q.put(('error',str(e)))
  finally:self.q.put(('record_done',))
 def pause(self): self.state='pausing'; self.refresh(); self.status.config(text='正在暫停')
 def finish(self):
  if self.state=='recording': self.state='finishing'; self.status.config(text='正在結束錄製')
  else: self.state='idle'; self.status.config(text='錄製完成')
  self.refresh()
 def save(self):
  p=filedialog.asksaveasfilename(defaultextension='.jsonl',filetypes=[('JSON Lines','*.jsonl'),('所有檔案','*.*')]);
  if p:
   with open(p,'w',encoding='utf-8') as f:f.write(self.editor.get('1.0','end-1c'))
 def load(self):
  p=filedialog.askopenfilename(filetypes=[('腳本','*.jsonl *.txt *.json'),('所有檔案','*.*')]);
  if p:
   with open(p,encoding='utf-8-sig') as f: data=f.read()
   self.editor.delete('1.0','end'); self.editor.insert('1.0',data)
 def run(self):
  try:
   count=int(self.count.get()); assert count>0
   steps=[json.loads(line) for line in self.editor.get('1.0','end-1c').splitlines() if line.strip()]; assert steps
   for s in steps:
    assert s['action'] in ('click','clear','send_keys','key') and s['xpath'] and float(s.get('timeout',5))>0
  except Exception as e: messagebox.showerror('腳本錯誤',f'請檢查執行次數及每行 JSON 格式：{e}'); return
  names=set(re.findall(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}',json.dumps(steps,ensure_ascii=False))); values={}
  for name in names:
   v=simpledialog.askstring('變數',f'請輸入 {name} 的值',show='*',parent=self.root)
   if v is None:return
   values[name]=v
  self.stop_event.clear(); self.state='running'; self.refresh()
  def work():
   try:
    for i in range(count):
     for j,s in enumerate(steps):
      if self.stop_event.is_set(): self.q.put(('state','idle','已停止執行')); return
      self.q.put(('status',f'第 {i+1}/{count} 次，第 {j+1}/{len(steps)} 步：{s.get("name","")}'))
      try:
       el=WebDriverWait(self.driver,float(s.get('timeout',5)),poll_frequency=.2).until(EC.presence_of_element_located((By.XPATH,s['xpath'])))
      except TimeoutException:
       raise RuntimeError(f'第 {i+1} 次、第 {j+1} 步「{s.get("name", "")}」等待元件超過 {s.get("timeout", 5)} 秒：{s["xpath"]}') from None
      action=s['action']; value=str(s.get('value',''))
      for n,v in values.items():value=value.replace('${'+n+'}',v)
      if action=='click':el.click()
      elif action=='clear':el.clear()
      elif action=='send_keys':el.send_keys(value)
      else:el.send_keys(getattr(Keys,value.upper()))
    self.q.put(('state','idle','執行完成'))
   except Exception as e:self.q.put(('error',f'執行失敗：{e}'))
  self.worker(work)
 def poll(self):
  try:
   while True:
    m=self.q.get_nowait()
    if m[0]=='events':
     for s in m[1]:
      if self.editor.get('1.0','end-1c') and not self.editor.get('1.0','end-1c').endswith('\n'):self.editor.insert('end','\n')
      self.editor.insert('end',json.dumps(s,ensure_ascii=False)+'\n'); self.editor.see('end')
    elif m[0]=='record_done':
     if self.state=='pausing': self.state='paused'; self.status.config(text='已暫停')
     elif self.state=='finishing': self.state='idle'; self.status.config(text='錄製完成')
     self.refresh()
    elif m[0]=='status':self.status.config(text=m[1])
    elif m[0]=='state':self.state=m[1]; self.status.config(text=m[2]); self.refresh()
    elif m[0]=='error':self.state='idle'; self.refresh(); self.status.config(text='發生錯誤'); messagebox.showerror('錯誤',m[1])
  except queue.Empty:pass
  self.root.after(150,self.poll)
 def close(self):
  self.stop_event.set(); self.state='closing'
  if self.driver:
   try:self.driver.quit()
   except Exception:pass
  self.root.destroy()

if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='--diagnose-chrome':
  result=Path(sys.argv[2])
  try:
   driver=ChromeDriver()
   try:
    driver.get('data:text/html,<title>ClickPilot test</title>')
    result.write_text('OK: '+driver.title,encoding='utf-8')
   finally: driver.quit()
  except Exception:
   result.write_text(traceback.format_exc(),encoding='utf-8')
 else: App(tk.Tk()).root.mainloop()

