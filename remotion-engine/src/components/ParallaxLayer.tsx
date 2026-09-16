/**
 * Project Chronos — Parallax Layer Component
 *
 * Implements 2.5D parallax cutout depth simulation:
 * - Simulates multi-layer depth by separating foreground and background
 * - Creates independent velocity motion for each layer
 * - Uses CSS transform3d for hardware-accelerated rendering
 *
 * Note: Full subject extraction (rembg) would be performed server-side.
 * This component simulates the parallax effect using the asset as-is.
 */

import React, { useMemo } from "react";
import { interpolate, useCurrentFrame, Img, Video } from "remotion";
import type { MotionPreset } from "../types/schema";

export interface ParallaxLayerProps {
  /** Source URL for the image/video */
  src: string;
  /** Type of source */
  type: "image" | "video";
  /** Duration in frames */
  durationInFrames: number;
  /** Scene start frame */
  sceneStartFrame?: number;
  /** Depth level (0 = background, 1 = foreground) */
  depth?: number;
  /** Motion preset */
  motionPreset?: MotionPreset;
  /** Whether muted (for video) */
  muted?: boolean;
}

/**
 * ParallaxLayer — 2.5D parallax cutout with multi-layer depth.
 *
 * Simulates depth by offsetting foreground and background layers
 * at different rates during camera movement, creating a parallax
 * effect that adds dimensionality to flat 2D assets.
 */
export const ParallaxLayer: React.FC<ParallaxLayerProps> = ({
  src,
  type,
  durationInFrames,
  sceneStartFrame = 0,
  depth = 0.5,
  motionPreset = "PARALLUX_DRIFT",
  muted = true,
}) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - sceneStartFrame;

  // Multi-layer parallax: foreground moves faster than background
  // This creates a 2.5D effect when combined with Ken Burns on each layer
  const parallaxFactor = (depth - 0.5) * 40; // -20 to +20px offset

  const scale = useMemo(() => {
    const baseScale = 1.1;
    const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));
    // Subtle scale oscillation for organic feel
    const scaleOsc = 1 + Math.sin(progress * Math.PI * 2) * 0.01;
    return baseScale * scaleOsc;
  }, [relativeFrame, durationInFrames]);

  const translateX = useMemo(() => {
    const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));
    return interpolate(progress, [0, 0.5, 1], [parallaxFactor, -parallaxFactor, parallaxFactor], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }, [relativeFrame, durationInFrames, parallaxFactor]);

  const translateY = useMemo(() => {
    const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));
    const drift = interpolate(progress, [0, 1], [-10, 15], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return drift + parallaxFactor * 0.5;
  }, [relativeFrame, durationInFrames, parallaxFactor]);

  // Layer offset for parallax depth
  const layerOffsetX = parallaxFactor * 0.3;
  const layerOffsetY = parallaxFactor * 0.2;

  const mediaStyle: React.CSSProperties = {
    position: "absolute" as const,
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    transform: `scale(${scale}) translateX(${translateX + layerOffsetX}px) translateY(${translateY + layerOffsetY}px)`,
    willChange: "transform",
  };

  const backgroundStyle: React.CSSProperties = {
    position: "absolute" as const,
    inset: 0,
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    transform: `scale(${scale * 0.95}) translateX(${-layerOffsetX}px) translateY(${-layerOffsetY}px)`,
    filter: "blur(2px) brightness(0.8)",
    opacity: 0.7,
  };

  return (
    <div
      style={{
        position: "absolute" as const,
        inset: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      }}
    >
      {/* Background layer (slower movement) */}
      {type === "video" ? (
        <Video muted={muted} src={src} style={backgroundStyle} />
      ) : (
        <Img src={src} style={backgroundStyle} />
      )}

      {/* Foreground layer (faster movement) */}
      {type === "video" ? (
        <Video muted={muted} src={src} style={mediaStyle} />
      ) : (
        <Img src={src} style={mediaStyle} />
      )}
    </div>
  );
};
