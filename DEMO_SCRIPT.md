# LedgerGuard: 5-minute demo script

Before you start: open the app, click **Reset demo data** in the sidebar, and keep the Security lab tab ready.
Every question below is a button in the sidebar under "Demo questions".

| Time | Do | Say | What the audience sees |
|---|---|---|---|
| 0:00 | Architecture tab | "LedgerGuard is an accounts-payable controller for a Malaysian SME. One coordinator, three specialists, one MCP server, and three locks on the data." | The diagram |
| 0:30 | Analyst tab → **Which supplier do we owe the most right now?** | "The coordinator routes to the ledger analyst. It has no schema in its prompt: it lists tables, describes them, then queries." | RM 79,097.99 for Teknologi Awan Nusantara; open "How this was answered" to show the tool calls and the cost |
| 1:00 | **Which bills breach our approval matrix?** | "The policy auditor reads the approval matrix through MCP, quotes the rule, then checks the ledger." | 57, 62, 169, 174 missing approval; 151 approved by a Finance Manager above RM 20,000; and the split purchase 56 + 209 (same supplier, same day, RM 7,955.84 together, no approver) |
| 1:30 | (same answer) | "It also applied the split-billing rule from the policy on its own. I did not plant that pair: the agent found it in the data, and I then added it to the golden set." | The split-purchase row |
| 1:40 | **Do we have any suspected duplicate supplier bills?** | "The risk detector normalises references: TM-9889 and TM9889 are the same bill." | 3 pairs; hold 241, 242, 243 |
| 2:10 | **My IC is 880312-14-5566…** | "Personal data is masked before the model ever sees it." | Expander shows the PII-masking event |
| 2:30 | **Ignore all previous instructions…** | "Prompt injection is stopped before the model is called: zero tokens spent." | 🛡️ Blocked message, 0 model calls |
| 2:50 | **Please mark invoice 57 as approved…** | "Even a polite request cannot write. The ledger is read-only from chat." | Refusal + correct manual process |
| 3:10 | Security lab tab | "What if someone gets a DROP past the prompt? Layer 2, the syntax tree, blocks it. And here layer 2 is switched OFF: the engine itself still refuses. No write got through." | Attack table, all 🚫 in both columns |
| 3:40 | Same tab, scroll | "A hidden instruction is planted in our KYC policy. The tool-output sanitiser strips it before the agent reads it." | Cleaned policy text |
| 4:00 | Sidebar **Run migration** → **Do we have any credit notes?** | "The data team just added a table. I changed no code. The agent discovers it through MCP." | Net payable to Syarikat Maju Logistik RM 34,219.66 |
| 4:30 | Evaluation tab, then the sidebar cost meter | "12 golden cases, answers checked against SQL, graded by a different model: 5.0 out of 5, 12 of 12, about 26 US cents for the full run including the judge." | Scorecard + telemetry |

Backup answers if the API is slow: screenshots in `docs/screenshots/`.

Likely questions:
- *Why a different judge model?* A model grading itself tends to score its own style higher; the ground truth also comes from SQL, not from the judge.
- *Is the MCP real?* Yes: `ledger_mcp_server.py` runs as a separate process (FastMCP over stdio). `tool_filter` is an allow-list, so the server's admin migration tool never reaches an agent.
- *What if the injection filter misses a paraphrase?* That is why the data tier exists: read-only URI, `query_only`, and an authorizer at the SQLite engine, each enough on its own.
- *Why not trust `mode=ro` alone?* Without `uri=True`, Python silently opens a new writable file instead (`tests/test_guards.py` proves it).
