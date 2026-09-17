import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
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
 * KineticCaptions — Word-level highlighted typography.
 *
 * Uses pure inline styles (no Tailwind classes) to guarantee rendering
 * in Remotion's headless Chromium environment where CSS may not be bundled.
 *
 * - Words have trailing whitespace to prevent merging
 * - Centered flex-wrap with gap for consistent horizontal positioning
 * - Rolling window: only renders words active ±20 frames from current frame
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
  const currentAbsFrame = startFrame + frame;

  // Filter words within active rolling window
  const windowSize = 20;
  const activeWords = captions.filter(
    (w) => currentAbsFrame >= w.start_frame - windowSize &&
           currentAbsFrame <= w.end_frame + windowSize
  );

  if (activeWords.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        zIndex: 50,
        pointerEvents: "none",
        ...style,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: "12px",
          padding: "12px 28px",
          backgroundColor: "rgba(0, 0, 0, 0.75)",
          backdropFilter: "blur(8px)",
          borderRadius: "16px",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          maxWidth: `${maxWidth}%`,
        }}
      >
        {activeWords.map((token, index) => {
          const isActive =
            currentAbsFrame >= token.start_frame &&
            currentAbsFrame <= token.end_frame;

          // Opacity with fade in/out
          let opacity = 0.5;
          if (frame >= token.start_frame - 10 && frame < token.start_frame) {
            opacity = interpolate(frame, [token.start_frame - 10, token.start_frame], [0, 1]);
          } else if (isActive) {
            opacity = 1;
          } else if (frame > token.end_frame && frame <= token.end_frame + 15) {
            opacity = interpolate(frame, [token.end_frame, token.end_frame + 15], [1, 0]);
          }

          // Scale spring effect
          let scale = 1;
          if (isActive) {
            const wordProgress = (frame - token.start_frame) / Math.max(1, token.end_frame - token.start_frame);
            scale = interpolate(wordProgress, [0, 0.3, 1], [1.15, 1.0, 1.0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
          }

          // Color: gold for highlighted+active, cyan for active, white for inactive
          let color = "#FFFFFF";
          let textShadow = "0 2px 4px rgba(0, 0, 0, 0.8)";
          if (isActive) {
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
                fontWeight: isActive ? 700 : 500,
                color,
                textShadow,
                opacity,
                transform: `scale(${scale})`,
                transition: "all 0.1s ease-out",
                whiteSpace: "nowrap",
                textTransform: "uppercase",
                letterSpacing: "1px",
                display: "inline-block",
              }}
            >
              {token.word}{" "}
            </span>
          );
        })}
      </div>
    </div>
  );
};
