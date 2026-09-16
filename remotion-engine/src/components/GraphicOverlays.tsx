/**
 * Project Chronos — Graphic Overlays Component
 *
 * Implements animated newspaper/document callouts, stat counters,
 * and other graphical overlays that appear on top of scenes.
 *
 * Overlay types:
 * - NEWSPAPER: Historical newspaper clipping with yellow marker highlight
 * - STAT_COUNTER: Animated numeric counter with label
 * - MAP: (Handled by MapVisualizer component)
 * - NONE: No overlay
 */

import React, { useMemo, useCallback } from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { OverlaySpec, OverlayType } from "../types/schema";

export interface GraphicOverlaysProps {
  /** The overlay specification for this scene */
  overlaySpec: OverlaySpec;
  /** Scene start frame */
  startFrame?: number;
  /** Scene duration in frames */
  durationInFrames: number;
  /** Screen dimensions */
  width?: number;
  height?: number;
}

/**
 * NewspaperHighlighter — Animated newspaper/document clipping overlay.
 *
 * Renders a vintage newspaper clipping with:
 * - Yellow highlighter marker sweep animation
 * - Typewriter-style text reveal
 * - Sepia/paper texture background
 * - Scissors-cut paper edge effect
 */
export const NewspaperHighlighter: React.FC<{
  overlaySpec: OverlaySpec;
  startFrame: number;
  durationInFrames: number;
  width: number;
  height: number;
}> = ({ overlaySpec, startFrame, durationInFrames, width, height }) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - startFrame;
  const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));

  const data = overlaySpec.data as Record<string, unknown>;
  const headline = (data["headline"] as string) || "HISTORICAL DOCUMENT";
  const source = (data["source"] as string) || "Unknown Archive";

  // Entrance animation: slide in from left
  const entryProgress = interpolate(progress, [0, 0.15], [0, 1], {
    extrapolateRight: "clamp",
  });
  const slideX = interpolate(entryProgress, [0, 1], [-100, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(entryProgress, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Highlighter sweep animation
  const sweepProgress = interpolate(progress, [0.15, 0.6], [0, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Paper texture dimensions
  const paperWidth = Math.min(width * 0.6, 800);
  const paperHeight = Math.min(height * 0.25, 250);
  const paperX = (width - paperWidth) / 2;
  const paperY = height * 0.15;

  return (
    <div
      style={{
        position: "absolute" as const,
        left: paperX + slideX,
        top: paperY,
        width: paperWidth,
        height: paperHeight,
        opacity,
        pointerEvents: "none" as const,
      }}
    >
      {/* Paper background with texture */}
      <div
        style={{
          position: "absolute" as const,
          inset: 0,
          backgroundColor: "#f5f1e6",
          borderRadius: 8,
          borderWidth: 2,
          borderStyle: "solid" as const,
          borderColor: "#d4c8a6",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.4)",
          overflow: "hidden",
        }}
      >
        {/* Paper grain texture */}
        <div
          style={{
            position: "absolute" as const,
            inset: 0,
            backgroundImage: `url("data:image/svg+xml;base64,${btoa(
              '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><rect width="100" height="100" fill="%23f5f1e6"/><path d="M0 0L100 100M100 0L0 100" stroke="%23e8e0c5" stroke-width="0.5" opacity="0.3"/></svg>'
            )}")`,
            opacity: 0.3,
          }}
        />

        {/* Scissors-cut edge effect */}
        <div
          style={{
            position: "absolute" as const,
            top: 0,
            left: 0,
            right: 0,
            height: 20,
            backgroundColor: "#f5f1e6",
            borderBottom: "none",
            borderTopLeftRadius: 8,
            borderTopRightRadius: 8,
          }}
        />
      </div>

      {/* Content */}
      <div
        style={{
          position: "absolute" as const,
          inset: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {/* Source tag */}
        <div
          style={{
            fontSize: 12,
            color: "#8b7355",
            fontWeight: 600,
            textTransform: "uppercase" as const,
            letterSpacing: "0.1em",
          }}
        >
          {source} • {new Date().getFullYear()}
        </div>

        {/* Headline */}
        <div
          style={{
            fontSize: paperWidth * 0.045,
            fontWeight: 700,
            color: "#333",
            lineHeight: 1.2,
            position: "relative" as const,
          }}
        >
          {headline}

          {/* Highlighter sweep */}
          <div
            style={{
              position: "absolute" as const,
              top: 0,
              left: 0,
              height: "100%",
              width: `${sweepProgress}%`,
              backgroundColor: "rgba(255, 255, 0, 0.5)",
              zIndex: 1,
            }}
          />
        </div>

        {/* Byline */}
        <div
          style={{
            fontSize: 11,
            color: "#8b7355",
            fontStyle: "italic",
          }}
        >
          — Classified Archive Document
        </div>
      </div>
    </div>
  );
};

/**
 * StatCounter — Animated numeric counter with label.
 *
 * Renders a dynamic counter that animates from start to end value,
 * with a label and optional unit suffix.
 */
export const StatCounter: React.FC<{
  overlaySpec: OverlaySpec;
  startFrame: number;
  durationInFrames: number;
  width: number;
  height: number;
}> = ({ overlaySpec, startFrame, durationInFrames, width, height }) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - startFrame;
  const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));

  const data = overlaySpec.data as Record<string, unknown>;
  const label = (data["label"] as string) || "STATISTIC";
  const startValue = (data["start_value"] as number) || 0;
  const endValue = (data["end_value"] as number) || 100;
  const unit = (data["unit"] as string) || "";

  // Counter animation with easing (fast start, slow end)
  const counterProgress = interpolate(progress, [0, 0.85], [0, 1], {
    extrapolateRight: "clamp",
  });

  const currentValue = startValue + (endValue - startValue) * counterProgress;

  // Format the number with appropriate precision
  const formattedValue = useMemo(() => {
    if (Math.abs(endValue) >= 1000) {
      return Math.round(currentValue).toLocaleString();
    }
    return currentValue.toFixed(Math.abs(endValue) >= 100 ? 0 : 1);
  }, [currentValue, endValue]);

  // Entry animation
  const scale = interpolate(progress, [0, 0.2, 1], [0.5, 1.1, 1.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const opacity = interpolate(progress, [0, 0.1, 0.95, 1], [0, 1, 1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const boxWidth = Math.min(width * 0.35, 400);
  const boxHeight = Math.min(height * 0.12, 150);
  const boxX = width * 0.08;
  const boxY = height * 0.08;

  return (
    <div
      style={{
        position: "absolute" as const,
        left: boxX,
        top: boxY,
        width: boxWidth,
        height: boxHeight,
        opacity,
        transform: `scale(${scale})`,
        transformOrigin: "top left",
        pointerEvents: "none" as const,
      }}
    >
      <div
        style={{
          position: "absolute" as const,
          inset: 0,
          backgroundColor: "rgba(0, 0, 0, 0.6)",
          borderRadius: 12,
          padding: 20,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          gap: 8,
        }}
      >
        {/* Value */}
        <div
          style={{
            fontSize: boxHeight * 0.45,
            fontWeight: 800,
            color: "#00FFFF",
            textShadow: "0 0 15px rgba(0, 255, 255, 0.8)",
            fontFamily: "monospace",
            lineHeight: 1,
          }}
        >
          {formattedValue}
          {unit}
        </div>

        {/* Label */}
        <div
          style={{
            fontSize: boxHeight * 0.18,
            color: "#FFFFFF",
            textTransform: "uppercase" as const,
            letterSpacing: "0.1em",
            textAlign: "center" as const,
          }}
        >
          {label}
        </div>

        {/* Progress bar */}
        <div
          style={{
            position: "absolute" as const,
            bottom: 8,
            left: 20,
            right: 20,
            height: 3,
            backgroundColor: "rgba(255, 255, 255, 0.1)",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${counterProgress * 100}%`,
              height: "100%",
              backgroundColor: "#00FFFF",
              transition: "width 0.1s linear",
            }}
          />
        </div>
      </div>
    </div>
  );
};

/**
 * GraphicOverlays — Root component that dispatches to the appropriate
 * overlay renderer based on the overlay type.
 */
export const GraphicOverlays: React.FC<GraphicOverlaysProps> = ({
  overlaySpec,
  startFrame = 0,
  durationInFrames,
  width = 1920,
  height = 1080,
}) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - startFrame;

  if (overlaySpec.type === "NONE" || !overlaySpec.type) {
    return null;
  }

  // Don't render before the overlay's scene starts
  if (relativeFrame < 0) {
    return null;
  }

  // Only render if within a reasonable time window (scene + 2 seconds buffer)
  if (relativeFrame > durationInFrames + 120) {
    return null;
  }

  switch (overlaySpec.type) {
    case "NEWSPAPER":
      return (
        <NewspaperHighlighter
          overlaySpec={overlaySpec}
          startFrame={startFrame}
          durationInFrames={durationInFrames}
          width={width}
          height={height}
        />
      );

    case "STAT_COUNTER":
      return (
        <StatCounter
          overlaySpec={overlaySpec}
          startFrame={startFrame}
          durationInFrames={durationInFrames}
          width={width}
          height={height}
        />
      );

    case "MAP":
      // Maps are handled by MapVisualizer component
      return null;

    default:
      return null;
  }
};
