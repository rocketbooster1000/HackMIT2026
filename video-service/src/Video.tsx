import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type Scene = {
  title: string;
  bullets: string[];
  markup?: string;
  assumption?: string | null;
  audio: string;
  durationInFrames: number;
};

export type VideoProps = {
  fps?: number;
  scenes: Scene[];
};

const enter = (frame: number, fps: number, delay = 0) =>
  spring({
    frame: frame - delay,
    fps,
    config: {damping: 16, stiffness: 120, mass: 0.9},
  });

const Bullets: React.FC<{bullets: string[]; startDelay: number}> = ({
  bullets,
  startDelay,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <ul style={{listStyle: 'none', padding: 0, margin: 0}}>
      {bullets.map((bullet, i) => {
        const progress = enter(frame, fps, startDelay + i * 10);
        return (
          <li
            key={i}
            style={{
              fontSize: 44,
              lineHeight: 1.4,
              marginBottom: 24,
              color: '#cfc8bd',
              opacity: progress,
              transform: `translateY(${(1 - progress) * 18}px)`,
            }}
          >
            {bullet}
          </li>
        );
      })}
    </ul>
  );
};

const SceneCard: React.FC<{scene: Scene; index: number; total: number}> = ({
  scene,
  index,
  total,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const cardIn = enter(frame, fps);
  const exit = interpolate(
    frame,
    [scene.durationInFrames - 12, scene.durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const fade = {
    opacity: cardIn * exit,
    transform: `translateY(${(1 - cardIn) * 24}px) scale(${0.98 + 0.02 * cardIn})`,
  };
  return (
    <>
      {scene.markup ? (
        // The LLM owns the whole frame — sanitized server-side.
        <div
          style={{position: 'absolute', inset: 0, ...fade}}
          dangerouslySetInnerHTML={{__html: scene.markup}}
        />
      ) : (
        // Fallback when the model returned no markup.
        <AbsoluteFill style={{padding: 96, justifyContent: 'center', ...fade}}>
          <div
            style={{
              position: 'absolute',
              top: 56,
              right: 96,
              fontSize: 24,
              letterSpacing: 6,
              color: '#8a8378',
            }}
          >
            {index + 1} / {total}
          </div>
          <h1 style={{fontSize: 72, fontWeight: 700, marginBottom: 24}}>
            {scene.title}
          </h1>
          <Bullets bullets={scene.bullets} startDelay={14} />
        </AbsoluteFill>
      )}
      {scene.assumption && (
        <div
          style={{
            position: 'absolute',
            bottom: 40,
            left: 96,
            right: 96,
            fontSize: 26,
            fontStyle: 'italic',
            color: '#8a8378',
          }}
        >
          Note — {scene.assumption}
        </div>
      )}
    </>
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
            <SceneCard scene={scene} index={i} total={scenes.length} />
            <Audio src={staticFile(scene.audio)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
