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
import {ArrowRight, Sparkles, icons} from 'lucide-react';
import type {LucideIcon} from 'lucide-react';

export type Keyword = {
  term: string;
  icon?: string | null;
};

export type Scene = {
  title: string;
  bullets: string[];
  keywords?: Keyword[];
  layout?: string;
  visual?: string;
  assumption?: string | null;
  audio: string;
  durationInFrames: number;
};

export type VideoProps = {
  fps?: number;
  scenes: Scene[];
};

// Substring -> lucide icon name. LLM-suggested icon names take priority;
// this map and the Sparkles fallback keep unknown keywords consistent —
// the same term always renders the same icon, in every scene and video.
const KEYWORD_ICONS: Record<string, string> = {
  dna: 'Dna',
  rna: 'Dna',
  gene: 'Dna',
  protein: 'Hexagon',
  ribosome: 'Hexagon',
  enzyme: 'FlaskConical',
  cell: 'Microscope',
  neuron: 'Brain',
  synapse: 'Brain',
  atom: 'Atom',
  molecule: 'Atom',
  electron: 'Zap',
  derivative: 'Sigma',
  integral: 'Sigma',
  limit: 'TrendingUp',
  vector: 'MoveDiagonal',
  matrix: 'LayoutGrid',
  algorithm: 'Code',
  network: 'Network',
  circuit: 'Cpu',
  wave: 'Waves',
  force: 'Magnet',
  orbit: 'Globe',
  reaction: 'FlaskConical',
  probability: 'Dices',
};

function iconFor(keyword: Keyword): LucideIcon {
  if (keyword.icon) {
    const suggested = icons[keyword.icon as keyof typeof icons];
    if (suggested) return suggested as LucideIcon;
  }
  const term = keyword.term.toLowerCase();
  for (const [match, name] of Object.entries(KEYWORD_ICONS)) {
    if (term.includes(match)) {
      const icon = icons[name as keyof typeof icons];
      if (icon) return icon as LucideIcon;
    }
  }
  return Sparkles;
}

// Deterministic accent per keyword — same term gets the same hue across
// scenes and across videos, which is our visual-motif continuity.
function accent(term: string): string {
  let hash = 0;
  for (const ch of term) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 60% 65%)`;
}

const enter = (frame: number, fps: number, delay = 0) =>
  spring({
    frame: frame - delay,
    fps,
    config: {damping: 16, stiffness: 120, mass: 0.9},
  });

const KeywordChip: React.FC<{keyword: Keyword; delay: number}> = ({
  keyword,
  delay,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = enter(frame, fps, delay);
  const Icon = iconFor(keyword);
  const color = accent(keyword.term);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 22px',
        borderRadius: 999,
        border: `2px solid ${color}`,
        color,
        fontSize: 30,
        fontWeight: 600,
        opacity: progress,
        transform: `scale(${0.7 + 0.3 * progress})`,
      }}
    >
      <Icon size={30} />
      {keyword.term}
    </span>
  );
};

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

const ChipRow: React.FC<{keywords: Keyword[]; flow: boolean}> = ({
  keywords,
  flow,
}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 18,
      flexWrap: 'wrap',
      marginBottom: 40,
    }}
  >
    {keywords.map((keyword, i) => (
      <React.Fragment key={keyword.term}>
        {flow && i > 0 && <ArrowRight size={34} color="#8a8378" />}
        <KeywordChip keyword={keyword} delay={6 + i * 6} />
      </React.Fragment>
    ))}
  </div>
);

const SceneCard: React.FC<{scene: Scene; index: number; total: number}> = ({
  scene,
  index,
  total,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const keywords = scene.keywords ?? [];
  const layout = scene.layout ?? 'definition';
  const cardIn = enter(frame, fps);
  const exit = interpolate(
    frame,
    [scene.durationInFrames - 12, scene.durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const centered = layout === 'recap';
  return (
    <AbsoluteFill
      style={{
        padding: 96,
        justifyContent: 'center',
        alignItems: centered ? 'center' : 'flex-start',
        textAlign: centered ? 'center' : 'left',
        opacity: cardIn * exit,
        transform: `translateY(${(1 - cardIn) * 24}px) scale(${0.98 + 0.02 * cardIn})`,
      }}
    >
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
      <h1
        style={{
          fontSize: layout === 'definition' ? 88 : 72,
          fontWeight: 700,
          marginBottom: 48,
        }}
      >
        {scene.title}
      </h1>
      <ChipRow keywords={keywords} flow={layout === 'process'} />
      <Bullets bullets={scene.bullets} startDelay={14} />
      {scene.assumption && (
        <div
          style={{
            position: 'absolute',
            bottom: 56,
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
            <SceneCard scene={scene} index={i} total={scenes.length} />
            <Audio src={staticFile(scene.audio)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
