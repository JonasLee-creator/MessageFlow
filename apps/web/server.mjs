import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createAiGateway } from './api/gateway.mjs';
const root = path.resolve(fileURLToPath(new URL('./dist/', import.meta.url)));
const types = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json; charset=utf-8'};
const handleAi = createAiGateway();
const server = http.createServer(async (req,res) => {
  try {
    if(await handleAi(req,res))return;
    const pathname = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    if(!file.startsWith(root + path.sep) && file !== path.join(root,'index.html')) {res.writeHead(403);res.end('Forbidden');return;}
    const body = await readFile(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(body);
  } catch {res.writeHead(404);res.end('Not found');}
});
const port=Number(process.env.PORT || 4173);
server.listen(port,process.env.HOST||'127.0.0.1',()=>console.log(`ChronoFlow: http://127.0.0.1:${port}`));
