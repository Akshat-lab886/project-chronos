/**
 * Project Chronos - Remotion Root
 *
 * Composition registry for documentary rendering.
 * The manifest is passed as props to the DocumentaryMaster composition
 * via the --props CLI argument.
 */

import { Composition } from "remotion";
import React from "react";
import { DocumentaryMaster } from "./compositions/DocumentaryMaster";
import type { ProjectChronosManifest } from "./types/schema";

const FALLBACK_MANIFEST: ProjectChronosManifest = {
  project_id: "dev-fallback",
  title: "Project Chronos - Development",
  metadata: {
    title: "Documentary",
    topic: "Development",
    width: 1920,
    height: 1080,
    fps: 60,
    total_duration_seconds: 480,
    total_frames: 28800,
    aspect_ratio: 16 / 9,
    created_at: new Date().toISOString(),
  },
  scenes: [],
  audio_tracks: [],
  sfx_triggers: [],
  version: "1.0.0",
} as ProjectChronosManifest;

export const RemotionRoot: React.FC<{ manifest?: ProjectChronosManifest }> = ({ manifest }) => {
  const effectiveManifest = manifest || FALLBACK_MANIFEST;
  return (
    <Composition
      id="DocumentaryMaster"
      component={DocumentaryMaster as React.FC<any>}
      durationInFrames={effectiveManifest.metadata.total_frames}
      fps={effectiveManifest.metadata.fps}
      width={effectiveManifest.metadata.width}
      height={effectiveManifest.metadata.height}
      defaultProps={{
        manifest: effectiveManifest,
      }}
    />
  );
};

export { DocumentaryMaster };
