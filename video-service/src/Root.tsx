import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import {Video, VideoProps} from './Video';

const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({props}) => ({
  durationInFrames: Math.max(
    1,
    props.scenes.reduce((sum, scene) => sum + scene.durationInFrames, 0),
  ),
  fps: props.fps ?? 30,
});

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Video"
    component={Video}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={30}
    defaultProps={{fps: 30, scenes: []}}
    calculateMetadata={calculateMetadata}
  />
);
