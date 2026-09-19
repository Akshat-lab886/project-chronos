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
 * KineticCaptions — Premium word-level highlighted typography.
 *
 * - Bebas Neue / Impact style display font (uppercase, condensed, bold)
 * - Letter-spaced, cinema-grade text
 * - Active word: golden glow + slight scale-up
 * - Inactive: bright white with soft drop-shadow for legibility on any background
 * - Black gradient strip behind text for guaranteed contrast
 * - Rolling window: only renders words active ±30 frames from current frame
 */
export const KineticCaptions: React.FC<KineticCaptionsProps> = ({
  captions,
  startFrame,
  durationInFrames,
  style,
  fontSize = 64,
  maxWidth = 88,
}) => {
  const frame = useCurrentFrame();
  const currentAbsFrame = startFrame + frame;

  // Filter words within active rolling window
  const windowSize = 30;
  const activeWords = captions.filter(
    (w) => currentAbsFrame >= w.start_frame - windowSize &&
           currentAbsFrame <= w.end_frame + windowSize
  );

  if (activeWords.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 100,
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
      {/* Gradient backdrop strip for guaranteed legibility */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 60,
          height: 200,
          background: "linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.6) 50%, rgba(0,0,0,0.85) 100%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "relative",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: "0 18px",
          maxWidth: `${maxWidth}%`,
          padding: "16px 0",
        }}
      >
        {activeWords.map((token, index) => {
          const isActive =
            currentAbsFrame >= token.start_frame &&
            currentAbsFrame <= token.end_frame;

          // Opacity: active = 1, fading in/out smoothly
          let opacity = 0.4;
          if (frame >= token.start_frame - 8 && frame < token.start_frame) {
            opacity = interpolate(frame, [token.start_frame - 8, token.start_frame], [0, 1]);
          } else if (isActive) {
            opacity = 1;
          } else if (frame > token.end_frame && frame <= token.end_frame + 12) {
            opacity = interpolate(frame, [token.end_frame, token.end_frame + 12], [1, 0]);
          }

          // Scale spring effect on active word
          let scale = 1;
          if (isActive) {
            const wordProgress = (frame - token.start_frame) / Math.max(1, token.end_frame - token.start_frame);
            scale = interpolate(wordProgress, [0, 0.25, 1], [1.08, 1.0, 1.0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
          }

          // Color & glow:
          // - Active highlighted: gold (#FFD700) with strong glow
          // - Active regular: cyan (#00E5FF) with subtle glow
          // - Inactive: bright white (#FFFFFF) with soft drop shadow
          let color = "#FFFFFF";
          let textShadow = "0 2px 12px rgba(0, 0, 0, 0.95), 0 0 4px rgba(0, 0, 0, 0.9)";
          let fontWeight = 800;
          if (isActive) {
            if (token.is_highlight) {
              color = "#FFD700";
              textShadow = "0 0 20px rgba(255, 215, 0, 0.95), 0 0 40px rgba(255, 215, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.9)";
            } else {
              color = "#FFFFFF";
              textShadow = "0 0 16px rgba(0, 229, 255, 0.85), 0 0 32px rgba(0, 229, 255, 0.5), 0 2px 8px rgba(0, 0, 0, 0.9)";
            }
            fontWeight = 900;
          } else if (token.is_highlight) {
            color = "#FFC940";
            textShadow = "0 0 6px rgba(255, 201, 64, 0.6), 0 2px 8px rgba(0, 0, 0, 0.9)";
          }

          return (
            <span
              key={`${token.word}_${index}`}
              style={{
                fontFamily: '"Bebas Neue", "Impact", "Anton", "Arial Black", sans-serif',
                fontSize: `${fontSize}px`,
                fontWeight,
                color,
                textShadow,
                opacity,
                transform: `scale(${scale})`,
                transition: "all 0.08s ease-out",
                whiteSpace: "nowrap",
                textTransform: "uppercase",
                letterSpacing: "2.5px",
                lineHeight: 1.1,
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
