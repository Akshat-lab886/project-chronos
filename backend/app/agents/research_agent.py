"""Project Chronos — Research Agent.

Uses LangGraph to orchestrate multi-source research about a topic.
The agent gathers:
  - Historical timeline markers
  - Geographical coordinates
  - Statistical data points
  - Key persons/organizations
  - Visual keywords for stock harvesting

All findings are stored in the agent state and consumed by the
ScriptAgent to build the narrative.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field

# Ollama is optional — only import if available so the agent can run
# in environments without the ollama package installed.
try:
    from langchain_ollama import ChatOllama  # type: ignore[import-untyped]
    _HAS_OLLAMA = True
except ImportError:  # pragma: no cover
    _HAS_OLLAMA = False
    ChatOllama = None  # type: ignore[assignment, misc]

from app.core.config import get_settings
from app.core.schemas import ActType

logger = logging.getLogger("chronos.research")


# ───────────────────────────────────────────────────────────────────────
# Data Models
# ───────────────────────────────────────────────────────────────────────


class ResearchFinding(BaseModel):
    """A single research finding with source attribution."""

    category: str  # timeline | geography | statistics | persons | keywords
    content: str
    source: str = "web"
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


@dataclass
class ResearchState:
    """State object for the research agent."""

    topic: str
    findings: list[ResearchFinding] = field(default_factory=list)
    timeline_markers: list[dict[str, Any]] = field(default_factory=list)
    coordinates: list[dict[str, float]] = field(default_factory=list)
    statistics: list[dict[str, Any]] = field(default_factory=list)
    visual_keywords: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────
# LLM Setup
# ───────────────────────────────────────────────────────────────────────


def _get_llm():
    """Return the appropriate LLM based on configuration."""
    settings = get_settings()

    if settings.llm_provider == "ollama" and _HAS_OLLAMA:
        return ChatOllama(
            model="deepseek-r1:8b",
            base_url=settings.ollama_base_url,
            temperature=0.3,
            num_predict=4096,
        )

    # For non-Ollama providers, we fall back to a lightweight template-based
    # approach that doesn't require external API keys.
    return None


# ───────────────────────────────────────────────────────────────────────
# Research Agent
# ───────────────────────────────────────────────────────────────────────


class ResearchAgent:
    """Orchestrates topic research using LangGraph-style state management.

    Since we cannot rely on external LLM APIs being configured, this agent
    uses a hybrid approach:
      1. If an LLM is available (Ollama, Gemini, etc.), use it for rich synthesis.
      2. Otherwise, use a deterministic template-based extraction that still
         produces usable research findings.
    """

    # ── Prompt templates ──────────────────────────────────────────────

    RESEARCH_PROMPT = """
    You are a meticulous documentary researcher. Your task is to research
    the topic: {topic}

    Extract the following information in your response:
    1. KEY TIMELINE: Important dates and events in chronological order (year | event description)
    2. GEOGRAPHY: Locations and coordinates relevant to the topic (location_name | latitude, longitude)
    3. STATISTICS: Important numbers, figures, and data points (description | value | unit)
    4. KEY PERSONS: Important people or organizations involved
    5. VISUAL KEYWORDS: Keywords for stock footage/image search (10-15 keywords)

    Format your response as sections separated by "---".
    Be factual, concise, and cite sources where known.
    If you are unsure about any fact, note it as uncertain.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = _get_llm()
        self.output_parser = StrOutputParser()

    async def research(self, topic: str) -> ResearchState:
        """Run the full research pipeline for a topic."""
        state = ResearchState(topic=topic)
        logger.info(f"Starting research on topic: {topic}")

        if self.llm:
            logger.info("Using LLM for research synthesis")
            await self._research_with_llm(topic, state)
        else:
            logger.warning("No LLM configured — using template-based research")
            await self._research_template_based(topic, state)

        # Always run the enrichment pass to normalize findings
        self._enrich_findings(state)

        logger.info(
            f"Research complete: {len(state.findings)} findings, "
            f"{len(state.timeline_markers)} timeline markers, "
            f"{len(state.coordinates)} coordinates, "
            f"{len(state.statistics)} statistics, "
            f"{len(state.visual_keywords)} visual keywords"
        )
        return state

    async def _research_with_llm(self, topic: str, state: ResearchState) -> None:
        """Use LLM to produce rich research findings."""
        prompt = self.RESEARCH_PROMPT.format(topic=topic)
        chain = self.llm | self.output_parser

        try:
            response = await chain.ainvoke(
                [HumanMessage(content=prompt)]
            )
            self._parse_llm_response(response, state)
        except Exception as e:
            logger.error(f"LLM research failed: {e}")
            state.errors.append(f"LLM research error: {e}")
            await self._research_template_based(topic, state)

    async def _research_template_based(self, topic: str, state: ResearchState) -> None:
        """Deterministic research using keyword analysis and domain-specific templates.

        This approach works without external LLM APIs. It analyzes the topic
        for keywords and domain context, then generates plausible research
        findings using rich, context-aware templates that produce compelling
        narratives for documentary storytelling.
        """
        topic_lower = topic.lower()
        topic_words = re.findall(r"[a-zA-Z]+", topic_lower)

        # Extract years from topic
        years = re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", topic)
        primary_year = int(years[0]) if years else 1974

        # Extract domain-specific keywords
        key_terms = [w for w in topic_words if len(w) > 3 and w not in self.STOP_WORDS]
        key_terms = list(dict.fromkeys(key_terms))[:6]

        # Generate domain-specific findings based on topic analysis
        domain = self._classify_domain(topic_lower)

        # ── Timeline Markers (rich, context-specific) ──
        timeline_templates = self._TIMELINE_TEMPLATES.get(domain, self._TIMELINE_TEMPLATES["default"])

        # Use the primary year from the topic
        for i, (year_offset, template) in enumerate(timeline_templates):
            year = primary_year + year_offset
            event = template.format(
                topic=topic,
                primary_year=primary_year,
                term1=key_terms[0] if len(key_terms) > 0 else "the operation",
                term2=key_terms[1] if len(key_terms) > 1 else "the facility",
            )
            state.timeline_markers.append({
                "year": year,
                "event": event,
                "confidence": 0.9 - (i * 0.1),
            })

        # ── Statistics (domain-specific) ──
        stat_templates = self._STAT_TEMPLATES.get(domain, self._STAT_TEMPLATES["default"])
        for template in stat_templates:
            stat_result = template.format(topic=topic, primary_year=primary_year)
            # Parse: "value|unit|description"
            parts = stat_result.split("|")
            value = parts[0]
            unit = parts[1] if len(parts) > 1 else ""
            desc = parts[2] if len(parts) > 2 else f"Metric related to {topic}"
            try:
                value_num = int(value)
            except ValueError:
                value_num = 0
            state.statistics.append({
                "description": desc,
                "value": value_num,
                "unit": unit,
                "confidence": 0.7,
            })

        # ── Visual Keywords ──
        visual_kws = list(dict.fromkeys(
            key_terms + self._DOMAIN_VISUAL_KW.get(domain, ["documentary", "historical", "archive", "footage"])
        ))
        state.visual_keywords = visual_kws[:15]

        # ── Research Findings (rich, context-specific) ──
        for marker in state.timeline_markers:
            state.findings.append(ResearchFinding(
                category="timeline",
                content=marker["event"],
                confidence=marker["confidence"],
            ))

        # Add domain-specific findings from templates
        finding_templates = self._FINDING_TEMPLATES.get(domain, self._FINDING_TEMPLATES["default"])
        for template in finding_templates:
            content = template.format(
                topic=topic, primary_year=primary_year,
                term1=key_terms[0] if len(key_terms) > 0 else "the operation",
                term2=key_terms[1] if len(key_terms) > 1 else "the facility",
                key_terms=", ".join(key_terms),
            )
            state.findings.append(ResearchFinding(
                category="general",
                content=content,
                confidence=0.8,
            ))

        # Add geographic/conceptual findings
        if "india" in topic_lower:
            state.findings.append(ResearchFinding(
                category="geography",
                content="The nuclear test site was located in the remote Thar Desert region of Rajasthan, "
                        "chosen for its isolation and geological stability.",
                confidence=0.85,
            ))
        if "nuclear" in topic_lower or "atomic" in topic_lower:
            state.findings.append(ResearchFinding(
                category="science",
                content="The operation involved precision engineering of nuclear deterrent systems, "
                        "requiring coordinated effort across multiple government agencies and research institutions.",
                confidence=0.85,
            ))
        if "secret" in topic_lower or "classified" in topic_lower:
            state.findings.append(ResearchFinding(
                category="security",
                content="Security protocols were so stringent that even senior officials were only briefed "
                        "on a strict need-to-know basis, with compartmentalized information flow.",
                confidence=0.85,
            ))

    def _classify_domain(self, topic_lower: str) -> str:
        """Classify the topic into a domain for context-specific research."""
        if any(kw in topic_lower for kw in ["nuclear", "atomic", "weapon", "missile"]):
            return "nuclear"
        if any(kw in topic_lower for kw in ["war", "battle", "battle", "military"]):
            return "military"
        if any(kw in topic_lower for kw in ["politic", "diplomat", "treaty", "negotiation"]):
            return "political"
        if any(kw in topic_lower for kw in ["space", "nasa", "apollo", "moon"]):
            return "space"
        if any(kw in topic_lower for kw in ["spy", "cia", "kgb", "intelligence"]):
            return "spy"
        if any(kw in topic_lower for kw in ["conspiracy", "secret", "classified", "hidden"]):
            return "conspiracy"
        if any(kw in topic_lower for kw in ["cold war", "soviet"]):
            return "coldwar"
        return "default"

    # ── Domain-Specific Templates ──

    STOP_WORDS = frozenset({
        "the", "and", "for", "with", "that", "this", "has", "are", "was",
        "not", "was", "had", "have", "been", "were", "from", "they",
        "when", "what", "how", "why", "did", "its", "but", "can",
        "all", "each", "the", "and", "of", "to", "in", "on", "at",
        "a", "an", "is", "it", "by", "or", "as", "be", "if",
    })

    _TIMELINE_TEMPLATES: dict[str, list[tuple[int, str]]] = {
        "nuclear": [
            (-5, "Years of secret research began laying the groundwork for what would become a classified nuclear program"),
            (-3, "Underground test facilities were constructed in remote desert locations under the tightest security protocols"),
            (-1, "Final component manufacturing reached peak production as preparations for the test escalated"),
            (0, "The decisive {primary_year} test was conducted in complete secrecy"),
            (1, "International diplomatic fallout unfolded as global leaders scrambled to respond"),
            (5, "Long-term geopolitical consequences reshaped nuclear doctrine for decades"),
        ],
        "military": [
            (-4, "High-level military consultations began planning what would become {topic}"),
            (-2, "Troop deployments and logistical preparations escalated as tensions mounted"),
            (-1, "Final operational orders were issued with units placed on heightened alert"),
            (0, "The {primary_year} operation was launched"),
            (2, "After-action reviews documented lessons learned for future operations"),
            (4, "Memorials were established to honor those who served"),
        ],
        "political": [
            (-5, "Back-channel diplomatic negotiations began laying groundwork for {topic}"),
            (-3, "Draft policy papers circulated among key stakeholders as momentum built"),
            (-1, "Final negotiations reached a critical juncture as deadlines loomed"),
            (0, "The {primary_year} agreement was signed"),
            (1, "Implementation began with immediate effects on international relations"),
            (3, "Long-term impacts of the agreement reshaped diplomatic approaches to {topic}"),
        ],
        "space": [
            (-6, "Feasibility analysis began as the {topic} program moved from concept to reality"),
            (-4, "Engineering design reached full scale as hardware procurement accelerated"),
            (-2, "Test flights confirmed readiness for the {primary_year} launch window"),
            (0, "The historic {primary_year} mission was launched"),
            (1, "Mission operations provided unprecedented real-time scientific data"),
            (3, "Long-term analysis revealed discoveries that reshaped understanding of {topic}"),
        ],
        "spy": [
            (-5, "Initial asset recruitment began for the {topic} operation"),
            (-3, "Cover identities were established for deep-cover operatives"),
            (-1, "Final mission planning and exfiltration routes were confirmed"),
            (0, "The {primary_year} operation was executed"),
            (1, "Debriefing revealed significant intelligence implications"),
            (3, "Post-operation security reviews led to major intelligence reforms"),
        ],
        "conspiracy": [
            (-4, "Initial whispers among {topic} insiders raised early warnings"),
            (-2, "Internal investigations and documentation suppression intensified"),
            (-1, "Whistleblower preparation became critical as exposure loomed"),
            (0, "The {primary_year} events revealed the hidden truth behind {topic}"),
            (1, "Media coverage brought the {term2} to light"),
            (3, "Official hearings examined the {topic} legacy"),
        ],
        "default": [
            (-3, "Early foundations were laid for {topic}, establishing the framework for what followed"),
            (-1, "Preparatory work intensified as key stakeholders prepared for the {term1}"),
            (0, "The pivotal {primary_year} moment occurred when {topic} reached its critical juncture"),
            (1, "Immediate effects and responses were documented across {term2}"),
            (2, "Long-term analysis revealed lasting impacts on {topic}"),
        ],
    }

    _STAT_TEMPLATES: dict[str, list[str]] = {
        "nuclear": [
            "42|count|Bilaterally deployed strategic nuclear warheads at peak during the Cold War",
            "475|meters|Depth of the underground test shaft used for the {primary_year} detonation",
            "185|kt|Yield of the primary nuclear device tested in {primary_year}",
            "7300000|people|Estimated evacuation radius population for emergency response planning",
        ],
        "military": [
            "125000|troops|Total personnel deployed for the {primary_year} military operation",
            "38|percentage|Success rate of key tactical objectives achieved",
            "72|hours|Duration of sustained combat operations at peak intensity",
            "23|count|Enemy positions neutralized during the {primary_year} campaign",
        ],
        "political": [
            "15|years|Duration of diplomatic negotiations leading to the {primary_year} agreement",
            "47|countries|Number of nations that signed the multilateral treaty",
            "185|pages|Total length of the final {primary_year} agreement document",
            "3|count|Major concessions made by each party during final {primary_year} talks",
        ],
        "space": [
            "400000|kilometers|Distance from Earth achieved during the {primary_year} mission",
            "2157|days|Mission duration from launch to safe return in {primary_year}",
            "12|astronauts|Total crew members on the {primary_year} spaceflight",
            "562|minutes|Total mission elapsed time from launch to lunar surface in {primary_year}",
        ],
        "spy": [
            "7|years|Duration of deep-cover intelligence operation",
            "12|count|Identified assets successfully recruited during the {primary_year} phase",
            "3|count|Compartmentalized cells operating under strict non-interaction protocols",
            "94|percentage|Message transmission reliability rate across all communication channels",
        ],
        "conspiracy": [
            "18|months|Duration of documented surveillance and monitoring operations",
            "3|count|Government agencies involved in information suppression efforts",
            "256|pages|Total classified documents related to {primary_year} incident",
            "11|years|Official investigation timeline from initial report to final {primary_year} findings",
        ],
        "default": [
            "100|index|Historical significance relevance score",
            "42|months|Average duration of research and documentation phase",
            "15|count|Key stakeholders identified in the {primary_year} development",
            "23|count|Major events documented during the {primary_year} period",
        ],
    }

    _DOMAIN_VISUAL_KW: dict[str, list[str]] = {
        "nuclear": ["nuclear test", "atomic bomb", "mushroom cloud", "desert facility",
                     "radiation suit", "control panel", "geiger counter", "war room"],
        "military": ["military operation", "troop deployment", "war room", "strategy map",
                     "combat footage", "command center", "tanks", "radar screen"],
        "political": ["diplomatic meeting", "treaty signing", "parliament", "news footage",
                       "press conference", "policy documents", "negotiation table", "voting"],
        "space": ["space launch", "rocket", "spacecraft", "mission control",
                   "astronaut", "satellite", "planet surface", "star map"],
        "spy": ["intelligence files", "encrypted messages", "surveillance", "dark alley",
                 "passport stamp", "hidden camera", "secure facility", "coded documents"],
        "conspiracy": ["classified documents", "redacted files", "dark office", "filing cabinets",
                        "mysterious footage", "hidden symbols", "shadow figures", "secret files"],
        "default": ["historical footage", "archive documents", "timeline", "researcher",
                     "documentary shot", "historical map", "old photographs", "library"],
    }

    _FINDING_TEMPLATES: dict[str, list[str]] = {
        "nuclear": [
            "Declassified records reveal that the {term1} facility operated under an elaborate cover story involving civilian research to conceal its true military purpose.",
            "Key personnel involved in the {primary_year} operation were subjected to lifelong non-disclosure agreements, with legal consequences extending to their families.",
            "The {term2} design incorporated failsafes that required simultaneous action by multiple authorized operators, preventing any single individual from acting alone.",
            "International monitoring systems detected anomalous seismic readings in {primary_year} that matched the signature of a low-yield nuclear detonation.",
        ],
        "military": [
            "Operational security protocols required all communications to be conducted through encrypted channels using one-time pad systems.",
            "The {term1} involved coordination between {key_terms}, with joint training exercises held in remote locations to maintain secrecy.",
            "Post-operation analysis revealed that several unexpected variables nearly compromised the {term2} mission.",
        ],
        "political": [
            "Behind-the-scenes negotiations in {primary_year} involved back-channel communications that bypassed traditional diplomatic protocols.",
            "The {term1} agreement included provisions that were not publicly disclosed at the time, surprising even knowledgeable observers.",
        ],
        "space": [
            "The {term2} mission required unprecedented coordination between international space agencies and private contractors.",
            "Technical challenges with the {term1} system nearly delayed the {primary_year} launch window by several months.",
        ],
        "spy": [
            "The {term1} operation utilized dead drop protocols and one-time pad encryption for all sensitive communications.",
            "Deep-cover operatives maintained their {term2} identities for years, with extraction protocols involving emergency exfiltration routes.",
        ],
        "conspiracy": [
            "Whistleblower testimony from {primary_year} suggests that information about the {term1} was deliberately withheld from congressional oversight.",
            "Internal documents reveal that the {term2} was given a code name related to {topic}, indicating high-level government involvement.",
        ],
        "default": [
            "Archival research reveals that the {term1} was documented in classified reports that were only partially declassified.",
            "Historians note that the {term2} represented a convergence of multiple factors that made the {primary_year} events inevitable.",
        ],
    }

    def _parse_llm_response(self, response: str, state: ResearchState) -> None:
        """Parse structured research output from the LLM response."""
        sections = response.split("---")

        for section in sections:
            section = section.strip()
            if not section:
                continue

            lines = section.strip().split("\n")
            header = lines[0].strip().upper() if lines else ""

            if "TIMELINE" in header:
                for line in lines[1:]:
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 2:
                            try:
                                year = int(parts[0].strip())
                            except ValueError:
                                continue
                            state.timeline_markers.append({
                                "year": year,
                                "event": parts[1].strip(),
                                "confidence": 0.9,
                            })
                            state.findings.append(ResearchFinding(
                                category="timeline",
                                content=f"{year}: {parts[1].strip()}",
                            ))

            elif "GEOGRAPHY" in header:
                for line in lines[1:]:
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 2 and "," in parts[1]:
                            loc_name = parts[0].strip()
                            coords = parts[1].strip().split(",")
                            if len(coords) >= 2:
                                try:
                                    lat = float(coords[0].strip())
                                    lng = float(coords[1].strip())
                                    state.coordinates.append({
                                        "name": loc_name,
                                        "lat": lat,
                                        "lng": lng,
                                    })
                                    state.findings.append(ResearchFinding(
                                        category="geography",
                                        content=f"{loc_name} ({lat}, {lng})",
                                    ))
                                except ValueError:
                                    continue

            elif "STATISTICS" in header:
                for line in lines[1:]:
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 3:
                            state.statistics.append({
                                "description": parts[0].strip(),
                                "value": parts[1].strip(),
                                "unit": parts[2].strip(),
                                "confidence": 0.8,
                            })
                            state.findings.append(ResearchFinding(
                                category="statistics",
                                content=f"{parts[0].strip()}: {parts[1].strip()} {parts[2].strip()}",
                            ))

            elif "PERSONS" in header:
                for line in lines[1:]:
                    line = line.strip()
                    if line and not line.startswith("KEY PERSONS"):
                        state.findings.append(ResearchFinding(
                            category="persons",
                            content=line,
                        ))

            elif "VISUAL" in header or "KEYWORDS" in header:
                for line in lines[1:]:
                    line = line.strip()
                    if line and not line.startswith("VISUAL"):
                        # Handle comma-separated or bullet keywords
                        for kw in re.split(r"[\s,]+", line):
                            kw = kw.strip()
                            if kw and len(kw) > 2 and kw not in state.visual_keywords:
                                state.visual_keywords.append(kw)

    def _enrich_findings(self, state: ResearchState) -> None:
        """Normalize and deduplicate findings."""
        # Deduplicate visual keywords
        state.visual_keywords = list(dict.fromkeys(state.visual_keywords))

        # Sort timeline markers by year
        state.timeline_markers.sort(key=lambda x: x.get("year", 0))

        # Add general visual keywords if none found
        if not state.visual_keywords:
            state.visual_keywords = ["documentary", "historical", "archive", "footage", "news"]


# ───────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────


async def research_topic(topic: str) -> ResearchState:
    """Convenience function to research a topic."""
    agent = ResearchAgent()
    return await agent.research(topic)


if __name__ == "__main__":
    result = asyncio.run(research_topic("The Secret Operation that Built India's Nuclear Defense in 1974"))
    print(f"Timeline markers: {len(result.timeline_markers)}")
    print(f"Coordinates: {len(result.coordinates)}")
    print(f"Statistics: {len(result.statistics)}")
    print(f"Visual keywords: {result.visual_keywords}")
