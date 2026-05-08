import pytest

from hubspot_agent.models import BatchApprovalMode
from hubspot_agent.orchestrator import dispatch_agents_parallel, dispatch_agent


@pytest.mark.asyncio
async def test_parallel_dispatch_preview_mode():
    agent_names = ["objects", "analytics", "pipelines"]
    results = await dispatch_agents_parallel(
        agent_names,
        "find contacts",
        mode="preview",
    )
    assert len(results) == 3
    names = [r.agent_name for r in results]
    assert sorted(names) == sorted(agent_names)
    for r in results:
        assert r.status == "preview"


@pytest.mark.asyncio
async def test_parallel_dispatch_execute_mode_is_serial():
    agent_names = ["objects", "analytics"]
    results = await dispatch_agents_parallel(
        agent_names,
        "update contacts",
        mode="execute",
    )
    assert len(results) == 2
    for r in results:
        assert r.status == "ready"


@pytest.mark.asyncio
async def test_parallel_dispatch_single_agent():
    results = await dispatch_agents_parallel(
        ["objects"],
        "find contacts",
        mode="preview",
    )
    assert len(results) == 1
    assert results[0].agent_name == "objects"


@pytest.mark.asyncio
async def test_parallel_dispatch_empty_list():
    results = await dispatch_agents_parallel(
        [],
        "find contacts",
        mode="preview",
    )
    assert results == []


@pytest.mark.asyncio
async def test_parallel_dispatch_preserves_batch_mode():
    results = await dispatch_agents_parallel(
        ["objects"],
        "find contacts",
        mode="preview",
        batch_mode=BatchApprovalMode.BATCH,
    )
    assert results[0].data["batch_mode"] == "batch"
