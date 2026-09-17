"""Project Chronos — Script & Storyboard Agent.

Uses LangGraph-style state management to decompose any broad topic into
5 structured acts (HOOK, CONTEXT, CONFLICT, CLIMAX, OUTRO) with scene
durations calibrated to an average speaking rate of 145 words/minute.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from app.agents.research_agent import ResearchAgent, ResearchState
from app.core.config import get_settings

# Try importing openai for LLM-based generation
try:
    import openai
    _has_openai = True
except ImportError:
    _has_openai = False
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
                "{hook_statement} "
                "This event went largely unreported in {earliest_year}, hidden behind "
                "layers of {topic_domain} classification that most experts are still "
                "unraveling today. The operation involved {key_person}, "
                "covert facility protocols, and decisions made in secure rooms "
                "that would reshape the global balance of power. "
                "Declassified records and insider testimony reveal what really happened."
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
                "Classified documents reveal that critical decisions for {topic} "
                "were made in windowless rooms with soundproof walls. "
                "The records were sealed, names redacted, and files locked away "
                "in secure vaults that required multiple authorization codes. "
                "{person_description} "
                "Yet fragments survived — technical reports, audit trails, "
                "and personnel testimonies stored in different archives. "
                "Each piece tells part of the story that official channels "
                "worked to suppress."
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
                "{foundation_event}. "
                "Personnel files show that {key_person} were directly involved "
                "in early planning sessions held in secure conference rooms. "
                "The global situation at the time was tense — "
                "nations competing for strategic advantage, "
                "intelligence agencies monitoring every move. "
                "Decisions made that year would have consequences "
                "for decades to come. Through declassified documents, "
                "we trace the origins of this {topic_domain} operation "
                "that shaped the modern world."
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
                "Personnel records show that {key_person} "
                "operated with extraordinary secrecy. "
                "{person_description} "
                "Their motivations were complex — national security, "
                "scientific curiosity, and strategic advantage all played a role. "
                "Each operated within a compartmentalized structure "
                "where information flow was strictly controlled. "
                "Communication logs reveal the meticulous planning "
                "that went into every phase of {topic}. "
                "The intersection of their interests created a web of alliances "
                "and rivalries that shaped everything that followed."
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
                "As {topic} progressed, complications emerged. "
                "The situation became precarious when {conflict_event}. "
                "Internal and external pressures began to collide. "
                "What had started as a tightly controlled operation "
                "began to show vulnerabilities. "
                "Communication intercepts raised alarms, "
                "security protocols were questioned, and doubts crept in. "
                "Whispers of betrayal, compromised assets, "
                "and growing fears that exposure was imminent. "
                "{stakes_description}. "
                "Despite mounting pressure, the project pressed on, "
                "driven by sunk costs and strategic necessity. "
                "The margin for error had shrunk to zero."
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
                "The stakes were existential. {stakes_description}. "
                "Every decision carried cascading consequences. "
                "The window for action was closing rapidly. "
                "The implications extended beyond "
                "the immediate operational circle. "
                "If the mission were compromised, "
                "the fallout would trigger diplomatic and economic collapse. "
                "External observers detected unusual activity. "
                "Alarms sounded, investigations launched. "
                "Time was running out, and the margin for error "
                "had effectively shrunk to zero. Every second counted."
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
                "Everything led to this moment. {climax_event}. "
                "The outcome reshaped {topic_domain} and shifted geopolitics. "
                "Months of planning culminated in a single, defining instant "
                "that would echo through decades. "
                "The consequences rippled outward, affecting "
                "populations and nations far beyond the immediate operation. "
                "Intelligence agencies confirmed the results, "
                "diplomatic cables reflected the shock, "
                "and the geopolitical landscape shifted irrevocably. "
                "In the aftermath, those involved faced "
                "the weight of what they had done. "
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
                "In the immediate aftermath, the scope of what transpired "
                "became clear. Intelligence briefings circulated among "
                "international observers, and diplomatic cables reflected "
                "widespread uncertainty. "
                "Emergency sessions were convened at the highest levels. "
                "The geopolitical ramifications were immediate and far-reaching. "
                "Allied nations scrambled to reassess their positions, "
                "adversaries saw strategic opportunities, "
                "and neutral parties found themselves forced to align. "
                "The landscape of international {topic_domain} "
                "was permanently altered. "
                "This was not just a moment — it was a turning point "
                "that would define the next decade of global politics."
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
                "{legacy_description} "
                "These developments continue to shape {topic_domain} policy. "
                "The decisions made in those critical moments "
                "still influence international relations today. "
                "We see the fingerprints of this operation "
                "in current strategic doctrines and treaty frameworks. "
                "While official records provide one account, "
                "classified archives contain a fuller picture "
                "that scholars are only now beginning to piece together. "
                "The legacy persists."
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
                "Three lasting lessons emerge from {topic}. "
                "First, {lesson_one}. "
                "Second, {lesson_two}. "
                "And third, {lesson_three}. "
                "As we look to the future, these lessons remain relevant. "
                "The story of {topic} is ultimately about "
                "ambition, strategic calculation, and the weight of choices. "
                "It was not an isolated event, "
                "but a turning point whose echoes continue to shape {topic_domain} today. "
                "The truth has a way of surfacing."
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


class LlmScriptEngine:
    """LLM-based script generation using OpenAI-compatible APIs.

    Falls back to template-based generation when no LLM is configured.
    Supports OpenAI, DeepSeek, and any OpenAI-compatible endpoint.
    """

    SYSTEM_PROMPT = """You are an elite investigative documentary director in the style of Gaurav Thakur (GetSetFly) and Vox. You write compelling, cinematic narrative scripts that transform historical topics into engaging 5-act documentaries.

CRITICAL NEGATIVE CONSTRAINTS:
1. NEVER repeat the user prompt or video title verbatim.
2. BANNED CLICHES: Do NOT use phrases like "What if we told you", "A tale of...", "Picture this", "Little did they know", "In a world where", "Let's dive in", or "This is the story of".
3. NO empty exposition: Start each scene In Medias Res with concrete sensory details — specific dates, locations, temperatures, sounds, or technical details.
4. Every scene must mention at least one concrete noun: a person's name/title, a specific location (e.g., Pokhran, Thar Desert), a codename, or a specific fact from the research data.
5. Do not use second person ("you") or first person ("I", "we").
6. Write in third person, present tense for narrative sections.

STRUCTURAL REQUIREMENTS:
- 5 acts: HOOK (cold open, immediate tension), CONTEXT (background/setup), CONFLICT (rising tension), CLIMAX (peak moment), OUTRO (legacy/lessons)
- Each scene: 40-120 words
- Total duration: 300-400 seconds for ~8 scenes
- Include a clear narrative arc across acts

Return ONLY valid JSON. No commentary, no markdown.
"""

    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self.model = "gpt-4o-mini"

        if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
            self.client = openai.OpenAI(api_key=self.settings.openai_api_key)
            self.model = "gpt-4o-mini"
        elif self.settings.llm_provider == "deepseek" and self.settings.deepseek_api_key:
            self.client = openai.OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url="https://api.deepseek.com/v1",
            )
            self.model = "deepseek-chat"
        elif self.settings.llm_provider == "ollama" and self.settings.ollama_base_url:
            self.client = openai.OpenAI(
                api_key="ollama",
                base_url=f"{self.settings.ollama_base_url}/v1",
            )
            self.model = "llama3"

    async def generate_scenes(self, topic: str, research: ResearchState, max_scenes: int) -> list[dict]:
        """Generate scenes using LLM. Returns list of scene dicts."""
        if not self.client:
            return []

        # Build research summary string
        research_data = self._summarize_research(research)

        user_prompt = f"""
Topic: {topic}

Research Data (use these facts to ground your narrative):
{research_data}

Generate {max_scenes} scenes as valid JSON array. Each scene object must have:
- "act_type": one of "HOOK", "CONTEXT", "CONFLICT", "CLIMAX", "OUTRO"
- "title": a compelling, specific title (not generic)
- "narrative": 40-120 words of narrative text
- "search_queries": list of 2-3 search terms for finding relevant stock footage
- "ai_fallback_prompt": descriptive prompt for AI image generation if stock fails
- "overlay_type": "NONE", "MAP", "NEWSPAPER", or "STAT_COUNTER"
- "visual_tags": list of 2-4 descriptive tags

Distribute scenes across acts proportionally (e.g., for 8 scenes: 2 HOOK, 2 CONTEXT, 2 CONFLICT, 1 CLIMAX, 1 OUTRO).

Return ONLY the JSON array. No markdown, no commentary.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
                max_tokens=4000,
            )
            result = json.loads(response.choices[0].message.content)
            if isinstance(result, list) and len(result) > 0:
                logger.info(f"[LlmScriptEngine] Generated {len(result)} scenes via {self.model}")
                return result
            elif isinstance(result, dict) and "scenes" in result:
                logger.info(f"[LlmScriptEngine] Generated {len(result['scenes'])} scenes via {self.model}")
                return result["scenes"]
        except Exception as e:
            logger.warning(f"[LlmScriptEngine] LLM generation failed: {e}")

        return []

    def _summarize_research(self, research: ResearchState) -> str:
        """Summarize research findings for LLM context."""
        lines = []
        lines.append(f"Domain: {research.visual_keywords[:5] if research.visual_keywords else 'general'}")
        if research.timeline_markers:
            lines.append("Timeline:")
            for m in research.timeline_markers:
                lines.append(f"  - {m.get('year', '?')}: {m.get('event', '')}")
        if research.findings:
            lines.append("Findings:")
            for f in research.findings[:8]:
                lines.append(f"  - [{f.category}] {f.content}")
        if research.statistics:
            lines.append("Statistics:")
            for s in research.statistics[:4]:
                lines.append(f"  - {s.get('description', '')}: {s.get('value', '')} {s.get('unit', '')}")
        return "\n".join(lines)


class ScriptAgent:
    """Generates the narrative and storyboard from research findings."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.research_agent = ResearchAgent()
        self.llm_engine = LlmScriptEngine()

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

        # Try LLM-based generation first, fall back to templates
        if self.llm_engine.client:
            logger.info(f"[ScriptAgent] Using LLM generation ({self.llm_engine.model})")
            try:
                llm_scenes = await self.llm_engine.generate_scenes(topic, research, max_scenes)
                if llm_scenes:
                    self._generate_scenes_from_llm(state, llm_scenes)
                    logger.info(f"[ScriptAgent] LLM-generated {len(state.scenes)} scenes")
                else:
                    logger.warning("[ScriptAgent] LLM returned no scenes — falling back to templates")
                    self._generate_scenes(state, max_scenes)
            except Exception as e:
                logger.warning(f"[ScriptAgent] LLM generation failed, falling back to templates: {e}")
                self._generate_scenes(state, max_scenes)
        else:
            logger.info("[ScriptAgent] No LLM configured — using template-based generation")
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

    def _generate_scenes_from_llm(self, state: ScriptState, llm_scenes: list[dict]) -> None:
        """Generate scenes from LLM output, merging with research-based fallbacks."""
        scenes: list[SceneSpec] = []

        for i, llm_scene in enumerate(llm_scenes):
            narrative = llm_scene.get("narrative", "")
            word_count = len(narrative.split())
            estimated_duration = (word_count / WORDS_PER_MINUTE) * 60
            duration_frames = max(MIN_SCENE_FRAMES, min(MAX_SCENE_FRAMES, int(estimated_duration * state.fps)))

            # Parse act_type from LLM output
            act_type_str = llm_scene.get("act_type", "CONTEXT")
            try:
                act_type = ActType[act_type_str.upper()]
            except (KeyError, ValueError):
                act_type = ActType.CONTEXT

            # Parse overlay type
            overlay_type_str = llm_scene.get("overlay_type", "NONE")
            try:
                overlay_type = OverlayType[overlay_type_str.upper()]
            except (KeyError, ValueError):
                overlay_type = OverlayType.NONE

            overlay_spec = OverlaySpec(type=overlay_type, data=llm_scene.get("overlay_data", {}))

            visual_asset = VisualAssetSpec(
                source_type=VisualSourceType.STOCK_VIDEO,
                asset_uri="",
                fallback_prompt=llm_scene.get("ai_fallback_prompt", narrative[:120]),
                motion_preset=MotionPreset.KEN_BURNS_ZOOM_IN,
                width=state.width,
                height=state.height,
                duration_frames=duration_frames,
                overlay_spec=overlay_spec,
            )

            scene_id = f"scene_{i:02d}_{act_type.value.lower()}"

            scene = SceneSpec(
                scene_id=scene_id,
                act_type=act_type,
                start_frame=state.current_start_frame,
                duration_frames=duration_frames,
                title=llm_scene.get("title", f"Scene {i}"),
                narrative=narrative,
                visual_tags=llm_scene.get("visual_tags", []),
                search_queries=llm_scene.get("search_queries", []),
                visual_asset=visual_asset,
                voiceover=VoiceoverSpec(
                    audio_path=f"/workspace/assets/audio/{scene_id}_voiceover.wav",
                    duration_seconds=round(duration_frames / state.fps, 3),
                    word_count=word_count,
                    speaker_wpm=WORDS_PER_MINUTE,
                ),
            )
            state.current_start_frame += duration_frames
            scenes.append(scene)

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

        # Truncated to ~50 chars for use in key_person slots
        first_finding_terse = (first_finding[:50].rsplit(' ', 1)[0] + "...") if first_finding and len(first_finding) > 50 else first_finding

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

        # Extract key persons from findings — match findings about specific personnel
        # Use stronger keywords that indicate actual people, not generic "leaders"
        # Exclude findings that are about scientific/engineering descriptions
        person_findings = []
        strong_person_kw = ["scientist", "general", "minister", "director", "officer", "commander", "physicist"]
        for fc in finding_contents:
            fl = fc.lower()
            if any(kw in fl for kw in strong_person_kw) and "global leaders" not in fl:
                # Exclude findings that are really about engineering/science, not people
                if not any(bad in fl for bad in ["engineering", "deterrent", "design", "manufacturing", "component"]):
                    person_findings.append(fc[:80])
        if person_findings:
            key_person = person_findings[0] if len(person_findings) == 1 else f"multiple key figures"
        else:
            # Fall back to a narrative-sounding key person reference with research context
            key_person = "senior officials at the classified facility"

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
            "climax_year": climax_year,
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
