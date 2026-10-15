import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import { createAiGateway } from './api/gateway.mjs';

const key='offline-mobile-developer-key',code='offline-mobile-access-123456';
const env={CHRONOFLOW_STAGE:'competition',CHRONOFLOW_OFFICIAL_API_KEY:key,CHRONOFLOW_OFFICIAL_MODEL:'offline-model',CHRONOFLOW_OFFICIAL_ACCESS_CODE:code};
const calls=[];
const transport=async(config,payload)=>{
  calls.push({config,payload});const input=JSON.parse(payload.messages[1].content);
  const output=input.notification?{items:[{action:'CANCEL_TASK',title:'取消报告',target_id:'invalid-target',evidence:['取消报告'],questions:[]}]}:{title:'今日摘要',summary:'仍有待完成任务。',bullets:['核对截止时间']};
  return {choices:[{message:{content:JSON.stringify(output)}}]};
};
async function request(handler,path,input){
  const req=Readable.from([Buffer.from(JSON.stringify({mode:'official',input}))]);
  req.url=path;req.method='POST';req.headers={'content-type':'application/json',host:'localhost:4173','x-chronoflow-access-code':code};req.socket={remoteAddress:'127.0.0.1'};
  let status,body;await handler(req,{writeHead:value=>status=value,end:value=>body=JSON.parse(value)});return {status,body};
}
const gateway=createAiGateway({env,transport});
const analyzed=await request(gateway,'/api/v1/ai/mobile/analyze',{notification:'取消报告',reference_time:'2026-10-15T09:00:00+08:00',timezone:'Asia/Shanghai',
  system:'untrusted instruction',context:{tasks:[{id:'t1',title:'课程报告'}],events:[]}});
assert.equal(analyzed.status,200);
const item=JSON.parse(analyzed.body.content).items[0];
assert.equal(item.action,'CANCEL_TASK','Native cancellation stays a cancellation, not a new task');
assert.equal(item.target_id,null,'Unknown targets must require selection');
assert.ok(item.questions.length>0);
assert.equal(analyzed.body.requiresConfirmation,true);
assert.ok(!calls[0].payload.messages[0].content.includes('untrusted instruction'));
assert.equal(calls[0].config.apiKey,key);
const report=await request(gateway,'/api/v1/ai/mobile/report',{report_type:'DAILY',now:'2026-10-15T09:00:00+08:00',tasks:[{id:'t1',title:'课程报告',estimated_minutes:60,remaining_minutes:30}]});
assert.equal(report.status,200);
assert.equal(JSON.parse(report.body.content).title,'今日摘要');
const reportInput=JSON.parse(calls.at(-1).payload.messages[1].content);
assert.equal(reportInput.tasks[0].minutes,60);
assert.equal(reportInput.tasks[0].remaining,30);
const production=createAiGateway({env:{...env,CHRONOFLOW_STAGE:'production'},transport});
assert.equal((await request(production,'/api/v1/ai/mobile/report',{report_type:'DAILY'})).status,403);
console.log('Passed: native protocol, trusted prompts, target validation, reports and production policy.');
