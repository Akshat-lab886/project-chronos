/**
 * Project Chronos — Map Visualizer Component
 *
 * Implements animated cartographic visualizations:
 * - Smooth camera pan and zoom across geographic coordinates
 * - Glowing route lines connecting locations
 * - Location pins with labels
 * - Coordinate-based path drawing animation
 *
 * Uses SVG for crisp, resolution-independent rendering.
 */

import React, { useMemo } from "react";
import { interpolate, useCurrentFrame } from "remotion";
import type { OverlaySpec, OverlayType } from "../types/schema";

export interface MapVisualizerProps {
  /** Overlay spec containing map data (coordinates, zoom level) */
  overlaySpec: OverlaySpec;
  /** Scene duration in frames */
  durationInFrames: number;
  /** Scene start frame */
  startFrame?: number;
  /** Map style: dark, light, satellite */
  mapStyle?: "dark" | "light" | "satellite";
  /** Whether to show route line animation */
  animateRoute?: boolean;
}

interface Coordinate {
  lat: number;
  lng: number;
  name?: string;
  timestamp?: string;
}

interface MapPath {
  coordinates: Coordinate[];
  distanceKm?: number;
  duration?: string;
}

/**
 * Convert geographic coordinates to SVG pixel coordinates.
 * Uses a simple equirectangular projection.
 */
function latLngToPixel(
  lat: number,
  lng: number,
  width: number,
  height: number
): { x: number; y: number } {
  const x = ((lng + 180) / 360) * width;
  const y = ((90 - lat) / 180) * height;
  return { x, y };
}

/**
 * Calculate distance between two coordinates in kilometers.
 */
function calculateDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371; // Earth radius in km
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lng2 - lng1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Smooth easing function for camera movements (ease-in-out cubic).
 */
function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * MapVisualizer — Animated map with route line drawer and camera pan.
 */
export const MapVisualizer: React.FC<MapVisualizerProps> = ({
  overlaySpec,
  durationInFrames,
  startFrame = 0,
  mapStyle = "dark",
  animateRoute = true,
}) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - startFrame;
  const progress = Math.max(0, Math.min(1, relativeFrame / Math.max(1, durationInFrames)));

  // SVG dimensions
  const svgWidth = 1920;
  const svgHeight = 1080;
  const padding = 100; // Map padding

  // Extract coordinates from overlay data
  const coordinates: Coordinate[] = useMemo(() => {
    const data = overlaySpec.data as Record<string, unknown>;
    const coords = data["coordinates"] as any[] | undefined;

    if (!coords || !Array.isArray(coords)) return [];

    return coords.map((c: any) => ({
      lat: c.lat || c[0],
      lng: c.lng || c[1],
      name: c.name,
      timestamp: c.timestamp,
    })).filter(c => c.lat !== undefined && c.lng !== undefined);
  }, [overlaySpec.data]);

  // Determine map bounds
  const mapBounds = useMemo(() => {
    if (coordinates.length === 0) {
      return { minLat: -85, maxLat: 85, minLng: -180, maxLng: 180 };
    }

    let minLat = Infinity, maxLat = -Infinity;
    let minLng = Infinity, maxLng = -180;

    for (const coord of coordinates) {
      minLat = Math.min(minLat, coord.lat);
      maxLat = Math.max(maxLat, coord.lat);
      minLng = Math.min(minLng, coord.lng);
      maxLng = Math.max(maxLng, coord.lng);
    }

    // Add padding
    const latRange = maxLat - minLat;
    const lngRange = maxLng - minLng;
    return {
      minLat: minLat - latRange * 0.1,
      maxLat: maxLat + latRange * 0.1,
      minLng: minLng - lngRange * 0.1,
      maxLng: maxLng + lngRange * 0.1,
    };
  }, [coordinates]);

  // Convert coordinates to pixel positions
  const pixelCoords = useMemo(() => {
    const mapWidth = svgWidth - padding * 2;
    const mapHeight = svgHeight - padding * 2;

    return coordinates.map(coord => {
      const x = padding + ((coord.lng - mapBounds.minLng) / (mapBounds.maxLng - mapBounds.minLng)) * mapWidth;
      const y = padding + ((mapBounds.maxLat - coord.lat) / (mapBounds.maxLat - mapBounds.minLat)) * mapHeight;
      return { ...coord, x, y };
    });
  }, [coordinates, mapBounds]);

  // Calculate path length for animation
  const pathLength = useMemo(() => {
    if (pixelCoords.length < 2) return 0;
    let totalLength = 0;
    for (let i = 1; i < pixelCoords.length; i++) {
      const dx = pixelCoords[i].x - pixelCoords[i - 1].x;
      const dy = pixelCoords[i].y - pixelCoords[i - 1].y;
      totalLength += Math.sqrt(dx * dx + dy * dy);
    }
    return totalLength;
  }, [pixelCoords]);

  // Camera pan/zoom
  const cameraScale = interpolate(progress, [0, 1], [1.0, 1.1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cameraOffsetX = interpolate(progress, [0, 1], [0, 20], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cameraOffsetY = interpolate(progress, [0, 1], [0, -15], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Route animation progress
  const routeProgress = animateRoute
    ? interpolate(progress, [0, 0.8], [0, 1], { extrapolateRight: "clamp" })
    : 1;

  // Map background colors
  const mapBgColors = {
    dark: "linear-gradient(135deg, #0a0a1a 0%, #151525 50%, #0a0a1a 100%)",
    light: "linear-gradient(135deg, #f0f0f0 0%, #e0e0e0 50%, #f0f0f0 100%)",
    satellite: "linear-gradient(135deg, #1a3d1a 0%, #2d5a2d 50%, #1a3d1a 100%)",
  };

  // Grid color
  const gridColor = mapStyle === "dark" ? "rgba(100, 200, 255, 0.1)" : "rgba(100, 100, 100, 0.2)";

  // Pin colors
  const pinColors = coordinates.map((_, i) =>
    i === 0 ? "#00FFFF" : i === coordinates.length - 1 ? "#FF1493" : "#FFD700"
  );

  return (
    <div
      style={{
        position: "absolute" as const,
        inset: 0,
        background: mapBgColors[mapStyle],
        overflow: "hidden",
        transform: `scale(${cameraScale}) translate(${cameraOffsetX}px, ${cameraOffsetY}px)`,
        transformOrigin: "center",
      }}
    >
      <svg
        width={svgWidth}
        height={svgHeight}
        style={{ position: "absolute", inset: 0 }}
      >
        {/* Grid lines */}
        <defs>
          <pattern id="mapGrid" width={80} height={80} patternUnits="userSpaceOnUse">
            <path
              d={`M 80 0 L 0 0 0 80`}
              fill="none"
              stroke={gridColor}
              strokeWidth={1}
            />
          </pattern>
          {/* Glow filter for route line */}
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background grid */}
        <rect width="100%" height="100%" fill="url(#mapGrid)" />

        {/* Route line (animated) */}
        {pixelCoords.length > 1 && (
          <>
            {/* Full path (dim) */}
            <polyline
              points={pixelCoords.map(p => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke={gridColor}
              strokeWidth={2}
              opacity={0.4}
            />

            {/* Animated path (glowing) */}
            {animateRoute && (
              <svg
                style={{
                  position: "absolute",
                  inset: 0,
                  overflow: "hidden",
                }}
              >
                <polyline
                  points={pixelCoords.map(p => `${p.x},${p.y}`).join(" ")}
                  fill="none"
                  stroke="#00FFFF"
                  strokeWidth={4}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray={pathLength}
                  strokeDashoffset={pathLength * (1 - routeProgress)}
                  filter="url(#glow)"
                  style={{ transition: "stroke-dashoffset 0.1s linear" }}
                />
              </svg>
            )}
          </>
        )}

        {/* Location pins */}
        {pixelCoords.map((coord, i) => (
          <g key={`pin-${i}`}>
            {/* Pin circle */}
            <circle
              cx={coord.x}
              cy={coord.y}
              r={8}
              fill={pinColors[i]}
              stroke="#FFFFFF"
              strokeWidth={2}
              style={{
                filter: "url(#glow)",
                animation: `pulse 2s infinite`,
              }}
            />
            {/* Pin label */}
            {coord.name && (
              <text
                x={coord.x}
                y={coord.y - 20}
                textAnchor="middle"
                fill={mapStyle === "dark" ? "#FFFFFF" : "#333333"}
                fontSize={16}
                fontWeight={600}
                style={{
                  textShadow: "0 2px 4px rgba(0, 0, 0, 0.5)",
                }}
              >
                {coord.name}
              </text>
            )}
          </g>
        ))}
      </svg>

      {/* Distance counter */}
      {coordinates.length > 1 && (
        <div
          style={{
            position: "absolute" as const,
            bottom: 40,
            right: 40,
            backgroundColor: "rgba(0, 0, 0, 0.6)",
            padding: "12px 24px",
            borderRadius: 8,
            fontFamily: "monospace",
            fontSize: 24,
            fontWeight: 600,
            color: "#00FFFF",
            textShadow: "0 0 10px #00FFFF",
          }}
        >
          {(() => {
            let totalDist = 0;
            for (let i = 1; i < coordinates.length; i++) {
              totalDist += calculateDistance(
                coordinates[i - 1].lat, coordinates[i - 1].lng,
                coordinates[i].lat, coordinates[i].lng
              );
            }
            return `${totalDist.toFixed(0)} km traveled`;
          })()}
        </div>
      )}
    </div>
  );
};
