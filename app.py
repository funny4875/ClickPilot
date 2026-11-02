import json, math, os, queue, re, secrets, sys, threading, time, traceback, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from selenium.webdriver.chrome.options import Options
import script_engine
import video_recorder
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC


class App:
 def __init__(self, root):
  self.root=root; root.title('ClickPilot - Chrome 操作錄製器'); root.iconbitmap(str(Path(__file__).resolve().parent / 'assets' / 'icon.ico')); root.geometry('1100x700'); self.driver=None; self.drivers=[]; self.state='idle'; self.q=queue.Queue(); self.stop_event=threading.Event()
  top=ttk.Frame(root,padding=8); top.pack(fill='x'); ttk.Label(top,text='網址').pack(side='left'); self.url=ttk.Entry(top); self.url.insert(0,'https://example.com'); self.url.pack(side='left',fill='x',expand=True,padx=6)
  self.buttons={}
  for text,cmd in [('開啟 Chrome',self.open_browser),('開始錄製',self.start),('暫停錄製',self.pause),('結束錄製',self.finish),('開啟腳本',self.load),('存檔',self.save)]:
   b=ttk.Button(top,text=text,command=cmd); b.pack(side='left',padx=2); self.buttons[text]=b
  bar=ttk.Frame(root,padding=(8,0)); bar.pack(fill='x'); self.runbtn=ttk.Button(bar,text='執行腳本',command=self.run); self.runbtn.pack(side='left'); self.count=ttk.Entry(bar,width=5); self.count.insert(0,'1'); self.count.pack(side='left',padx=5); ttk.Label(bar,text='次').pack(side='left'); self.stopbtn=ttk.Button(bar,text='停止執行',command=self.stop_event.set); self.stopbtn.pack(side='left',padx=10); self.status=ttk.Label(bar,text='準備就緒'); self.status.pack(side='left',padx=10)
  video_bar=ttk.Frame(root,padding=(8,4)); video_bar.pack(fill='x')
  ttk.Label(video_bar,text='插入指令：').pack(side='left')
  ttk.Button(video_bar,text='等待秒數',command=self.insert_wait_step).pack(side='left',padx=2)
  ttk.Button(video_bar,text='開啟網址',command=self.insert_url_step).pack(side='left',padx=2)
  ttk.Button(video_bar,text='關閉 Chrome',command=lambda:self.insert_step({'name':'關閉 Chrome','action':'close_browser'})).pack(side='left',padx=2)
  self.reuse_region=tk.BooleanVar(value=False)
  ttk.Checkbutton(video_bar,text='沿用上次錄影範圍',variable=self.reuse_region).pack(side='left',padx=5)
  for label,action in [('開始錄影','video_start'),('暫停錄影','video_pause'),('結束錄影','video_stop')]:
   ttk.Button(video_bar,text=label,command=lambda a=action,n=label:self.insert_video_step(a,n)).pack(side='left',padx=2)
  region_bar=ttk.Frame(root,padding=(8,0)); region_bar.pack(fill='x')
  ttk.Label(region_bar,text='錄影範圍（網頁 CSS 像素）：').pack(side='left')
  self.region_fields={}
  saved_region=video_recorder.load_region() or {}
  for key in ('x','y','w','h'):
   ttk.Label(region_bar,text=key.upper()).pack(side='left',padx=(5,1))
   field=ttk.Entry(region_bar,width=7); field.pack(side='left'); self.region_fields[key]=field
   if key in saved_region: field.insert(0,str(saved_region[key]))
  experimental=ttk.Frame(root,padding=(8,4)); experimental.pack(fill='x')
  ttk.Label(experimental,text='實驗功能 XPath：').pack(side='left')
  self.xpath_entry=ttk.Entry(experimental); self.xpath_entry.pack(side='left',fill='x',expand=True,padx=5)
  self.get_text_btn=ttk.Button(experimental,text='取得文字',command=self.get_xpath_text); self.get_text_btn.pack(side='left')
  frame=ttk.Frame(root,padding=8); frame.pack(fill='both',expand=True); self.lines=tk.Text(frame,width=5,state='disabled',takefocus=0,bg='#eeeeee',wrap='none'); self.lines.grid(row=0,column=0,sticky='ns'); self.editor=tk.Text(frame,wrap='none',undo=True); self.editor.grid(row=0,column=1,sticky='nsew'); y=ttk.Scrollbar(frame,orient='vertical',command=self.scroll); self.ybar=y; y.grid(row=0,column=2,sticky='ns'); x=ttk.Scrollbar(frame,orient='horizontal',command=self.editor.xview); x.grid(row=1,column=1,sticky='ew'); self.editor.configure(yscrollcommand=self.yscroll,xscrollcommand=x.set); frame.rowconfigure(0,weight=1); frame.columnconfigure(1,weight=1); self.editor.bind('<<Modified>>',self.modified); self.refresh(); root.after(150,self.poll); root.protocol('WM_DELETE_WINDOW',self.close)
 def get_xpath_text(self):
  xpath=self.xpath_entry.get().strip()
  if not xpath: messagebox.showerror('XPath 錯誤','請輸入 XPath。',parent=self.root); return
  if self.driver is None or self.state!='idle': return
  driver=self.driver; self.state='busy'; self.refresh(); self.status.config(text='正在取得文字')
  def work():
   try:
    elements=driver.find_elements(By.XPATH,xpath)
    if not elements: raise ValueError('找不到符合 XPath 的元素。')
    text=elements[0].get_property('textContent') or ''
    self.q.put(('xpath_text',text))
   except Exception as e:self.q.put(('error',str(e)))
  self.worker(work)
 def show_xpath_text(self,text):
  window=tk.Toplevel(self.root); window.title('XPath 文字內容'); window.geometry('640x400')
  frame=ttk.Frame(window,padding=8); frame.pack(fill='both',expand=True)
  result=tk.Text(frame,wrap='word'); result.pack(side='left',fill='both',expand=True)
  scroll=ttk.Scrollbar(frame,orient='vertical',command=result.yview); scroll.pack(side='right',fill='y'); result.configure(yscrollcommand=scroll.set)
  result.insert('1.0',text); result.config(state='disabled'); result.focus_set()
 def insert_video_step(self,action,name):
  data={'name':name,'action':action}
  if action=='video_start' and self.reuse_region.get():
   try:
    raw={k:v.get().strip() for k,v in self.region_fields.items()}
    if not any(raw.values()): data['reuse_region']=True
    else:
     region=video_recorder.validate_region({k:float(v) for k,v in raw.items()})
     region={k:int(v) if v.is_integer() else v for k,v in region.items()}
     data.update(region); video_recorder.save_region(region)
   except (ValueError,OSError) as e: messagebox.showerror('錄影範圍錯誤',str(e),parent=self.root); return
  self.insert_step(data)
 def insert_wait_step(self):
  seconds=simpledialog.askfloat('等待秒數','請輸入等待秒數（可使用小數）：',minvalue=0,parent=self.root)
  if seconds is None:return
  if not math.isfinite(seconds): messagebox.showerror('輸入錯誤','秒數必須是有限數字。',parent=self.root); return
  self.insert_step({'name':f'等待 {seconds:g} 秒','action':'wait','seconds':seconds})
 def insert_url_step(self):
  url=simpledialog.askstring('開啟網址','請輸入完整網址（http:// 或 https://）：',parent=self.root)
  if url is None:return
  url=url.strip()
  if not script_engine.valid_url(url): messagebox.showerror('網址錯誤','請輸入完整的 http:// 或 https:// 網址。',parent=self.root); return
  self.insert_step({'name':'開啟網址','action':'navigate','url':url})
 def insert_step(self,data):
  position=self.editor.index('insert linestart')
  step=json.dumps(data,ensure_ascii=False)+'\n'
  self.editor.insert(position,step); self.editor.mark_set('insert',f'{position} + {len(step)} chars'); self.editor.focus_set()
 def scroll(self,*args): self.editor.yview(*args); self.lines.yview(*args)
 def yscroll(self,*args): self.ybar.set(*args); self.lines.yview_moveto(args[0])
 def modified(self,event=None):
  if self.editor.edit_modified():
   n=int(self.editor.index('end-1c').split('.')[0]); self.lines.config(state='normal'); self.lines.delete('1.0','end'); self.lines.insert('1.0','\n'.join(map(str,range(1,n+1)))); self.lines.config(state='disabled'); self.editor.edit_modified(False)
 def refresh(self):
  connected=self.driver is not None
  for k,enabled in {'開啟 Chrome':self.state=='idle','開始錄製':connected and self.state in ('idle','paused'),'暫停錄製':self.state=='recording','結束錄製':self.state in ('recording','paused'),'開啟腳本':self.state=='idle','存檔':self.state in ('idle','paused')}.items(): self.buttons[k].config(state='normal' if enabled else 'disabled')
  self.get_text_btn.config(state='normal' if connected and self.state=='idle' else 'disabled')
  self.buttons['開始錄製'].config(text='繼續錄製' if self.state=='paused' else '開始錄製'); self.runbtn.config(state='normal' if self.state=='idle' else 'disabled'); self.stopbtn.config(state='normal' if self.state=='running' else 'disabled')
 def worker(self,fn): threading.Thread(target=fn,daemon=True).start()
 def open_browser(self):
  url=self.url.get().strip()
  if not re.match(r'^https?://',url): messagebox.showerror('網址錯誤','請輸入 http:// 或 https:// 網址'); return
  self.state='busy'; self.refresh()
  def work():
   try:
    if self.driver:
     self.driver.quit()
     if self.driver in self.drivers: self.drivers.remove(self.driver)
     self.driver=None
    self.driver=script_engine.create_browser(); self.drivers.append(self.driver); self.driver.get(url); self.q.put(('state','idle','Chrome 已開啟'))
   except Exception as e: self.driver=None; self.q.put(('error',str(e)))
  self.worker(work)
 def start(self):
  self.state='recording'; self.refresh(); self.status.config(text='錄製中'); self.worker(self.record)
 def record(self):
  identifier=None
  try:
   identifier=script_engine.start_recording(self.driver)
   while self.state=='recording':
    events=script_engine.read_recording(self.driver)
    if events:self.q.put(('events',events))
    time.sleep(.2)
   script_engine.stop_recording(self.driver,identifier); identifier=None
   events=script_engine.read_recording(self.driver)
   if events:self.q.put(('events',events))
  except Exception as e:self.q.put(('error',str(e)))
  finally:
   if identifier is not None:
    try:script_engine.stop_recording(self.driver,identifier)
    except Exception:pass
   self.q.put(('record_done',))
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
   count=int(self.count.get())
   if count<=0: raise ValueError('執行次數必須大於 0')
   steps=script_engine.parse_script(self.editor.get('1.0','end-1c'))
  except (ValueError, TypeError) as e:
   messagebox.showerror('腳本錯誤',str(e)); return
  names=set(re.findall(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}',json.dumps([s for _,s in steps],ensure_ascii=False))); values={}
  for name in sorted(names):
   v=simpledialog.askstring('變數',f'請輸入 {name} 的值',show='*',parent=self.root)
   if v is None:return
   values[name]=v
  self.stop_event.clear(); self.state='running'; self.refresh()
  def work():
   try:
    def progress(cycle,line,step):
     self.q.put(('status',f'第 {cycle}/{count} 次，第 {line} 行：{step.get("name") or step["action"]}'))
    def use_driver(driver):
     if self.state=='closing': raise RuntimeError('程式正在關閉。')
     if driver is None:
      if self.driver in self.drivers: self.drivers.remove(self.driver)
     else: self.drivers.append(driver)
     self.driver=driver
    output=script_engine.run_script(self.driver,steps,count,values,self.stop_event,progress,use_driver,lambda region:self.q.put(('region',region)))
    self.q.put(('state','idle',f'影片已儲存：{output}' if output else '執行完成'))
   except script_engine.Stopped:self.q.put(('state','idle','已停止執行'))
   except Exception as e:self.q.put(('error',str(e)))
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
    elif m[0]=='xpath_text':
     self.state='idle'; self.status.config(text='已取得文字'); self.refresh(); self.show_xpath_text(m[1])
    elif m[0]=='region':
     for key,field in self.region_fields.items(): field.delete(0,'end'); field.insert(0,str(m[1][key]))
    elif m[0]=='status':self.status.config(text=m[1])
    elif m[0]=='state':self.state=m[1]; self.status.config(text=m[2]); self.refresh()
    elif m[0]=='error':self.state='idle'; self.refresh(); self.status.config(text='發生錯誤'); messagebox.showerror('錯誤',m[1])
  except queue.Empty:pass
  self.root.after(150,self.poll)
 def close(self):
  self.stop_event.set(); self.state='closing'
  for driver in self.drivers:
   try:driver.quit()
   except Exception:pass
  self.drivers.clear(); self.driver=None
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

