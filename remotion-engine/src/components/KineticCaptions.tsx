import React, { useMemo } from "react";
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

/**
 * KineticCaptions — Word-level highlighted typography with centered layout.
 *
 * Fixes:
 * - Words rendered with trailing whitespace (space character) to prevent merging
 * - Centered flex-wrap container with gap for consistent horizontal positioning
 * - Rolling window: only renders words active ±15 frames from current frame
 * - No justify-between or unconstrained positioning
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

  // Only render words active within a rolling window (~4-5 seconds at 60fps)
  const windowSize = 20; // frames before/after
  const activeWords = useMemo(() => {
    return captions.filter((cap) => {
      const isActive =
        frame >= cap.start_frame - windowSize &&
        frame <= cap.end_frame + windowSize;
      return isActive;
    });
  }, [captions, frame, windowSize]);

  // If nothing in window, don't render
  if (activeWords.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute" as const,
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none" as const,
        zIndex: 50,
        ...style,
      }}
    >
      {/* Centered container with backdrop */}
      <div className="absolute bottom-20 left-0 right-0 flex justify-center pointer-events-none">
        <div
          className="flex flex-wrap items-center justify-center gap-2 px-8 py-4 rounded-2xl border shadow-2xl"
          style={{
            backgroundColor: "rgba(0, 0, 0, 0.55)",
            backdropFilter: "blur(6px)",
            borderColor: "rgba(255, 255, 255, 0.08)",
            maxWidth: `${width * 0.76}px`,
          }}
        >
          {activeWords.map((token, index) => {
            const isSpeakingNow =
              frame >= token.start_frame && frame <= token.end_frame;

            // Opacity: visible during spoken, fading in/out
            let opacity = 0.5;
            if (frame >= token.start_frame - 10 && frame < token.start_frame) {
              opacity = interpolate(frame, [token.start_frame - 10, token.start_frame], [0, 1]);
            } else if (isSpeakingNow) {
              opacity = 1;
            } else if (frame > token.end_frame && frame <= token.end_frame + 15) {
              opacity = interpolate(frame, [token.end_frame, token.end_frame + 15], [1, 0]);
            }

            // Scale: spring effect when active
            let scale = 1;
            if (isSpeakingNow) {
              const wordProgress = (frame - token.start_frame) / Math.max(1, token.end_frame - token.start_frame);
              scale = interpolate(wordProgress, [0, 0.3, 1], [1.15, 1.0, 1.0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
            }

            // Color: gold for highlighted+active, cyan for active non-highlight, white for inactive
            let color = "#FFFFFF";
            let textShadow = "0 2px 4px rgba(0, 0, 0, 0.8)";
            if (isSpeakingNow) {
              if (token.is_highlight) {
                color = "#FFD700";
                textShadow = "0 0 10px #FFD700, 0 0 20px rgba(255, 215, 0, 0.8)";
              } else {
                color = "#00FFFF";
                textShadow = "0 0 8px #00FFFF, 0 0 16px rgba(0, 255, 255, 0.7)";
              }
            } else if (token.is_highlight) {
              color = "#B8860B";
              textShadow = "0 0 5px rgba(184, 134, 11, 0.5)";
            }

            return (
              <span
                key={`${token.word}_${index}`}
                style={{
                  fontSize: `${fontSize}px`,
                  fontWeight: isSpeakingNow ? 700 : 500,
                  color,
                  textShadow,
                  opacity,
                  transform: `scale(${scale})`,
                  transition: "all 0.1s ease-out",
                  whiteSpace: "nowrap",
                  letterSpacing: "-0.02em",
                }}
              >
                {token.word}{" "}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};
