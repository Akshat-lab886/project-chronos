/**
 * Project Chronos — Ken Burns Canvas Component
 *
 * Implements continuous multi-axis motion (zoom, pan, drift) for visual assets.
 * Supports both image and video sources with frame-interpolated easing.
 *
 * Motion presets:
 * - KEN_BURNS_ZOOM_IN: Slow zoom into the image while drifting upward
 * - KEN_BURNS_ZOOM_OUT: Slow zoom out from the image while drifting downward
 * - PARALLAX_DRIFT: Subtle continuous pan for parallax depth simulation
 * - STATIC: No animation (used for map overlays and graphic layers)
 */

import React, { useMemo } from "react";
import { interpolate, useCurrentFrame, Img, Video, type ImgProps } from "remotion";
import type { MotionPreset } from "../types/schema";
import { MotionStyle } from "./styles";

export interface KenBurnsCanvasProps {
  /** Source URL or local file path for the image/video */
  src: string;
  /** Type of source: image or video */
  type: "image" | "video";
  /** Motion preset to apply */
  motionPreset: MotionPreset;
  /** Total duration in frames */
  durationInFrames: number;
  /** Scene start frame (for offset calculations) */
  sceneStartFrame?: number;
  /** Whether the asset should be muted (for video) */
  muted?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Style override */
  style?: React.CSSProperties;
}

/**
 * Generates the interpolation parameters for each motion preset.
 * Returns start and end values for scale, translateX, and translateY.
 */
function useMotionParams(
  motionPreset: MotionPreset,
  durationInFrames: number,
  sceneStartFrame: number
) {
  const frame = useCurrentFrame();
  const relativeFrame = frame;  // Inside Sequence, useCurrentFrame() returns local frame (0-based)

  const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));

  return useMemo(() => {
    switch (motionPreset) {
      case "KEN_BURNS_ZOOM_IN": {
        // Start zoomed out, slowly zoom in while drifting up
        return {
          scale: interpolate(progress, [0, 1], [1.0, 1.2], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translateX: interpolate(progress, [0, 1], [0, -15], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translateY: interpolate(progress, [0, 1], [0, -25], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        };
      }

      case "KEN_BURNS_ZOOM_OUT": {
        // Start zoomed in, slowly zoom out while drifting down
        return {
          scale: interpolate(progress, [0, 1], [1.2, 1.0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translateX: interpolate(progress, [0, 1], [-15, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translateY: interpolate(progress, [0, 1], [-25, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        };
      }

      case "PARALLAX_DRIFT": {
        // Continuous subtle drift with slight zoom oscillation
        const driftX = Math.sin(progress * Math.PI * 2) * 10;
        const driftY = Math.cos(progress * Math.PI * 1.5) * 8;
        const zoomOsc = 1.0 + Math.sin(progress * Math.PI * 2) * 0.02;
        return {
          scale: zoomOsc,
          translateX: driftX,
          translateY: driftY,
        };
      }

      default:
        return {
          scale: 1.0,
          translateX: 0,
          translateY: 0,
        };
    }
  }, [progress, motionPreset]);
}

/**
 * KenBurnsCanvas — Frame-interpolated zoom, pan, and drift transitions.
 *
 * Uses Remotion's interpolate() for smooth, frame-accurate motion.
 * The component handles both still images and video sources.
 */
export const KenBurnsCanvas: React.FC<KenBurnsCanvasProps> = ({
  src,
  type,
  motionPreset,
  durationInFrames,
  sceneStartFrame = 0,
  muted = false,
  className,
  style,
}) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame;  // Inside Sequence, useCurrentFrame() returns local frame (0-based)

  const { scale, translateX, translateY } = useMotionParams(
    motionPreset,
    durationInFrames,
    sceneStartFrame
  );

  const transformStyle: React.CSSProperties = useMemo(() => ({
    transform: `scale(${scale}) translateX(${translateX}px) translateY(${translateY}px)`,
    transition: "transform 0.1s linear",
  }), [scale, translateX, translateY]);

  const containerStyle: React.CSSProperties = {
    position: "absolute" as const,
    inset: 0,
    overflow: "hidden",
    width: "100%",
    height: "100%",
  };

  const mediaStyle: React.CSSProperties = {
    position: "absolute" as const,
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    ...transformStyle,
  };

  return (
    <div className={className} style={{ ...containerStyle, ...style }}>
      {type === "video" ? (
        <Video
          muted={muted}
          src={src}
          style={mediaStyle}
          startFrom={relativeFrame}
          endAt={relativeFrame + durationInFrames}
        />
      ) : (
        <Img
          src={src}
          style={mediaStyle}
        />
      )}
    </div>
  );
};
