"""Call an explicitly configured literature MCP server; never read its workspace."""

import asyncio
import hashlib
import os
import shlex
import shutil
import time

from aiscientist_mcp.common.tasks import ACTIVE
from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def query(command: str, question: str, analysis_id: str, timeout: float):
    argv = shlex.split(command)
    if not argv:
        raise ValueError("PHENOTYPE_LITERATURE_COMMAND is empty")
    # Independent literature workspaces per case/question, accessible only through MCP.
    token = hashlib.sha256(f"{analysis_id}\0{question}".encode()).hexdigest()[:32]
    literature_id = "phenotype-" + token
    parameters = StdioServerParameters(command=shutil.which(argv[0]) or argv[0], args=argv[1:], env=dict(os.environ))
    deadline = time.monotonic() + timeout
    async with Client(parameters, read_timeout_seconds=timeout) as client:

        async def call(name, arguments):
            result = await client.call_tool(name, arguments)
            if result.is_error:
                raise RuntimeError("literature MCP tool failed; inspect its job status/logs")
            if not isinstance(result.structured_content, dict):
                raise ValueError("literature MCP returned no structured result")
            return result.structured_content

        result = await call("deep_literature", {"question": question, "analysis_id": literature_id})
        while result.get("state") in ACTIVE:
            if time.monotonic() >= deadline:
                raise TimeoutError("literature MCP task timed out")
            if not result.get("task_id"):
                raise ValueError("literature MCP task returned no task_id")
            await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
            result = await call("literature_job_status", {"analysis_id": literature_id, "task_id": result["task_id"]})
        if result.get("state") == "FAILED":
            return {"status": "error", "note": "literature MCP job failed", "task_id": result.get("task_id")}
        if result.get("response_omitted"):
            return {
                "status": "error",
                "note": "literature MCP evidence was truncated; reduce the configured evidence breadth before grading",
            }
        return result


def executor(command: str, analysis_id: str, timeout: float):
    def call(arguments, _context=None):
        return asyncio.run(query(command, arguments["question"], analysis_id, timeout))

    return call
