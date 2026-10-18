import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("document.addEventListener('click'")[0];
const RealDate=Date;
class Clock extends RealDate {constructor(...a){super(...(a.length?a:['2026-10-12T08:00:00+08:00']));}static now(){return new Clock().getTime();}}
const storage=new Map();
const ctx=vm.createContext({Date:Clock,Intl,crypto:{randomUUID},ChronoApi:{setScope:()=>{}},ChronoAuth:{getSession:()=>({kind:'guest',username:'游客'})},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},console});
vm.runInContext(source,ctx);
function run(code){return vm.runInContext(code,ctx);}
assert.equal(run('state.tasks.length + state.events.length + state.notices.length + state.blocks.length'),0,'New workspace must start empty');
assert.ok(run("canvasPanel().includes('canvas-form')"));
assert.ok(!source.includes('ChronoPlanner') && !source.includes('runModelPlan'), 'Web must not invoke the trained planner');
run("state.tasks.push({id:'guest-task',title:'游客任务'});save();session={kind:'member',userId:'account-a',username:'甲'};loadWorkspace();");
assert.equal(run('state.tasks.length'),0,'Members must not inherit guest records');
run("state.tasks.push({id:'member-task',title:'账号甲的任务'});save();session={kind:'member',userId:'account-b',username:'乙'};loadWorkspace();");
assert.equal(run('state.tasks.length'),0,'Different accounts must have separate workspaces');
run("session={kind:'member',userId:'account-a',username:'甲'};loadWorkspace();");
assert.equal(run('state.tasks[0].id'),'member-task','Returning members retain their own records');
run("session={kind:'guest',username:'游客'};loadWorkspace();");
assert.equal(run('state.tasks[0].id'),'guest-task','Guest records survive account switching');
vm.runInContext("function schedulingFixture() {\n  const w=monday(new Date()), day=n=>plusDays(w,n);\n  const tasks=[\n    {id:'t1',title:'完成实验三报告',course:'计算机网络',category:'报告',minutes:180,remaining:180,deadline:at(day(2),18),priority:3,color:'purple',done:false},\n    {id:'t2',title:'阅读论文并整理笔记',course:'学术阅读',category:'阅读',minutes:120,remaining:120,deadline:at(day(4),20),priority:2,color:'green',done:false},\n    {id:'t3',title:'高等数学习题 · 第四章',course:'高等数学',category:'复习',minutes:90,remaining:90,deadline:at(day(1),23,59),priority:3,color:'blue',done:false},\n    {id:'t4',title:'准备小组展示',course:'软件工程',category:'报告',minutes:150,remaining:150,deadline:at(day(4),17),priority:2,color:'amber',done:false},\n    {id:'t5',title:'数据结构编程作业',course:'数据结构',category:'编程',minutes:120,remaining:120,deadline:at(day(3),23,59),priority:3,color:'purple',done:false},\n    {id:'t6',title:'复习英语词汇',course:'大学英语',category:'背诵',minutes:60,remaining:0,deadline:at(day(0),22),priority:1,color:'green',done:true,actual:55,completedAt:at(day(0),8)}\n  ];\n  const events=[\n    {id:'e1',title:'高等数学',course:'固定课程',start:at(day(0),9),end:at(day(0),10,30),color:'blue'},\n    {id:'e2',title:'计算机网络',course:'固定课程',start:at(day(1),9),end:at(day(1),11),color:'blue'},\n    {id:'e3',title:'数据结构',course:'固定课程',start:at(day(2),9),end:at(day(2),10,30),color:'blue'},\n    {id:'e4',title:'软件工程',course:'固定课程',start:at(day(3),9),end:at(day(3),11),color:'blue'},\n    {id:'e5',title:'大学英语',course:'固定课程',start:at(day(4),9),end:at(day(4),10,30),color:'blue'},\n    {id:'e6',title:'实验室组会',course:'固定日程',start:at(day(2),15),end:at(day(2),16,30),color:'amber'}\n  ];\n  const blocks=[\n    {id:'b1',taskId:'t1',start:at(day(0),10,30),end:at(day(0),12),locked:false},\n    {id:'b2',taskId:'t2',start:at(day(0),14),end:at(day(0),16),locked:true},\n    {id:'b3',taskId:'t3',start:at(day(0),17),end:at(day(0),18,30),locked:false},\n    {id:'b4',taskId:'t1',start:at(day(1),14),end:at(day(1),15,30),locked:false},\n    {id:'b5',taskId:'t5',start:at(day(2),11),end:at(day(2),13),locked:false},\n    {id:'b6',taskId:'t4',start:at(day(3),14),end:at(day(3),16,30),locked:false}\n  ];\n  const notices=[\n    {id:'n1',title:'实验三提交时间调整',source:'微信',group:'计算机网络课程群',received:at(day(0),8,42),text:'同学们，实验三报告的提交时间由本周三18:00调整到本周五18:00，请大家注意。报告要求不变。',action:'update',target:'t1',proposalTitle:'完成实验三报告',deadline:at(day(4),18),minutes:180,course:'计算机网络',status:'review',evidence:'原文明确给出了新的截止时间，并指向已有的实验三报告。'},\n    {id:'n2',title:'新增课程作业',source:'Canvas',group:'软件工程',received:at(day(0),8,15),text:'作业二：需求分析文档。请于本周日23:59前提交。建议用时2小时，需要包含用例图与需求说明。',action:'create',proposalTitle:'完成需求分析文档',deadline:at(day(6),23,59),minutes:120,course:'软件工程',status:'review',evidence:'示例中截止时间与建议用时完整。确认后会新增任务。'},\n    {id:'n3',title:'小组讨论时间确认',source:'QQ',group:'软件工程项目组',received:at(day(0),7,56),text:'我们周四晚上七点到八点开项目讨论会，线上会议。大家提前准备好各自负责的内容。',action:'event',proposalTitle:'项目小组讨论',start:at(day(3),19),end:at(day(3),20),course:'软件工程',status:'review',evidence:'示例中给出了会议日期及完整时间段。确认后会新增固定日程。'}\n  ];\n  return {version:1,tasks,events,blocks,notices,settings:{startHour:8,endHour:22,autoCreate:false},risks:[],scheduleVersion:1};\n}"+';state=schedulingFixture();',ctx);
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
