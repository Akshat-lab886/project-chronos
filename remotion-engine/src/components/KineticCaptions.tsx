/**
 * Project Chronos — Kinetic Captions Component
 *
 * High-contrast, drop-shadowed typography with spring-physics entry
 * transitions and gold/cyan active-word highlighting.
 *
 * Features:
 * - Word-level active highlighting synced to audio via frame timestamps
 * - Spring-physics entry animation for each word
 * - Gold/cyan color accents for highlighted keywords
 * - Automatic line wrapping with optimal word spacing
 * - Semi-transparent background for readability on any footage
 */

import React, { useMemo, useCallback } from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CaptionWord } from "../types/schema";

export interface KineticCaptionsProps {
  /** Array of word-level captions with frame timestamps */
  captions: CaptionWord[];
  /** Scene start frame (for offset calculations) */
  startFrame: number;
  /** Scene duration in frames */
  durationInFrames: number;
  /** Optional styling override */
  style?: React.CSSProperties;
  /** Font size in pixels */
  fontSize?: number;
  /** Maximum caption width as percentage of screen */
  maxWidth?: number;
}

interface TimedWord {
  word: string;
  startFrame: number;
  endFrame: number;
  isHighlight: boolean;
  opacity: number;
  scale: number;
}

/**
 * Calculate the timing state for each word based on the current frame.
 */
function useTimedWords(
  captions: CaptionWord[],
  startFrame: number,
  currentFrame: number
): TimedWord[] {
  return useMemo(() => {
    return captions.map((cap) => {
      const absoluteStart = cap.start_frame;
      const absoluteEnd = cap.end_frame;

      // Word is "active" (being spoken) when current frame is within range
      const isActive = currentFrame >= absoluteStart && currentFrame <= absoluteEnd;

      // Calculate opacity: fades in before start, full during, fades out after end
      let opacity: number;
      if (currentFrame < absoluteStart) {
        // Fade in 15 frames before the word starts
        const fadeInStart = absoluteStart - 15;
        opacity = currentFrame >= fadeInStart
          ? interpolate(currentFrame, [fadeInStart, absoluteStart], [0, 1])
          : 0;
      } else if (currentFrame > absoluteEnd) {
        // Fade out 10 frames after the word ends
        const fadeOutEnd = absoluteEnd + 10;
        opacity = currentFrame <= fadeOutEnd
          ? interpolate(currentFrame, [absoluteEnd, fadeOutEnd], [1, 0])
          : 0;
      } else {
        opacity = 1;
      }

      // Scale with spring physics effect when word becomes active
      let scale: number = 1;
      if (isActive) {
        // Spring effect: start slightly larger and settle
        const wordProgress = (currentFrame - absoluteStart) / Math.max(1, absoluteEnd - absoluteStart);
        scale = interpolate(wordProgress, [0, 0.3, 1], [1.2, 1.0, 1.0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
      } else if (opacity > 0) {
        scale = 1.0;
      } else {
        scale = 0.9;
      }

      return {
        word: cap.word,
        startFrame: absoluteStart,
        endFrame: absoluteEnd,
        isHighlight: cap.is_highlight,
        opacity,
        scale,
      };
    });
  }, [captions, currentFrame]);
}

/**
 * Group timed words into lines based on maximum line width.
 */
function useWordLines(
  timedWords: TimedWord[],
  maxWidth: number
): TimedWord[][] {
  return useMemo(() => {
    const lines: TimedWord[][] = [];
    let currentLine: TimedWord[] = [];
    let currentWidth = 0;

    // Approximate character width as 0.6em
    const avgCharWidth = 0.6;

    for (const word of timedWords) {
      const wordWidth = word.word.length * avgCharWidth;

      if (currentWidth + wordWidth > maxWidth && currentLine.length > 0) {
        lines.push(currentLine);
        currentLine = [];
        currentWidth = 0;
      }

      currentLine.push(word);
      currentWidth += wordWidth + 0.3; // space width
    }

    if (currentLine.length > 0) {
      lines.push(currentLine);
    }

    return lines;
  }, [timedWords, maxWidth]);
}

/**
 * KineticCaptions — Word-level highlighted typography with spring animations.
 *
 * Renders subtitles with:
 * - Active word highlighting (gold/cyan accent fill)
 * - Spring-physics scale animation on word entry
 * - Drop shadow for high contrast on any background
 * - Semi-transparent background overlay for readability
 */
export const KineticCaptions: React.FC<KineticCaptionsProps> = ({
  captions,
  startFrame,
  durationInFrames,
  style,
  fontSize = 48,
  maxWidth = 80,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const timedWords = useTimedWords(captions, startFrame, frame);
  const wordLines = useWordLines(timedWords, maxWidth);

  // Calculate total height for vertical centering
  const lineHeight = fontSize * 1.3;
  const totalHeight = wordLines.length * lineHeight;
  const startY = height * 0.78 - totalHeight / 2; // Position at 78% from top

  // Background position and size
  const bgPadding = 30;
  const bgY = Math.max(0, startY - bgPadding / 2);
  const bgHeight = Math.min(height * 0.18, totalHeight + bgPadding);
  const bgWidth = width * (maxWidth / 100) * fontSize * 0.6 + bgPadding;
  const bgX = (width - bgWidth) / 2;

  return (
    <div
      style={{
        position: "absolute" as const,
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none" as const,
        ...style,
      }}
    >
      {/* Background for readability */}
      <div
        style={{
          position: "absolute" as const,
          left: bgX,
          top: bgY,
          width: bgWidth,
          height: bgHeight,
          backgroundColor: "rgba(0, 0, 0, 0.5)",
          borderRadius: 12,
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Render each line of words */}
      {wordLines.map((line, lineIdx) => (
        <div
          key={`line-${lineIdx}`}
          style={{
            position: "absolute" as const,
            left: "50%",
            transform: "translateX(-50%)",
            top: startY + lineIdx * lineHeight,
            display: "flex",
            gap: "0.3em",
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          {line.map((tw, wordIdx) => {
            // Active word color: gold for highlighted, cyan for active non-highlight
            const isCurrentlyActive = tw.opacity > 0.3;
            let color: string;
            let textShadow: string;

            if (tw.isHighlight && isCurrentlyActive) {
              color = "#FFD700"; // Gold
              textShadow = "0 0 10px #FFD700, 0 0 20px rgba(255, 215, 0, 0.8)";
            } else if (isCurrentlyActive) {
              color = "#00FFFF"; // Cyan
              textShadow = "0 0 8px #00FFFF, 0 0 16px rgba(0, 255, 255, 0.7)";
            } else if (tw.isHighlight) {
              color = "#B8860B"; // Dark gold (inactive highlight)
              textShadow = "0 0 5px rgba(184, 134, 11, 0.5)";
            } else {
              color = "#FFFFFF";
              textShadow = "0 2px 4px rgba(0, 0, 0, 0.8)";
            }

            return (
              <span
                key={`word-${wordIdx}`}
                style={{
                  fontSize: `${fontSize}px`,
                  fontWeight: tw.isHighlight && isCurrentlyActive ? 700 : 500,
                  color,
                  textShadow,
                  opacity: tw.opacity,
                  transform: `scale(${tw.scale})`,
                  transition: "all 0.1s ease-out",
                  whiteSpace: "nowrap",
                  letterSpacing: "-0.02em",
                }}
              >
                {tw.word}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};
