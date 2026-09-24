# AI Observatory

**LLM 品牌推薦洞察平台** · 本機研究平台

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

AI Observatory 是一個本機研究平台，用於進行受控的提示詞與模型實驗、保存原始回覆、擷取品牌觀察並檢視描述性趨勢。儲存庫附帶實際實驗資料；應用程式不會在資料或服務提供者缺失時生成替代回答。

## 介面截圖

![AI Observatory 總覽：篩選自 SQLite 快照中的實際手機推薦實驗](docs/images/live-overview.png)

*總覽：來自儲存庫 SQLite 實驗資料庫的即時實驗記錄。*

![回覆瀏覽器：實際 MiniMax、DeepSeek 回覆及已記錄的失敗嘗試](docs/images/live-response-explorer.png)

*回覆瀏覽器：實驗資料庫中的服務提供者原始輸出、擷取觀察結果和失敗嘗試。*

## 架構

- **前端：** TypeScript、React 與 Vite，提供分析檢視、篩選、建立實驗、回覆檢視、CSV/JSON 匯出及人工審核。
- **API：** FastAPI 與 Pydantic；文件位於 `http://localhost:8000/docs`。
- **資料庫：** 預設使用 SQLite 和 SQLAlchemy。安裝 PostgreSQL 驅動程式後，可用 `DATABASE_URL` 設定 PostgreSQL。
- **研究流程：** 提示詞/模型/重複次數 → 執行記錄 → 原始回覆 → 版本化擷取 → 標準品牌觀察 → 分析或人工註記。
- **附帶資料：** 儲存庫包含截圖使用的 SQLite 快照。API 啟動時只初始化品牌參照資料，不會合成回覆。

本機執行器適合研究示範，並非持久化分散式執行系統。即時執行支援 OpenAI、Anthropic、Google Gemini、MiniMax 和 DeepSeek API，以及執行 API 的電腦上已登入的 Claude Code、Codex 和 GitHub Copilot CLI。請求會依序執行，須明確確認，提供者錯誤也會保存。搜尋工具/引用、自動排程和價格估算尚未實作；即時執行會停用搜尋，成本顯示為不可用。

## 安裝與啟動（Windows PowerShell）

建議使用 Python 3.11 以上版本。在此目錄執行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\initialize_database.py
```

安裝前端相依套件：

```powershell
cd frontend
npm install
cd ..
```

在兩個終端機分別啟動 API 和前端：

```powershell
# 終端機 1
uvicorn backend.main:app --reload
```

```powershell
# 終端機 2
npm --prefix frontend run dev
```

開啟 `http://localhost:5173`。Vite 會將 API 請求代理至 8000 埠的 FastAPI。健康檢查與互動式 API 文件位於 `http://localhost:8000/health` 和 `/docs`。

## 附帶的實驗快照

儲存庫內的 `data/ai_observatory.db` 是時間點快照，讓儀表板開啟時即可檢視實際實驗記錄。它包含五個小型實驗的 16 次提供者請求：即時回覆、記錄下來的提供者/模型失敗，以及一筆因無法確認解析後模型而排除的 Copilot Auto 回覆。沒有合成回答。即時研究僅使用一個智慧型手機提示詞，適合描述性檢視，不構成具統計說服力的模型比較。資料庫不含 API 金鑰；憑證請保存在本機且已被 Git 忽略的 `.env`。

此快照已提交至儲存庫，之後的本機實驗不會自動發布。分享新記錄前，請先確認資料庫沒有私人資料或密鑰，再明確提交更新。

`.env.example` 設定 `APP_MODE=live` 並指向快照資料庫。無需 API 金鑰即可瀏覽已保存的回答。只有要收集新的即時回答時才加入憑證；啟動時不會呼叫模型。

如要使用即時 API，將一個或多個金鑰填入 `.env`（`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`MINIMAX_API_KEY` 或 `DEEPSEEK_API_KEY`），再重新啟動後端。MiniMax 和 DeepSeek 使用相容 OpenAI 的 Chat Completions API；可透過相應設定調整基礎 URL 和模型 ID。實驗室會偵測已登入的 Claude Code 和 Codex CLI。只有在 `COPILOT_CLI_MODEL_IDS` 明確列出模型 ID 時才會提供 Copilot；Auto 路由已停用，因為無法記錄實際解析到的模型。模型是否可用取決於 Copilot 方案、CLI 版本和組織政策；不可用請求會保留為失敗記錄，不會計入推薦結果。目前登入的 Copilot CLI 帳戶只提供 Auto，因此具名模型開放前 Copilot 會維持停用。應用程式不會透過瀏覽器登入連接 Gemini Enterprise。Claude Pro 和 ChatGPT Plus 透過各自的本機 CLI 使用，並受相關服務的訂閱條款管理。CLI 用量或額度由服務提供者管理。

建立即時實驗後，先檢視預計請求數，並勾選明確確認欄位再執行。目前未設定 API 定價，因此不提供費用估算；API 請求可能產生費用。單一提供者請求失敗會保存為失敗記錄，不會阻止其他請求繼續。如果即時執行期間 API 程序中斷，重新啟動並再次執行該實驗即可從已保存的請求繼續。請勿將 `.env` 公開。快照資料庫應先備份再變更或取代。

## 給程式代理的提示

如果要讓程式代理在本機複製並開啟已保存的研究資料，請直接傳送以下提示：

```text
請複製 https://github.com/rairurairu/ai-observatory-demo.git，並協助我在本機執行 AI Observatory。先閱讀 README.md 並遵照設定步驟。使用儲存庫附帶的 data/ai_observatory.db 作為實驗歷史記錄，不要生成合成回答。不要讀取、列印、複製或上傳任何 .env 檔案或 API 金鑰。不要發送即時服務提供者請求、取代資料庫或推送變更。啟動後端和前端，然後告訴我本機網址，以及如何停止兩個服務。
```

## 五分鐘導覽

1. 開啟 **Overview**，查看即時資料標記、分母、回覆層級提及率，以及領域/模型篩選器。
2. 開啟 **Experiment Lab**，檢視 MiniMax/DeepSeek 配對執行記錄，以及 CLI 和 Copilot 可用性記錄。
3. 開啟 **Response Explorer**，比較實際提供者回答、擷取觀察、提及順序與明確排名。
4. 檢視 **Model Comparison**、**Prompt Sensitivity** 和 **Historical Trends**。目前樣本很小，比例只供描述性參考。
5. 開啟 **Data Quality** 查看證據，再用 **System Monitor** 檢視請求/失敗次數及目前無法取得的 Token/費用資訊。

## 測試

```powershell
pytest -q
```

測試涵蓋 API 啟動、擷取與明確排名處理、限定領域的比例彙總、隔離的合成測試資料、即時/展示來源隔離，以及註記保存。合成資料僅供測試使用；一般啟動會載入附帶的即時資料，不會新增虛構回答。

## 範圍與限制

- **已實作：** 正規化持久化資料結構；附帶即時實驗歷史；受控實驗 CRUD/執行；實驗/執行/回答 ID；OpenAI、Anthropic、Gemini、MiniMax、DeepSeek API 適配器；Claude Code、Codex、GitHub Copilot CLI 適配器；即時費用確認；逐請求保存失敗；字典式品牌擷取、別名與產品連結；附證據的提及記錄；回覆層級品牌比例；模型比較；歷史趨勢；提示詞變體比例；人工審核註記；操作記錄；回答匯出；CSV/JSON；TypeScript/React 前端。
- **尚未實作：** SDK 重試之外的提供者限流、即時價格估算、持久化非同步工作佇列、提供者搜尋/引用、自動排程、進階分層推論、統計漂移檢定和 Parquet 快照。漂移檢視需要足夠觀測值，且只具描述性，不能證明服務版本改變。
- 情緒與屬性擷取使用保守的關鍵字規則。結果僅為研究輔助，並非經驗證的 NLP 測量；無法明確判斷時會保留未知值。

## 資料庫說明

SQLite 結構由 SQLAlchemy `create_all` 建立。附帶的 `data/ai_observatory.db` 僅包含即時實驗歷史：五個小型實驗的 16 次提供者請求，包括成功回答、失敗記錄及一筆排除的 Copilot Auto 回覆。資料庫不含 API 金鑰。長期研究請在結構演進前加入 Alembic 遷移，並設定 PostgreSQL 驅動程式。原始回覆和既有擷取記錄都會保留；擷取版本記錄於 `extraction_runs.pipeline_version`。
