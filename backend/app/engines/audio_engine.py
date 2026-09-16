"""Project Chronos Audio Engine - placeholder part 1."""
from __future__ import annotations
import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Set HF cache to workspace-writable path BEFORE importing ML packages
os.environ.setdefault("HF_HOME", str(Path("workspace/models/hf_cache")))
os.environ.setdefault("TRANSFORMERS_CACHE", str(Path("workspace/models/hf_cache")))
os.makedirs("workspace/models/hf_cache", exist_ok=True)

import numpy as np

logger = logging.getLogger("chronos.audio")

DEFAULT_SAMPLE_RATE = 24000
DEFAULT_FPS = 60
WORDS_PER_MINUTE = 145.0


@dataclass
class SynthesisResult:
    audio_path: str
    duration_seconds: float
    sample_rate: int
    word_count: int
    engine_used: str


@dataclass
class AlignmentResult:
    captions: list
    words: list
    engine_used: str


def _get_wav_duration(path: str) -> float:
    """Get audio duration using FFmpeg (handles WAV, MP3, AAC, etc.)."""
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        # Fallback: try scipy for WAV, estimate for others
        try:
            import scipy.io.wavfile as wav
            sample_rate, data = wav.read(path)
            return len(data) / sample_rate
        except Exception:
            return 0.0


def _is_key_word(word: str) -> bool:
    if not word:
        return False
    stripped = word.strip(".,!?;:\"'()[]{}")
    if len(stripped) > 6:
        return True
    if stripped.isupper():
        return True
    try:
        float(stripped)
        return True
    except ValueError:
        pass
    highlight_keywords = {
        "nuclear", "atomic", "secret", "classified", "operation", "mission",
        "explosion", "weapon", "defense", "attack", "reveal", "critical",
        "climax", "conflict", "tension", "declassified", "conspiracy",
        "government", "military", "intelligence", "covert", "program",
    }
    return stripped.lower() in highlight_keywords


class TTSEngine:
    """Abstract base for TTS engines."""
    def synthesize(self, text, output_path, voice_id="default"):
        raise NotImplementedError


class KokoroTTSEngine(TTSEngine):
    """Kokoro-TTS engine — local, zero-shot neural voice synthesis."""
    def __init__(self, voice_id="default"):
        try:
            import kokoro
            self._kokoro = kokoro
            self._available = True
            logger.info("Kokoro-TTS loaded successfully")
        except ImportError:
            self._available = False
            logger.warning("Kokoro-TTS not available")

    def synthesize(self, text, output_path, voice_id="default"):
        if not self._available:
            raise RuntimeError("Kokoro-TTS is not available")
        import time as _time
        start_time = _time.time()
        from kokoro import KPipeline
        pipeline = KPipeline(voice=voice_id)
        generator = pipeline(text, voice=voice_id)
        segments = []
        for _, _, audio in generator:
            segments.append(audio)
        if not segments:
            raise RuntimeError("Kokoro-TTS produced no audio segments")
        audio_data = np.concatenate(segments, axis=0) if len(segments) > 1 else segments[0]
        import scipy.io.wavfile as wav
        wav.write(output_path, DEFAULT_SAMPLE_RATE, audio_data.astype(np.float32))
        duration = len(audio_data) / DEFAULT_SAMPLE_RATE
        word_count = len(text.split())
        elapsed = _time.time() - start_time
        logger.info(f"Kokoro-TTS: {word_count} words in {duration:.2f}s ({elapsed:.2f}s wall)")
        from app.engines.audio_engine import SynthesisResult
        return SynthesisResult(output_path, duration, DEFAULT_SAMPLE_RATE, word_count, "kokoro")


class EdgeTTSEngine(TTSEngine):
    """Edge-TTS engine — uses Microsoft Edge TTS API (network-based)."""
    def __init__(self):
        try:
            import edge_tts
            self._edge_tts = edge_tts
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("edge-tts not available")

    async def _synthesize_async(self, text, output_path, voice_id="default"):
        voice_map = {
            "default": "en-US-AriaNeural",
            "male": "en-US-GuyNeural",
            "female": "en-US-AriaNeural",
        }
        voice = voice_map.get(voice_id, voice_id)
        communicate = self._edge_tts.Communicate(text, voice=voice)
        # edge_tts saves as MP3 — we need WAV for pipeline consistency
        # Save to temp MP3, then convert to WAV with FFmpeg
        import os, tempfile, subprocess
        mp3_path = output_path.replace(".wav", ".mp3")
        await communicate.save(mp3_path)
        # Convert MP3 to WAV using FFmpeg
        subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path,
            "-acodec", "pcm_s16le", "-ar", str(DEFAULT_SAMPLE_RATE), "-ac", "1",
            output_path,
        ], capture_output=True, timeout=30)
        # Clean up temp MP3
        try:
            os.remove(mp3_path)
        except OSError:
            pass
        duration = _get_wav_duration(output_path)
        word_count = len(text.split())
        logger.info(f"Edge-TTS: {word_count} words in {duration:.2f}s")
        from app.engines.audio_engine import SynthesisResult
        return SynthesisResult(output_path, duration, DEFAULT_SAMPLE_RATE, word_count, "edge-tts")

    def synthesize(self, text, output_path, voice_id="default"):
        if not self._available:
            raise RuntimeError("edge-tts is not available")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            # Can't use asyncio.run() in a running loop, create a new one
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(self._synthesize_async(text, output_path, voice_id))
            finally:
                new_loop.close()
        else:
            return asyncio.run(self._synthesize_async(text, output_path, voice_id))


class PyTTSX3Engine(TTSEngine):
    """System TTS fallback using pyttsx3."""
    def __init__(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("pyttsx3 not available")

    def synthesize(self, text, output_path, voice_id="default"):
        if not self._available:
            raise RuntimeError("pyttsx3 is not available")
        voices = self._engine.getProperty("voices")
        if voice_id == "male" and len(voices) > 1:
            self._engine.setProperty("voice", voices[1].id)
        elif voice_id == "female" and voices:
            self._engine.setProperty("voice", voices[0].id)
        self._engine.setProperty("rate", int(WORDS_PER_MINUTE))
        self._engine.save_to_file(text, output_path)
        self._engine.runAndWait()
        duration = _get_wav_duration(output_path)
        word_count = len(text.split())
        logger.info(f"pyttsx3: {word_count} words in {duration:.2f}s")
        from app.engines.audio_engine import SynthesisResult
        return SynthesisResult(output_path, duration, 22050, word_count, "pyttsx3")


class SilentAudioEngine(TTSEngine):
    """Last-resort fallback: generate silent audio with estimated duration."""
    _available = True

    def synthesize(self, text, output_path, voice_id="default"):
        word_count = len(text.split())
        duration = (word_count / WORDS_PER_MINUTE) * 60
        sample_rate = DEFAULT_SAMPLE_RATE
        samples = int(duration * sample_rate)
        audio_data = np.zeros(samples, dtype=np.float32)
        import scipy.io.wavfile as wav
        wav.write(output_path, sample_rate, audio_data)
        logger.warning(f"SilentAudioEngine: silent audio for {word_count} words ({duration:.2f}s)")
        from app.engines.audio_engine import SynthesisResult
        return SynthesisResult(output_path, duration, sample_rate, word_count, "silent")


class AlignmentEngine:
    """Abstract base for alignment engines."""
    def align(self, audio_path, text, fps=DEFAULT_FPS):
        raise NotImplementedError


class WhisperXAligner(AlignmentEngine):
    """WhisperX forced alignment engine for phoneme-level timestamps."""
    def __init__(self, model_size="large-v3", device="cpu"):
        self._model = None
        self._align_model = None
        self._metadata = None
        self._device = device
        self._model_size = model_size
        self._available = False
        try:
            import whisperx
            self._whisperx = whisperx
            self._available = True
            logger.info("WhisperX imported successfully")
        except ImportError:
            logger.warning("WhisperX not available")

    def _load_models(self):
        if self._model is None:
            logger.info(f"Loading WhisperX model: {self._model_size} on {self._device}")
            self._model = self._whisperx.load_model(
                self._model_size, device=self._device,
                compute_type="int8" if self._device == "cpu" else "float16",
            )
        if self._align_model is None:
            self._align_model, self._metadata = self._whisperx.load_align_model(
                language_code="en", device=self._device,
            )

    def align(self, audio_path, text, fps=DEFAULT_FPS):
        if not self._available:
            raise RuntimeError("WhisperX is not available")
        self._load_models()
        logger.info(f"Aligning with WhisperX: {audio_path}")
        from app.core.schemas import CaptionWord
        audio = self._whisperx.load_audio(audio_path)
        result = self._model.transcribe(audio, batch_size=16)
        aligned_result = self._whisperx.align(
            result["segments"], self._align_model, self._metadata,
            audio, device=self._device,
        )
        captions = []
        words_list = []
        for segment in aligned_result.get("word_segments", []):
            if "start" not in segment or "end" not in segment:
                continue
            word = segment["word"].strip()
            captions.append(CaptionWord(
                word=word,
                start_frame=int(segment["start"] * fps),
                end_frame=int(segment["end"] * fps),
                is_highlight=_is_key_word(word),
                confidence=segment.get("confidence", 1.0),
            ))
            words_list.append(word)
        logger.info(f"WhisperX aligned {len(captions)} words")
        return AlignmentResult(captions, words_list, "whisperx")


class FasterWhisperAligner(AlignmentEngine):
    """Fallback alignment using faster-whisper with word timestamps."""
    def __init__(self, model_size="large-v3", device="cpu"):
        self._model = None
        self._model_size = model_size
        self._device = device
        self._available = False
        try:
            import faster_whisper
            self._available = True
            logger.info("faster-whisper loaded successfully")
        except ImportError:
            logger.warning("faster-whisper not available")

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size, device=self._device,
                compute_type="int8" if self._device == "cpu" else "float16",
            )

    def align(self, audio_path, text, fps=DEFAULT_FPS):
        if not self._available:
            raise RuntimeError("faster-whisper is not available")
        self._load_model()
        from app.core.schemas import CaptionWord
        segments, _ = self._model.transcribe(audio_path, word_timestamps=True)
        captions = []
        words_list = []
        for segment in segments:
            for word_info in segment.words:
                word = word_info.word.strip()
                captions.append(CaptionWord(
                    word=word,
                    start_frame=int(word_info.start * fps),
                    end_frame=int(word_info.end * fps),
                    is_highlight=_is_key_word(word),
                    confidence=getattr(word_info, "confidence", 1.0),
                ))
                words_list.append(word)
        logger.info(f"faster-whisper aligned {len(captions)} words")
        return AlignmentResult(captions, words_list, "whisper")


class EstimatedAligner(AlignmentEngine):
    """Last-resort alignment: distribute duration evenly across words."""
    def align(self, audio_path, text, fps=DEFAULT_FPS):
        from app.core.schemas import CaptionWord
        words_list = text.split()
        duration = _get_wav_duration(audio_path)
        seconds_per_word = duration / max(len(words_list), 1)
        captions = []
        for i, word in enumerate(words_list):
            start = i * seconds_per_word
            end = (i + 1) * seconds_per_word
            captions.append(CaptionWord(
                word=word,
                start_frame=int(start * fps),
                end_frame=int(end * fps),
                is_highlight=_is_key_word(word),
                confidence=0.3,
            ))
        logger.warning(f"EstimatedAligner: estimated {len(captions)} words from {duration:.2f}s")
        return AlignmentResult(captions, words_list, "estimated")



class AudioEngine:
    """High-level orchestrator for TTS synthesis and forced alignment.

    Automatically selects the best available engine and provides retry
    logic with exponential backoff for all operations.
    """

    def __init__(self):
        from app.core.config import get_settings
        from app.agents.research_agent import ResearchAgent
        settings = get_settings()
        self.settings = settings
        self.tts_voice = settings.tts_voice
        self.whisper_model_size = settings.whisper_model_size
        self.whisper_device = settings.whisper_device
        self.fps = settings.default_fps
        self.assets_dir = settings.assets_dir

        # Initialize TTS engine chain (best-to-fallback)
        self._tts_engines = [
            KokoroTTSEngine(voice_id=self.tts_voice),
            EdgeTTSEngine(),
            PyTTSX3Engine(),
            SilentAudioEngine(),
        ]

        # Initialize alignment engine chain (best-to-fallback)
        self._aligners = [
            WhisperXAligner(model_size=self.whisper_model_size, device=self.whisper_device),
            FasterWhisperAligner(model_size=self.whisper_model_size, device=self.whisper_device),
            EstimatedAligner(),
        ]

        self._tts_engine = None
        for engine in self._tts_engines:
            if getattr(engine, "_available", True):
                self._tts_engine = engine
                logger.info(f"Selected TTS engine: {engine.__class__.__name__}")
                break

        self._aligner = None
        for aligner in self._aligners:
            if getattr(aligner, "_available", True):
                self._aligner = aligner
                logger.info(f"Selected aligner: {aligner.__class__.__name__}")
                break

    async def synthesize_voiceover(
        self, text, scene_id, voice_id="default", retries=3
    ):
        """Synthesize voiceover audio for a scene with retry logic.

        Args:
            text: The narrative text to synthesize.
            scene_id: The scene identifier for output file naming.
            voice_id: The voice to use.
            retries: Maximum number of retry attempts.

        Returns:
            SynthesisResult with the audio file path and metadata.
        """
        output_path = str(self.assets_dir / "audio" / f"{scene_id}_voiceover.wav")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(retries):
            try:
                if self._tts_engine is None:
                    raise RuntimeError("No TTS engine available")
                if hasattr(self._tts_engine, '_synthesize_async'):
                    result = await self._tts_engine._synthesize_async(text, output_path, voice_id)
                else:
                    result = self._tts_engine.synthesize(text, output_path, voice_id)
                return result
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(
                    f"TTS attempt {attempt + 1}/{retries} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)

        logger.error(f"All TTS attempts failed. Last error: {last_error}")
        logger.info("Falling back to silent audio generation")
        return SilentAudioEngine().synthesize(text, output_path, voice_id)

    async def align_word_timestamps(
        self, audio_path, text, retries=3
    ):
        """Run forced alignment to extract word-level timestamps.

        Args:
            audio_path: Path to the audio WAV file.
            text: The transcript to align.
            retries: Maximum number of retry attempts.

        Returns:
            AlignmentResult with CaptionWord list and word list.
        """
        last_error = None
        for attempt in range(retries):
            try:
                if self._aligner is None:
                    raise RuntimeError("No aligner available")
                result = self._aligner.align(audio_path, text, fps=self.fps)
                return result
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(
                    f"Alignment attempt {attempt + 1}/{retries} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)

        logger.error(f"All alignment attempts failed. Last error: {last_error}")
        logger.info("Falling back to estimated alignment")
        return EstimatedAligner().align(audio_path, text, fps=self.fps)

    async def process_scene(self, narrative, scene_id, voice_id="default"):
        """Full pipeline for a single scene: synthesize + align."""
        synthesis = await self.synthesize_voiceover(narrative, scene_id, voice_id)
        alignment = await self.align_word_timestamps(
            synthesis.audio_path, narrative
        )

        from app.core.schemas import VoiceoverSpec
        voiceover_spec = VoiceoverSpec(
            audio_path=synthesis.audio_path,
            duration_seconds=synthesis.duration_seconds,
            sample_rate=synthesis.sample_rate,
            voice_id=voice_id,
            word_count=synthesis.word_count,
            speaker_wpm=WORDS_PER_MINUTE,
        )
        return voiceover_spec, alignment.captions

    async def process_all_scenes(self, scenes_data):
        """Process multiple scenes concurrently.

        Args:
            scenes_data: List of (scene_id, narrative) tuples.

        Returns:
            List of (VoiceoverSpec, list[CaptionWord]) tuples.
        """
        tasks = [
            self.process_scene(narrative, scene_id)
            for scene_id, narrative in scenes_data
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        from app.core.schemas import VoiceoverSpec, CaptionWord
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                scene_id, narrative = scenes_data[i]
                logger.error(f"Failed to process scene {scene_id}: {result}")
                word_count = len(narrative.split())
                est_duration = (word_count / WORDS_PER_MINUTE) * 60
                vo_spec = VoiceoverSpec(
                    audio_path=f"/workspace/assets/audio/{scene_id}_voiceover.wav",
                    duration_seconds=round(est_duration, 3),
                    word_count=word_count,
                    speaker_wpm=WORDS_PER_MINUTE,
                )
                captions = [
                    CaptionWord(word=w, start_frame=0, end_frame=0,
                                is_highlight=_is_key_word(w))
                    for w in narrative.split()
                ]
                processed.append((vo_spec, captions))
            else:
                processed.append(result)
        return processed


async def synthesize_all_scenes(scenes_data):
    """Convenience function to process multiple scenes."""
    engine = AudioEngine()
    return await engine.process_all_scenes(scenes_data)


if __name__ == "__main__":
    async def _test():
        engine = AudioEngine()
        test_text = (
            "In 1974, something extraordinary happened that changed everything. "
            "What if we told you the truth behind India's nuclear program? "
            "This is the story that history books barely mention."
        )
        vo, captions = await engine.process_scene(test_text, "test_scene_00")
        print(f"Voiceover: duration={vo.duration_seconds:.2f}s, words={vo.word_count}, engine={vo.voice_id}")
        print(f"Captions: {len(captions)} words aligned")
        if captions:
            print(f"  First: '{captions[0].word}' frames {captions[0].start_frame}-{captions[0].end_frame}")
            print(f"  Highlighted: {[c.word for c in captions[:10] if c.is_highlight]}")

    asyncio.run(_test())
