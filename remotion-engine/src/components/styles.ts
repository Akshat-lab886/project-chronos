/**
 * Project Chronos — Shared Style Constants
 *
 * Centralized style definitions for consistent visual appearance
 * across all Remotion components.
 */

export const MotionStyle = {
  // Easing functions matching documentary pacing
  easeOutCubic: "cubic-bezier(0.21, 0.64, 0.92, 0.78)",
  easeInOutQuad: "cubic-bezier(0.45, 0, 0.55, 1)",
  springStiff: "cubic-bezier(0.17, 0.67, 0.37, 1.22)",

  // Color palette
  colors: {
    primary: "#00FFFF",      // Cyan accent
    secondary: "#FFD700",    // Gold highlight
    background: "#050505",   // Dark background
    text: "#FFFFFF",         // Primary text
    textDim: "#CCCCCC",      // Dimmed text
    textHighlight: "#B8860B", // Dark gold
  },

  // Typography
  fonts: {
    heading: "Inter, system-ui, sans-serif",
    body: "Inter, system-ui, sans-serif",
    monospace: "Fira Code, monospace",
  },

  // Shadow presets
  shadows: {
    text: "0 2px 4px rgba(0, 0, 0, 0.8), 0 0 8px rgba(0, 0, 0, 0.6)",
    glowCyan: "0 0 10px #00FFFF, 0 0 20px rgba(0, 255, 255, 0.8)",
    glowGold: "0 0 10px #FFD700, 0 0 20px rgba(255, 215, 0, 0.8)",
  },
};

// Animation constants
export const GRAIN_ANIM_DURATION = 48; // frames (0.8s at 60fps)
export const PIN_GLOW_PULSE = 30; // frames
export const CAPTION_FADE = 15; // frames for fade in/out

export default MotionStyle;
