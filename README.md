# ClickPilot

<img src="assets/icon.png" alt="ClickPilot 圖示" width="140">

ClickPilot 是 Windows 上的 Chrome 操作錄製與重播工具。將網頁操作記錄為可編輯的 JSON Lines 腳本，再依指定次數執行。

## 下載與安裝

從 [最新 Release](https://github.com/funny4875/ClickPilot/releases/latest) 下載 最新的 `ClickPilot` MSI 安裝檔，執行安裝程式，再從桌面或開始功能表開啟 ClickPilot。需要 Windows 及已安裝的 Google Chrome；首次啟動瀏覽器時 Selenium 可能需要網路下載相容的 ChromeDriver。

## 使用方式

1. 輸入完整網址，按「開啟 Chrome」。
2. 按「開始錄製」，在 Chrome 操作。可暫停、繼續及結束錄製。
3. 在附有行號及水平捲軸的文字框檢查或編輯腳本，按「存檔」保存。也可開啟既有腳本。
4. 輸入執行次數，按「執行腳本」。停止執行會在目前步驟結束後生效。

每一行是一個 JSON 物件，例如：

```json
{"name":"簽章","action":"click","xpath":"/html[1]/body[1]/button[1]","timeout":5}
{"name":"輸入 PIN","action":"send_keys","xpath":"/html[1]/body[1]/input[1]","value":"${PIN}","timeout":5}
```

支援 `click`、`clear`、`send_keys`、`paste`、`key`、`wait` 與 `wait_for`。`key` 支援 `ENTER`、`TAB`、`ESCAPE`；空行與 `#` 開頭的註解會略過。

```json
{"name":"等待清單","action":"wait_for","xpath":"//*[@id='list']","timeout":30}
{"name":"等待動畫","action":"wait","seconds":3}
{"name":"貼上文字","action":"paste","xpath":"//*[@id='field']","value":"文字"}
```

每個 XPath 步驟都會等待目標可見且啟用，並在元素變動或點擊被遮擋時重新嘗試，直到可操作或超過 `timeout` 秒（預設 5 秒）。`wait_for` 只等待元件，`wait` 則固定等待秒數。按「停止執行」可中斷等待；逾時會顯示執行次數、行號、步驟與 XPath。

錄製時，文字欄位會記錄為 `clear` 與 `send_keys`，按 Enter 前或暫停、結束錄製時也會儲存尚未失焦的輸入。Ctrl+V 會記錄為 `paste`，回放時暫存並嘗試還原剪貼簿；若剪貼簿含無法安全備份的圖片或特殊格式，會停止並提示。`${PIN}` 等變數在執行前要求輸入，密碼欄位錄製為 `${PIN}`。非密碼類型的敏感欄位可能記錄明文，請在儲存前檢查。

XPath 依賴網頁結構，網頁改版後可能需要調整。錄製使用 Chrome 日誌以保留跨頁操作，切換分頁、iframe、彈出視窗、網站內建對話框及快速跳頁仍可能無法完整記錄，請檢查腳本。錄製與剪貼簿處理參考 [DocPilot](https://github.com/funny4875/DocPilot)。

## 從原始碼執行

安裝 Python 和 Google Chrome，然後執行：

```powershell
py -m pip install -r requirements.txt
py app.py
```

