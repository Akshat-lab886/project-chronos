import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(90);
Config.setConcurrency(4);
Config.setOutputLocation("./workspace/output/master.mp4");
Config.setOverwriteOutput(true);
