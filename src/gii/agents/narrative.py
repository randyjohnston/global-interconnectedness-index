"""Narrative agent — generates human-readable explanations of index changes."""

import logging

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage

from gii.agents.tools import get_index_delta, get_pillar_breakdown
from gii.config import settings
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an analyst writing concise narratives about changes in the Global Interconnectedness Index.

For each country pair, explain:
1. What changed in their composite score
2. Which pillar(s) drove the change
3. Possible real-world context (trade agreements, geopolitical events, new flight routes, etc.)

Keep each narrative to 2-3 sentences. Be specific about numbers.
Use the tools to get delta and breakdown data."""


async def generate_period_narratives(period: str, top_n: int = 10) -> int:
    """Generate narratives for the top movers in a period."""
    if not settings.nvidia_api_key:
        logger.warning("NVIDIA API key not configured, skipping narratives")
        return 0

    session = get_session()
    repo = Repository(session)
    snapshots = repo.get_snapshots(period)

    if len(snapshots) < 2:
        session.close()
        return 0

    # Get pairs with largest composite scores (proxy for "most interesting")
    top_pairs = [(s.country_a, s.country_b) for s in snapshots[:top_n]]

    llm = ChatNVIDIA(
        model=settings.llm_model,
        api_key=settings.nvidia_api_key,
        temperature=1,
        top_p=0.95,
        max_tokens=4096,
    )

    llm_with_tools = llm.bind_tools([get_index_delta, get_pillar_breakdown])
    count = 0

    for country_a, country_b in top_pairs:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Generate a narrative for {country_a}-{country_b} in period {period}. Use the tools to get the data first."),
        ]

        for _ in range(5):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_fn = get_index_delta if tool_name == "get_index_delta" else get_pillar_breakdown
                tool_result = tool_fn.invoke(tool_call["args"])
                messages.append({"role": "tool", "content": str(tool_result), "tool_call_id": tool_call["id"]})

        narrative = response.content if isinstance(response.content, str) else str(response.content)
        repo.save_narrative(country_a, country_b, period, narrative)
        count += 1

    repo.commit()
    session.close()
    logger.info(f"Generated {count} narratives for {period}")
    return count
