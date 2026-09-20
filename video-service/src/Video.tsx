import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from 'remotion';

export type Scene = {
  title: string;
  bullets: string[];
  audio: string;
  durationInFrames: number;
};

export type VideoProps = {
  fps?: number;
  scenes: Scene[];
};

const SceneCard: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        padding: 96,
        justifyContent: 'center',
        opacity,
      }}
    >
      <h1 style={{fontSize: 72, fontWeight: 700, marginBottom: 48}}>
        {scene.title}
      </h1>
      <ul style={{listStyle: 'none', padding: 0, margin: 0}}>
        {scene.bullets.map((bullet, i) => (
          <li
            key={i}
            style={{
              fontSize: 44,
              lineHeight: 1.4,
              marginBottom: 24,
              color: '#cfc8bd',
            }}
          >
            {bullet}
          </li>
        ))}
      </ul>
    </AbsoluteFill>
  );
};

export const Video: React.FC<VideoProps> = ({scenes}) => {
  let offset = 0;
  return (
    <AbsoluteFill
      style={{
        background: '#16161a',
        color: '#f5f1ea',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      {scenes.map((scene, i) => {
        const start = offset;
        offset += scene.durationInFrames;
        return (
          <Sequence
            key={i}
            from={start}
            durationInFrames={scene.durationInFrames}
          >
            <SceneCard scene={scene} />
            <Audio src={staticFile(scene.audio)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
