"""Legacy middleware compatibility helpers.

The assistant runtime no longer wires LangChain create_agent middleware.  The
modules in this package are retained only for narrow tests/import compatibility
while graph orchestration is handled by the imperative pipeline.
"""
