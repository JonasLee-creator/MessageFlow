import assert from 'node:assert/strict';
import {canvasOrigin,syncCanvas} from './api/canvas.mjs';
assert.equal(canvasOrigin('https://school.example/'),'https://school.example');
assert.throws(()=>canvasOrigin('http://school.example'));
const imported=await syncCanvas({consent:true,baseUrl:'https://school.example',token:'sample-token'},async url=>({rows:url.pathname.endsWith('/courses')?[{id:1,name:'课程'}]:[{id:2,name:'作业',due_at:'2026-10-20T10:00:00Z'}],link:''}));
assert.equal(imported.items.length,1);assert.equal(imported.items[0].title,'作业');
await assert.rejects(()=>syncCanvas({consent:true,baseUrl:'https://school.example',token:'sample-token'},async()=>({rows:[],link:'<https://other.example/page>; rel="next"'})),/跨站/);
console.log('Passed: Canvas origin, import and cross-origin pagination checks.');
