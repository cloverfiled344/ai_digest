import React from "react";
import { Shell } from "./frame";
import { buildScenes } from "./scam";

const { scenes, hide } = buildScenes();
export const Video: React.FC = () => <Shell scenes={scenes} hideCaptions={hide} captionTop={1300} captionSize={72} maxChars={16} />;
