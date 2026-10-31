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

支援 `click`、`clear`、`send_keys` 與 `key`（例如 `ENTER`）。`timeout` 是等待元件出現的最長秒數；每 0.2 秒重新查找，找到後立即執行，逾時會停止並顯示步驟與 XPath。`${PIN}` 等變數在執行前要求輸入，密碼欄位錄製為 `${PIN}`。

XPath 依賴網頁結構，網頁改版後可能需要調整。跨頁跳轉瞬間、iframe、特殊元件及瀏覽器原生對話框可能無法記錄，請檢查腳本；輸入欄位在變更完成、失焦時記錄。

## 從原始碼執行

安裝 Python 和 Google Chrome，然後執行：

```powershell
py -m pip install -r requirements.txt
py app.py
```

