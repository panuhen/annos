"""Domain layer — the only place business logic lives.

Parity means anything doable over MCP is also doable in the web UI. That only
stays true if both surfaces call the same functions: the FastMCP tools and the
REST routes are thin adapters over this package and contain no logic of their
own. If a rule lives in an adapter, the other surface will grow its own copy and
the two will drift on exactly what matters — day boundaries, macro snapshots,
goal-phase resolution.
"""
