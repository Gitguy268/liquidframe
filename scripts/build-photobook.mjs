// Build the separately licensed companion, retaining its complete source offer.
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../companions/photobook/', import.meta.url));
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const run = args => { const result = spawnSync(npm, args, {cwd:root, stdio:'inherit', shell:process.platform === 'win32', env:{...process.env,NEXT_TELEMETRY_DISABLED:'1'}}); if (result.error) throw result.error; if(result.status !== 0) process.exit(result.status || 1); };
const lock = createHash('sha256').update(readFileSync(path.join(root,'package-lock.json'))).digest('hex');
const marker = path.join(root,'node_modules','.liquidframe-lock');
if (!existsSync(marker) || readFileSync(marker,'utf8') !== lock) { run(['ci','--ignore-scripts','--no-audit','--no-fund']); writeFileSync(marker,lock); }
run(['run','build']);
const hashes = new Set();
function scan(folder) { for (const entry of readdirSync(folder)) { const file=path.join(folder,entry); if(statSync(file).isDirectory()) scan(file); else if(file.endsWith('.html')) { for(const match of readFileSync(file,'utf8').matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) { if(!/\bsrc=/.test(match[1])) hashes.add(createHash('sha256').update(match[2]).digest('base64')); } } } }
scan(path.join(root,'out'));
writeFileSync(path.join(root,'out','csp.json'),JSON.stringify([...hashes]));
const {default:JSZip} = await import(path.join(root,'node_modules/jszip/lib/index.js'));
const zip = new JSZip();
const ignored = new Set(['node_modules','.next','out','.git','next-env.d.ts']);
function source(folder, prefix='') { for (const entry of readdirSync(folder)) { if(ignored.has(entry) || entry.endsWith('.tsbuildinfo')) continue; const file=path.join(folder,entry), relative=prefix+entry; if(statSync(file).isDirectory()) source(file,relative+'/'); else zip.file('photobook/'+relative,readFileSync(file)); } }
source(root);
zip.file('build-photobook.mjs',readFileSync(fileURLToPath(import.meta.url)));
zip.file('BUILD.txt','Source for the installed Ente Photobook companion (AGPL-3.0). See photobook/LIQUIDFRAME.md. To rebuild with Node.js 22+: cd photobook; npm ci --ignore-scripts; npm run build. The LiquidFrame repository keeps this folder at companions/photobook and the supplied build script at scripts/build-photobook.mjs.');
writeFileSync(path.join(root,'out','source.zip'),await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));
console.log('Photobook built with local assets, CSP script hashes and corresponding source.');
