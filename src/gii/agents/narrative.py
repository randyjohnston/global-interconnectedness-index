"""Narrative agent — supervisor with domain-specialist subagents.

The supervisor delegates to three subagents (trade, travel, geopolitics),
each with access to domain-specific database tools and a Tavily web search
tool restricted to a configurable whitelist of allowed domains. The supervisor
awaits each subagent's report, then synthesizes a single summary narrative.

All runs are traced in LangSmith when configured.
"""

import logging

from deepagents import create_deep_agent

from gii.agents.llm import get_llm, is_llm_configured
from gii.agents.tools import (
    build_geopolitics_search,
    build_trade_search,
    build_travel_search,
    get_index_delta,
    get_pillar_breakdown,
    query_geopolitics_data,
    query_trade_data,
    query_travel_data
)
from gii.config import settings
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)

SUPERVISOR_INSTRUCTIONS = """\
You are a supervisor analyst for the Global Interconnectedness Index (GII).

When asked to generate a narrative for a country pair and period, you MUST:
1. Delegate to ALL THREE specialist subagents in parallel by calling the `task` tool three times — once for each: trade_analyst, travel_analyst, geopolitics_analyst.
   Pass each the country pair ISO3 codes and period so they can query their domain data and search for relevant news.
2. Wait for all three reports to come back.
3. Synthesize their findings into a single, cohesive 3-5 paragraph narrative covering:
   - Overall composite score movement and what drove it
   - Key highlights from each pillar (trade, travel, geopolitics)
   - Any notable recent news or events that contextualise the score changes

Important formatting rules:
- On first mention, refer to each country by its full name followed by its ISO3 code in parentheses, e.g. "United States (USA)".
- Use markdown formatting (bold, bullet points, etc.) for readability.
- Be specific about numbers — include actual scores, deltas, and percentages.
- Write the final narrative directly with no preamble like "Here's what I found:" nor "Now let me query..." and without new lines and horitontal lines.
"""

TRADE_SUBAGENT_PROMPT = """\
You are a trade analyst for the Global Interconnectedness Index.
When given a country pair and period:
1. Use query_trade_data to get bilateral trade volumes, index scores, and deltas.
2. Use search_trade_news to find recent trade-related news between these countries (tariffs, agreements, sanctions, trade volumes).
3. Write a concise 2-3 paragraph analysis of the trade relationship, covering:
   - Current bilateral trade volumes and direction
   - How the trade pillar score changed vs the previous period and why
   - Any relevant recent news or policy changes that may explain the trend
Be specific with numbers. Return your analysis as plain text.
"""

TRAVEL_SUBAGENT_PROMPT = """\
You are a travel and aviation analyst for the Global Interconnectedness Index.
When given a country pair and period:
1. Use query_travel_data to get flight connectivity data, index scores, and deltas.
2. Use search_travel_news to find recent travel-related news between these countries (new routes, travel restrictions, tourism trends).
3. Write a concise 2-3 paragraph analysis of travel connectivity, covering:
   - Current flight route count and connectivity level
   - How the travel pillar score changed vs the previous period and why
   - Any relevant recent news about aviation, tourism, or travel policy
Be specific with numbers. Return your analysis as plain text.
"""

GEOPOLITICS_SUBAGENT_PROMPT = """\
You are a geopolitical analyst for the Global Interconnectedness Index.
When given a country pair and period:
1. Use query_geopolitics_data to get Goldstein scores, cooperation ratios, event counts, and deltas.
2. Use search_geopolitics_news to find recent geopolitical news between these countries (diplomacy, sanctions, treaties, conflicts).
3. Write a concise 2-3 paragraph analysis of the geopolitical relationship, covering:
   - Current Goldstein scale average and cooperative ratio
   - How the geopolitics pillar score changed vs the previous period and why
   - Any relevant recent diplomatic, security, or political developments
Be specific with numbers. Return your analysis as plain text.
"""


def build_agent(streaming: bool = False):
    """Build the supervisor agent with three domain-specialist subagents."""
    llm = get_llm(streaming=streaming)

    all_tools = [
        get_index_delta,
        get_pillar_breakdown,
        query_trade_data,
        query_travel_data,
        query_geopolitics_data,
    ]

    trade_tool_names = ["query_trade_data"]
    travel_tool_names = ["query_travel_data"]
    geopolitics_tool_names = ["query_geopolitics_data"]

    if settings.tavily_api_key:
        all_tools.extend([build_trade_search(), build_travel_search(), build_geopolitics_search()])
        trade_tool_names.append("search_trade_news")
        travel_tool_names.append("search_travel_news")
        geopolitics_tool_names.append("search_geopolitics_news")

    return create_deep_agent(
        model=llm,
        instructions=SUPERVISOR_INSTRUCTIONS,
        tools=all_tools,
        subagents=[
            {
                "name": "trade_analyst",
                "description": "Analyze bilateral trade data and recent trade news for a country pair",
                "prompt": TRADE_SUBAGENT_PROMPT,
                "tools": trade_tool_names,
            },
            {
                "name": "travel_analyst",
                "description": "Analyze flight connectivity and recent travel news for a country pair",
                "prompt": TRAVEL_SUBAGENT_PROMPT,
                "tools": travel_tool_names,
            },
            {
                "name": "geopolitics_analyst",
                "description": "Analyze geopolitical relations and recent geopolitics news for a country pair",
                "prompt": GEOPOLITICS_SUBAGENT_PROMPT,
                "tools": geopolitics_tool_names,
            },
        ],
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
            metadata = {"country_a": country_a,
                        "country_b": country_b, "period": period}
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
                logger.warning(
                    f"Narrative empty for {country_a}-{country_b}, skipping save")
                continue

            repo.save_narrative(country_a, country_b, period, narrative)
            count += 1
            logger.info(
                f"Narrative: {country_a}-{country_b} done ({count}/{len(top_pairs)})")

        except Exception as e:
            logger.error(f"Narrative failed for {country_a}-{country_b}: {e}")

    repo.commit()
    session.close()
    logger.info(f"Generated {count} narratives for {period}")
    return count

# hack for langgraph to detect the agent dependency without running generate_period_narratives at import time
agent = build_agent()
