"""Storage service package.

Import service modules explicitly at their call sites so loading one service does
not initialize every business workflow.
"""
