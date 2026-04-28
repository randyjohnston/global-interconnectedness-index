"""Narrative agent — LangChain Deep Agent that generates index change explanations.

Uses deepagents.create_deep_agent to give the LLM full control over
tool invocation. The agent decides when to call get_index_delta and
get_pillar_breakdown to gather context before writing the narrative.

All runs are traced in LangSmith when configured.
"""

import logging

from deepagents import create_deep_agent

from gii.agents.llm import get_llm, is_llm_configured
from gii.agents.tools import get_index_delta, get_pillar_breakdown
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)

INSTRUCTIONS = """You are an analyst writing concise narratives about changes in the Global Interconnectedness Index.

You have tools to look up index data. For each country pair you are asked about:
1. Use get_pillar_breakdown to see the current pillar scores
2. Use get_index_delta to see how scores changed vs the previous period
3. Write a 2-3 sentence narrative explaining what changed and why

Important formatting rules:
- On first mention, refer to each country by its full name followed by its ISO3 code in parentheses, e.g. "United States (USA)" or "China (CHN)". After the first mention, you may use either the full name or code.
- Use markdown formatting (bold, bullet points, etc.) for readability.
- Be specific about numbers.
- After gathering data with tools, write your final narrative as a plain text response (no tool calls).
- Exclude and preamble before the narrative, e.g. "Here's what I found:" or "Based on the data:". Just write the narrative directly."""

def build_agent(streaming: bool = False):
    """Build the narrative deep agent."""
    llm = get_llm(streaming=streaming)
    return create_deep_agent(
        tools=[get_index_delta, get_pillar_breakdown],
        instructions=INSTRUCTIONS,
        model=llm,
    )


async def generate_period_narratives(period: str, top_n: int = 10, source: str = "temporal", thread_id: str | None = None) -> int:
    """Generate narratives for the top movers in a period.

    Each country-pair narrative is traced as a separate LangSmith run,
    grouped under a shared thread (the Temporal workflow ID when available).
    """
    if not is_llm_configured():
        logger.warning("LLM provider not configured, skipping narratives")
        return 0

    session = get_session()
    repo = Repository(session)
    snapshots = repo.get_snapshots(period)

    if len(snapshots) < 2:
        session.close()
        return 0

    # Build country name lookup
    countries = {c.iso3: c.name for c in repo.list_countries()}

    # Get pairs with largest composite scores (proxy for "most interesting")
    top_pairs = [(s.country_a, s.country_b) for s in snapshots[:top_n]]

    agent = build_agent()
    count = 0

    for country_a, country_b in top_pairs:
        name_a = countries.get(country_a, country_a)
        name_b = countries.get(country_b, country_b)

        try:
            metadata = {"country_a": country_a, "country_b": country_b, "period": period}
            if thread_id:
                metadata["thread_id"] = thread_id

            result = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Generate a narrative for {name_a} ({country_a}) "
                                f"and {name_b} ({country_b}) in period {period}. "
                                f"Use the tools to gather data first."
                            ),
                        }
                    ],
                },
                config={
                    "run_name": "generate_narrative",
                    "tags": [source, period],
                    "metadata": metadata,
                    "callbacks": [],  # isolate from parent trace context
                },
            )

            # Walk backwards to find the last AI message with actual text (not a tool call)
            narrative = ""
            for msg in reversed(result["messages"]):
                if msg.type != "ai":
                    continue
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    continue
                # Extract text: str for NVIDIA, list of content blocks for Bedrock
                if isinstance(msg.content, str):
                    text = msg.content
                elif isinstance(msg.content, list):
                    text = "".join(
                        block.get("text", "") for block in msg.content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                else:
                    continue
                if text.strip():
                    narrative = text
                    break

            if not narrative:
                logger.warning(f"Narrative empty for {country_a}-{country_b}, skipping save")
                continue

            repo.save_narrative(country_a, country_b, period, narrative)
            count += 1
            logger.info(f"Narrative: {country_a}-{country_b} done ({count}/{len(top_pairs)})")

        except Exception as e:
            logger.error(f"Narrative failed for {country_a}-{country_b}: {e}")

    repo.commit()
    session.close()
    logger.info(f"Generated {count} narratives for {period}")
    return count
