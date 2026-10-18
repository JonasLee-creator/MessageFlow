import https from 'node:https';
import {lookup} from 'node:dns/promises';
import {isPublicAddress} from './gateway.mjs';

export function canvasOrigin(value){
  const url=new URL(value);
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||(url.port&&url.port!=='443')||!['','/'].includes(url.pathname))throw Error('请填写不带路径的学校Canvas HTTPS地址');
  return url.origin;
}
async function publicGet(url,token){
  const records=await lookup(url.hostname,{all:true,verbatim:true});
  if(!records.length||records.some(r=>!isPublicAddress(r.address)))throw Error('Canvas地址必须是公开站点');
  const pinned=records[0];
  return new Promise((resolve,reject)=>{
    const req=https.request(url,{method:'GET',headers:{Authorization:`Bearer ${token}`,Accept:'application/json'},
      lookup:(_host,options,callback)=>options?.all?callback(null,[pinned]):callback(null,pinned.address,pinned.family)},res=>{
      const chunks=[];let size=0;
      res.on('data',chunk=>{size+=chunk.length;if(size>2*1024*1024){res.destroy();reject(Error('Canvas返回内容过大'));}else chunks.push(chunk);});
      res.on('error',reject);
      res.on('end',()=>{if(res.statusCode!==200)return reject(Error('Canvas访问失败，请检查Token及课程权限'));try{resolve({rows:JSON.parse(Buffer.concat(chunks).toString('utf8')),link:res.headers.link||''});}catch{reject(Error('Canvas返回格式无效'));}});
    });
    req.setTimeout(15000,()=>req.destroy(Error('Canvas连接超时')));req.on('error',reject);req.end();
  });
}
export async function syncCanvas(raw,get=publicGet){
  if(raw?.consent!==true)throw Error('请授权读取课程网站');
  const origin=canvasOrigin(raw.baseUrl);
  if(typeof raw.token!=='string'||raw.token.length<8||raw.token.length>4096||/[\r\n]/.test(raw.token))throw Error('Canvas Token格式无效');
  async function pages(path,max=3){
    let url=new URL(path,origin),rows=[],truncated=false;
    for(let i=0;i<max;i++){
      if(url.origin!==origin)throw Error('Canvas分页地址跨站，已停止');
      const reply=await get(url,raw.token);
      if(!Array.isArray(reply.rows))throw Error('Canvas列表格式无效');
      rows.push(...reply.rows);
      const next=reply.link.match(/<([^>]+)>;\s*rel="next"/);
      if(!next)return {rows,truncated};
      url=new URL(next[1],url);
      if(url.origin!==origin)throw Error('Canvas分页地址跨站，已停止');
      truncated=i===max-1;
    }
    return {rows,truncated};
  }
  const courses=await pages('/api/v1/courses?enrollment_state=active&per_page=50',1),items=[];
  let truncated=courses.truncated||courses.rows.length>10;
  for(const course of courses.rows.slice(0,10)){
    if(!Number.isSafeInteger(Number(course.id))||Number(course.id)<=0)continue;
    const result=await pages(`/api/v1/courses/${course.id}/assignments?per_page=50`);
    truncated ||= result.truncated;
    for(const task of result.rows){
      if(!task.name||!Number.isSafeInteger(Number(task.id)))continue;
      items.push({sourceKey:`${origin}/courses/${course.id}/assignments/${task.id}`,title:String(task.name).slice(0,200),
        course:String(course.name||'Canvas课程').slice(0,100),deadline:task.due_at&&Number.isFinite(Date.parse(task.due_at))?new Date(task.due_at).toISOString():null,
        releasedAt:task.created_at&&Number.isFinite(Date.parse(task.created_at))?new Date(task.created_at).toISOString():null});
    }
  }
  return {items:items.slice(0,300),truncated:truncated||items.length>300};
}
export function createCanvasGateway({sync=syncCanvas}={}){
  let busy=false;
  return async(req,res)=>{
    if(new URL(req.url,'http://localhost').pathname!=='/api/connectors/canvas')return false;
    const send=(status,body)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
    let acquired=false;
    try{
      if(req.method!=='POST')return send(405,{error:'需要POST请求'}),true;
      if(!req.headers.origin||new URL(req.headers.origin).host!==req.headers.host)return send(403,{error:'请从当前网站连接Canvas'}),true;
      if(busy)return send(429,{error:'正在读取课程网站，请稍后重试'}),true;
      busy=true;acquired=true;
      const chunks=[];let size=0;
      for await(const chunk of req){size+=chunk.length;if(size>8192)return send(413,{error:'请求过大'}),true;chunks.push(chunk);}
      send(200,await sync(JSON.parse(Buffer.concat(chunks).toString('utf8'))));
    }catch{send(400,{error:'Canvas连接失败，请核对公开HTTPS站点、Token及访问权限'});}
    finally{if(acquired)busy=false;}
    return true;
  };
}
