# 🛡️ LedgerGuard: AP Controller Agent

Capstone for **AI Engineering: Production AI for Technical Teams** (AITraining2U, 11-13 Nov 2026, instructor
Richie Yu Yong Poh). An accounts-payable controller agent for a Malaysian SME: finance staff ask plain-English
questions about supplier bills, payments and approvals; LedgerGuard answers only from the ledger and the
company's policy documents, cannot change data, masks personal data and flags risk.

All company, supplier and personal data in this repo is invented.

## Results

| | |
|---|---|
| Evaluation (12 golden cases, judge `gemini-2.5-pro`) | **5.0 / 5 average, 12 / 12 passed**, US$0.26 per full run incl. judge ([report](eval_report.md)) |
| Offline guard tests | 55 / 55 passing, every guard mutation-checked (`pytest tests`) |
| UI end-to-end run | 6 / 6 demo questions answered correctly through the browser, incl. live migration (`tests/e2e_demo.py`) |
| Typical cost per question | about US$0.01-0.04 (8-14 model calls, `gemini-3.5-flash`) |

## How every capstone pillar is met

| Pillar | Implementation | File |
|---|---|---|
| 1. Multi-agent architecture | `controller_agent` routes through `AgentTool` to `ledger_analyst`, `policy_auditor`, `risk_detector` | `agents.py` |
| 2. Enterprise integration via MCP | Real FastMCP stdio server with `mcp_list_tables`, `mcp_describe_table`, `mcp_read_query`, `mcp_list_policies`, `mcp_read_policy`; agents get them through `McpToolset(tool_filter=...)`; the server's admin tool `mcp_apply_migration` is never registered with an agent; no schema in any prompt | `ledger_mcp_server.py` |
| 3. Two-tier guardrails | **Input:** PII masking (MY IC, phones, email, Luhn-checked cards, bank accounts) and injection blocking in `before_model_callback`. **Data:** `is_sql_mutation` (sqlparse syntax tree) at the agent (`before_tool_callback`) and again in the server, `file:...?mode=ro` with `uri=True`, `PRAGMA query_only`, plus a SQLite authorizer that only allows reads. `after_tool_callback` masks PII in tool output and strips hidden instructions from documents | `guards.py`, `callbacks.py` |
| 4. Observability & cost | `after_model_callback` records prompt, output and thinking tokens per agent and converts to US$ (prices configurable) | `callbacks.py` |
| 5. Evaluation harness | 12 golden cases (`capstone_golden.json`): ground truth from plain SQL, judge agent on a different model scores 1-5, deterministic checks for figures, leaked secrets and database integrity | `evaluate.py` |
| 6. Streamlit Cloud deployment | Chat with route/tool/guardrail trace per answer, cost meter, live migration simulator, schema inspector (`st.text`), security lab, evaluation tab, architecture tab; `st.secrets` with env fallback | `app.py` |
| Step 8: zero-code schema evolution | Sidebar "Run migration" adds `credit_notes` via a separate writable admin connection; the agent discovers and uses it | `seed_data.py` |

Architecture summary for submission: [ARCHITECTURE.md](ARCHITECTURE.md). Colab version of everything:
[capstone_ledgerguard.ipynb](capstone_ledgerguard.ipynb) (regenerate with `python build_notebook.py`).

## Run locally

```bash
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt pytest
python seed_data.py                                    # builds enterprise.db + policies/
set GOOGLE_API_KEY=your-key                            # macOS/Linux: export GOOGLE_API_KEY=your-key
streamlit run app.py
pytest tests                                           # offline guard tests, no key needed
python evaluate.py                                     # full evaluation (~90 model calls)
```

Settings (env vars or Streamlit secrets): `GOOGLE_API_KEY`, `LEDGERGUARD_MODEL` (default `gemini-3.5-flash`),
`LEDGERGUARD_JUDGE_MODEL` (default `gemini-2.5-pro`), `LEDGERGUARD_TRANSPORT` (`mcp` default, or `inprocess`
if a host blocks subprocesses), `LEDGERGUARD_PRICE_IN` / `LEDGERGUARD_PRICE_OUT` (US$ per 1M tokens).

## Deploy to Streamlit Community Cloud

1. share.streamlit.io → **Create app** → this repository, branch `main`, main file `app.py`.
2. **Advanced settings** → Python **3.12** → Secrets:
   ```toml
   GOOGLE_API_KEY = "your-gemini-key"
   ```
3. **Deploy.** If the MCP subprocess is refused on the host, add `LEDGERGUARD_TRANSPORT = "inprocess"` to the secrets.

## Known limits (stated honestly)

- The injection filter is a phrase list: it stops common attacks, not every paraphrase. The data tier is built to
  hold even when the input tier is bypassed (the Security lab tab proves this with the guard switched off).
- Gemini prices in `callbacks.py` are assumptions to verify on Google's pricing page; `gemini-3.5-flash` is
  priced like `gemini-2.5-flash` there.
- Raw user text (before masking) stays in the in-memory ADK session; it is never sent to the model or shown.
- `credit_notes` and the demo data are reset by the sidebar "Reset demo data" button.
