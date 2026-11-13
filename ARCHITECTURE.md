### Architecture summary

**LedgerGuard** is an accounts-payable controller agent for a Malaysian SME. A coordinator agent
(`controller_agent`, Google ADK) routes each question through `AgentTool` to one of three specialists:
`ledger_analyst` (figures, balances, rankings), `policy_auditor` (what a policy says and which bills break it)
and `risk_detector` (duplicate bills, SST errors, overdue bills). No schema is written into any prompt. The
specialists reach the data only through a real **Model Context Protocol server** (`ledger_mcp_server.py`,
FastMCP over stdio) and discover it at run time with `mcp_list_tables`, `mcp_describe_table`,
`mcp_read_query`, `mcp_list_policies` and `mcp_read_policy`. Least privilege is enforced at the protocol
level: the server also offers an admin tool, `mcp_apply_migration`, but each `McpToolset` carries a
`tool_filter` allow-list, so no agent ever receives it. Because tools are discovered rather than hard-coded,
when the data team adds a `credit_notes` table the agents find and use it with no code change.

Safety is layered so that no single control has to be perfect. **Input tier:** a `before_model_callback`
masks Malaysian personal data (IC numbers, phones, emails, Luhn-valid card numbers, bank accounts) in
everything the model is about to read, and short-circuits prompt-injection attempts before the model is
called. **Data tier:** a `before_tool_callback` and the MCP server both run `is_sql_mutation`, a `sqlparse`
syntax-tree check that allows exactly one plain SELECT (stacked statements, CTE-wrapped writes, PRAGMA,
ATTACH and VACUUM are refused). Below that, the connection itself is physically read-only
(`file:...?mode=ro` with `uri=True`, `PRAGMA query_only`) and a SQLite authorizer permits only read
operations, so even a bypass of the syntax check cannot write. An `after_tool_callback` masks personal data
in tool output and strips instructions hidden in documents (the vendor KYC policy contains a planted one).
An `after_model_callback` records prompt, output and thinking tokens per agent and converts them to US$.
Quality is measured by a 12-case golden set whose answers are computed with plain SQL, graded 1-5 by a
judge agent on a different model (`gemini-2.5-pro`), plus deterministic checks for figures, leaks and
database integrity.
