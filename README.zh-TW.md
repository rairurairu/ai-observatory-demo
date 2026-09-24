# AI Observatory

**LLM 品牌推薦洞察平台** · 研究展示平台

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

AI Observatory 是一個本機研究原型，可用來進行受控的提示詞與模型實驗、保存原始回覆、擷取品牌觀察結果並檢視描述性趨勢。預設資料集是確定性產生的合成展示資料，並明確標示為展示資料；它不代表 ChatGPT、Claude、Gemini 或其他商業模型的實際測量結果。

## 介面截圖

![包含合成展示資料的 AI Observatory 總覽](docs/images/overview.png)

*總覽頁面：展示資料會清楚標示為模擬資料。*

![顯示 API 實驗與歷史記錄的實驗室](docs/images/experiment-history.png)

*實驗室頁面：成功執行、失敗嘗試和排除項目都會保留在歷史記錄中。*

## 架構

- **前端：** TypeScript、React 與 Vite，提供響應式分析檢視、篩選、建立實驗、檢視回覆、下載 CSV/JSON 和人工審核。
- **API：** FastAPI 與 Pydantic；文件位於 `http://localhost:8000/docs`。
- **資料持久化：** 預設使用 SQLite 的 SQLAlchemy ORM。設定 PostgreSQL 驅動程式後，可透過 `DATABASE_URL` 改用 PostgreSQL。
- **研究資料流程：** 提示詞/模型/重複次數 → 執行記錄 → 原始回覆 → 版本化擷取記錄 → 標準化品牌觀察 → 彙總分析或人工註記。
- **展示資料產生：** 使用固定亂數種子，涵蓋 5 個領域、3 個模擬模型和連續 90 天的歷史資料。API 啟動時只會在資料庫為空時寫入展示資料，不會在每次頁面呈現時重複產生。

本機同步執行器適合展示，不是持久化的分散式任務系統。即時執行支援 OpenAI、Anthropic、Google Gemini、MiniMax 和 DeepSeek API 介接器，也支援偵測執行 API 的電腦上已登入的 Claude Code、Codex 和 GitHub Copilot CLI。即時請求會依序執行、需要明確確認，並會保存服務提供者錯誤。目前尚未實作搜尋工具/引用、自動排程或價格估算；即時執行會停用搜尋，並將費用標示為無法提供。

## 安裝與啟動（Windows PowerShell）

建議使用 Python 3.11 或更新版本。在專案目錄執行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\initialize_database.py
python scripts\generate_demo_data.py
```

首次安裝前端相依套件：

```powershell
cd frontend
npm install
cd ..
```

在兩個終端機分別啟動 API 與前端：

```powershell
# 終端機 1
uvicorn backend.main:app --reload
```

```powershell
# 終端機 2
npm --prefix frontend run dev
```

開啟 `http://localhost:5173`。Vite 開發伺服器會將 API 請求代理到 8000 埠的 FastAPI。健康檢查與互動式 API 文件分別位於 `http://localhost:8000/health` 和 `/docs`。

建立正式環境前端套件：

```powershell
npm --prefix frontend run build
```

輸出會寫入 `frontend/dist`。

專案預設使用 `APP_MODE=demo`、`DATABASE_URL=sqlite:///./ai_observatory.db` 和 `API_BASE_URL=http://localhost:8000`。可在 `.env` 中設定這些值。API 金鑰留空仍可執行展示模式；展示模式不會發出付費 API 請求。

若要使用即時 API 服務提供者，請將一或多個金鑰填入本機 `.env`：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GOOGLE_API_KEY`、`MINIMAX_API_KEY` 或 `DEEPSEEK_API_KEY`，然後重新啟動後端。MiniMax 和 DeepSeek 介接器使用相容 OpenAI 的 Chat Completions API；可透過對應設定覆寫基礎 URL 和模型 ID。實驗室會偵測已登入的 Claude Code 與 Codex CLI。只有在 `COPILOT_CLI_MODEL_IDS` 明確列出模型 ID 時才會啟用 Copilot；由於 Auto 不會記錄實際解析到的模型，Auto 路由已停用。模型可用性取決於 Copilot 方案、CLI 版本和組織原則；不可用的模型請求會記錄為失敗，且不會計入推薦統計。目前已登入的 Copilot CLI 帳戶只提供 Auto，因此在帳戶開放具名模型之前，Copilot 會保持停用。應用程式不會透過瀏覽器登入直接連接 Gemini Enterprise。Claude Pro 和 ChatGPT Plus 透過各自的本機 CLI 使用，並遵循對應服務的訂閱條款。CLI 的用量或額度由相應服務管理。

選擇 **Live** 後建立實驗，檢查預計請求數量，並勾選明確確認項目後再執行。目前沒有設定 API 定價，因此不會顯示費用預估；API 服務提供者可能會對請求收費。單一實驗不能混用展示模型和即時模型。個別服務提供者請求失敗會保存為失敗記錄，但不會阻止其他請求繼續執行。如果 API 程序在即時執行期間中斷，請重新啟動後端並再次執行該實驗，系統會從已保存的請求繼續。應用程式不會從終端機輸出讀取 API 金鑰；請將金鑰保存在本機 `.env`，不要公開該檔案。

## 隨附的研究快照

儲存庫包含 `ai_observatory.db` 時點快照，因此複製後即可檢視實驗歷史。資料庫包含確定性合成展示資料，以及少量即時試執行記錄，包括 MiniMax、DeepSeek、Claude Code 和 Codex CLI 的成功回覆、服務提供者模型可用性失敗記錄，以及因無法確認實際模型而標記為排除的 Copilot Auto 回覆。即時實驗僅使用一個智慧型手機提示詞，只適合描述性展示，不構成統計上有說服力的模型比較。資料庫不含 API 金鑰；憑證應填入本機且已被 Git 忽略的 `.env` 檔案。

由於快照資料庫已提交至儲存庫，之後在本機執行的新實驗不會自動發布。若要分享較新的歷史記錄，請先檢查資料庫不含私人資訊或機密，再明確提交更新後的資料庫。

## 可直接交給程式設計代理的提示詞

如果你想讓程式設計代理複製並在本機啟動展示，可將以下提示詞直接傳給代理：

```text
請複製 https://github.com/rairurairu/ai-observatory-demo.git，並協助我在本機執行 AI Observatory。先閱讀 README.md，再依照其中的步驟操作。保留儲存庫附帶的 ai_observatory.db 實驗歷史。使用展示模式；不要讀取、列印、複製或上傳任何 .env 檔案或 API 金鑰。不要執行會產生費用的即時實驗、不要重設資料庫，也不要推送任何變更。啟動後端和前端後，告訴我本機網址，以及如何停止兩個服務。
```

## 五分鐘展示流程

1. 開啟 **Overview**，介紹合成資料標示、分母說明、以回覆為單位的提及率，以及領域/模型篩選器。
2. 在 **Experiment Lab** 建立一個 Automobiles 實驗，選擇全部 3 個模擬模型、3 個提示詞變體和 2 次重複。執行前先檢查設定。
3. 檢視執行摘要，再將結果匯出為 JSON 或 CSV。
4. 開啟 **Model Comparison**、**Prompt Sensitivity** 和 **Historical Trends**，討論依目前提示詞集合而定的描述性差異。漂移提示只供說明。
5. 開啟 **Response Explorer**，比較原始回覆與有證據支持的擷取觀察、提及順序和明確排名。
6. 在 **Data Quality** 儲存一筆註記並展示其持久化結果。最後開啟 **System Monitor**，說明請求/失敗計數，以及系統不會捏造缺漏的 Token 或費用資料。

## 測試

```powershell
pytest -q
```

測試涵蓋種子 API、資訊擷取與明確排名、依領域範圍計算比例、保留重複項目的展示執行、展示/即時資料隔離，以及註記持久化。

## 目前範圍與限制

- **已實作：** 持久化標準化核心架構；展示資料產生；受控實驗的增刪改查與執行；實驗/執行/回覆 ID；OpenAI、Anthropic、Gemini、MiniMax、DeepSeek API 介接器；Claude Code、Codex 和 GitHub Copilot CLI 介接器；即時執行費用確認；逐請求保存失敗記錄；依字典、別名和產品連結進行確定性擷取；附有證據的提及記錄；依回覆計算品牌比例；模型比較；歷史趨勢；提示詞變體比例；審核註記；營運狀態計數/記錄；回覆匯出；CSV 和 JSON；TypeScript/React 網頁前端。
- **尚未實作：** 除 SDK 重試以外的服務提供者速率限制；即時費用估算；非同步持久化工作佇列；服務提供者搜尋/引用；自動排程；進階分層推論與統計漂移檢定；Parquet 快照。請勿將說明性的漂移提示解讀為實際測得的模型更新。
- 情緒與屬性擷取採用保守的關鍵字規則。輸出是研究輔助資料，並非經驗證的 NLP 測量結果；若規則無法明確判斷，會保留為「未知」。

## 資料庫說明

SQLite 架構以 SQLAlchemy `create_all` 建立。若要長期研究，請在修改架構前加入 Alembic 遷移，並設定 PostgreSQL 驅動程式。原始回覆文字與既有擷取記錄都會保留；擷取版本記錄在 `extraction_runs.pipeline_version`。
