/* ChronoFlow interactive draft. All records remain in this browser. */
const STORAGE_KEY = 'chronoflow.web.draft.v1';
const DAYS = ['周一','周二','周三','周四','周五','周六','周日'];
const icons = {
  logo:'<path d="M5 5h14L5 19h14"/>', sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  inbox:'<path d="M4 4h16l2 12v4H2v-4L4 4Z"/><path d="M2 15h6l2 3h4l2-3h6"/>', check:'<path d="m5 12 4 4L19 6"/>', tasks:'<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 9 1 1 2-2m3 1h3m-9 6 1 1 2-2m3 1h3"/>', calendar:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2"/>',
  chart:'<path d="M4 3v17h17M8 15v-4m5 4V7m5 8V4"/>', settings:'<path d="m9 3-1 3-3 1-2 4 2 2v4l4 2 3-1 3 1 4-2v-4l2-2-2-4-3-1-1-3H9Z"/><circle cx="12" cy="12" r="3"/>', plus:'<path d="M12 5v14M5 12h14"/>', search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>', bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>', phone:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/>', more:'<circle cx="5" cy="12" r=".7"/><circle cx="12" cy="12" r=".7"/><circle cx="19" cy="12" r=".7"/>', left:'<path d="m14 6-6 6 6 6"/>', right:'<path d="m10 6 6 6-6 6"/>', arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>', refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', risk:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v.2"/>', lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>', unlock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8-1m-4 8v3"/>', book:'<path d="M3 4h6l3 2 3-2h6v15h-6l-3 2-3-2H3V4Zm9 2v15"/>', message:'<path d="M3 4h18v13H9l-6 4V4Z"/><path d="M7 8h10M7 12h6"/>', close:'<path d="m6 6 12 12M18 6 6 18"/>', menu:'<path d="M4 6h16M4 12h16M4 18h16"/>', edit:'<path d="m16 3 5 5-12 12H4v-5L16 3Zm-2 2 5 5"/>', download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>', trash:'<path d="M3 6h18M9 3h6m-10 3 1 15h12l1-15M10 10v7m4-7v7"/>', spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>', link:'<path d="m9 15 6-6M8 14l-2 2a3 3 0 0 1-4-4l5-5a3 3 0 0 1 4 0m2 3 2-2a3 3 0 0 1 4 4l-5 5a3 3 0 0 1-4 0"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.tasks}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid = () => crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
function dateKey(date) { const d=new Date(date); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
function plusDays(date,n) { const d=new Date(date); d.setDate(d.getDate()+n); return d; }
function monday(date) { const d=new Date(date); d.setHours(0,0,0,0); d.setDate(d.getDate()-((d.getDay()+6)%7)); return d; }
function at(date,h,m=0) { const d=new Date(date); d.setHours(h,m,0,0); return d.toISOString(); }
function hm(value) { return new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}); }
function shortDate(value) { return new Date(value).toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'}); }
function inputDate(value) { if(!value) return ''; const d=new Date(value); return `${dateKey(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`; }
function hours(minutes) { return Number((minutes/60).toFixed(1)); }
function seed() {
  const w=monday(new Date()), day=n=>plusDays(w,n);
  const tasks=[
    {id:'t1',title:'完成实验三报告',course:'计算机网络',category:'报告',minutes:180,remaining:180,deadline:at(day(2),18),priority:3,color:'purple',done:false},
    {id:'t2',title:'阅读论文并整理笔记',course:'学术阅读',category:'阅读',minutes:120,remaining:120,deadline:at(day(4),20),priority:2,color:'green',done:false},
    {id:'t3',title:'高等数学习题 · 第四章',course:'高等数学',category:'复习',minutes:90,remaining:90,deadline:at(day(1),23,59),priority:3,color:'blue',done:false},
    {id:'t4',title:'准备小组展示',course:'软件工程',category:'报告',minutes:150,remaining:150,deadline:at(day(4),17),priority:2,color:'amber',done:false},
    {id:'t5',title:'数据结构编程作业',course:'数据结构',category:'编程',minutes:120,remaining:120,deadline:at(day(3),23,59),priority:3,color:'purple',done:false},
    {id:'t6',title:'复习英语词汇',course:'大学英语',category:'背诵',minutes:60,remaining:0,deadline:at(day(0),22),priority:1,color:'green',done:true,actual:55,completedAt:at(day(0),8)}
  ];
  const events=[
    {id:'e1',title:'高等数学',course:'固定课程',start:at(day(0),9),end:at(day(0),10,30),color:'blue'},
    {id:'e2',title:'计算机网络',course:'固定课程',start:at(day(1),9),end:at(day(1),11),color:'blue'},
    {id:'e3',title:'数据结构',course:'固定课程',start:at(day(2),9),end:at(day(2),10,30),color:'blue'},
    {id:'e4',title:'软件工程',course:'固定课程',start:at(day(3),9),end:at(day(3),11),color:'blue'},
    {id:'e5',title:'大学英语',course:'固定课程',start:at(day(4),9),end:at(day(4),10,30),color:'blue'},
    {id:'e6',title:'实验室组会',course:'固定日程',start:at(day(2),15),end:at(day(2),16,30),color:'amber'}
  ];
  const blocks=[
    {id:'b1',taskId:'t1',start:at(day(0),10,30),end:at(day(0),12),locked:false},
    {id:'b2',taskId:'t2',start:at(day(0),14),end:at(day(0),16),locked:true},
    {id:'b3',taskId:'t3',start:at(day(0),17),end:at(day(0),18,30),locked:false},
    {id:'b4',taskId:'t1',start:at(day(1),14),end:at(day(1),15,30),locked:false},
    {id:'b5',taskId:'t5',start:at(day(2),11),end:at(day(2),13),locked:false},
    {id:'b6',taskId:'t4',start:at(day(3),14),end:at(day(3),16,30),locked:false}
  ];
  const notices=[
    {id:'n1',title:'实验三提交时间调整',source:'微信',group:'计算机网络课程群',received:at(day(0),8,42),text:'同学们，实验三报告的提交时间由本周三18:00调整到本周五18:00，请大家注意。报告要求不变。',action:'update',target:'t1',proposalTitle:'完成实验三报告',deadline:at(day(4),18),minutes:180,course:'计算机网络',status:'review',evidence:'原文明确给出了新的截止时间，并指向已有的实验三报告。'},
    {id:'n2',title:'新增课程作业',source:'Canvas',group:'软件工程',received:at(day(0),8,15),text:'作业二：需求分析文档。请于本周日23:59前提交。建议用时2小时，需要包含用例图与需求说明。',action:'create',proposalTitle:'完成需求分析文档',deadline:at(day(6),23,59),minutes:120,course:'软件工程',status:'review',evidence:'示例中截止时间与建议用时完整。确认后会新增任务。'},
    {id:'n3',title:'小组讨论时间确认',source:'QQ',group:'软件工程项目组',received:at(day(0),7,56),text:'我们周四晚上七点到八点开项目讨论会，线上会议。大家提前准备好各自负责的内容。',action:'event',proposalTitle:'项目小组讨论',start:at(day(3),19),end:at(day(3),20),course:'软件工程',status:'review',evidence:'示例中给出了会议日期及完整时间段。确认后会新增固定日程。'}
  ];
  return {version:1,tasks,events,blocks,notices,settings:{startHour:8,endHour:22,autoCreate:false},risks:[],scheduleVersion:1};
}
let state, storageError=false;
try {const raw=localStorage.getItem(STORAGE_KEY);state=raw?JSON.parse(raw):seed();if(state.version!==1||!Array.isArray(state.tasks)||!Array.isArray(state.notices)||!Array.isArray(state.blocks)||!Array.isArray(state.events)||!state.settings)throw Error('Invalid draft data');}
catch {state=seed();storageError=true;}
let view='today',week=monday(new Date()),calendarMode='week',taskFilter='active',courseFilter='',selectedNotice=null,searchQuery='',mobileOpen=false;
const pending = () => state.notices.filter(n=>n.status==='review');
const active = () => state.tasks.filter(t=>!t.done);
const todayKey = () => dateKey(new Date());
function save() {try {localStorage.setItem(STORAGE_KEY,JSON.stringify(state));return true;}catch{storageError=true;toast('浏览器存储不可用，本次修改仅保留到页面关闭');return false;}}
let toastTimer;
function toast(message) {const el=document.getElementById('toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),3400);}
const btn=(label,action,ico='',classes='')=>`<button class="btn ${classes}" data-action="${action}">${ico?icon(ico):''}${label}</button>`;
const routeNames={today:'今天',inbox:'发现',tasks:'任务',calendar:'日历',reports:'复盘',settings:'设置'};
function render() {
  view=location.hash.slice(1).split('?')[0]||'today';if(!routeNames[view])view='today';
  const app=document.getElementById('app');
  app.innerHTML=`<div class="shell"><aside class="sidebar ${mobileOpen?'open':''}"><a href="#today" class="logo"><div class="logo-mark">${icon('logo')}</div><div><div class="logo-title">时序</div><div class="logo-sub">CHRONOFLOW</div></div></a><div class="nav-label">我的工作台</div><nav class="nav" aria-label="主导航">${Object.entries(routeNames).map(([key,label])=>`<a href="#${key}" class="${view===key?'active':''}" ${view===key?'aria-current="page"':''}>${icon({today:'sun',inbox:'inbox',tasks:'tasks',calendar:'calendar',reports:'chart',settings:'settings'}[key])}<span>${label}</span>${key==='inbox'&&pending().length?`<span class="count">${pending().length}</span>`:''}</a>`).join('')}</nav><div class="sidebar-bottom"><div class="phone-card"><div class="row"><span>${icon('phone')}</span><span class="tiny">随时随地，接续你的计划</span></div><p>手机采集，电脑规划。<br>跨端同步将在后续版本接入。</p>${btn('连接手机','connect','link','sm')}</div><div class="user row"><div class="avatar">序</div><div><div class="user-name">我的工作空间</div><div class="user-sub">本机演示 · 无需登录</div></div><button class="icon-btn" data-action="settings" aria-label="打开设置">${icon('more')}</button></div></div></aside><main class="workspace"><header class="topbar"><div class="row"><button class="icon-btn mobile-menu" data-action="menu" aria-label="展开导航">${icon('menu')}</button><div class="breadcrumb"><span>工作空间</span>${icon('right')}<b>${routeNames[view]}</b></div></div><div class="top-actions"><form class="search" id="search-form" role="search">${icon('search')}<input id="global-search" name="query" value="${esc(searchQuery)}" placeholder="搜索任务，按回车查找" aria-label="搜索任务"><span class="key">↵</span></form><span class="preview-badge">网页版 · 交互初稿</span><button class="icon-btn notify-btn" data-action="inbox" aria-label="查看待确认通知">${icon('bell')}</button><div class="avatar" style="width:27px;height:27px;font-size:10px">序</div></div></header><div class="content">${({today:todayView,inbox:inboxView,tasks:tasksView,calendar:calendarView,reports:reportsView,settings:settingsView}[view])()}<p class="footer-note"><span class="demo-dot"></span>演示数据 · ${storageError?'存储不可用，修改仅保留在当前页面':'修改仅保存在当前浏览器'} · 未连接手机、Canvas 或 AI</p></div></main></div>`;
}
function header(title,description,actions='') {return `<div class="page-header"><div><h1>${title}</h1><p>${description}</p></div><div class="header-actions">${actions}</div></div>`;}
function statsView() {
  const todayBlocks=state.blocks.filter(b=>dateKey(b.start)===todayKey()&&state.tasks.some(t=>t.id===b.taskId&&!t.done));
  const planned=todayBlocks.reduce((s,b)=>s+(new Date(b.end)-new Date(b.start))/60000,0);
  const due=active().filter(t=>t.deadline&&new Date(t.deadline)>=new Date()&&new Date(t.deadline)<=plusDays(new Date(),3)).length;
  const values=[['待办任务',active().length,'项','tasks','按自己的节奏，逐一完成',''],['今日专注',hours(planned),'小时','clock','已安排的任务时间','good'],['待确认',pending().length,'条','inbox','确认后，计划才会更新',''],['近期截止',due,'项','risk','未来 3 天内需要完成','attention']];
  return `<div class="stats">${values.map((s,i)=>`<div class="panel stat"><div class="stat-title"><span>${s[0]}</span>${icon(s[3])}</div><div class="stat-value">${s[1]}<small>${s[2]}</small></div><div class="stat-note ${s[5]}">${i===1?'<span class="dot"></span>':''}${s[4]}</div>${i===1?'<div class="stat-graphic"><span style="height:9px"></span><span style="height:15px"></span><span style="height:11px"></span><span style="height:22px"></span><span style="height:18px"></span><span style="height:29px"></span><span style="height:24px"></span></div>':''}</div>`).join('')}</div>`;
}
function todayView() {
  const d=new Date();
  return `${header('今天，让时间有条不紊。',`<span class="date">${d.toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</span> &nbsp; / &nbsp; 从一件小事开始，专注于眼前。`,btn('录入通知','new-notice','plus')+btn('新建任务','new-task','plus','primary'))}${statsView()}<div class="dashboard"><div>${calendarPanel()}${agendaView()}</div><div class="stack">${pendingPanel()}${riskPanel()}<div class="quote"><div class="quote-line"></div>把纷杂留给时序，<br>把专注留给自己。</div></div></div>`;
}
function calendarRange() { const start=Math.min(8,state.settings.startHour),end=Math.max(20,state.settings.endHour);return {start,end,total:(end-start)*60}; }
function calendarPanel(full=false) {
  const range=calendarRange(),hourCount=range.end-range.start;
  const dates=Array.from({length:7},(_,i)=>plusDays(week,i)), shown=calendarMode==='day'?[new Date()]:dates;
  const now=new Date(), dayIndex=dates.findIndex(d=>dateKey(d)===dateKey(now));
  return `<section class="panel calendar-panel ${full?'calendar-page':''}"><div class="panel-head"><div><div class="panel-title">${icon('calendar')}<h2>${calendarMode==='day'?'今日时间线':'本周计划'}</h2></div><div class="panel-desc">给重要的事，留出合适的时间</div></div><div class="row">${btn('重新安排','replan','refresh','sm')}<div class="segmented" aria-label="日历视图"><button data-action="mode-week" class="${calendarMode==='week'?'active':''}">周</button><button data-action="mode-day" class="${calendarMode==='day'?'active':''}">日</button></div></div></div><div class="calendar-toolbar"><div class="row"><span class="week-title">${calendarMode==='day'?`${shortDate(now)} · 今天`:`${week.getFullYear()} 年 ${week.getMonth()+1} 月 ${week.getDate()} 日 — ${shortDate(plusDays(week,6))}`}</span>${calendarMode==='week'?`<button class="icon-btn" data-action="prev-week" aria-label="上一周">${icon('left')}</button><button class="icon-btn" data-action="next-week" aria-label="下一周">${icon('right')}</button>`:''}</div>${btn('今天','this-week','','sm')}</div><div class="calendar-wrap"><div class="calendar" style="${calendarMode==='day'?'min-width:300px':''}"><div class="day-heads" style="grid-template-columns:46px repeat(${shown.length},minmax(0,1fr))"><div></div>${shown.map(d=>`<div class="day-head ${dateKey(d)===todayKey()?'today':''} ${d.getDay()===0||d.getDay()===6?'weekend':''}"><span>${DAYS[(d.getDay()+6)%7]}</span><strong>${d.getDate()}</strong></div>`).join('')}</div><div class="calendar-body" style="grid-template-columns:46px repeat(${shown.length},minmax(0,1fr))"><div class="time-gutter">${Array.from({length:hourCount},(_,i)=>`<span class="hour-label" style="top:${i/hourCount*100}%">${String(i+range.start).padStart(2,'0')}:00</span>`).join('')}</div>${shown.map(d=>`<div class="day-column ${dateKey(d)===todayKey()?'today':''} ${d.getDay()===0||d.getDay()===6?'weekend':''}" data-day="${dateKey(d)}" style="background-image:linear-gradient(to bottom,#f0f1f5 1px,transparent 1px);background-size:100% ${100/hourCount}%">${dayItems(d).map(item=>eventMarkup(item)).join('')}${dateKey(d)===todayKey()&&now.getHours()>=range.start&&now.getHours()<range.end?`<div class="now-line" style="top:${((now.getHours()-range.start)*60+now.getMinutes())/range.total*100}%"></div>`:''}</div>`).join('')}</div></div></div><div class="calendar-footer"><span class="legend"><span class="legend-dot blue"></span>固定课程</span><span class="legend"><span class="legend-dot"></span>作业 / 实验</span><span class="legend"><span class="legend-dot green"></span>阅读 / 复习</span><span class="legend"><span class="legend-dot amber"></span>会议 / 展示</span><span class="hint">拖动任务块调整 · 点击查看详情</span></div></section>`;
}
function dayItems(date) {
  const key=dateKey(date);
  return [...state.events.filter(e=>dateKey(e.start)===key).map(e=>({...e,kind:'event',locked:true})),...state.blocks.filter(b=>dateKey(b.start)===key).flatMap(b=>{const t=state.tasks.find(t=>t.id===b.taskId&&!t.done);return t?[{...t,...b,kind:'block'}]:[];})].sort((a,b)=>new Date(a.start)-new Date(b.start));
}
function eventMarkup(item) {
  const range=calendarRange(),start=new Date(item.start),end=new Date(item.end),min=(start.getHours()-range.start)*60+start.getMinutes(),dur=(end-start)/60000;
  if(min+dur<=0||min>=range.total)return '';
  return `<button class="cal-event ${item.color||'purple'}" style="top:${Math.max(0,min)/range.total*100}%;height:${(Math.min(range.total,min+dur)-Math.max(0,min))/range.total*100}%" data-action="${item.kind==='event'?'event-detail':'block-detail'}" data-id="${esc(item.id)}" ${item.kind==='block'?'draggable="true"':''} aria-label="${esc(item.title)}, ${hm(start)}至${hm(end)}${item.locked?'，已锁定':''}"><span class="event-name">${esc(item.title)}</span><span class="event-time">${hm(start)} — ${hm(end)}</span>${dur>=90?`<span class="event-course">${esc(item.course)}</span>`:''}${item.locked?`<span class="lock-mark">${icon('lock')}</span>`:''}</button>`;
}
function agendaView() {
  const items=dayItems(new Date());
  return `<section class="panel agenda"><div class="agenda-head row between"><h2 style="font-size:13px">今日安排</h2><span class="tiny muted">${items.length} 个时间块</span></div>${items.length?items.map(item=>`<div class="agenda-item"><span class="agenda-time">${hm(item.start)}</span><div class="agenda-bar" style="background:${{blue:'#a2bad1',green:'#a2c3ac',amber:'#d7bb8e',purple:'#ad9fd8'}[item.color]||'#ad9fd8'}"></div><div><h3>${esc(item.title)}</h3><p>${esc(item.course)} · ${hours((new Date(item.end)-new Date(item.start))/60000)} 小时</p></div>${item.kind==='block'?`<button class="btn sm" data-action="complete-task" data-id="${item.taskId}">${icon('check')}完成任务</button>`:`<span class="pill gray" style="margin-left:auto">固定日程</span>`}</div>`).join(''):'<p class="muted tiny">今天还没有安排，可以新建任务后重新排程。</p>'}</section>`;
}
function pendingPanel() {
  return `<section class="panel side-panel"><div class="side-heading"><h2>待确认<span class="number">${pending().length}</span></h2><a href="#inbox">查看全部 →</a></div>${pending().slice(0,2).map(n=>`<div class="notice-card"><div class="notice-source"><span class="source-mark">${icon(n.source==='Canvas'?'book':'message')}${esc(n.source)} · ${esc(n.group.replace('课程群',''))}</span><span>${hm(n.received)}</span></div><h3>${esc(n.title)}</h3><p>${esc(n.action==='update'?`截止时间调整为 ${shortDate(n.deadline)} ${hm(n.deadline)}`:n.text.slice(0,48))}</p><button class="btn sm" data-action="review-notice" data-id="${n.id}">核对${icon('arrow')}</button></div>`).join('')||'<div class="empty" style="padding:20px 0">已全部核对，计划清清楚楚。</div>'}</section>`;
}
function riskPanel() {
  const urgent=active().filter(t=>t.deadline).sort((a,b)=>new Date(a.deadline)-new Date(b.deadline))[0];
  const gap=state.risks[0];
  return `<section class="panel side-panel risk-panel"><div class="side-heading"><div class="row">${icon('risk')}<h2>留意一下</h2></div><span class="tiny">本地规则</span></div><p class="risk-content">${gap?`${esc(gap.title)}还有 ${gap.minutes} 分钟未找到可用时段。可以调整可用时间或任务耗时。`:urgent?`「${esc(urgent.title)}」将于 ${shortDate(urgent.deadline)} ${hm(urgent.deadline)} 截止。给它留一点余量，准备起来更从容。`:'当前没有待完成的任务，给自己留一点休息时间。'}</p><div class="risk-meta"><span>${gap?'排程缺口':'最近的截止事项'}</span><span>计划 v${state.scheduleVersion}</span></div>${btn('查看任务安排','tasks','arrow','sm')}</section>`;
}
function calendarView() {return `${header('把一周，安排得刚刚好。','固定课程与专注时间，一眼看清。',btn('新建日程','new-event','plus')+btn('新建任务','new-task','plus','primary'))}${calendarPanel(true)}${state.risks.length?`<div class="panel agenda">${state.risks.map(r=>`<p class="risk-content">${esc(r.title)}：尚缺 ${r.minutes} 分钟可用时间。</p>`).join('')}</div>`:''}`;}
function tasksView() {
  const courses=[...new Set(state.tasks.map(t=>t.course).filter(Boolean))];
  const filtered=state.tasks.filter(t=>(taskFilter==='all'||(taskFilter==='done'?t.done:!t.done))&&(!courseFilter||t.course===courseFilter)&&(!searchQuery||`${t.title} ${t.course}`.toLowerCase().includes(searchQuery.toLowerCase()))).sort((a,b)=>(new Date(a.deadline||'2099-01-01'))-(new Date(b.deadline||'2099-01-01')));
  return `${header('每件事，都有它的位置。','把任务拆清楚，让行动更轻松。',btn('新建任务','new-task','plus','primary'))}<div class="view-toolbar"><div class="filters">${[['active','进行中'],['done','已完成'],['all','全部任务']].map(([k,l])=>`<button class="filter ${taskFilter===k?'active':''}" data-action="filter-${k}">${l}</button>`).join('')}<select id="course-filter" class="filter-select" aria-label="按课程筛选"><option value="">全部课程</option>${courses.map(c=>`<option ${courseFilter===c?'selected':''}>${esc(c)}</option>`).join('')}</select>${searchQuery?`<button class="filter active" data-action="clear-search">${esc(searchQuery)} ×</button>`:''}</div><span class="view-status">${filtered.length} 项任务 · 按截止时间排序</span></div><section class="panel task-table"><table><thead><tr><th style="width:40%">任务名称</th><th>截止时间</th><th>剩余耗时</th><th>优先级</th><th>操作</th></tr></thead><tbody>${filtered.map(t=>`<tr><td><div class="task-title-cell"><button class="task-check ${t.done?'done':''}" data-action="${t.done?'reopen-task':'complete-task'}" data-id="${t.id}" aria-label="${t.done?'重新打开':'完成'}${esc(t.title)}">${t.done?icon('check'):''}</button><div><div class="task-name" style="${t.done?'text-decoration:line-through;color:#a0a1b1':''}">${esc(t.title)}</div><div class="task-sub">${esc(t.course||'未分类')} · ${esc(t.category||'其他')}</div></div></div></td><td>${t.deadline?`${shortDate(t.deadline)}<span class="muted" style="display:block;font-size:10px;margin-top:5px">${hm(t.deadline)}</span>`:'未设定'}</td><td>${hours(t.remaining)} 小时<div class="task-progress"><span style="width:${Math.min(100,(t.minutes-t.remaining)/Math.max(1,t.minutes)*100)}%"></span></div></td><td><span class="pill ${t.priority===3?'amber':t.priority===2?'purple':'gray'}">${['','低','中','高'][t.priority]}</span></td><td><button class="icon-btn" data-action="edit-task" data-id="${t.id}" aria-label="编辑${esc(t.title)}">${icon('edit')}</button></td></tr>`).join('')||'<tr><td colspan="5"><div class="empty">没有符合条件的任务。</div></td></tr>'}</tbody></table></section>`;
}
function inboxView() {
  const list=state.notices.filter(n=>n.status==='review');
  const n=list.find(n=>n.id===selectedNotice)||list[0]; if(n)selectedNotice=n.id;
  return `${header('信息纷杂，行动清晰。','对照原文核对，确认后更新你的计划。',btn('录入通知','new-notice','plus','primary'))}${!n?`<section class="panel empty">${icon('check')}<h2>待确认事项已清空</h2><p>可以手动录入通知，继续体验提取与确认流程。</p><p style="font-size:11px;margin-top:10px">已确认 ${state.notices.filter(n=>n.status==='applied').length} 条 · 已忽略 ${state.notices.filter(n=>n.status==='ignored').length} 条</p></section>`:`<div class="review-layout"><section class="panel inbox-list">${list.map(item=>`<button class="inbox-item ${n.id===item.id?'active':''}" data-action="select-notice" data-id="${item.id}"><div class="notice-source"><span>${esc(item.source)}</span><span>${hm(item.received)}</span></div><h3>${esc(item.title)}</h3><p>${esc(item.group)}</p><span class="pill ${item.action==='update'?'amber':'purple'}" style="margin-top:10px">${{update:'修改事项',create:'新增任务',event:'新增日程'}[item.action]}</span></button>`).join('')}</section><section class="panel"><div class="panel-head"><h2>原始通知</h2><span class="pill gray">${esc(n.source)}</span></div><div class="review-body"><div class="row tiny muted">${icon('message')}${esc(n.group)}</div><div class="source-text">${esc(n.text)}</div><div class="source-detail">收到时间：${shortDate(n.received)} ${hm(n.received)}<br>来源：${n.source==='手动'?'手动录入':'演示通知'}<br>原文保留，方便随时追溯。</div></div></section><section class="panel review-result"><div class="panel-head"><h2>核对提取结果</h2><span class="pill ${n.action==='update'?'amber':'green'}">${n.action==='update'?'修改需确认':'等待确认'}</span></div><form id="review-form" class="review-body"><input type="hidden" name="id" value="${n.id}"><div class="field"><label for="review-title">${n.action==='event'?'日程名称':'任务名称'}</label><input id="review-title" name="title" required maxlength="120" value="${esc(n.proposalTitle)}"></div>${n.action==='update'?`<div class="field"><label for="review-target">关联已有任务</label><select id="review-target" name="target" required>${active().map(t=>`<option value="${t.id}" ${t.id===n.target?'selected':''}>${esc(t.title)}</option>`).join('')}</select></div><div class="change-arrow"><s>${state.tasks.find(t=>t.id===n.target)?.deadline?shortDate(state.tasks.find(t=>t.id===n.target).deadline):'原截止时间'}</s>${icon('arrow')}<span>${shortDate(n.deadline)}</span></div>`:''}${n.action==='event'?`<div class="field"><label for="review-start">开始时间</label><input id="review-start" name="start" type="datetime-local" required value="${inputDate(n.start)}"></div><div class="field"><label for="review-end">结束时间</label><input id="review-end" name="end" type="datetime-local" required value="${inputDate(n.end)}"></div>`:`<div class="field"><label for="review-deadline">截止时间${n.deadline?'':' · 请补全'}</label><input id="review-deadline" name="deadline" type="datetime-local" required value="${inputDate(n.deadline)}"></div><div class="field-grid"><div class="field"><label for="review-minutes">预计耗时（分钟）</label><input id="review-minutes" name="minutes" type="number" min="30" max="14400" step="30" required value="${n.minutes}"></div><div class="field"><label for="review-course">所属课程</label><input id="review-course" name="course" maxlength="80" value="${esc(n.course)}"></div></div>`}<div class="evidence"><div class="row" style="margin-bottom:5px">${icon('spark')}提取依据</div>${esc(n.evidence)}</div><div class="tiny muted">${n.action==='update'?'修改已有事项始终需要你的确认。':'日期和耗时可修改，请以原文为准。'}</div><div class="review-buttons"><button type="button" class="btn" data-action="ignore-notice" data-id="${n.id}">忽略</button><button class="btn primary" type="submit">${icon('check')}确认并更新计划</button></div></form></section></div>`}`;
}
function reportsView() {
  const done=state.tasks.filter(t=>t.done), actual=done.reduce((s,t)=>s+(t.actual||0),0),estimated=done.filter(t=>t.actual).reduce((s,t)=>s+t.minutes,0);
  const max=Math.max(60,...Array.from({length:7},(_,i)=>done.filter(t=>t.completedAt&&dateKey(t.completedAt)===dateKey(plusDays(week,i))).reduce((s,t)=>s+(t.actual||0),0)));
  return `${header('回头看看，也是一种前进。','从实际完成记录中，慢慢了解自己的节奏。',btn('导出数据','export','download'))}${statsView()}<div class="report-grid"><section class="panel report-panel"><div class="row between"><h2>本周完成耗时</h2><span class="pill purple">本地记录</span></div><p class="panel-desc">${shortDate(week)} — ${shortDate(plusDays(week,6))} · 记录实际耗时后计入</p><div class="bar-chart">${Array.from({length:7},(_,i)=>{const mins=done.filter(t=>t.completedAt&&dateKey(t.completedAt)===dateKey(plusDays(week,i))).reduce((s,t)=>s+(t.actual||0),0);return `<div class="bar-group"><div class="bar ${mins?'':'pale'}" style="height:${Math.max(2,mins/max*100)}%" title="${DAYS[i]}：${mins} 分钟"></div><label>${DAYS[i]}</label></div>`;}).join('')}</div><div class="row between" style="margin-top:20px"><span class="tiny muted">已记录实际耗时</span><span>${hours(actual)} <small class="muted tiny">小时</small></span></div><p class="report-note">统计基于当前浏览器里的演示记录。这里展示的是实际记录汇总，尚未接入 AI 周报。</p></section><section class="panel report-panel"><h2>认识你的时间</h2><div class="report-line"><span>已完成任务</span><b>${done.length} 项</b></div><div class="report-line"><span>记录实际用时的任务</span><b>${done.filter(t=>t.actual).length} 项</b></div><div class="report-line"><span>实际 / 预计耗时</span><b>${estimated?(actual/estimated).toFixed(2)+' 倍':'暂无记录'}</b></div><div class="report-tip">${done.length<5?'样本还很少，先不急着下结论。完成任务时记录实际用时，让未来的估时更贴近你的节奏。':'留意实际耗时与预计耗时的差距，下次安排同类任务时可以预留更多余量。'}</div><p class="report-note">网页版初稿暂未迁移手机端的个人学习模型。</p></section></div>`;
}
function settingsView() {
  return `${header('按你的习惯，调整时序。','先照顾好自己的节奏，再安排任务。')}<div class="settings-grid"><section class="panel settings-panel"><h2>每日可用时间</h2><p>重新安排时，将在这个时间范围内寻找空闲时段，避开固定日程和锁定块。</p><form id="settings-form"><div class="field-grid"><div class="field"><label for="start-hour">开始时间</label><select name="startHour" id="start-hour">${Array.from({length:24},(_,i)=>`<option value="${i}" ${state.settings.startHour===i?'selected':''}>${String(i).padStart(2,'0')}:00</option>`).join('')}</select></div><div class="field"><label for="end-hour">结束时间</label><select name="endHour" id="end-hour">${Array.from({length:24},(_,i)=>`<option value="${i+1}" ${state.settings.endHour===i+1?'selected':''}>${String(i+1).padStart(2,'0')}:00</option>`).join('')}</select></div></div><p class="tiny muted" style="margin-bottom:18px">时区：${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)} · 跟随浏览器</p><button class="btn primary" type="submit">保存可用时间</button></form></section><section class="panel settings-panel"><h2>连接与同步</h2><p>当前是浏览器本地初稿。连接能力将在接入后端后开放。</p>${[['phone','手机 App','待接入跨端同步'],['book','Canvas 课程平台','待接入课程与作业同步'],['spark','AI 提取与复盘','当前仅支持简单本地规则']].map(([i,l,d])=>`<div class="settings-row"><div class="row">${icon(i)}<div><h3 style="font-size:12px">${l}</h3><p>${d}</p></div></div><span class="pill gray">未连接</span></div>`).join('')}</section><section class="panel settings-panel"><h2>数据管理</h2><p>数据仅保存在当前浏览器。清除浏览器数据可能导致记录丢失，可以导出 JSON 留存。</p><div class="settings-row"><div><h3 style="font-size:12px">导出当前数据</h3><p>包含任务、通知与时间安排</p></div>${btn('导出 JSON','export','download','sm')}</div><div class="settings-row"><div><h3 style="font-size:12px">恢复演示数据</h3><p>将覆盖当前浏览器内的修改</p></div>${btn('重置','reset','','sm danger')}</div></section><section class="panel settings-panel"><h2>关于这个初稿</h2><p>时序 · ChronoFlow Web</p><div class="source-detail">已支持任务编辑、通知确认、简单排程、时间块锁定与拖动、完成耗时记录和本地保存。<br><br>演示通知用于体验核对流程；网页不会读取手机上的微信或 QQ 通知。<br><br>日历随每日可用时间扩展显示范围；排程以 30 分钟为单位。</div></section></div>`;
}
function overlaps(start,end,item) {return start<new Date(item.end)&&end>new Date(item.start);}
function plan() {
  const now=new Date(),floor=new Date(now);floor.setSeconds(0,0);floor.setMinutes(Math.ceil(floor.getMinutes()/30)*30);
  const protectedBlocks=state.blocks.filter(b=>state.tasks.some(t=>t.id===b.taskId&&!t.done)&&(b.locked||new Date(b.start)<=now));
  const occupied=[...state.events,...protectedBlocks];const blocks=[...protectedBlocks];const risks=[];
  for(const task of [...active()].sort((a,b)=>(new Date(a.deadline||'2099-01-01')-new Date(b.deadline||'2099-01-01'))||b.priority-a.priority)){
    let need=Math.max(0,Math.ceil(task.remaining/30)*30-protectedBlocks.filter(b=>b.taskId===task.id).reduce((s,b)=>s+Math.max(0,(new Date(b.end)-Math.max(now,new Date(b.start)))/60000),0));need=Math.ceil(need/30)*30;
    let run=null;
    for(let di=0;di<14&&need>0;di++){
      const day=plusDays(monday(now),((now.getDay()+6)%7)+di);
      for(let m=state.settings.startHour*60;m<state.settings.endHour*60&&need>0;m+=30){
        const start=new Date(day);start.setHours(Math.floor(m/60),m%60,0,0);const end=new Date(start.getTime()+30*60000);
        if(start<floor||end>new Date(task.deadline||plusDays(now,14))||occupied.some(o=>overlaps(start,end,o))){run=null;continue;}
        if(run&&run.end===start.toISOString()){run.end=end.toISOString();}else{run={id:uid(),taskId:task.id,start:start.toISOString(),end:end.toISOString(),locked:false};blocks.push(run);occupied.push(run);}
        need-=30;
      }run=null;
    }
    if(need>0)risks.push({title:task.title,minutes:need});
  }
  state.blocks=blocks;state.risks=risks;state.scheduleVersion++;save();
}
function modal(title,body) {document.getElementById('editor-content').innerHTML=`<div class="dialog-title"><h2>${title}</h2><button class="icon-btn" data-action="close-modal" aria-label="关闭">${icon('close')}</button></div>${body}`;document.getElementById('editor').showModal();}
function closeModal(){document.getElementById('editor').close();}
function taskEditor(id) {
  const t=state.tasks.find(t=>t.id===id);
  modal(t?'编辑任务':'给新任务留一点时间',`<form id="task-form"><input type="hidden" name="id" value="${esc(id||'')}"><div class="field"><label for="task-title">任务名称</label><input id="task-title" name="title" required maxlength="120" placeholder="例如：完成实验报告" value="${esc(t?.title||'')}"></div><div class="field-grid"><div class="field"><label for="task-course">课程 / 分组</label><input id="task-course" name="course" maxlength="80" value="${esc(t?.course||'')}" placeholder="例如：计算机网络"></div><div class="field"><label for="task-category">任务类型</label><select id="task-category" name="category">${['报告','实验','编程','复习','阅读','背诵','其他'].map(c=>`<option ${t?.category===c?'selected':''}>${c}</option>`).join('')}</select></div></div><div class="field"><label for="task-deadline">截止时间（可选）</label><input id="task-deadline" name="deadline" type="datetime-local" value="${inputDate(t?.deadline)}"></div><div class="field-grid"><div class="field"><label for="task-minutes">${t?'剩余':'预计'}耗时（分钟）</label><input id="task-minutes" name="minutes" type="number" min="30" max="14400" step="30" required value="${t?t.remaining||t.minutes:60}"></div><div class="field"><label for="task-priority">优先级</label><select id="task-priority" name="priority">${[[1,'低'],[2,'中'],[3,'高']].map(([p,l])=>`<option value="${p}" ${(t?.priority||2)===p?'selected':''}>${l}</option>`).join('')}</select></div></div><p class="tiny muted">保存后会按截止时间重新安排未来未锁定的时间块。</p><div class="dialog-actions">${t?`<button type="button" class="btn danger" data-action="delete-task" data-id="${t.id}">删除任务</button>`:''}<button type="button" class="btn" data-action="close-modal">取消</button><button class="btn primary" type="submit">保存任务</button></div></form>`);
}
function eventEditor() {modal('添加固定日程',`<form id="event-form"><div class="field"><label for="event-title">日程名称</label><input id="event-title" name="title" required maxlength="120" placeholder="例如：高等数学课程"></div><div class="field"><label for="event-course">课程 / 分组</label><input id="event-course" name="course" maxlength="80" placeholder="例如：高等数学"></div><div class="field"><label for="event-start">开始时间</label><input id="event-start" name="start" type="datetime-local" required></div><div class="field"><label for="event-end">结束时间</label><input id="event-end" name="end" type="datetime-local" required></div><div class="dialog-actions"><button type="button" class="btn" data-action="close-modal">取消</button><button class="btn primary">保存日程</button></div></form>`);}
function noticeEditor() {modal('把通知，变成下一步行动',`<form id="notice-form"><div class="dialog-help">初稿使用简单本地规则，识别完整日期（如 2026-10-18 18:00）、今天 / 明天与耗时。当前仅生成新增任务提议，复杂修改和取消不会自动处理。</div><div class="field"><label for="notice-text">通知原文</label><textarea id="notice-text" name="text" required maxlength="5000" placeholder="例如：明天18:00前提交实验报告，预计2小时"></textarea></div><div class="field"><label for="notice-group">课程 / 分组</label><input id="notice-group" name="group" maxlength="80" placeholder="例如：计算机网络"></div><div class="dialog-actions"><button type="button" class="btn" data-action="close-modal">取消</button><button class="btn primary">生成待确认事项</button></div></form>`);}
function parseNotice(text,group) {
  const now=new Date();let deadline=null,evidence=[];
  const explicit=text.match(/(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?\s*(\d{1,2})[:：](\d{2})/);
  const relative=text.match(/(今天|明天|后天).*?(\d{1,2})[:：点](\d{2})?/);
  if(explicit){const [,y,mo,da,h,mi]=explicit.map((v,i)=>i?Number(v):v);const d=new Date(y,mo-1,da,h,mi);if(d.getFullYear()===y&&d.getMonth()===mo-1&&d.getDate()===da&&d.getHours()===h&&d.getMinutes()===mi){deadline=d.toISOString();evidence.push('识别到完整日期和时间');}}
  else if(relative){let h=Number(relative[2]);if(/下午|晚上/.test(text)&&h<12)h+=12;if(h<24&&Number(relative[3]||0)<60&&!(h<12&&text.includes('点')&&!/上午|早上|凌晨|下午|晚上/.test(text))){const d=plusDays(now,{今天:0,明天:1,后天:2}[relative[1]]);deadline=at(d,h,Number(relative[3]||0));evidence.push('相对日期以当前浏览器日期为基准');}}
  const duration=text.match(/(?:预计|耗时|用时)\s*(\d+(?:\.\d+)?)\s*(小时|分钟)/),minutes=duration?Math.max(30,Math.ceil(Number(duration[1])*(duration[2]==='小时'?60:1)/30)*30):60;
  if(!deadline)evidence.push('未能明确识别截止时间，请手动补全');if(!duration)evidence.push('未识别耗时，暂填 60 分钟，请核对');
  return {id:uid(),title:'手动录入的通知',source:'手动',group:group||'手动录入',received:now.toISOString(),text,action:'create',proposalTitle:text.split(/[，。\n]/)[0].slice(0,80),deadline,minutes:Math.min(14400,minutes),course:group||'',status:'review',evidence:evidence.join('；')+'。本地规则结果需要人工核对。'};
}
function blockDetail(id) {
  const b=state.blocks.find(b=>b.id===id),t=state.tasks.find(t=>t.id===b?.taskId);if(!b||!t)return;
  modal(esc(t.title),`<div class="source-detail">${esc(t.course)}<br>${shortDate(b.start)} ${hm(b.start)} — ${hm(b.end)}<br>截止：${t.deadline?`${shortDate(t.deadline)} ${hm(t.deadline)}`:'未设定'}<br>状态：${b.locked?'已锁定，重新安排时保留':'未锁定，可自动调整'}</div><div class="dialog-actions"><button class="btn" data-action="toggle-lock" data-id="${b.id}">${icon(b.locked?'unlock':'lock')}${b.locked?'解锁':'锁定时间'}</button><button class="btn" data-action="edit-task" data-id="${t.id}">编辑任务</button><button class="btn primary" data-action="complete-task" data-id="${t.id}">完成任务</button></div>`);
}
function completeEditor(id) {
  const t=state.tasks.find(t=>t.id===id);if(!t)return;if(document.getElementById('editor').open)closeModal();
  modal('完成一件事，记录一点进步',`<form id="complete-form"><input type="hidden" name="id" value="${t.id}"><p style="margin-bottom:21px;font-size:13px;line-height:1.8">${esc(t.title)}</p><div class="field"><label for="actual-minutes">实际耗时（分钟）</label><input id="actual-minutes" name="actual" type="number" min="1" max="14400" required value="${t.minutes}"></div><div class="tiny muted">这里完成的是整项任务，未来的相关时间块会移除。</div><div class="dialog-actions"><button type="button" class="btn" data-action="close-modal">取消</button><button class="btn primary">${icon('check')}记录并完成</button></div></form>`);
}
function confirmAction(title,message,action,id='') {if(document.getElementById('editor').open)closeModal();modal(title,`<p class="source-detail">${esc(message)}</p><div class="dialog-actions">${btn('取消','close-modal')}<button class="btn primary" data-action="${action}" data-id="${id}">确认</button></div>`);}
function navigate(route){if(location.hash==='#'+route)render();else location.hash=route;}
document.addEventListener('click',e=>{
  const target=e.target.closest('[data-action]');if(!target){if(e.target.closest('.nav a'))mobileOpen=false;return;}const action=target.dataset.action,id=target.dataset.id;
  if(routeNames[action]){navigate(action);return;}
  if(action==='close-modal'){closeModal();return;}
  if(action==='menu'){mobileOpen=!mobileOpen;render();return;}
  if(action==='connect'){modal('接续你的手机计划',`<div class="dialog-help">网页版初稿目前独立运行，尚未接入账号和手机同步。</div><div class="source-detail">后续连接流程：<br>1. 手机开启同步并关联账号<br>2. 网页登录同一账号<br>3. 核对首次同步的数据范围<br><br>当前可以使用演示数据体验网页里的任务与日历。</div><div class="dialog-actions">${btn('知道了','close-modal','','primary')}</div>`);return;}
  if(action==='new-task'){taskEditor();return;}if(action==='edit-task'){if(document.getElementById('editor').open)closeModal();taskEditor(id);return;}
  if(action==='new-notice'){noticeEditor();return;}if(action==='new-event'){eventEditor();return;}
  if(action==='complete-task'){completeEditor(id);return;}
  if(action==='reopen-task'){const t=state.tasks.find(t=>t.id===id);t.done=false;t.remaining=t.minutes;delete t.actual;delete t.completedAt;plan();render();toast('任务已重新打开');return;}
  if(action==='delete-task'){confirmAction('删除任务？','任务及其时间安排会从当前浏览器中删除。','confirm-delete-task',id);return;}
  if(action==='confirm-delete-task'){state.tasks=state.tasks.filter(t=>t.id!==id);state.blocks=state.blocks.filter(b=>b.taskId!==id);closeModal();plan();render();toast('任务已删除');return;}
  if(action==='block-detail'){blockDetail(id);return;}
  if(action==='event-detail'){const event=state.events.find(x=>x.id===id);modal(esc(event.title),`<div class="source-detail">${esc(event.course)}<br>${shortDate(event.start)} ${hm(event.start)} — ${hm(event.end)}<br>固定日程会在自动排程时被避让。</div><div class="dialog-actions"><button class="btn danger" data-action="delete-event" data-id="${id}">删除日程</button>${btn('关闭','close-modal')}</div>`);return;}
  if(action==='delete-event'){confirmAction('删除固定日程？','删除后，该时间可用于任务安排。','confirm-delete-event',id);return;}
  if(action==='confirm-delete-event'){state.events=state.events.filter(e=>e.id!==id);closeModal();plan();render();toast('固定日程已删除');return;}
  if(action==='toggle-lock'){const b=state.blocks.find(b=>b.id===id);b.locked=!b.locked;save();closeModal();render();toast(b.locked?'时间块已锁定':'时间块已解锁');return;}
  if(action==='mode-day'||action==='mode-week'){calendarMode=action.slice(5);render();return;}
  if(action==='prev-week'||action==='next-week'){week=plusDays(week,action==='prev-week'?-7:7);render();return;}
  if(action==='this-week'){week=monday(new Date());render();return;}
  if(action==='replan'){confirmAction('重新安排未来时间？','会调整未来未锁定的任务块，保留锁定块与已经开始的安排。','confirm-replan');return;}
  if(action==='confirm-replan'){plan();week=monday(new Date());closeModal();render();toast(state.risks.length?`已重新安排，${state.risks.length} 项任务存在时间缺口`:'未来任务已重新安排');return;}
  if(action.startsWith('filter-')){taskFilter=action.slice(7);render();return;}
  if(action==='clear-search'){searchQuery='';render();return;}
  if(action==='review-notice'||action==='select-notice'){selectedNotice=id;if(view==='inbox')render();else navigate('inbox');return;}
  if(action==='ignore-notice'){const n=state.notices.find(n=>n.id===id);n.status='ignored';save();render();toast('已忽略这条通知');return;}
  if(action==='export'){const blob=new Blob([JSON.stringify(state,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`chronoflow-${todayKey()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出当前浏览器数据');return;}
  if(action==='reset'){confirmAction('恢复演示数据？','当前浏览器中的所有修改将被演示数据覆盖，建议先导出。','confirm-reset');return;}
  if(action==='confirm-reset'){state=seed();selectedNotice=null;save();closeModal();render();toast('已恢复演示数据');return;}
});
document.addEventListener('submit',e=>{
  const form=e.target,formId=form.getAttribute('id');if(!formId)return;e.preventDefault();const data=Object.fromEntries(new FormData(form));
  if(formId==='search-form'){searchQuery=(data.query||'').trim();taskFilter='all';courseFilter='';navigate('tasks');return;}
  if(formId==='task-form'){
    if(!data.title.trim()){toast('请填写任务名称');return;}
    const current=state.tasks.find(t=>t.id===data.id),minutes=Number(data.minutes),fields={title:data.title.trim(),course:data.course.trim(),category:data.category,deadline:data.deadline?new Date(data.deadline).toISOString():null,priority:Number(data.priority)};
    if(current&&fields.deadline&&state.blocks.some(b=>b.taskId===current.id&&b.locked&&new Date(b.end)>new Date(fields.deadline))){toast('截止时间早于锁定时间块，请先解锁或调整截止时间');return;}
    if(current){Object.assign(current,fields);if(!current.done){current.remaining=minutes;current.minutes=Math.max(current.minutes,minutes);}}
    else state.tasks.push({id:uid(),...fields,minutes,remaining:minutes,color:{阅读:'green',复习:'green',背诵:'green'}[data.category]||'purple',done:false});
    plan();closeModal();render();toast('任务已保存，未来计划已更新');return;
  }
  if(formId==='event-form'){
    const start=new Date(data.start),end=new Date(data.end);if(end<=start){toast('结束时间需要晚于开始时间');return;}
    if(!data.title.trim()){toast('请填写日程名称');return;}
    if(state.events.some(item=>overlaps(start,end,item))||state.blocks.some(b=>(b.locked||new Date(b.start)<=new Date())&&overlaps(start,end,b))){toast('与固定日程或锁定时间块冲突，请调整时间');return;}
    state.events.push({id:uid(),title:data.title.trim(),course:data.course.trim()||'固定日程',start:start.toISOString(),end:end.toISOString(),color:'blue'});plan();closeModal();render();toast('固定日程已保存');return;
  }
  if(formId==='notice-form'){
    if(!data.text.trim()){toast('请填写通知原文');return;}const n=parseNotice(data.text.trim(),data.group.trim());state.notices.unshift(n);selectedNotice=n.id;save();closeModal();navigate('inbox');toast('已生成待确认事项，请核对提取结果');return;
  }
  if(formId==='review-form'){
    const n=state.notices.find(n=>n.id===data.id);if(!n||n.status!=='review'){toast('这条通知已经处理');return;}
    if(!data.title.trim()){toast('请填写事项名称');return;}
    if(n.action==='event'){
      const start=new Date(data.start),end=new Date(data.end);if(end<=start){toast('结束时间需要晚于开始时间');return;}
      if([...state.events,...state.blocks.filter(b=>b.locked||new Date(b.start)<=new Date())].some(item=>overlaps(start,end,item))){toast('与固定日程或锁定块冲突，请调整时间');return;}
      state.events.push({id:uid(),title:data.title.trim(),course:n.course,start:start.toISOString(),end:end.toISOString(),color:'amber'});
    }else{
      const deadline=new Date(data.deadline).toISOString(),minutes=Number(data.minutes);
      if(n.action==='update'){const t=active().find(t=>t.id===data.target);if(!t){toast('请选择有效的关联任务');return;}if(state.blocks.some(b=>b.taskId===t.id&&b.locked&&new Date(b.end)>new Date(deadline))){toast('新截止时间早于锁定时间块，请先解锁或调整截止时间');return;}Object.assign(t,{title:data.title.trim(),deadline,remaining:minutes,minutes:Math.max(t.minutes,minutes),course:data.course.trim()});}
      else state.tasks.push({id:uid(),title:data.title.trim(),course:data.course.trim(),category:'其他',minutes,remaining:minutes,deadline,priority:2,color:'purple',done:false});
    }
    n.status='applied';plan();render();toast('已确认，任务与日历已更新');return;
  }
  if(formId==='complete-form'){
    const t=state.tasks.find(t=>t.id===data.id);t.done=true;t.remaining=0;t.actual=Number(data.actual);t.completedAt=new Date().toISOString();state.blocks=state.blocks.filter(b=>b.taskId!==t.id||new Date(b.end)<=new Date());save();closeModal();render();toast('任务已完成，实际耗时已记录');return;
  }
  if(formId==='settings-form'){const start=Number(data.startHour),end=Number(data.endHour);if(end<=start){toast('结束时间需要晚于开始时间');return;}Object.assign(state.settings,{startHour:start,endHour:end});plan();render();toast('可用时间已保存，计划已更新');return;}
});
document.addEventListener('change',e=>{if(e.target.id==='course-filter'){courseFilter=e.target.value;render();}});
let draggedBlock=null;
document.addEventListener('dragstart',e=>{const item=e.target.closest('.cal-event[draggable]');if(!item)return;draggedBlock=item.dataset.id;e.dataTransfer.setData('text/plain',draggedBlock);e.dataTransfer.effectAllowed='move';item.classList.add('dragging');});
document.addEventListener('dragover',e=>{const col=e.target.closest('.day-column');if(!col||!draggedBlock)return;e.preventDefault();col.classList.add('drop-target');e.dataTransfer.dropEffect='move';});
document.addEventListener('dragleave',e=>{const col=e.target.closest('.day-column');if(col&&!col.contains(e.relatedTarget))col.classList.remove('drop-target');});
document.addEventListener('dragend',()=>{draggedBlock=null;document.querySelectorAll('.dragging,.drop-target').forEach(el=>el.classList.remove('dragging','drop-target'));});
document.addEventListener('drop',e=>{
  const col=e.target.closest('.day-column');if(!col||!draggedBlock)return;e.preventDefault();col.classList.remove('drop-target');const b=state.blocks.find(b=>b.id===draggedBlock),t=state.tasks.find(t=>t.id===b?.taskId);if(!b||!t)return;
  const rect=col.getBoundingClientRect(),range=calendarRange(),minute=Math.floor((e.clientY-rect.top)/rect.height*(range.total/30))*30+range.start*60,start=new Date(`${col.dataset.day}T00:00:00`);start.setHours(Math.floor(minute/60),minute%60,0,0);const end=new Date(start.getTime()+(new Date(b.end)-new Date(b.start)));
  if(start<new Date()){toast('请安排到未来的时间');return;}
  if(start.getHours()<state.settings.startHour||end>atLocalEnd(start)){toast('超出每日可用时间，请调整');return;}
  if(t.deadline&&end>new Date(t.deadline)){toast('安排不能超过任务截止时间');return;}
  if([...state.events,...state.blocks.filter(x=>x.id!==b.id&&state.tasks.some(t=>t.id===x.taskId&&!t.done))].some(o=>overlaps(start,end,o))){toast('这个时段已有安排，请选择空闲时间');return;}
  b.start=start.toISOString();b.end=end.toISOString();b.locked=true;state.scheduleVersion++;save();render();toast('时间已调整并锁定');
});
function atLocalEnd(date) {const d=new Date(date);d.setHours(state.settings.endHour,0,0,0);return d;}
window.addEventListener('hashchange',()=>{mobileOpen=false;render();window.scrollTo(0,0);});
document.getElementById('editor').addEventListener('click',e=>{if(e.target===document.getElementById('editor')){const rect=e.target.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)closeModal();}});
render();if(storageError)toast('未能读取浏览器记录，当前显示临时演示数据');
