/**
 * MasterFilmGrade.tsx
 *
 * Post-processing shader applied as a global overlay on all visual layers.
 * Implements:
 *   1. 2.35:1 letterbox bars for cinematic aspect ratio
 *   2. Radial vignette for focus guidance
 *   3. Animated film grain texture overlay
 */

import React from "react";
import { interpolate, useCurrentFrame, staticFile } from "remotion";
import { GRAIN_ANIM_DURATION } from "./styles";

export interface MasterFilmGradeProps {
  /** Film grade specification (LUT, vignette, grain) */
  lut?: "teal-orange" | "noir" | "vintage" | "desaturated" | "neutral";
  /** Vignette strength (0.0 to 1.0) */
  vignetteStrength?: number;
  /** Film grain opacity (0.0 to 1.0) */
  grainOpacity?: number;
  /** Whether to show letterbox bars */
  letterbox?: boolean;
  /** Letterbox ratio (e.g., "2.35:1") */
  letterboxRatio?: string;
  /** Z-index for layering */
  zIndex?: number;
}

const LUT_COLORS: Record<string, { tint: string; contrast: number; saturation: number }> = {
  "teal-orange": { tint: "sepia(0.3) hue-rotate(-15deg) saturate(1.3) contrast(1.1)", contrast: 1.1, saturation: 1.05 },
  "noir": { tint: "grayscale(1) contrast(1.3) brightness(0.9)", contrast: 1.3, saturation: 1.0 },
  "vintage": { tint: "sepia(0.4) hue-rotate(-10deg) brightness(0.95) contrast(1.05)", contrast: 1.05, saturation: 0.9 },
  "desaturated": { tint: "saturate(0.7) contrast(1.15) brightness(1.05)", contrast: 1.15, saturation: 0.7 },
  "neutral": { tint: "none", contrast: 1.0, saturation: 1.0 },
};

export const MasterFilmGrade: React.FC<MasterFilmGradeProps> = ({
  lut = "neutral",
  vignetteStrength = 0.45,
  grainOpacity = 0.07,
  letterbox = true,
  letterboxRatio = "2.35:1",
  zIndex = 40,
}) => {
  const frame = useCurrentFrame();
  const grainShift = interpolate(
    frame % GRAIN_ANIM_DURATION,
    [0, GRAIN_ANIM_DURATION],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const lutStyle = LUT_COLORS[lut] ?? LUT_COLORS["neutral"];

  // Calculate letterbox bar height (2.35:1 on 16:9 = ~12.5% top + bottom)
  const [, ratio] = letterboxRatio.split(":").map(Number);
  const aspect = 2.35;
  const barHeight = Math.round((1080 - 1080 / aspect) / 2);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        zIndex,
        overflow: "hidden",
      }}
    >
      {/* Film grade filter (color grading) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          filter: lutStyle.tint,
          backgroundColor: "rgba(0, 0, 0, 0.02)",
        }}
      />

      {/* 1. 2.35:1 Letterbox Bars */}
      {letterbox && (
        <>
          <div
            className="absolute left-0 w-full bg-black"
            style={{ height: barHeight, top: 0 }}
          />
          <div
            className="absolute left-0 w-full bg-black"
            style={{ height: barHeight, bottom: 0 }}
          />
        </>
      )}

      {/* 2. Radial Vignette */}
      <div
        className="absolute inset-0 bg-black"
        style={{
          background: `radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,${vignetteStrength + 0.1}) 100%)`,
        }}
      />

      {/* 3. Animated Film Grain */}
      <div
        className="absolute inset-0 opacity-[0.07] mix-blend-overlay pointer-events-none"
        style={{
          backgroundImage: `url('${staticFile("textures/film-grain.png")}')`,
          backgroundSize: "200% 200%",
          backgroundPosition: `${grainShift * 100}% ${grainShift * 100}%`,
          opacity: grainOpacity,
        }}
      />
    </div>
  );
};
