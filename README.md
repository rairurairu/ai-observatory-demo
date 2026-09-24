# AI Observatory

**LLM Brand Recommendation Intelligence Platform** · Research demonstration platform

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

AI Observatory is a local research prototype for running controlled prompt/model experiments, preserving raw responses, extracting brand observations, and reviewing descriptive trends. The default dataset is deterministic, synthetic, and labeled as demo data. It does not represent actual measurements from ChatGPT, Claude, Gemini, or another commercial model.

## Screenshots

![AI Observatory overview with the synthetic demo dataset](docs/images/overview.png)

*Overview — synthetic demonstration data, clearly labeled as simulated.*

![Experiment Lab showing live API comparison and experiment history](docs/images/experiment-history.png)

*Experiment Lab — saved live runs and failed or excluded attempts remain visible in the history.*

## Architecture

- **Frontend:** TypeScript, React, and Vite with responsive analytics views, filters, experiment creation, response inspection, CSV/JSON downloads, and human review.
- **API:** FastAPI and Pydantic; docs at `http://localhost:8000/docs`.
- **Persistence:** SQLAlchemy ORM over SQLite by default. Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL when using a PostgreSQL driver.
- **Research data path:** prompt/model/repetition → run → immutable raw response → versioned extraction run → canonical brand observation → aggregation or human annotation.
- **Demo generation:** fixed seed and 90 historical days across 5 domains and 3 simulated models. Data is seeded once when the API starts, not on each page render.

The local in-process runner is suitable for a demo, not durable distributed execution. Live execution supports API-key adapters for OpenAI, Anthropic, Google Gemini, MiniMax, and DeepSeek, plus authenticated Claude Code, Codex, and GitHub Copilot CLI sessions detected on the machine running the API. Live execution is sequential, explicitly confirmed, and records provider errors. Search tools/citations, automatic scheduling, and pricing estimates are not implemented; search is disabled for live runs and cost is shown as unavailable.

## Install and launch (Windows PowerShell)

Python 3.11+ is recommended. From this directory:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\initialize_database.py
python scripts\generate_demo_data.py
```

Install the frontend dependencies once:

```powershell
cd frontend
npm install
cd ..
```

Start the API and frontend in two terminals:

```powershell
# Terminal 1
uvicorn backend.main:app --reload
```

```powershell
# Terminal 2
npm --prefix frontend run dev
```

Open `http://localhost:5173`. The Vite development server proxies API calls to FastAPI at port 8000. API health and interactive docs are at `http://localhost:8000/health` and `/docs`.

## Included research snapshot

The repository includes `ai_observatory.db` as a point-in-time snapshot so the dashboard opens with the experiment history. It contains the deterministic synthetic demo dataset and a small number of live pilot runs, including successful MiniMax, DeepSeek, Claude Code, and Codex CLI responses, failed provider-availability checks, and the Copilot Auto response marked excluded because its resolved model was unknown. The live work uses a single smartphone prompt and is descriptive demonstration data, not a statistically conclusive comparison. The database contains no API keys; credentials belong in your local, ignored `.env` file.

Because this snapshot database is intentionally committed, later local experiment runs are not automatically published. To share a newer history, commit the updated database explicitly after checking that it contains no private data or secrets.

To make a production frontend bundle, run `npm --prefix frontend run build`; the output is written to `frontend/dist`.

Set `APP_MODE=demo`, `DATABASE_URL=sqlite:///./ai_observatory.db`, and `API_BASE_URL=http://localhost:8000` in `.env`. Empty API-key values are fine; demo mode makes no paid API requests.

For live API-key providers, add one or more keys to `.env` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `MINIMAX_API_KEY`, or `DEEPSEEK_API_KEY`) and restart the backend. The MiniMax and DeepSeek adapters use their OpenAI-compatible chat-completions APIs; base URLs and model IDs can be overridden with the corresponding settings. The Experiment Lab detects signed-in Claude Code and Codex CLIs. Copilot is offered only with explicitly named models listed in `COPILOT_CLI_MODEL_IDS`; Auto routing is disabled because the resolved model is not recorded. Availability depends on the Copilot plan, CLI version, and organization policy; unavailable model requests are retained as failures and never counted as recommendations. The current signed-in Copilot CLI account exposes only Auto, so Copilot is disabled until the account provides a named model. The app does not directly connect to Gemini Enterprise through a browser login. Claude Pro and ChatGPT Plus are accessed through their respective local CLIs and use the CLI accounts' subscription terms. The CLI providers' usage or credit charges are controlled by those services.

Select **Live**, create the experiment, review its planned request count, and check the explicit acknowledgement before running. API pricing is not configured, so no estimate is shown; API providers may charge for requests. Live and demo models cannot be mixed in one experiment. A provider call failure is stored as a failed response and does not stop the remaining tasks. If the API process is interrupted during a live run, restart it and run that experiment again to continue from persisted requests. The app never reads API keys from terminal output; put API keys in `.env` and keep that file private.

To reset the synthetic observations for development, stop the API and run:

```powershell
python scripts\reset_demo_data.py
```

For a clean reset of IDs/schema, remove `ai_observatory.db`, then rerun initialization and generation. The API itself will seed demo data on first startup if the database is empty.

## Prompt for a coding agent

Copy this prompt into your coding agent if you want it to clone and run the demo locally:

```text
Clone https://github.com/rairurairu/ai-observatory-demo.git and help me run AI Observatory locally. Read README.md first and follow its setup steps. Keep the bundled ai_observatory.db experiment history intact. Use demo mode; do not read, print, copy, or upload any .env file or API key. Do not run paid/live experiments, reset the database, or push changes. Start the backend and frontend, then tell me the local URL and how to stop both servers.
```

## Five-minute demonstration

1. Open **Overview** and point out the synthetic data badge, denominator note, response-level mention rate, and domain/model filters.
2. In **Experiment Lab**, create an Automobiles experiment using all three simulated models, three prompt variants, and two repetitions. Review the configuration before selecting Run.
3. Inspect its run summary, then export the run as JSON or CSV.
4. Open **Model Comparison**, **Prompt Sensitivity**, and **Historical Trends** to discuss descriptive differences conditional on the prompt set. The drift item is explicitly illustrative.
5. Open **Response Explorer** to compare a raw response with its evidence-backed extracted observations, mention order, and explicit rank.
6. Save an annotation in **Data Quality** and show that it persists. Finish in **System Monitor** to show request/failure counts and that unavailable token/cost information is not fabricated.

## Tests

```powershell
pytest -q
```

Tests cover the seeded API, extraction and explicit-rank handling, domain-scoped rate aggregation, repeat-preserving demo execution, demo/live source isolation, and annotation persistence.

## Current scope and limitations

- Implemented: persistent normalized core schema; demo generation; controlled experiment CRUD/run; IDs for experiments/runs/responses; OpenAI, Anthropic, Gemini, MiniMax, and DeepSeek API adapters; Claude Code, Codex, and GitHub Copilot CLI adapters; explicit live cost acknowledgement; per-request failure persistence; deterministic dictionary extraction with aliases/product links; mention-level evidence; response-level brand rates; model comparison; historical trends; prompt-variant rates; review annotations; operational counts/logs; response export; CSV and JSON; TypeScript/React web frontend.
- Not implemented yet: provider-specific rate limiting beyond SDK retries; live price estimation; asynchronous durable job queue; provider search/citations; automatic scheduler; advanced hierarchical inference and statistical drift tests; Parquet snapshots. Do not interpret the illustrative drift note as a measured provider update.
- Sentiment and attribute extraction are conservative keyword rules. Outputs are research aids, not validated NLP measurements; unknown is retained where the rules do not find clear evidence.

## Database notes

SQLite schema is created with SQLAlchemy `create_all`. For a long-running study, add Alembic migrations before schema evolution and configure a PostgreSQL driver. Raw response text and prior extraction rows are retained; extraction versions are represented by `extraction_runs.pipeline_version`.
