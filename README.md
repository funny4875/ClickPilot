# ClickPilot

<img src="assets/icon.png" alt="ClickPilot 圖示" width="140">

ClickPilot 是 Windows 上的 Chrome 操作錄製與重播工具。將網頁操作記錄為可編輯的 JSON Lines 腳本，再依指定次數執行。

目前程式版本：**1.0.4**。視窗標題會顯示版本號；原始碼以 `main` 分支為準。

## 主要功能

- **側錄網頁操作**：開啟 Chrome 後，使用「側錄網頁」的開始、暫停、繼續及結束，記錄點擊、文字輸入、貼上及 Enter。
- **編輯及執行腳本**：在帶有行號的編輯區修改 JSON Lines，儲存或開啟腳本，指定重複次數，也可停止執行。
- **一次開啟多個腳本**：在「開啟腳本」的選擇視窗中選取多個檔案，程式依選擇視窗回傳的順序載入，並以 `<====檔名====>` 標示每個檔案。執行時會略過標示，依編輯區的順序連續執行；載入會取代編輯區原有內容。
- **插入指令**：在游標所在行插入開啟網址、等待、關閉 Chrome 與錄影指令。等待可輸入 `時:分:秒`、`分:秒` 或秒數，最後一段秒數可使用小數。
- **錄製分頁影片**：依腳本選取網頁區域，錄製畫面與分頁聲音，支援暫停、繼續及結束；可沿用上次範圍並開啟影片資料夾。
- **取得 XPath 文字**：將第一個符合 XPath 的元素文字複製到剪貼簿，在 XPath 欄位下方顯示紅色通知。
- **網址與視窗**：網址欄預設為 Google，保存最近 30 個成功開啟的網址；支援視窗置頂，以及下次啟動時還原位置、大小和輸入狀態。

## 下載與安裝

從 [最新 Release](https://github.com/funny4875/ClickPilot/releases/latest) 下載 最新的 `ClickPilot` MSI 安裝檔，執行安裝程式，再從桌面或開始功能表開啟 ClickPilot。需要 Windows 及已安裝的 Google Chrome；首次啟動瀏覽器時 Selenium 可能需要網路下載相容的 ChromeDriver。

## 使用方式

1. 輸入網址，按「開啟 Chrome」；省略協定時會加上 `https://`。點選網址欄可選擇最近開啟的網址。
2. 在「側錄網頁」按「開始」，操作 Chrome，再按「暫停」或「結束」。暫停後可按「繼續」。
3. 在編輯區檢查或修改腳本，按「存檔」保存；也可用「開啟腳本」一次選擇一個或多個檔案。
4. 輸入執行次數，按「執行腳本」。執行期間可按「停止執行」；等待操作可被中斷。

使用「等待」時，`1:02:03` 表示 1 小時 2 分 3 秒，`2:30` 表示 2 分 30 秒，`1.5` 表示 1.5 秒。含冒號的格式中，秒數及三段格式的分鐘數須小於 60。腳本以總秒數儲存等待時間。

每一行是一個 JSON 物件，例如：

```json
{"name":"簽章","action":"click","xpath":"/html[1]/body[1]/button[1]","timeout":5}
{"name":"輸入 PIN","action":"send_keys","xpath":"/html[1]/body[1]/input[1]","value":"${PIN}","timeout":5}
```

支援 `click`、`clear`、`send_keys`、`paste`、`key`、`wait`、`wait_for`、`navigate` 與 `close_browser`。可使用「等待」及「開啟網址」按鈕，在游標所在行插入指令。「等待」接受時:分:秒、分:秒或秒數。開啟網址會建立新的 Chrome 視窗，後續腳本操作會在新視窗執行；原有視窗會保留至程式關閉。「關閉 Chrome」指令會關閉目前腳本使用的瀏覽器；若正在錄影，請先結束錄影。程式啟動後可直接執行腳本，例如先執行「開啟網址」。`key` 支援 `ENTER`、`TAB`、`ESCAPE`；空行與 `#` 開頭的註解會略過。

```json
{"name":"等待清單","action":"wait_for","xpath":"//*[@id='list']","timeout":30}
{"name":"等待動畫","action":"wait","seconds":3}
{"name":"開啟網址","action":"navigate","url":"https://example.com"}
{"name":"關閉 Chrome","action":"close_browser"}
{"name":"貼上文字","action":"paste","xpath":"//*[@id='field']","value":"文字"}
```

每個 XPath 步驟都會等待目標可見且啟用，並在元素變動或點擊被遮擋時重新嘗試，直到可操作或超過 `timeout` 秒（預設 15 秒）。`wait_for` 只等待元件，`wait` 則固定等待秒數。按「停止執行」可中斷等待；逾時會顯示執行次數、行號、步驟與 XPath。

錄製時，文字欄位會記錄為 `clear` 與 `send_keys`，按 Enter 前或暫停、結束錄製時也會儲存尚未失焦的輸入。Ctrl+V 會記錄為 `paste`，回放時暫存並嘗試還原剪貼簿；若剪貼簿含無法安全備份的圖片或特殊格式，會停止並提示。`${PIN}` 等變數在執行前要求輸入，密碼欄位錄製為 `${PIN}`。非密碼類型的敏感欄位可能記錄明文，請在儲存前檢查。

XPath 依賴網頁結構，網頁改版後可能需要調整。錄製使用 Chrome 日誌以保留跨頁操作，切換分頁、iframe、彈出視窗、網站內建對話框及快速跳頁仍可能無法完整記錄，請檢查腳本。錄製與剪貼簿處理參考 [DocPilot](https://github.com/funny4875/DocPilot)。

## 從原始碼執行和開發

需要 Windows、Google Chrome、Git 和 Python（1.0.4 的 MSI 使用 Python 3.12 建置）。在 PowerShell 執行：

```powershell
git clone https://github.com/funny4875/ClickPilot.git
cd ClickPilot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

主要檔案：`app.py` 負責介面、狀態及背景工作；`script_engine.py` 負責錄製、解析與執行腳本；`video_recorder.py` 負責分頁錄影及輸出；`tests/test_browser.py` 包含需要 Chrome 的瀏覽器測試；`ClickPilot.spec` 和 `installer.wxs` 分別是 PyInstaller 與 WiX 安裝檔設定。

瀏覽器測試需要可運作的 Chrome 和 ChromeDriver／Selenium Manager，會開啟瀏覽器：

```powershell
python -m unittest discover -s tests
```

### 建置 MSI

需要 PyInstaller 及 **WiX Toolset 3**（`candle.exe` 和 `light.exe` 可從 PATH 執行）。在專案目錄及已啟用的虛擬環境中執行：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm ClickPilot.spec
candle.exe installer.wxs
light.exe -out ClickPilot-1.0.4.msi installer.wixobj
```

程式視窗版本在 `app.py` 的 `APP_VERSION`，MSI 版本在 `installer.wxs` 的 `Product` `Version`；發佈新版時需同步更新。MSI 使用 per-user 安裝，並透過既有 UpgradeCode 支援升級。

## 本機資料

正常關閉時，網址、執行次數、XPath、錄影範圍、腳本編輯區內容及勾選狀態會儲存在 `%LOCALAPPDATA%\ClickPilot\inputs.json`；一般視窗的位置與大小存於 `window.json`。網址歷史存於 `url_history.json`，上次錄影範圍另存於 `last_video_region.json`。這些資料只保存在本機，不會因下載原始碼而同步。編輯區可能包含敏感文字，請自行保護這些檔案。

## 錄製分頁影片和聲音

在腳本游標所在行，使用「開始錄影」、「暫停錄影」、「結束錄影」按鈕插入指令。執行開始錄影時，在 ClickPilot 開啟的第一個分頁拖曳選取區域；程式會自動選取該分頁並錄製畫面和聲音。拖曳選取後，X、Y、W、H（網頁 CSS 像素）會顯示在輸入框並保存在本機，重新啟動時載入。插入「開始錄影」前勾選「沿用上次錄影範圍」，會將輸入框內的座標直接寫入指令；可先手動修改座標。取消勾選則在執行時重新拖曳。範圍不得超出目前可視區域，錄影時請維持視窗尺寸與縮放比例。

「暫停錄影」後再次執行「開始錄影」會繼續同一段影片；「結束錄影」會用 FFmpeg 編碼 MP4，儲存在使用者的 `Videos/ClickPilot` 資料夾，也可按「開啟錄影資料夾」前往。每次完成錄影都會建立不同檔案。影片包含所選區域的畫面及整個分頁的聲音，不包含瀏覽器工具列。首次安裝相依套件時會一併安裝 FFmpeg 執行檔。

```json
{"name":"開始錄影","action":"video_start","x":100,"y":100,"w":640,"h":360}
{"action":"wait","seconds":10}
{"name":"暫停錄影","action":"video_pause"}
{"action":"wait","seconds":2}
{"name":"繼續錄影","action":"video_start","reuse_region":true}
{"action":"wait","seconds":5}
{"name":"結束錄影","action":"video_stop"}
```

## 取得 XPath 文字

開啟 Chrome 並進入網頁後，輸入 XPath 並按「取得 XPath 文字」，會將第一個符合元素的文字內容（包含子元素文字）複製到剪貼簿，並在該列下方顯示紅色通知。偵測到 Ctrl+C 或 Ctrl+V 後通知消失。此功能直接讀取目前瀏覽器分頁，不會插入腳本；若找不到元素或 XPath 格式無效會顯示錯誤。
