"""Step 4: the LedgerGuard MCP server (FastMCP, stdio transport).

Discovery primitives the agents use (no schema is hard-coded in any prompt):
  mcp_list_tables, mcp_describe_table, mcp_read_query, mcp_list_policies, mcp_read_policy
Administrative primitive that agents must NEVER receive (excluded by McpToolset.tool_filter):
  mcp_apply_migration  (used by the data team's migration simulator)

Run standalone for MCP Inspector:  python ledger_mcp_server.py
"""
import json
import os
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from guards import connect_ro, is_sql_mutation

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LEDGERGUARD_DB", HERE / "enterprise.db"))
POLICY_DIR = Path(os.environ.get("LEDGERGUARD_POLICIES", HERE / "policies"))
MAX_ROWS = 200

mcp = FastMCP("ledgerguard")


def _tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


@mcp.tool()
def mcp_list_tables() -> dict:
    """List every table in the accounts-payable database with its row count.
    Call this first: tables can be added at any time, so never assume the schema."""
    conn = connect_ro(DB_PATH)
    try:
        return {"tables": [{"name": t, "rows": conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]}
                           for t in _tables(conn)]}
    finally:
        conn.close()


@mcp.tool()
def mcp_describe_table(table_name: str) -> dict:
    """Return the CREATE TABLE definition, row count and 3 sample rows of one table.
    Use it to learn column names and types before writing a query."""
    conn = connect_ro(DB_PATH)
    try:
        if table_name not in _tables(conn):  # also stops identifier injection in the f-strings below
            return {"error": f"Unknown table '{table_name}'. Call mcp_list_tables first."}
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()[0]
        cur = conn.execute(f'SELECT * FROM "{table_name}" LIMIT 3')
        cols = [d[0] for d in cur.description]
        return {"table": table_name, "ddl": ddl,
                "row_count": conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0],
                "sample_rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        conn.close()


@mcp.tool()
def mcp_read_query(sql: str) -> dict:
    """Run ONE read-only SQLite SELECT query and return up to 200 rows.
    Any write, DDL, PRAGMA, ATTACH or stacked statement is refused. Use SQLite date functions,
    e.g. julianday('2026-11-13') - julianday(due_date) for days past due."""
    if is_sql_mutation(sql):
        return {"blocked": True, "layer": "AST guard (is_sql_mutation)",
                "error": "Refused: only a single read-only SELECT statement is allowed."}
    conn = connect_ro(DB_PATH)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        return {"columns": cols, "rows": [list(r) for r in rows[:MAX_ROWS]],
                "row_count": min(len(rows), MAX_ROWS), "truncated": len(rows) > MAX_ROWS}
    except sqlite3.DatabaseError as e:  # authorizer / mode=ro / syntax errors land here
        msg = str(e)
        layer = "SQLite authorizer / read-only connection" if ("not authorized" in msg or "readonly" in msg) else "SQL error"
        return {"blocked": layer != "SQL error", "layer": layer, "error": msg}
    finally:
        conn.close()


@mcp.tool()
def mcp_list_policies() -> dict:
    """List the company's finance policy documents (approval matrix, SST guide, payment, KYC)."""
    return {"policies": sorted(p.name for p in POLICY_DIR.glob("*.md"))}


@mcp.tool()
def mcp_read_policy(name: str) -> dict:
    """Return the full text of one policy document by file name (from mcp_list_policies)."""
    target = (POLICY_DIR / name).resolve()
    if target.parent != POLICY_DIR.resolve() or target.suffix != ".md" or not target.is_file():
        return {"error": f"Unknown policy '{name}'. Call mcp_list_policies first."}  # blocks ../ traversal
    return {"name": target.name, "text": target.read_text(encoding="utf-8")}


@mcp.tool()
def mcp_apply_migration(sql_script: str) -> dict:
    """ADMIN ONLY: apply a schema migration script with a writable connection.
    Never exposed to the analyst agents (excluded by tool_filter)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql_script)
        conn.commit()
        return {"applied": True, "tables": _tables(conn)}
    finally:
        conn.close()


AGENT_DB_TOOLS = ["mcp_list_tables", "mcp_describe_table", "mcp_read_query"]
AGENT_POLICY_TOOLS = ["mcp_list_policies", "mcp_read_policy"]

if __name__ == "__main__":
    mcp.run()  # stdio
