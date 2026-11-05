import ctypes, json, math, os, queue, re, secrets, sys, threading, time, traceback, tkinter as tk
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
  self.window_settings_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'ClickPilot' / 'window.json'
  try:
   settings=json.loads(self.window_settings_path.read_text(encoding='utf-8'))
   geometry=settings['geometry']; x=settings['x']; y=settings['y']
   user32=ctypes.windll.user32
   if re.fullmatch(r'\d+x\d+[+-]\d+[+-]\d+',geometry) and user32.GetSystemMetrics(76)<=x<user32.GetSystemMetrics(76)+user32.GetSystemMetrics(78) and user32.GetSystemMetrics(77)<=y<user32.GetSystemMetrics(77)+user32.GetSystemMetrics(79): root.geometry(geometry)
  except (OSError,ValueError,KeyError,TypeError): pass
  self.url_history_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'ClickPilot' / 'url_history.json'
  try:
   history=json.loads(self.url_history_path.read_text(encoding='utf-8'))
   self.url_history=list(dict.fromkeys(url for url in history if isinstance(url,str) and script_engine.valid_url(url)))[:30] if isinstance(history,list) else []
  except (OSError,ValueError): self.url_history=[]
  top=ttk.Frame(root,padding=8); top.pack(fill='x'); ttk.Label(top,text='網址').pack(side='left'); self.url=ttk.Combobox(top,values=self.url_history); self.url.set('https://www.google.com'); self.url.pack(side='left',fill='x',expand=True,padx=6)
  self.url.bind('<Button-1>',self.show_url_history)
  self.buttons={}
  b=ttk.Button(top,text='開啟 Chrome',command=self.open_browser); b.pack(side='left',padx=2); self.buttons['開啟 Chrome']=b
  record_group=ttk.LabelFrame(top,text='側錄網頁',padding=2); record_group.pack(side='left',padx=2)
  for key,label,cmd in [('開始錄製','開始',self.start),('暫停錄製','暫停',self.pause),('結束錄製','結束',self.finish)]:
   b=ttk.Button(record_group,text=label,command=cmd); b.pack(side='left',padx=2); self.buttons[key]=b
  for text,cmd in [('開啟腳本',self.load),('存檔',self.save)]:
   b=ttk.Button(top,text=text,command=cmd); b.pack(side='left',padx=2); self.buttons[text]=b
  bar=ttk.Frame(root,padding=(8,0)); bar.pack(fill='x'); self.runbtn=ttk.Button(bar,text='執行腳本',command=self.run); self.runbtn.pack(side='left'); self.count=ttk.Entry(bar,width=5); self.count.insert(0,'1'); self.count.pack(side='left',padx=5); ttk.Label(bar,text='次').pack(side='left'); self.stopbtn=ttk.Button(bar,text='停止執行',command=self.stop_event.set); self.stopbtn.pack(side='left',padx=10); self.status=ttk.Label(bar,text='準備就緒'); self.status.pack(side='left',padx=10)
  self.always_on_top=tk.BooleanVar(value=False)
  ttk.Checkbutton(bar,text='視窗置頂',variable=self.always_on_top,command=self.apply_topmost).pack(side='right',padx=5)
  video_bar=ttk.LabelFrame(root,text='插入指令區',padding=(8,4)); video_bar.pack(fill='x',padx=8,pady=4)
  command_row=ttk.Frame(video_bar); command_row.pack(fill='x',pady=2)
  ttk.Button(command_row,text='開啟網址',command=self.insert_url_step).pack(side='left',padx=2)
  ttk.Button(command_row,text='等待',command=self.insert_wait_step).pack(side='left',padx=2)
  ttk.Button(command_row,text='關閉 Chrome',command=lambda:self.insert_step({'name':'關閉 Chrome','action':'close_browser'})).pack(side='left',padx=2)
  self.reuse_region=tk.BooleanVar(value=False)
  ttk.Checkbutton(video_bar,text='沿用上次錄影範圍',variable=self.reuse_region).pack(anchor='w',padx=2,pady=2)
  region_bar=ttk.Frame(video_bar); region_bar.pack(fill='x',pady=2)
  ttk.Label(region_bar,text='錄影範圍（網頁 CSS 像素）：').pack(side='left')
  self.region_fields={}
  saved_region=video_recorder.load_region() or {}
  for key in ('x','y','w','h'):
   ttk.Label(region_bar,text=key.upper()).pack(side='left',padx=(5,1))
   field=ttk.Entry(region_bar,width=7); field.pack(side='left'); self.region_fields[key]=field
   if key in saved_region: field.insert(0,str(saved_region[key]))
  recording_row=ttk.Frame(video_bar); recording_row.pack(fill='x',pady=2)
  for label,action in [('開始錄影','video_start'),('暫停錄影','video_pause'),('結束錄影','video_stop')]:
   ttk.Button(recording_row,text=label,command=lambda a=action,n=label:self.insert_video_step(a,n)).pack(side='left',padx=2)
  ttk.Button(recording_row,text='開啟錄影資料夾',command=self.open_video_folder).pack(side='left',padx=2)
  experimental=ttk.Frame(video_bar); experimental.pack(fill='x',pady=2)
  ttk.Label(experimental,text='XPath：').pack(side='left')
  self.xpath_entry=ttk.Entry(experimental); self.xpath_entry.pack(side='left',fill='x',expand=True,padx=5)
  self.get_text_btn=ttk.Button(experimental,text='取得 XPath 文字',command=self.get_xpath_text); self.get_text_btn.pack(side='left')
  self.xpath_notice=ttk.Label(video_bar,text='',foreground='red'); self.xpath_notice.pack(anchor='w',padx=2)
  self.clipboard_shortcut_down=False; root.after(50,self.watch_clipboard_shortcuts)
  frame=ttk.Frame(root,padding=8); frame.pack(fill='both',expand=True); self.lines=tk.Text(frame,width=5,state='disabled',takefocus=0,bg='#eeeeee',wrap='none'); self.lines.grid(row=0,column=0,sticky='ns'); self.editor=tk.Text(frame,wrap='none',undo=True); self.editor.grid(row=0,column=1,sticky='nsew'); y=ttk.Scrollbar(frame,orient='vertical',command=self.scroll); self.ybar=y; y.grid(row=0,column=2,sticky='ns'); x=ttk.Scrollbar(frame,orient='horizontal',command=self.editor.xview); x.grid(row=1,column=1,sticky='ew'); self.editor.configure(yscrollcommand=self.yscroll,xscrollcommand=x.set); frame.rowconfigure(0,weight=1); frame.columnconfigure(1,weight=1); self.editor.bind('<<Modified>>',self.modified); self.refresh(); root.after(150,self.poll); root.protocol('WM_DELETE_WINDOW',self.close)
  self.restore_inputs()
 def apply_topmost(self): self.root.attributes('-topmost',self.always_on_top.get())
 def restore_inputs(self):
  self.input_settings_path=self.window_settings_path.with_name('inputs.json')
  try:
   data=json.loads(self.input_settings_path.read_text(encoding='utf-8'))
   if not isinstance(data,dict): return
   for key,field in [('url',self.url),('count',self.count),('xpath',self.xpath_entry)]:
    if isinstance(data.get(key),str): field.delete(0,'end'); field.insert(0,data[key])
   region=data.get('region',{})
   if isinstance(region,dict):
    for key,field in self.region_fields.items():
     if isinstance(region.get(key),str): field.delete(0,'end'); field.insert(0,region[key])
   if isinstance(data.get('editor'),str): self.editor.insert('1.0',data['editor'])
   if isinstance(data.get('reuse_region'),bool): self.reuse_region.set(data['reuse_region'])
   if isinstance(data.get('always_on_top'),bool): self.always_on_top.set(data['always_on_top']); self.apply_topmost()
  except (OSError,ValueError,TypeError,tk.TclError): pass
 def save_inputs(self):
  data={'url':self.url.get(),'count':self.count.get(),'xpath':self.xpath_entry.get(),'region':{key:field.get() for key,field in self.region_fields.items()},'editor':self.editor.get('1.0','end-1c'),'reuse_region':self.reuse_region.get(),'always_on_top':self.always_on_top.get()}
  self.input_settings_path.parent.mkdir(parents=True,exist_ok=True)
  self.input_settings_path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
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
 def clear_xpath_notice(self,event=None): self.xpath_notice.config(text='')
 def watch_clipboard_shortcuts(self):
  keys=ctypes.windll.user32.GetAsyncKeyState
  pressed=bool(keys(0x11)&0x8000 and (keys(0x43)&0x8000 or keys(0x56)&0x8000))
  if pressed and not self.clipboard_shortcut_down: self.clear_xpath_notice()
  self.clipboard_shortcut_down=pressed; self.root.after(50,self.watch_clipboard_shortcuts)
 def open_video_folder(self):
  try:
   folder=video_recorder.video_output_dir(); folder.mkdir(parents=True,exist_ok=True); os.startfile(folder)
  except OSError as e: messagebox.showerror('無法開啟錄影資料夾',str(e),parent=self.root)
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
  value=simpledialog.askstring('等待時間','請輸入等待時間（時:分:秒、分:秒或秒）：',parent=self.root)
  if value is None:return
  value=value.strip()
  try:
   parts=value.split(':')
   if len(parts) not in (1,2,3) or any(not part.strip() for part in parts): raise ValueError
   numbers=[float(part.strip()) for part in parts]
   if any(not math.isfinite(number) or number<0 for number in numbers): raise ValueError
   if len(parts)>1 and any(not number.is_integer() for number in numbers[:-1]): raise ValueError
   if len(parts)==2 and numbers[1]>=60: raise ValueError
   if len(parts)==3 and (numbers[1]>=60 or numbers[2]>=60): raise ValueError
   seconds=numbers[-1]+(numbers[-2]*60 if len(parts)>=2 else 0)+(numbers[-3]*3600 if len(parts)==3 else 0)
  except ValueError:
   messagebox.showerror('輸入錯誤','請輸入非負數秒數，或有效的分:秒／時:分:秒（分、秒欄位需小於 60）。',parent=self.root); return
  self.insert_step({'name':f'等待 {value}','action':'wait','seconds':seconds})
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
  self.buttons['開始錄製'].config(text='繼續' if self.state=='paused' else '開始'); self.runbtn.config(state='normal' if self.state=='idle' else 'disabled'); self.stopbtn.config(state='normal' if self.state=='running' else 'disabled')
 def worker(self,fn): threading.Thread(target=fn,daemon=True).start()
 def show_url_history(self,event):
  if self.url_history and event.x < self.url.winfo_width()-20:
   self.root.after_idle(lambda:self.url.tk.call('ttk::combobox::Post',self.url))
 def remember_url(self,url):
  self.url_history=[url]+[item for item in self.url_history if item!=url]
  self.url_history=self.url_history[:30]; self.url.configure(values=self.url_history)
  try:
   self.url_history_path.parent.mkdir(parents=True,exist_ok=True)
   self.url_history_path.write_text(json.dumps(self.url_history,ensure_ascii=False),encoding='utf-8')
  except OSError: self.status.config(text='無法儲存網址歷史')
 def open_browser(self):
  url=self.url.get().strip()
  if url and not re.match(r'^https?://',url,re.I) and '://' not in url: url='https://'+url; self.url.set(url)
  if not re.match(r'^https?://',url): messagebox.showerror('網址錯誤','請輸入 http:// 或 https:// 網址'); return
  self.state='busy'; self.refresh()
  def work():
   try:
    if self.driver:
     self.driver.quit()
     if self.driver in self.drivers: self.drivers.remove(self.driver)
     self.driver=None
    self.driver=script_engine.create_browser(); self.drivers.append(self.driver); self.driver.get(url); self.q.put(('url_opened',url))
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
  paths=filedialog.askopenfilenames(filetypes=[('腳本','*.jsonl *.txt *.json'),('所有檔案','*.*')],parent=self.root)
  if not paths:return
  try:
   sections=[f'<===={Path(path).name}====>\n{Path(path).read_text(encoding="utf-8-sig").rstrip()}' for path in paths]
  except (OSError,UnicodeError) as e:
   messagebox.showerror('開啟腳本錯誤',str(e),parent=self.root); return
  self.editor.delete('1.0','end'); self.editor.insert('1.0','\n'.join(sections)+'\n')
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
     self.root.clipboard_clear(); self.root.clipboard_append(m[1]); self.state='idle'; self.status.config(text='準備就緒'); self.xpath_notice.config(text='已複製 XPath 文字到剪貼簿'); self.refresh()
    elif m[0]=='region':
     for key,field in self.region_fields.items(): field.delete(0,'end'); field.insert(0,str(m[1][key]))
    elif m[0]=='status':self.status.config(text=m[1])
    elif m[0]=='url_opened':self.state='idle'; self.status.config(text='Chrome 已開啟'); self.remember_url(m[1]); self.refresh()
    elif m[0]=='state':self.state=m[1]; self.status.config(text=m[2]); self.refresh()
    elif m[0]=='error':self.state='idle'; self.refresh(); self.status.config(text='發生錯誤'); messagebox.showerror('錯誤',m[1])
  except queue.Empty:pass
  self.root.after(150,self.poll)
 def close(self):
  try: self.save_inputs()
  except OSError as e:
   messagebox.showerror('無法儲存輸入狀態',str(e),parent=self.root); return
  self.stop_event.set(); self.state='closing'
  if self.root.state()=='normal':
   try:
    self.window_settings_path.parent.mkdir(parents=True,exist_ok=True)
    self.window_settings_path.write_text(json.dumps({'geometry':self.root.geometry(),'x':self.root.winfo_rootx(),'y':self.root.winfo_rooty()}),encoding='utf-8')
   except OSError: pass
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

