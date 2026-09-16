/**
 * Project Chronos — Film Grade Component
 *
 * Applies cinematic post-processing effects:
 * - LUT-based color grading (teal-orange, noir, vintage, etc.)
 * - Subtle film grain overlay (procedural noise texture)
 * - Vignette effect (darkened corners)
 * - Letterboxing support (2.35:1, 16:9, 2.39:1)
 *
 * This component renders as a full-screen overlay that can be composed
 * on top of all visual layers.
 */

import React, { useMemo } from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { SceneSpec } from "../types/schema";

export type FilmGradePreset = "teal-orange" | "noir" | "vintage" | "desaturated" | "neutral";

export interface FilmGradeProps {
  /** LUT color grade preset */
  lut?: FilmGradePreset;
  /** Film grain opacity (0.0 to 1.0) */
  filmGrainOpacity?: number;
  /** Vignette intensity (0.0 to 1.0) */
  vignetteIntensity?: number;
  /** Aspect ratio letterboxing */
  aspectRatio?: "16:9" | "2.35:1" | "2.39:1" | "4:3";
  /** Whether to apply a slight chromatic aberration */
  chromaticAberration?: boolean;
  /** Optional scene info for dynamic grading */
  scene?: SceneSpec;
  /** Override z-index */
  zIndex?: number;
}

/**
 * CSS filter string generators for each LUT preset.
 * These use CSS filter functions to approximate cinematic color grades.
 */
const LUT_FILTERS: Record<FilmGradePreset, string> = {
  "teal-orange":
    "contrast(1.1) saturate(0.9) hue-rotate(-10deg) " +
    "contrast(0.95) brightness(1.05) " +
    "sepia(0.15) hue-rotate(-15deg) saturate(2.5) contrast(1.2)",
  noir: "contrast(1.3) saturate(0) brightness(1.1) contrast(1.2) sepia(0.3)",
  vintage:
    "sepia(0.35) saturate(0.7) hue-rotate(-5deg) " +
    "contrast(1.05) brightness(0.95) " +
    "sepia(0.2) hue-rotate(10deg) saturate(1.2)",
  desaturated: "saturate(0.5) contrast(1.15) brightness(1.05) sepia(0.1)",
  neutral: "contrast(1.05) saturate(1.0) brightness(1.0) sepia(0.05)",
};

/**
 * Generate a film grain texture as a data URI.
 * Uses a pseudo-random noise pattern encoded as SVG.
 */
function generateGrainTexture(opacity: number): string {
  // Generate SVG-based noise texture
  return `data:image/svg+xml;base64,${btoa(`
    <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
      <filter id="noiseFilter">
        <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/>
        <feColorMatrix type="saturate" values="0"/>
        <feComponentTransfer>
          <feFuncA type="linear" slope="${opacity * 0.5}"/>
        </feComponentTransfer>
      </filter>
      <rect width="100%" height="100%" filter="url(#noiseFilter)"/>
    </svg>
  `)}`;
}

/**
 * Calculate vignette gradient based on intensity.
 */
function getVignetteGradient(intensity: number): string {
  const stop = 0.3 + intensity * 0.5;
  return `radial-gradient(ellipse at center, transparent 0%, rgba(0, 0, 0, ${intensity}) ${stop}%, rgba(0, 0, 0, ${intensity * 1.3}) 100%)`;
}

/**
 * FilmGrade — Cinematic LUT color grade, vignette, and film grain overlay.
 */
export const FilmGrade: React.FC<FilmGradeProps> = ({
  lut = "teal-orange",
  filmGrainOpacity = 0.06,
  vignetteIntensity = 0.35,
  aspectRatio = "16:9",
  chromaticAberration = false,
  scene,
  zIndex = 10,
}) => {
  const frame = useCurrentFrame();

  // Subtle flickering grain (varies slightly per frame for realism)
  const grainOpacity = useMemo(() => {
    const base = filmGrainOpacity * 0.8;
    const variation = 1 + Math.sin(frame * 0.5) * 0.2;
    return base * variation;
  }, [frame, filmGrainOpacity]);

  // Dynamic vignette based on scene intensity
  const dynamicVignette = useMemo(() => {
    if (!scene) return vignetteIntensity;

    // Increase vignette during hook and climax acts
    const actType = scene.act_type;
    if (actType === "HOOK" || actType === "CLIMAX") {
      return vignetteIntensity * 1.3;
    }
    return vignetteIntensity;
  }, [scene, vignetteIntensity]);

  // Film grain texture URL
  const grainTexture = useMemo(
    () => generateGrainTexture(grainOpacity),
    [grainOpacity]
  );

  // Vignette gradient
  const vignetteGradient = useMemo(
    () => getVignetteGradient(dynamicVignette),
    [dynamicVignette]
  );

  // Letterboxing calculations
  const letterboxHeight = (() => {
    const ratios: Record<string, number> = {
      "16:9": 16 / 9,
      "4:3": 4 / 3,
      "2.35:1": 2.35,
      "2.39:1": 2.39,
    };
    const targetRatio = ratios[aspectRatio] || 16 / 9;
    const screenRatio = 1920 / 1080;
    if (targetRatio > screenRatio) {
      // Wider than screen — letterbox top/bottom
      const barHeight = ((targetRatio / screenRatio - 1) / 2) * 1080;
      return Math.max(0, barHeight);
    }
    return 0;
  })();

  // Chromatic aberration offset (if enabled)
  const caOffset = chromaticAberration ? interpolate(
    Math.sin(frame * 0.3),
    [-1, 1],
    [-0.5, 0.5],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  ) : 0;

  return (
    <>
      {/* Letterbox bars */}
      {letterboxHeight > 0 && (
        <>
          <div
            style={{
              position: "absolute" as const,
              top: 0,
              left: 0,
              right: 0,
              height: letterboxHeight,
              backgroundColor: "#000000",
              zIndex,
            }}
          />
          <div
            style={{
              position: "absolute" as const,
              bottom: 0,
              left: 0,
              right: 0,
              height: letterboxHeight,
              backgroundColor: "#000000",
              zIndex,
            }}
          />
        </>
      )}

      {/* LUT Color Grade Overlay */}
      <div
        style={{
          position: "absolute" as const,
          inset: 0,
          backgroundColor: "transparent",
          filter: LUT_FILTERS[lut],
          zIndex: zIndex + 1,
          pointerEvents: "none" as const,
          ...(chromaticAberration && {
            boxShadow: `${caOffset}px 0 ${caOffset * -1}px 0 rgba(255, 0, 0, 0.05),
                        ${caOffset * -1}px 0 ${caOffset}px 0 rgba(0, 255, 0, 0.03),
                        0 ${caOffset}px 0 rgba(0, 0, 255, 0.05)`,
          }),
        }}
      />

      {/* Vignette Overlay */}
      <div
        style={{
          position: "absolute" as const,
          inset: 0,
          background: vignetteGradient,
          zIndex: zIndex + 2,
          pointerEvents: "none" as const,
        }}
      />

      {/* Film Grain Overlay */}
      {grainOpacity > 0 && (
        <div
          style={{
            position: "absolute" as const,
            inset: 0,
            backgroundImage: `url(${grainTexture})`,
            backgroundSize: "200px 200px",
            opacity: grainOpacity,
            zIndex: zIndex + 3,
            pointerEvents: "none" as const,
            animation: "grain-anim 0.8s steps(10) infinite",
          }}
        />
      )}

    </>
  );
};
