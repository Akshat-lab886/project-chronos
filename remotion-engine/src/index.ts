/**
 * Project Chronos — Remotion Entry Point
 *
 * Registers all compositions with Remotion so they can be rendered
 * headlessly via the CLI:
 *   npx remotion render DocumentaryMaster ./workspace/output/master.mp4
 */

import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
