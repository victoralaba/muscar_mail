import sys

# Python 3.14 alpha/beta compatibility guard:
# In Python 3.14 pre-releases, _asyncio.all_tasks C-extension can fault on loop shutdown.
# Falling back to the standard library's pure-Python implementation (_py_all_tasks) guarantees rock-solid stability.
if sys.version_info >= (3, 14):
    import asyncio
    import asyncio.tasks
    if hasattr(asyncio.tasks, "_py_all_tasks"):
        asyncio.tasks.all_tasks = asyncio.tasks._py_all_tasks
        asyncio.all_tasks = asyncio.tasks._py_all_tasks
