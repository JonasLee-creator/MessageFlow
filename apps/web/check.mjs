import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("document.addEventListener('click'")[0];
const RealDate=Date;
class Clock extends RealDate {constructor(...a){super(...(a.length?a:['2026-10-12T08:00:00+08:00']));}static now(){return new Clock().getTime();}}
const storage=new Map();
const ctx=vm.createContext({Date:Clock,Intl,crypto:{randomUUID},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},console});
vm.runInContext(source,ctx);
function run(code){return vm.runInContext(code,ctx);}
const originalLocked=run("JSON.stringify(state.blocks.filter(b=>b.locked))");
run('plan()');
assert.equal(run("JSON.stringify(state.blocks.filter(b=>b.locked))"),originalLocked,'Locked blocks must remain unchanged');
run(`for(const b of state.blocks){
  const t=state.tasks.find(t=>t.id===b.taskId);
  if(t.deadline&&new Date(b.end)>new Date(t.deadline))throw Error('Deadline exceeded');
  if(state.events.some(e=>overlaps(new Date(b.start),new Date(b.end),e)))throw Error('Event conflict');
  if(state.blocks.some(x=>x.id!==b.id&&overlaps(new Date(b.start),new Date(b.end),x)))throw Error('Block conflict');
}
for(const t of active()){
  const allocated=state.blocks.filter(b=>b.taskId===t.id).reduce((s,b)=>s+(new Date(b.end)-new Date(b.start))/60000,0);
  if(allocated!==Math.ceil(t.remaining/30)*30)throw Error('Duplicated or missing workload');
}`);
assert.equal(run('state.risks.length'),0);
run("state.tasks=[{id:'impossible',title:'时间不足',remaining:120,minutes:120,deadline:at(new Date(),8),done:false}];state.blocks=[];state.events=[];plan();");
assert.equal(run('state.blocks.length'),0,'Must not invent slots after deadline');
assert.equal(run('state.risks[0].minutes'),120,'Must report unallocated workload');
assert.equal(run("parseNotice('明天18:00前提交报告，预计2小时','课程').minutes"),120);
assert.ok(run("parseNotice('明天18:00前提交报告','课程').deadline"));
assert.equal(run("parseNotice('2026-02-30 18:00提交','').deadline"),null,'Invalid calendar date');
assert.equal(run("parseNotice('明天3点交报告','').deadline"),null,'Ambiguous AM/PM needs review');
assert.ok(run("parseNotice('明天下午3点交报告','').deadline"));
assert.equal(run('calendarRange().end'),22,'Evening slots must remain visible');
console.log('Passed: scheduling conflicts, deadline, locked blocks, workload, gaps, date parsing, calendar range.');
