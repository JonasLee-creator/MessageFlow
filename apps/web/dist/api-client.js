/* Non-secret preferences persist locally; API credentials stay in tab session storage. */
(() => {
  let scope='guest',preferences={},credentials={},service=null,serviceError='';
  const requests=new Set();
  const preferenceKey=()=>`chronoflow.api.preferences.v1.${scope}`;
  const credentialKey=()=>`chronoflow.api.credentials.v1.${scope}`;
  const mode=()=>service?.stage==='production'?'user':preferences.mode||service?.defaultMode||'official';
  function cancelAll(){for(const request of requests)request.abort();requests.clear();}
  function read(storage,key){try{const value=JSON.parse(storage.getItem(key)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}}
  function setScope(session){
    cancelAll();scope=session?.kind==='member'?session.userId:'guest';
    try{preferences=read(localStorage,preferenceKey());}catch{preferences={};}
    try{credentials=read(sessionStorage,credentialKey());}catch{credentials={};}
    if(!['official','user'].includes(preferences.mode))delete preferences.mode;
  }
  function state(){return {mode:mode(),baseUrl:typeof preferences.baseUrl==='string'?preferences.baseUrl:'https://api.deepseek.com',
    model:typeof preferences.model==='string'?preferences.model:'',hasUserKey:!!credentials.apiKey,hasAccessCode:!!credentials.accessCode,
    service,serviceError,ready:!!service&&(mode()==='official'?service.official.available&&!!credentials.accessCode:!!credentials.apiKey&&!!preferences.model&&!!preferences.baseUrl)};}
  async function request(path,options={}){
    const controller=new AbortController();requests.add(controller);const timer=setTimeout(()=>controller.abort(),60000);
    try {
      const response=await fetch(`/api/v1/ai/${path}`,{...options,signal:controller.signal,credentials:'same-origin',cache:'no-store'});
      let value;try{value=await response.json();}catch{throw new Error('AI 服务未连接，请使用运行了 API 服务的站点。');}
      if(!response.ok)throw new Error(value?.error?.message||'接口请求失败，请稍后重试。');
      return value;
    }catch(error){if(error.name==='AbortError')throw new Error('请求已取消或超时，请重试。');if(error instanceof TypeError)throw new Error('无法连接 AI 服务，请检查网络与服务地址。');throw error;}
    finally{clearTimeout(timer);requests.delete(controller);}
  }
  async function refresh(){
    try {
      const config=await request('config');
      if(!['competition','production'].includes(config.stage)||typeof config.official?.available!=='boolean')throw new Error('AI 服务配置无效。');
      service=config;serviceError='';
    }catch(error){service=null;serviceError=error.message;}
    return state();
  }
  function save(fields){
    const selected=service?.stage==='production'?'user':fields.mode;
    if(!['official','user'].includes(selected))throw new Error('请选择接口方式。');
    const next={mode:selected,baseUrl:String(fields.baseUrl||preferences.baseUrl||'https://api.deepseek.com').trim(),model:String(fields.model??preferences.model??'').trim()};
    if(next.baseUrl.length>1000||next.model.length>100)throw new Error('接口地址或模型名称过长。');
    const nextSecrets={...credentials};
    // Empty password inputs keep the already saved credential; clearing is an explicit action.
    if(fields.apiKey){if(fields.apiKey.length<8||fields.apiKey.length>512||/[^\x21-\x7e]/.test(fields.apiKey))throw new Error('API Key 格式不正确。');nextSecrets.apiKey=fields.apiKey;}
    if(fields.accessCode){if(!/^[\x21-\x7e]{16,128}$/.test(fields.accessCode))throw new Error('请输入 16–128 位英文字符组成的官方接口体验码。');nextSecrets.accessCode=fields.accessCode;}
    cancelAll();
    try{localStorage.setItem(preferenceKey(),JSON.stringify(next));}catch{throw new Error('接口偏好未能保存，请检查浏览器存储。');}
    let retained=true;try{sessionStorage.setItem(credentialKey(),JSON.stringify(nextSecrets));}catch{retained=false;}
    preferences=next;credentials=nextSecrets;return {retained};
  }
  function clearCredentials(){cancelAll();credentials={};try{sessionStorage.removeItem(credentialKey());}catch{/* Credentials remain cleared in memory. */}}
  function configuration(){
    const current=state();
    if(!current.service)throw new Error(current.serviceError||'请先在设置中连接 AI 服务。');
    if(current.mode==='official'){
      if(!current.service.official.available)throw new Error('官方接口当前不可用，请在设置中配置用户接口。');
      if(!credentials.accessCode)throw new Error('请先在设置中填写官方接口体验码。');
      return {body:{mode:'official'},headers:{'Content-Type':'application/json','X-ChronoFlow-Access-Code':credentials.accessCode}};
    }
    if(!credentials.apiKey||!preferences.model||!preferences.baseUrl)throw new Error('请先填写用户接口地址、模型名称和 API Key。');
    return {body:{mode:'user',user:{baseUrl:preferences.baseUrl,model:preferences.model,apiKey:credentials.apiKey}},headers:{'Content-Type':'application/json'}};
  }
  async function call(path,input){const config=configuration();return request(path,{method:'POST',headers:config.headers,body:JSON.stringify({...config.body,...(input?{input}:{})})});}
  globalThis.ChronoApi=Object.freeze({setScope,state,refresh,save,clearCredentials,cancelAll,test:()=>call('test'),analyze:input=>call('analyze',input)});
})();
