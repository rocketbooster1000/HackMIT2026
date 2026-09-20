// Render the "Video" composition to an mp4.
//   node render.mjs <props.json> <out.mp4>
// props shape: { fps?: number, scenes: [{ title, bullets: string[],
//   audio: "jobs/<id>/scene-N.mp3", durationInFrames }] }
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import {readFile, rm} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const [propsPath, outPath] = process.argv.slice(2);
if (!propsPath || !outPath) {
  console.error('usage: node render.mjs <props.json> <out.mp4>');
  process.exit(2);
}

const inputProps = JSON.parse(await readFile(propsPath, 'utf-8'));
const serveUrl = await bundle({
  entryPoint: path.join(root, 'src/index.ts'),
  publicDir: path.join(root, 'public'),
});
const composition = await selectComposition({
  serveUrl,
  id: 'Video',
  inputProps,
});
await rm(outPath, {force: true});
await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: path.resolve(outPath),
  inputProps,
});
console.log(`rendered ${outPath}`);
