"""Adapters — thin translation between a transport and the domain layer.

Nothing in here decides anything. Each function validates input, resolves the
caller, calls one domain function, and shapes the result. When you find yourself
writing an `if` that expresses a rule, it belongs in annos.domain instead.
"""
