/**
 * Project Chronos - Remotion Root
 *
 * Composition registry for documentary rendering.
 * The manifest is passed as props to the DocumentaryMaster composition
 * via the --props CLI argument.
 */

import { Composition, CalculateMetadataFunction } from "remotion";
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

// Calculate metadata dynamically based on the runtime props
const calculateMetadata: CalculateMetadataFunction<{
  manifest?: ProjectChronosManifest;
}> = ({ props }) => {
  const manifest = props.manifest || FALLBACK_MANIFEST;
  return {
    durationInFrames: manifest.metadata.total_frames,
    fps: manifest.metadata.fps,
    width: manifest.metadata.width,
    height: manifest.metadata.height,
  };
};

export const RemotionRoot: React.FC<{ manifest?: ProjectChronosManifest }> = () => {
  return (
    <Composition
      id="DocumentaryMaster"
      component={DocumentaryMaster as React.FC<any>}
      durationInFrames={FALLBACK_MANIFEST.metadata.total_frames}
      fps={FALLBACK_MANIFEST.metadata.fps}
      width={FALLBACK_MANIFEST.metadata.width}
      height={FALLBACK_MANIFEST.metadata.height}
      defaultProps={{
        manifest: FALLBACK_MANIFEST,
      }}
      calculateMetadata={calculateMetadata}
    />
  );
};
