/**
 * Project Chronos — Headless Render Entry Point
 *
 * This entry point loads a manifest JSON from the public folder
 * and renders the DocumentaryMaster composition with real data.
 *
 * Usage:
 *   npx remotion render DocumentaryMaster --frames=0-100 --quality=high \
 *     --public-dir=./public \
 *     --props='{"manifestPath": "manifest.json"}'
 */

import { Composition } from "remotion";
import React from "react";
import { DocumentaryMaster } from "./compositions/DocumentaryMaster";
import type { ProjectChronosManifest } from "./types/schema";

// Load manifest from public folder (copied by the Python pipeline)
function loadManifest(): ProjectChronosManifest {
  const manifestPath = process.env.CHRONOS_MANIFEST_PATH || "/manifest.json";
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require("fs");
    const data = fs.readFileSync(manifestPath, "utf-8");
    return JSON.parse(data) as ProjectChronosManifest;
  } catch (e) {
    console.warn("Could not load manifest from", manifestPath, e);
    // Build a minimal manifest from environment variables
    const fps = parseInt(process.env.CHRONOS_FPS || "60");
    const duration = parseInt(process.env.CHRONOS_DURATION || "28800");
    return {
      project_id: "render-fallback",
      title: "Project Chronos Render",
      metadata: {
        title: "Project Chronos Render",
        topic: process.env.CHRONOS_TOPIC || "Documentary",
        width: 1920,
        height: 1080,
        fps: fps,
        total_duration_seconds: duration / fps,
        total_frames: duration,
        aspect_ratio: 16 / 9,
        created_at: new Date().toISOString(),
      },
      scenes: [],
      audio_tracks: [],
      sfx_triggers: [],
      version: "1.0.0",
    } as ProjectChronosManifest;
  }
}

const manifest = loadManifest();

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="DocumentaryMaster"
      component={DocumentaryMaster as React.FC<any>}
      durationInFrames={manifest.metadata.total_frames}
      fps={manifest.metadata.fps}
      width={manifest.metadata.width}
      height={manifest.metadata.height}
      defaultProps={{
        manifest: manifest,
      }}
    />
  );
};

// Also export for static usage
export { DocumentaryMaster };
