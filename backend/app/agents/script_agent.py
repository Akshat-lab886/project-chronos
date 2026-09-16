"""Project Chronos — Script & Storyboard Agent.

Uses LangGraph-style state management to decompose any broad topic into
5 structured acts (HOOK, CONTEXT, CONFLICT, CLIMAX, OUTRO) with scene
durations calibrated to an average speaking rate of 145 words/minute.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from app.agents.research_agent import ResearchAgent, ResearchState
from app.core.config import get_settings
from app.core.schemas import (
    ActType,
    AudioTrackSpec,
    AudioTrackType,
    MotionPreset,
    OverlaySpec,
    OverlayType,
    ProjectChronosManifest,
    ProjectMetadata,
    SceneSpec,
    SfxTrigger,
    VisualAssetSpec,
    VisualSourceType,
    VoiceoverSpec,
)

logger = logging.getLogger("chronos.script")

WORDS_PER_MINUTE = 145.0
FPS = 60
MIN_SCENE_FRAMES = 180
MAX_SCENE_FRAMES = 2700


class SceneTemplate(BaseModel):
    """A template for generating a scene within an act."""
    act_type: ActType
    title_template: str
    narrative_template: str
    visual_tag_template: list[str]
    search_query_template: list[str]
    fallback_prompt_template: str
    overlay_type: OverlayType
    min_words: int
    max_words: int
    min_scenes: int = 1
    max_scenes: int = 3


ACT_SCENE_TEMPLATES: dict[ActType, list[SceneTemplate]] = {
    ActType.HOOK: [
        SceneTemplate(
            act_type=ActType.HOOK,
            title_template="Cold Open: Uncovering the Truth Behind \"{topic}\"",
            narrative_template=(
                "What if we told you that {hook_statement}? "
                "This is the story that history books barely mention — a tale of "
                "{topic_domain} so classified, so deeply buried, that even today "
                "most experts are only aware fragments of what happened. "
                "Going back to {earliest_year}, a secret operation was underway that would "
                "reshape the global balance of power. Hidden from public view, "
                "scientists and operatives worked in complete secrecy beneath the surface, "
                "their work carrying implications far beyond what any single nation could grasp. "
                "In this documentary, we uncover the untold truth behind one of the "
                "most closely guarded secrets in modern {topic_domain}."
            ),
            visual_tag_template=["dramatic", "mysterious", "historical", "declassified"],
            search_query_template=["declassified historical footage", "dramatic reveal"],
            fallback_prompt_template=(
                "Cinematic dramatic documentary shot, declassified documents, "
                "dramatic lighting, 35mm film grain, desaturated colors"
            ),
            overlay_type=OverlayType.NONE,
            min_words=80, max_words=120,
        ),
        SceneTemplate(
            act_type=ActType.HOOK,
            title_template="The Paradox: Why This Was Buried",
            narrative_template=(
                "Why would an entire nation spend billions in secret, only to bury "
                "the evidence of what they achieved? The answer lies deep in the "
                "records that were classified for decades. "
                "What started as a scientific curiosity became a matter of national "
                "security when the implications became clear. "
                "The decision was made to seal the files, remove the names, "
                "and pretend it never happened. "
                "But fragments remain - scattered across different archives, "
                "hidden in plain sight in technical reports, "
                "and whispered about in corridors of power. "
                "This is the untold story of what really happened."
            ),
            visual_tag_template=["mystery", "secrets", "classified", "documents"],
            search_query_template=["mysterious classified documents", "secret file room"],
            fallback_prompt_template=(
                "Mysterious classified documents, redacted files, "
                "dark office with filing cabinets, dramatic lighting"
            ),
            overlay_type=OverlayType.NONE,
            min_words=100, max_words=130,
        ),
    ],
    ActType.CONTEXT: [
        SceneTemplate(
            act_type=ActType.CONTEXT,
            title_template="Setting the Stage: Origins & Background",
            narrative_template=(
                "To understand {topic}, we must go back to {earliest_year}. "
                "The foundations were laid when {foundation_event}. "
                "Key figures like {key_person} shaped the early direction of this operation, "
                "operating from the shadows with unprecedented access to resources and intelligence. "
                "This was a time when the world was divided, tensions were high, "
                "and every major power was racing to develop new strategic capabilities. "
                "Behind closed doors in secure facilities, decisions were made that would have "
                "far-reaching consequences for decades to come. "
                "Through declassified documents, insider testimonies, and historical records, "
                "we trace the origins of this remarkable story — a tale of {topic_domain} "
                "that reads like a thriller but shaped the real world."
            ),
            visual_tag_template=["historical map", "archive footage", "timeline"],
            search_query_template=["historical map animation", "archive footage"],
            fallback_prompt_template=(
                "Historical map animation, vintage parchment texture, "
                "old world maps, sepia tone, cinematic style"
            ),
            overlay_type=OverlayType.MAP,
            min_words=120, max_words=200,
        ),
        SceneTemplate(
            act_type=ActType.CONTEXT,
            title_template="The Players: Key Figures & Organizations",
            narrative_template=(
                "The people behind {topic} operated in shadows. "
                "{person_description}. "
                "Their motivations were complex and often contradictory. "
                "Some were driven by ideology, others by ambition. "
                "These individuals moved through the corridors of power, "
                "influencing decisions from behind the scenes. "
                "They had access to resources beyond what most people could "
                "imagine. Every player had their own agenda, and the "
                "intersections of their interests created a web of alliances."
            ),
            visual_tag_template=["portrait", "mugshot", "personnel file"],
            search_query_template=["historical portraits", "personnel files"],
            fallback_prompt_template=(
                "Vintage portrait photography, historical headshot, "
                "black and white documentary style, film grain"
            ),
            overlay_type=OverlayType.NEWSPAPER,
            min_words=100, max_words=180,
        ),
    ],
    ActType.CONFLICT: [
        SceneTemplate(
            act_type=ActType.CONFLICT,
            title_template="The Rising Tension: Escalating Challenges",
            narrative_template=(
                "As {topic} progressed, tensions mounted in ways that few anticipated. "
                "The situation became increasingly precarious when {conflict_event}. "
                "This marked a critical turning point where internal and external "
                "pressures began to collide. What had started as a carefully "
                "orchestrated operation began to show cracks in its foundation. "
                "Communication intercepts raised alarms, security protocols were "
                "being questioned, and doubts crept in. There were whispers of "
                "betrayal, concerns about compromised assets, and growing fears "
                "that the entire operation might be exposed. {stakes_description} "
                "Yet the project pressed on, driven by unwavering determination "
                "and the weight of sunk costs. The margin for error had shrunk to zero."
            ),
            visual_tag_template=["tension", "conflict", "war room"],
            search_query_template=["war room maps", "tense meetings"],
            fallback_prompt_template=(
                "War room planning, maps with red strings, intense discussions, "
                "dramatic lighting, tension atmosphere"
            ),
            overlay_type=OverlayType.STAT_COUNTER,
            min_words=110, max_words=200,
        ),
        SceneTemplate(
            act_type=ActType.CONFLICT,
            title_template="Stakes & Consequences",
            narrative_template=(
                "The stakes were higher than anyone realized. {stakes_description}. "
                "Every decision had cascading effects. The window was closing fast. "
                "The implications extended far beyond "
                "the immediate circle of operatives. "
                "If the operation were exposed, the fallout would be "
                "devastating - diplomatic crises, economic collapse. "
                "External observers were beginning to notice unusual activity. "
                "Alarms were being raised, investigations launched. "
                "Time was running out, and the margin for error had "
                "effectively shrunk to zero. Every second counted."
            ),
            visual_tag_template=["close up", "urgent", "clock"],
            search_query_template=["ticking clock", "urgent documents"],
            fallback_prompt_template=(
                "Close-up of ticking clock, urgent documents, "
                "tension-filled shots, dramatic lighting"
            ),
            overlay_type=OverlayType.STAT_COUNTER,
            min_words=100, max_words=180,
        ),
    ],
    ActType.CLIMAX: [
        SceneTemplate(
            act_type=ActType.CLIMAX,
            title_template="The Climax: Critical Revelations",
            narrative_template=(
                "This is where everything changed. Everything led to this moment — "
                "{climax_event}. The outcome reshaped not just {topic_domain}, "
                "but geopolitics itself. What had been building for months all came to a head "
                "in a single, defining moment that would echo through decades. "
                "The consequences rippled outward, affecting not just the immediate "
                "participants but entire populations and nations. "
                "Secrets were finally revealed, alliances were forged and broken, "
                "and the geopolitical landscape shifted irrevocably. "
                "In the aftermath, those involved would have to live with the "
                "weight of what they had done. "
                "The world would never look at {topic_domain} the same way again."
            ),
            visual_tag_template=["explosion", "revelation", "climax"],
            search_query_template=["explosion footage", "dramatic reveal"],
            fallback_prompt_template=(
                "Dramatic historical explosion, revelation moment, "
                "cinematic lighting, high contrast, film grain"
            ),
            overlay_type=OverlayType.NEWSPAPER,
            min_words=120, max_words=150,
        ),
        SceneTemplate(
            act_type=ActType.CLIMAX,
            title_template="The Aftermath: Consequences Unfold",
            narrative_template=(
                "The dust had barely settled when the full extent of what had "
                "transpired began to sink in. International observers were scrambling "
                "to understand the implications of this singular event. "
                "Diplomatic channels were abuzz with urgent communications, "
                "and emergency sessions were convened at the highest levels. "
                "The political ramifications were immediate and far-reaching. "
                "Allied nations were caught off guard, adversaries saw opportunity, "
                "and neutral parties found themselves forced to take sides. "
                "In the months that followed, the landscape of international "
                "relations would be permanently altered. "
                "This was not just an event - it was a turning point that "
                "would define the next decade of global politics."
            ),
            visual_tag_template=["aftermath", "consequences", "diplomatic", "crisis"],
            search_query_template=["diplomatic crisis meeting", "emergency session"],
            fallback_prompt_template=(
                "Diplomatic crisis meeting, emergency sessions, "
                "politicians in discussion, serious atmosphere"
            ),
            overlay_type=OverlayType.NEWSPAPER,
            min_words=110, max_words=170,
        ),
    ],
    ActType.OUTRO: [
        SceneTemplate(
            act_type=ActType.OUTRO,
            title_template="Legacy & Takeaways: What It All Means",
            narrative_template=(
                "Today, the echoes of {topic} still resonate. {legacy_description} "
                "The lessons learned shape how we think about {topic_domain}. "
                "The events that unfolded were not just a story from the past - "
                "they are a blueprint for understanding the present. "
                "The decisions made in those critical moments continue to "
                "influence policy and shape international relations. "
                "We can see the fingerprints of this operation today. "
                "History remembers, but the full story remains untold. "
                "The legacy lives on."
            ),
            visual_tag_template=["modern day", "memorial", "reflection"],
            search_query_template=["modern memorial", "contemporary reflection"],
            fallback_prompt_template=(
                "Modern memorial site, contemporary reflection, "
                "people contemplating, soft natural lighting"
            ),
            overlay_type=OverlayType.MAP,
            min_words=100, max_words=180,
        ),
        SceneTemplate(
            act_type=ActType.OUTRO,
            title_template="What We Learned",
            narrative_template=(
                "So what can we take away from {topic}? Three key lessons emerge. "
                "Understanding these events helps us navigate the present and future. "
                "First, {lesson_one}. "
                "Second, {lesson_two}. "
                "And third, {lesson_three}. "
                "As we look to the future, these lessons remain as relevant as ever. "
                "The story of {topic} in {topic_domain} is ultimately a story "
                "about human nature — ambition, fear, courage, and the weight of choices. "
                "It reminds us that {topic} was not just an isolated event, "
                "but a turning point whose echoes continue to shape {topic_domain} today. "
                "The truth has a way of emerging, even from the deepest shadows."
            ),
            visual_tag_template=["summary", "infographic", "takeaway"],
            search_query_template=["documentary infographic", "takeaway analysis"],
            fallback_prompt_template=(
                "Documentary infographic, summary graphics, clean typography, "
                "dark cinematic background, professional style"
            ),
            overlay_type=OverlayType.STAT_COUNTER,
            min_words=90, max_words=160,
        ),
    ],
}


@dataclass
class ScriptState:
    """State object for the script agent."""
    topic: str
    project_id: str
    width: int
    height: int
    fps: int
    research: ResearchState
    scenes: list[SceneSpec] = field(default_factory=list)
    current_start_frame: int = 0
    errors: list[str] = field(default_factory=list)


class ScriptAgent:
    """Generates the narrative and storyboard from research findings."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.research_agent = ResearchAgent()

    async def generate_manifest(
        self,
        topic: str,
        project_id: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
        max_scenes: int = 15,
        style: str = "gaurav-thakur-documentary",
    ) -> ProjectChronosManifest:
        """Generate a complete project manifest from a topic."""
        logger.info(f"[ScriptAgent] Generating manifest for: {topic}")
        research = await self.research_agent.research(topic)

        state = ScriptState(
            topic=topic, project_id=project_id, width=width,
            height=height, fps=fps, research=research,
        )
        self._generate_scenes(state, max_scenes)

        # Phase 3: Voiceover specs
        for scene in state.scenes:
            narrative_words = len(scene.narrative.split())
            estimated_duration = (narrative_words / WORDS_PER_MINUTE) * 60
            scene.voiceover = VoiceoverSpec(
                audio_path=f"/workspace/assets/audio/{scene.scene_id}_voiceover.wav",
                duration_seconds=round(estimated_duration, 3),
                word_count=narrative_words,
                speaker_wpm=WORDS_PER_MINUTE,
            )

        self._repair_scene_continuity(state)

        total_duration = sum(s.duration_seconds for s in state.scenes)
        total_frames = (
            state.scenes[-1].start_frame + state.scenes[-1].duration_frames
            if state.scenes else 0
        )

        manifest = ProjectChronosManifest(
            project_id=project_id,
            title=f"Documentary: {topic}",
            metadata=ProjectMetadata(
                title=f"Documentary: {topic}", topic=topic,
                width=width, height=height, fps=fps,
                total_duration_seconds=max(480.0, total_duration),
                total_frames=total_frames,
            ),
            scenes=state.scenes,
            audio_tracks=self._generate_audio_tracks(state),
            sfx_triggers=self._generate_sfx_triggers(state),
            version="1.0.0",
        )
        logger.info(
            f"[ScriptAgent] Manifest complete: {len(manifest.scenes)} scenes, "
            f"{total_frames} frames, {total_duration:.1f}s"
        )
        return manifest

    def _generate_scenes(self, state: ScriptState, max_scenes: int) -> None:
        """Generate scenes for each act using templates.

        Distributes the scene budget across all 5 acts proportionally.
        When a single act has more budget than available templates,
        templates are reused with variation to reach the target scene count.
        Each scene is clamped to MAX_SCENE_FRAMES (45s @ 60fps).
        """
        scenes: list[SceneSpec] = []
        act_order = [ActType.HOOK, ActType.CONTEXT, ActType.CONFLICT, ActType.CLIMAX, ActType.OUTRO]
        total_acts = len(act_order)

        for act_idx, act_type in enumerate(act_order):
            templates = ACT_SCENE_TEMPLATES.get(act_type, [])
            if not templates:
                continue

            scenes_already = len(scenes)
            scenes_remaining = max_scenes - scenes_already
            acts_remaining = total_acts - act_idx
            budget = max(1, scenes_remaining // max(1, acts_remaining))
            # Use full budget — cycle through templates if budget > template count
            scenes_for_act = budget

            template_index = 0
            for _ in range(scenes_for_act):
                template = templates[template_index % len(templates)]
                scene = self._generate_scene(template, state, scenes)
                if scene:
                    scenes.append(scene)
                template_index += 1

        state.scenes = scenes

    def _generate_scene(
        self,
        template: SceneTemplate,
        state: ScriptState,
        existing_scenes: list[SceneSpec],
    ) -> Optional[SceneSpec]:
        """Generate a single scene from a template."""
        fps = state.fps
        research = state.research
        narrative = self._fill_narrative_template(template, state, research)
        word_count = len(narrative.split())
        estimated_duration = (word_count / WORDS_PER_MINUTE) * 60
        duration_frames = max(MIN_SCENE_FRAMES, min(MAX_SCENE_FRAMES, int(estimated_duration * fps)))
        overlay_spec = self._build_overlay_spec(template, research)
        motion_preset = (
            MotionPreset.PARALLAX_DRIFT
            if template.overlay_type != OverlayType.NONE
            else MotionPreset.KEN_BURNS_ZOOM_IN
        )

        visual_asset = VisualAssetSpec(
            source_type=VisualSourceType.STOCK_VIDEO,
            asset_uri="",
            fallback_prompt=template.fallback_prompt_template,
            motion_preset=motion_preset,
            width=state.width,
            height=state.height,
            duration_frames=duration_frames,
            overlay_spec=overlay_spec,
        )

        scene_id = f"scene_{len(existing_scenes):02d}_{template.act_type.value.lower()}"

        scene = SceneSpec(
            scene_id=scene_id,
            act_type=template.act_type,
            start_frame=state.current_start_frame,
            duration_frames=duration_frames,
            title=template.title_template.format(
                topic=state.topic,
                topic_question=self._extract_topic_question(state.topic),
                topic_summary=self._extract_topic_summary(state.topic, research),
                topic_domain=self._extract_topic_domain(state.topic),
                **self._extract_timeline_context(research),
            ),
            narrative=narrative,
            visual_tags=template.visual_tag_template,
            search_queries=template.search_query_template,
            visual_asset=visual_asset,
            voiceover=VoiceoverSpec(
                audio_path=f"/workspace/assets/audio/{scene_id}_voiceover.wav",
                duration_seconds=round(duration_frames / fps, 3),
                word_count=word_count,
                speaker_wpm=WORDS_PER_MINUTE,
            ),
        )
        state.current_start_frame += duration_frames
        return scene

    def _fill_narrative_template(
        self,
        template: SceneTemplate,
        state: ScriptState,
        research: ResearchState,
    ) -> str:
        """Fill in a narrative template with dynamic variables from research.

        Uses actual research findings (timeline markers, statistics, findings)
        to produce topic-specific, data-driven narratives. Falls back to
        generic substitutions only when research data is unavailable.
        """
        topic = state.topic
        vk = research.visual_keywords or ["secret"]

        # Extract timeline years as integers for proper comparison
        timeline_years = [
            int(str(m.get("year", "0")))
            for m in research.timeline_markers
            if str(m.get("year", "")).isdigit()
        ]
        earliest_year = str(timeline_years[0]) if timeline_years else "the 1970s"
        # Climax year is the primary year extracted from the topic (e.g., 1974)
        # rather than the last timeline marker (which may be an aftermath event)
        topic_years = re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", topic)
        climax_year = topic_years[0] if topic_years else (str(timeline_years[-1]) if timeline_years else "1974")

        # Extract finding content strings for keyword matching
        finding_contents = [f.content for f in research.findings]
        first_finding = finding_contents[0] if finding_contents else ""
        # Truncate at word boundary for clean hook statement
        if first_finding and len(first_finding) > 100:
            first_finding_short = first_finding[:100].rsplit(' ', 1)[0] + "..."
        else:
            first_finding_short = first_finding

        # Build topic-specific narrative values from real research data
        # These transform research findings into narrative prose
        hook_statement = (
            first_finding_short if first_finding_short
            else f"the {vk[0]} truth behind {topic}"
        )

        foundation_event = (
            first_finding[:140] if first_finding
            else f"the emergence of {topic}"
        )

        # Extract key persons from findings — only match findings where 'person'
        # or a specific title noun (general, minister, director, scientist, officer)
        # appears NOT as part of "global leaders" type phrase
        person_findings = []
        strong_person_kw = ["scientist", "general", "minister", "director", "officer", "commander", "physicist", "engineer"]
        for fc in finding_contents:
            fl = fc.lower()
            # Must contain a strong person keyword AND not just "global leaders"
            if any(kw in fl for kw in strong_person_kw) and "global leaders" not in fl:
                person_findings.append(fc[:80])
        if not person_findings:
            person_findings = ["the key architects who operated in complete secrecy"]
        key_person = person_findings[0] if len(person_findings) == 1 else f"multiple key figures"

        person_description = (
            "These individuals operated with extraordinary secrecy, making decisions "
            "that would change the course of history."
        )

        # Find conflict-related finding
        conflict_kw = ["tension", "threat", "crisis", "attack", "clash",
                       "pressure", "problem", "confront", "escalat", "compromise", "betrayal"]
        conflict_findings = [fc for fc in finding_contents if any(kw in fc.lower() for kw in conflict_kw)]
        if conflict_findings:
            conflict_event = conflict_findings[-1][:120]  # Prefer most recent timeline context
        else:
            conflict_event = "escalating tensions threatened to unravel everything"

        # Build stakes description from statistics
        stakes_description = "The future of entire nations hung in the balance"
        if research.statistics:
            stat = research.statistics[0]
            stat_desc = stat.get("description", "")
            stat_val = stat.get("value", "")
            if stat_desc and stat_val:
                stakes_description = (
                    f"The numbers reveal the magnitude: {stat_desc} — {stat_val}. "
                    + stakes_description
                )

        # Find climax event from findings — prefer findings with most keyword matches
        climax_kw = ["test", "launch", "executed", "activated", "detonated",
                     "revealed", "operation", "mission", "final", "decisive", "conducted"]
        climax_findings = [fc for fc in finding_contents if any(kw in fc.lower() for kw in climax_kw)]
        if climax_findings:
            # Sort by number of keyword matches (more specific = better)
            climax_event = max(climax_findings, key=lambda fc: sum(1 for kw in climax_kw if kw in fc.lower()))[:120]
        else:
            climax_event = f"the decisive operation on {climax_year} was executed"
        climax_date = climax_year
        topic_domain = self._extract_topic_domain(topic)

        # Build legacy description from timeline + topic
        legacy_description = (
            f"The impact of these events continues years later. "
            f"Even today, {topic} is studied for its lessons in {topic_domain}."
        )

        substitutions: dict[str, str] = {
            "topic": topic,
            "earliest_year": earliest_year,
            "topic_question": self._extract_topic_question(topic),
            "topic_summary": self._extract_topic_summary(topic, research),
            "topic_domain": self._extract_topic_domain(topic),
            "hook_statement": hook_statement,
            "foundation_event": foundation_event,
            "key_person": key_person,
            "person_description": person_description,
            "conflict_event": conflict_event,
            "stakes_description": stakes_description,
            "climax_date": climax_date,
            "climax_event": climax_event,
            "legacy_description": legacy_description,
            "lesson_one": "secrecy shapes history in ways we're only beginning to understand",
            "lesson_two": "small actions by a few individuals can change the trajectory of nations",
            "lesson_three": "the truth, once revealed, cannot be buried again",
        }
        try:
            return template.narrative_template.format(**substitutions)
        except KeyError as e:
            logger.warning(f"Missing narrative variable {e}, using template as-is")
            safe = {
                k: v for k, v in substitutions.items()
                if k in template.narrative_template
            }
            return template.narrative_template.format(**safe)

    def _extract_topic_question(self, topic: str) -> str:
        """Derive a compelling question from the topic."""
        if "?" in topic:
            return topic.split("?")[0].strip()
        # Extract the core verb/noun to form a question
        words = topic.split()
        if len(words) > 3:
            core = " ".join(words[1:]) if words[0].lower() in ("the", "a", "an") else topic
            return f"What really happened with {core.lower().rstrip('?')}?"
        return f"What happened with {topic}?"

    def _extract_topic_summary(self, topic: str, research: ResearchState) -> str:
        """Extract a short, compelling summary of the topic from research."""
        domain = self._extract_topic_domain(topic)
        if research.visual_keywords:
            primary_kw = research.visual_keywords[0]
            secondary_kw = research.visual_keywords[1] if len(research.visual_keywords) > 1 else "secrecy"
            return f"a {domain} saga of {primary_kw} and {secondary_kw}"
        return f"a {domain} story"

    def _extract_topic_domain(self, topic: str) -> str:
        """Extract the broader domain of the topic."""
        topic_lower = topic.lower()
        if "nuclear" in topic_lower or "atomic" in topic_lower:
            return "nuclear history"
        if "war" in topic_lower or "battle" in topic_lower:
            return "military history"
        if "politic" in topic_lower:
            return "international politics"
        return "history"

    def _extract_timeline_context(self, research: ResearchState) -> dict[str, str]:
        """Extract timeline context variables for template substitution."""
        timeline_years = [str(m.get("year", "")) for m in research.timeline_markers]
        earliest = timeline_years[0] if timeline_years else "1974"
        latest = timeline_years[-1] if timeline_years else "2024"
        return {"earliest_year": earliest, "climax_date": latest}

    def _build_overlay_spec(
        self,
        template: SceneTemplate,
        research: ResearchState,
    ) -> OverlaySpec:
        """Build an overlay spec based on the template's overlay type and research."""
        if template.overlay_type == OverlayType.MAP and research.coordinates:
            return OverlaySpec(
                type=OverlayType.MAP,
                data={"coordinates": research.coordinates, "zoom_level": 6},
            )
        elif template.overlay_type == OverlayType.MAP:
            return OverlaySpec(
                type=OverlayType.MAP,
                data={"coordinates": [{"lat": 0, "lng": 0}], "zoom_level": 2},
            )
        elif template.overlay_type == OverlayType.NEWSPAPER:
            return OverlaySpec(
                type=OverlayType.NEWSPAPER,
                data={
                    "headline": f"Historical Archive: {template.title_template[:50]}...",
                    "source": "Project Chronos Archives",
                },
            )
        elif template.overlay_type == OverlayType.STAT_COUNTER:
            stats = research.statistics[:1] if research.statistics else []
            stat = stats[0] if stats else {"description": "Key Metric", "value": 0, "unit": ""}
            try:
                end_val = int(stat.get("value", "0"))
            except (ValueError, TypeError):
                end_val = 0
            return OverlaySpec(
                type=OverlayType.STAT_COUNTER,
                data={
                    "label": stat.get("description", "Key Metric"),
                    "start_value": 0,
                    "end_value": end_val,
                    "unit": stat.get("unit", ""),
                },
            )
        return OverlaySpec(type=OverlayType.NONE, data={})

    def _repair_scene_continuity(self, state: ScriptState) -> None:
        """Ensure scenes are contiguous — fix any start_frame gaps."""
        current = 0
        for scene in state.scenes:
            scene.start_frame = current
            current += scene.duration_frames
        state.current_start_frame = current

    def _generate_audio_tracks(self, state: ScriptState) -> list[AudioTrackSpec]:
        """Generate audio track specs for all voiceover tracks."""
        tracks: list[AudioTrackSpec] = []
        for scene in state.scenes:
            tracks.append(AudioTrackSpec(
                track_id=f"vo_{scene.scene_id}",
                type=AudioTrackType.VOICEOVER,
                file_path=scene.voiceover.audio_path,
                start_frame=scene.start_frame,
                duration_frames=scene.duration_frames,
                volume=1.0,
                pan="mono",
                effects=[],
            ))
        return tracks

    def _generate_sfx_triggers(self, state: ScriptState) -> list[SfxTrigger]:
        """Generate SFX trigger specs at scene boundaries."""
        triggers: list[SfxTrigger] = []
        sfx_types = ["whoosh", "hit", "vinyl_crackle", "paper_slide"]
        for scene in state.scenes:
            idx = len(triggers) % len(sfx_types)
            triggers.append(SfxTrigger(
                sfx_id=f"sfx_{sfx_types[idx]}_{scene.scene_id}",
                frame=scene.start_frame,
                duration_frames=90,
                volume=0.7,
                asset_uri=f"/workspace/assets/sfx/{sfx_types[idx]}.wav",
            ))
        return triggers
