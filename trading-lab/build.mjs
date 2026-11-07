import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
const engine=(await readFile('worker/engine.mjs','utf8')).replaceAll('export ','');
const page=(await readFile('worker/page.mjs','utf8')).replace('export ','');
const worker=(await readFile('worker/index.mjs','utf8')).replace(/^import .*;\n/gm,'');
await mkdir('dist/server',{recursive:true});await mkdir('dist/.openai',{recursive:true});
await writeFile('dist/server/index.js',engine+'\n'+page+'\n'+worker);
try { await copyFile('.openai/hosting.json','dist/.openai/hosting.json'); } catch (error) { if(error.code!=='ENOENT')throw error; console.log('Fuente de investigación: sin identidad de hosting.'); }
console.log('Worker construido sin dependencias.');
