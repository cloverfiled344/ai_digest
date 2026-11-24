import React from "react";
import { Composition, Still } from "remotion";
import { Video } from "./Video";
import { Thumb } from "./Thumb";
import { TL } from "./tl";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Video" component={Video} durationInFrames={Math.ceil(TL.total * 30)} fps={30} width={1080} height={1920} />
    <Still id="Thumb" component={Thumb} width={1080} height={1920} />
  </>
);
