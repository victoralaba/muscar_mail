import os
import sys

# Inject test environment variables before module imports
os.environ.setdefault("VERIFALIA_USERNAME", "test_verifalia_user")
os.environ.setdefault("VERIFALIA_PASSWORD", "test_verifalia_pass")
os.environ.setdefault("MCP_API_KEYS", "test_key_1,test_key_2")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# Ensure Python 3.14 stability across all test runners
if sys.version_info >= (3, 14):
    import asyncio
    import asyncio.tasks
    if hasattr(asyncio.tasks, "_py_all_tasks"):
        asyncio.tasks.all_tasks = asyncio.tasks._py_all_tasks
        asyncio.all_tasks = asyncio.tasks._py_all_tasks
