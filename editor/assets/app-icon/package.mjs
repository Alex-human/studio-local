// Package pre-scaled PNG representations without changing their image data.
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
const [source, output] = process.argv.slice(2);
if (!source || !output) throw new Error('Usage: node package.mjs <iconset> <output.icns>');
const representations = [
  ['icp4', '16x16'], ['icp5', '32x32'], ['ic07', '128x128'],
  ['ic08', '256x256'], ['ic09', '512x512'],
  ['ic11', '16x16@2x'], ['ic12', '32x32@2x'], ['ic13', '128x128@2x'],
  ['ic14', '256x256@2x'], ['ic10', '512x512@2x'],
];
const blocks = representations.map(([type, name]) => {
  const png = readFileSync(resolve(source, `icon_${name}.png`));
  if (!png.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) throw new Error('Not PNG');
  const block = Buffer.alloc(8 + png.length);
  block.write(type); block.writeUInt32BE(block.length,4); png.copy(block,8);
  return block;
});
const header = Buffer.alloc(8);
header.write('icns'); header.writeUInt32BE(8 + blocks.reduce((n,b)=>n+b.length,0),4);
writeFileSync(output,Buffer.concat([header,...blocks]));
