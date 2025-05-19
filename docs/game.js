/* ---------- 常量 ---------- */
const API  = "https://gamo.onrender.com";
let   SID  = null;
let   lang = localStorage.getItem("lang") || "zh";

/* ---------- DOM ---------- */
const tagInput  = document.getElementById("tagInput");
const startBtn  = document.getElementById("startBtn");
const randomBtn = document.getElementById("randomBtn");
const restartBtn= document.getElementById("restartBtn");
const langSel   = document.getElementById("langSel");
const langLabel = document.getElementById("langLabel");
const loader    = document.getElementById("loader");
const intro     = document.getElementById("intro");
const historyEl = document.getElementById("history");
const choicesEl = document.getElementById("choices");
const partyEl   = document.getElementById("party");


/* ---------- i18n ---------- */
const I18N = {
  zh:{start:"开始冒险",restart:"重新开始",placeholder:"输入关键词，用逗号分隔",free:"自由输入…",exec:"执行",ending:"生成结局"},
  en:{start:"Start",restart:"Restart",placeholder:"Enter tags, e.g. isekai, comedy",free:"Free action…",exec:"Go",ending:"End Story"}
};
function t(k){return I18N[lang][k]||k}

/* ---------- 用户偏好 ---------- */
const CFG = {
  get need_cg(){return document.getElementById("toggleCG").checked},
  get need_avatar(){return document.getElementById("toggleAvatar").checked},
  avatar_style:"anime",
};

/* ---------- 小工具 ---------- */
function showLoader(){loader.style.display="block"}
function hideLoader(){loader.style.display="none"}
function addHTML(html){historyEl.insertAdjacentHTML("beforeend",`<div class="bubble">${html}</div>`); window.scrollTo(0,document.body.scrollHeight);}
function resetUI(){intro.innerHTML="";historyEl.innerHTML="";choicesEl.innerHTML="";partyEl.innerHTML=""}

/* ---------- 语言切换 ---------- */
function switchLang(l){lang=l;localStorage.setItem("lang",l);langSel.value=l;langLabel.textContent=l==="zh"?"语言:":"Language:";startBtn.textContent=t("start");restartBtn.textContent=t("restart");tagInput.placeholder=t("placeholder");}
langSel.onchange=e=>switchLang(e.target.value);
switchLang(lang); // 初始化

/* ---------- 后端通信 ---------- */
async function api(path, body){
  showLoader();
  const res = await fetch(`${API}/${path}`,{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({...body, lang, sid:SID}),credentials:"include"});
  hideLoader();
  if(!res.ok){alert(await res.text());throw new Error("API error")}
  return res.json();
}

/* ---------- 渲染角色卡 ---------- */
function renderParty(chars){
  const LONG = {                       // ← 英文/缩写 ↔ 全称（自行修改多语言）
    STR:"力量 Strength", DEX:"敏捷 Dexterity", CON:"体质 Constitution",
    INT:"智力 Intelligence", WIS:"感知 Wisdom", CHA:"魅力 Charisma"
  };

  const party = document.getElementById("party");
  party.innerHTML = Object.values(chars).filter(c=>c.id).map(c=>`
    <div class="card">
      ${c.avatar_url ? `<img src="${c.avatar_url}" class="ava">` : ""}
      <h4>${c.name} · ${c.role}</h4>

      <!-- ▼ 这里是改动重点 ▼ -->
      <div class="stats">
        ${Object.entries(c.stats).map(
            ([k,v]) => `<span data-full="${LONG[k]||k}">${k}:${v}</span>`
        ).join("")}
      </div>
      <!-- ▲ 改动结束 ▲ -->

      <p>${c.backstory}</p>
      <p>🎯 ${c.goal}</p>
    </div>
  `).join("");
}


/* ---------- 按钮区 ---------- */
function renderButtons(opts){
  choicesEl.innerHTML="";
  for(const o of opts){
    const b=document.createElement("button");b.textContent=`${o.id}. ${o.text}`;b.onclick=()=>choose(o.id);choicesEl.appendChild(b);
  }
  if(!opts.length) return;
  const inp=document.createElement("input");inp.id="customInput";inp.placeholder=t("free");choicesEl.appendChild(inp);
  inp.addEventListener("keydown",e=>e.key==="Enter"&&customAct());
  const exec=document.createElement("button");exec.textContent=t("exec");exec.style.background="var(--green)";exec.onclick=customAct;choicesEl.appendChild(exec);
  const end=document.createElement("button");end.textContent=t("ending");end.style.background="var(--red)";end.onclick=endGame;choicesEl.appendChild(end);
}
function disableChoices(){choicesEl.querySelectorAll("button").forEach(b=>b.disabled=true)}

/* ---------- 游戏逻辑 ---------- */
async function start(){
  resetUI();
  const tags = tagInput.value.split(",").map(s=>s.trim()).filter(Boolean);
  if(!tags.length){alert(t("placeholder"));return;}
  const data = await api("new",{
    tags,
    need_avatar: CFG.need_avatar,
    avatar_style: CFG.avatar_style
  });
  SID=data.sid;
  intro.innerHTML=`🌍 ${data.summary}<br>🎯 ${data.main_plot}`;
  renderParty(data.characters);
  addHTML(data.event.text);
  renderButtons(data.event.options);
}

async function choose(id){
  disableChoices();
  const d = await api("choice",{choice_id:id});
  addHTML(d.result);addHTML(d.event.text);renderButtons(d.event.options);
}

async function customAct(){
  const inp=document.getElementById("customInput"); const txt=inp.value.trim(); if(!txt) return; inp.value="";
  const d = await api("choice",{custom_input:txt});
  addHTML(d.result);addHTML(d.event.text);renderButtons(d.event.options);
}

async function endGame(){
  disableChoices(); showLoader();
  const d = await api("end",{});
  hideLoader(); choicesEl.innerHTML="";
  addHTML(`<b>=== ${d.title} ===</b>`); addHTML(d.ending);
}

/* ---------- 随机世界 ---------- */
const PRESETS=["赛博忍者,鲨鱼神教","维多利亚,蒸汽朋克,吸血鬼","猫咪王国,宇宙歌剧","校园恋爱,克苏鲁"];
function surprise(){ tagInput.value=PRESETS[Math.floor(Math.random()*PRESETS.length)]; start(); }

/* ---------- 事件绑定 ---------- */
startBtn.onclick=start; randomBtn.onclick=surprise; restartBtn.onclick=()=>location.reload();