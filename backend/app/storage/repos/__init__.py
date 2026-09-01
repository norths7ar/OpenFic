"""Storage repository package.

Import repository modules explicitly at their call sites so loading one repository
does not initialize the entire data-access layer.
"""
