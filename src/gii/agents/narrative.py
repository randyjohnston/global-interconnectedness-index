"""Narrative agent — supervisor with domain-specialist subagents.

The supervisor delegates to three subagents (trade, travel, geopolitics),
each with access to domain-specific database tools and a Tavily web search
tool restricted to a configurable whitelist of allowed domains. The supervisor
awaits each subagent's report, then synthesizes a single summary narrative.

All runs are traced in LangSmith when configured.
"""

import logging
import uuid

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from gii.agents.llm import get_llm, is_llm_configured
from gii.agents.tools import (
    build_geopolitics_search,
    build_trade_search,
    build_travel_search,
    get_index_delta,
    get_pillar_breakdown,
    query_geopolitics_data,
    query_trade_data,
    query_travel_data,
    save_narrative,
)
from gii.config import settings
from gii.storage.database import get_session
from gii.storage.repository import Repository

logger = logging.getLogger(__name__)

SUPERVISOR_INSTRUCTIONS = """\
You are a supervisor analyst for the Global Interconnectedness Index (GII).

INPUT: a country pair (ISO3) and period.

PROCESS:
1. Call `task` three times in parallel: trade_analyst, travel_analyst, geopolitics_analyst. Pass ISO3 codes and period to each.
2. Wait for all three reports.
3. Synthesize them into a single narrative.
4. Call `save_narrative` with the country pair, period, and narrative text.

OUTPUT FORMAT (strict):
- No preamble. No "Here's what I found", "Now I'll synthesize, "In summary", or any meta-commentary.
- Exactly 4 paragraphs. 60-100 words each. Hard cap: 400 words total.
- Paragraph 1: composite GII score, delta vs prior period, and the top driver pillar. Cite specific numbers.
- Paragraph 2: trade pillar — score delta and one supporting figure or event.
- Paragraph 3: travel pillar — score delta and one supporting figure or event.
- Paragraph 4: geopolitics pillar — score delta and one supporting figure or event.
- First mention of each country: full name + ISO3, e.g. "United States (USA)". Thereafter use ISO3.
- Bold key figures. Use bullets only when listing 3+ parallel items.

STYLE RULES (non-negotiable):
- No hedging: remove "appears to", "seems to", "suggests that", "notably", "significantly", "interestingly".
- No adjectives unless quantitative ("12% higher", not "substantially higher").
- One claim per sentence. Active voice. Past or present tense only.
- If a fact isn't in a subagent report, omit it. Do not speculate or add outside knowledge.

REJECT your draft and rewrite if it contains:
- More than 400 words or more than 4 paragraphs
- Any sentence over 25 words
- Phrases like "robust", "complex landscape", "amid", "underscores", "highlights", "fraught", "burgeoning", "geopolitical headwinds", "broader context"

EXAMPLE OUTPUT (match this length and density):

The **United States (USA)–Mexico (MEX)** composite GII score rose from **0.75 to 0.78** in Q3 2025, a **4.0% increase**. Trade drove most of the gain, with travel and geopolitics contributing smaller upward moves. All three pillars improved versus the prior period.

Trade volume reached **$798B**, up **4.2% YoY**, lifting the trade pillar from **0.81 to 0.84**. The October 2025 USMCA review concluded without new tariffs. A November semiconductor co-investment pact added **$12B** in committed cross-border flows.

Bilateral seat capacity reached **4.2M**, up **6.8% YoY**, lifting the travel pillar from **0.76 to 0.79**. Viva Aerobus launched daily Monterrey–Austin service in September 2025. The October 2025 US–Mexico open-skies extension preserved unrestricted carrier access through 2030.

The geopolitics pillar rose from **0.68 to 0.73** as the average Goldstein score climbed from **2.1 to 3.4** across **1,240 events**. Presidents met in Mexico City on October 12, 2025, signing a joint security framework on fentanyl interdiction. A November water-treaty agreement resolved a 3-year Rio Grande dispute.
"""


TRADE_SUBAGENT_PROMPT = """\
You are a trade analyst for the Global Interconnectedness Index.

INPUT: a country pair and period.

PROCESS:
1. Call query_trade_data for bilateral volumes, scores, deltas.
2. Call search_trade_news for tariffs, agreements, sanctions, volume shifts.

OUTPUT FORMAT (strict):
- Exactly 2 paragraphs. 60-100 words each. Hard cap: 200 words total.
- Paragraph 1: current bilateral trade volume, direction, and pillar score delta vs prior period. Cite specific numbers.
- Paragraph 2: one or two news items that explain the delta. Name the policy/event and date.

STYLE RULES (non-negotiable):
- No preamble. No "This analysis examines..." or "In summary...".
- No hedging adverbs: remove "notably", "significantly", "interestingly", "it is worth noting".
- No adjectives unless quantitative ("12% higher", not "substantially higher").
- One claim per sentence. Active voice. Past or present tense only.
- If a fact isn't in the tool output, omit it. Do not speculate.

REJECT your draft and rewrite if it contains:
- More than 200 words
- Any sentence over 25 words
- Phrases like "robust", "complex landscape", "amid", "underscores", "highlights"
"""

TRAVEL_SUBAGENT_PROMPT = """\
You are a travel and aviation analyst for the Global Interconnectedness Index.

INPUT: a country pair (ISO3) and period.

PROCESS:
1. Call `query_travel_data` for flight connectivity, seat capacity, route counts, and pillar score deltas.
2. Call `search_travel_news` for route launches/suspensions, airline agreements, visa changes, border policy shifts.

OUTPUT FORMAT (strict):
- Exactly 2 paragraphs. 60-100 words each. Hard cap: 200 words total.
- Paragraph 1: current bilateral flight connectivity (seats, routes, or frequency) and travel pillar score delta vs prior period. Cite specific numbers.
- Paragraph 2: one or two news items that explain the delta. Name the airline, route, or policy and the date.

STYLE RULES (non-negotiable):
- No preamble. No "This analysis examines..." or "In summary...".
- No hedging adverbs: remove "notably", "significantly", "interestingly", "it is worth noting".
- No adjectives unless quantitative ("18% more seats", not "substantially more seats").
- One claim per sentence. Active voice. Past or present tense only.
- If a fact isn't in the tool output, omit it. Do not speculate.

REJECT your draft and rewrite if it contains:
- More than 200 words
- Any sentence over 25 words
- Phrases like "robust", "vibrant", "burgeoning", "amid", "underscores", "highlights", "complex landscape"
"""


GEOPOLITICS_SUBAGENT_PROMPT = """\
You are a geopolitics analyst for the Global Interconnectedness Index.

INPUT: a country pair (ISO3) and period.

PROCESS:
1. Call `query_geopolitics_data` for Goldstein scores, event counts, cooperation/conflict balance, and pillar score deltas.
2. Call `search_geopolitics_news` for diplomatic visits, treaties, sanctions, disputes, multilateral actions.

OUTPUT FORMAT (strict):
- Exactly 2 paragraphs. 60-100 words each. Hard cap: 200 words total.
- Paragraph 1: average Goldstein score, event volume, and geopolitics pillar score delta vs prior period. Cite specific numbers.
- Paragraph 2: one or two diplomatic events that explain the delta. Name the actors, action, and date.

STYLE RULES (non-negotiable):
- No preamble. No "This analysis examines..." or "In summary...".
- No hedging adverbs: remove "notably", "significantly", "interestingly", "it is worth noting".
- No adjectives unless quantitative ("Goldstein score fell 1.2 points", not "tensions deepened markedly").
- One claim per sentence. Active voice. Past or present tense only.
- If a fact isn't in the tool output, omit it. Do not speculate.

REJECT your draft and rewrite if it contains:
- More than 200 words
- Any sentence over 25 words
- Phrases like "fraught", "tensions mount", "amid", "underscores", "highlights", "geopolitical headwinds", "complex landscape"
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
        save_narrative,
    ]

    trade_tools = [query_trade_data]
    travel_tools = [query_travel_data]
    geopolitics_tools = [query_geopolitics_data]

    if settings.tavily_api_key:
        trade_search = build_trade_search()
        travel_search = build_travel_search()
        geopolitics_search = build_geopolitics_search()
        all_tools.extend([trade_search, travel_search, geopolitics_search])
        trade_tools.append(trade_search)
        travel_tools.append(travel_search)
        geopolitics_tools.append(geopolitics_search)

    return create_deep_agent(
        model=llm,
        system_prompt=SUPERVISOR_INSTRUCTIONS,
        tools=all_tools,
        interrupt_on={"save_narrative":
                      {"allowed_decisions": [
                          "approve", "reject"]}} if streaming else None,
        checkpointer=MemorySaver() if streaming else None,
        subagents=[
            {
                "name": "trade_analyst",
                "description": "Analyze bilateral trade data and recent trade news for a country pair",
                "system_prompt": TRADE_SUBAGENT_PROMPT,
                "tools": trade_tools,
            },
            {
                "name": "travel_analyst",
                "description": "Analyze flight connectivity and recent travel news for a country pair",
                "system_prompt": TRAVEL_SUBAGENT_PROMPT,
                "tools": travel_tools,
            },
            {
                "name": "geopolitics_analyst",
                "description": "Analyze geopolitical relations and recent geopolitics news for a country pair",
                "system_prompt": GEOPOLITICS_SUBAGENT_PROMPT,
                "tools": geopolitics_tools,
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

    agent = build_agent(streaming=False)
    count = 0

    for country_a, country_b in top_pairs:
        name_a = countries.get(country_a, country_a)
        name_b = countries.get(country_b, country_b)

        try:
            metadata = {"country_a": country_a,
                        "country_b": country_b, "period": period}
            if thread_id:
                metadata["thread_id"] = thread_id
                
            cfg = {
                "run_name": "generate_narrative",
                "tags": [source, period],
                "metadata": metadata,
                "callbacks": [],  # isolate from parent trace 
                "configurable": {"thread_id": thread_id or str(uuid.uuid4())}
            }
                
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
                config=cfg,
            )

            # The agent calls save_narrative tool directly during its run
            # (no interrupt_on in batch mode), so no manual save needed.
            # Just verify it was called by checking for a tool message.
            saved = any(
                getattr(msg, "name", None) == "save_narrative"
                for msg in result["messages"]
                if msg.type == "tool"
            )
            if not saved:
                logger.warning(
                    f"Agent did not call save_narrative for {country_a}-{country_b}, skipping")
                continue

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
agent = build_agent(streaming=False)
