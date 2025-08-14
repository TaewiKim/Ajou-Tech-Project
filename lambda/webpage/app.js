// ====== 자동 기본값 설정 ======
const DEFAULT_BASE_URL =
  window.API_BASE_URL || `${window.location.origin}/prod/lambda`;

// ====== 유틸 ======
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const lsKey = "ajou.postChat.v2";

const state = {
  baseUrl: "",
  userId: "",
  order: "desc",
  items: [],
  sending: false,
};

const elements = {
  baseUrl: null,
  userId: null,
  order: null,
  btnLoad: null,
  btnSave: null,
  btnClearLocal: null,
  btnRefresh: null,
  loadSpin: null,
  loadTxt: null,
  status: null,
  msgList: null,
  message: null,
  btnSend: null,
  tagUser: null,
  tagCount: null,
  toastwrap: null,
  overlay: null,
  modalTitle: null,
  modalBody: null,
  modalOk: null,
  modalCancel: null,
};

function ts(){
  // ISO8601 (초 단위) → DynamoDB/S3 정렬 친화
  const d = new Date();
  return new Date(Date.UTC(
    d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(),
    d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds()
  )).toISOString().replace(/\..+/, 'Z');
}

function toast(msg, type="ok", timeout=2200){
  const div = document.createElement("div");
  div.className = `toast ${type}`;
  div.textContent = msg;
  elements.toastwrap.appendChild(div);
  setTimeout(()=>{ div.style.opacity="0"; div.style.transform="translateY(-4px)"; }, timeout - 300);
  setTimeout(()=>{ div.remove(); }, timeout);
}

function setStatus(text){ elements.status.textContent = text; }

function saveSettings(){
  const data = {
    baseUrl: elements.baseUrl.value.trim(),
    userId: elements.userId.value.trim(),
    order: elements.order.value,
  };
  localStorage.setItem(lsKey, JSON.stringify(data));
  state.baseUrl = data.baseUrl;
  state.userId = data.userId;
  state.order = data.order;
  updateHeaderTags();
  toast("설정 저장됨", "ok");
}

function loadSettings(){
  try{
    const data = JSON.parse(localStorage.getItem(lsKey) || "{}");
    state.baseUrl = data.baseUrl || "";
    state.userId = data.userId || "";
    state.order = data.order || "desc";

    // 저장된 값이 없으면 기본값으로 자동 채움
    elements.baseUrl.value = state.baseUrl || DEFAULT_BASE_URL;
    elements.userId.value = state.userId;
    elements.order.value = state.order;
    updateHeaderTags();
  }catch{ /* ignore */ }
}

function requireSettings(){
  const base = (elements.baseUrl.value || "").trim();
  const user = (elements.userId.value || "").trim();
  if(!base) throw new Error("API Base URL을 입력하세요.");
  if(!user) throw new Error("userId를 입력하세요.");
  state.baseUrl = base;
  state.userId = user;
  state.order = elements.order.value;
}

function updateHeaderTags(){
  elements.tagUser.textContent = `userId: ${state.userId || "-"}`;
  elements.tagCount.textContent = `${state.items.length}개`;
}

// ====== API (모두 POST) ======
async function api(action, payload = {}){
  requireSettings();
  const body = JSON.stringify({ action, userId: state.userId, ...payload });
  const res = await fetch(state.baseUrl, {
    method: "POST", // ★ 모든 요청은 POST
    headers: { "Content-Type": "application/json" },
    body
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); }
  catch { data = { raw: text }; }
  if(!res.ok){
    // 서버가 에러 메시지 보낼 가능성 고려
    const msg = data?.message || data?.error || res.statusText || "요청 실패";
    throw new Error(`HTTP ${res.status} - ${msg}`);
  }
  return data;
}

function normalizeListResponse(data){
  // 다양한 람다/게이트웨이 응답 패턴 호환
  const maybe = (v) => Array.isArray(v) ? v : [];
  if(Array.isArray(data)) return data;
  if(data?.Items) return maybe(data.Items);
  if(data?.items) return maybe(data.items);
  if(data?.body){
    try{
      const body = typeof data.body === "string" ? JSON.parse(data.body) : data.body;
      if(Array.isArray(body)) return body;
      if(body?.Items) return maybe(body.Items);
      if(body?.items) return maybe(body.items);
    }catch{ /* ignore */ }
  }
  return [];
}

function normalizeItem(raw){
  // 서버가 data:{message, sender} 구조일 수도 있고, 평평할 수도 있음
  const msg = (raw.message ?? raw?.data?.message ?? "");
  const sender = (raw.sender ?? raw?.data?.sender ?? "user");
  return {
    userId: raw.userId || state.userId,
    timestamp: raw.timestamp,
    message: msg,
    sender
  };
}

function sortItems(items, order){
  const asc = order === "asc";
  return items.sort((a,b)=>{
    if(a.timestamp === b.timestamp) return 0;
    return (a.timestamp > b.timestamp ? 1 : -1) * (asc ? 1 : -1);
  });
}

// ====== 렌더링 ======
function render(){
  const list = elements.msgList;
  list.innerHTML = "";
  updateHeaderTags();

  if(!state.items.length){
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "대화가 없습니다.";
    list.appendChild(li);
    return;
  }

  state.items.forEach(item => {
    const li = document.createElement("li");
    li.className = "card";
    li.dataset.ts = item.timestamp;

    const meta = document.createElement("div");
    meta.className = "meta";

    const time = document.createElement("div");
    time.className = "time";
    time.textContent = `${item.timestamp} · ${item.sender || "user"}`;

    const actions = document.createElement("div");
    actions.className = "actions";

    const btnEdit = document.createElement("button");
    btnEdit.className = "btn";
    btnEdit.textContent = "수정";
    btnEdit.onclick = () => enterEdit(item.timestamp);

    const btnDel = document.createElement("button");
    btnDel.className = "btn danger";
    btnDel.textContent = "삭제";
    btnDel.onclick = () => confirmDelete(item);

    actions.append(btnEdit, btnDel);
    meta.append(time, actions);

    const body = document.createElement("div");
    body.className = "msgtext";
    body.textContent = item.message ?? "";

    li.append(meta, body);
    list.appendChild(li);
  });
}

function enterEdit(ts){
  const li = elements.msgList.querySelector(`li[data-ts="${ts}"]`);
  if(!li) return;
  const item = state.items.find(x=>x.timestamp===ts);
  if(!item) return;

  // 이미 편집중이면 무시
  if(li.querySelector("textarea")) return;

  // 본문 숨기고 에디터 표시
  const body = li.querySelector(".msgtext");
  body.style.display = "none";

  const editor = document.createElement("div");
  editor.className = "editor";
  const ta = document.createElement("textarea");
  ta.value = item.message ?? "";
  ta.autofocus = true;
  const row = document.createElement("div");
  row.className = "row";
  const btnSave = document.createElement("button");
  btnSave.className = "btn primary";
  btnSave.textContent = "저장";
  const btnCancel = document.createElement("button");
  btnCancel.className = "btn";
  btnCancel.textContent = "취소";

  btnSave.onclick = async () => {
    const next = (ta.value || "").trim();
    try{
      setStatus("수정 중...");
      await api("update", { timestamp: item.timestamp, data: { message: next } });
      item.message = next;
      body.textContent = next;
      toast("수정 완료", "ok");
      setStatus("수정 완료");
      editor.remove(); body.style.display = "";
    }catch(e){
      toast(`수정 오류: ${e.message}`, "error");
      setStatus(`수정 오류: ${e.message}`);
    }
  };
  btnCancel.onclick = () => { editor.remove(); body.style.display = ""; };

  row.append(btnSave, btnCancel);
  editor.append(ta, row);
  li.appendChild(editor);
  ta.focus();
}

function confirmDialog({ title="확인", body="", okText="확인", cancelText="취소", okType="danger" }){
  return new Promise(resolve=>{
    elements.modalTitle.textContent = title;
    elements.modalBody.textContent = body;
    elements.modalOk.textContent = okText;
    elements.modalOk.className = `btn ${okType}`;
    elements.modalCancel.textContent = cancelText;

    const cleanup = () => {
      elements.overlay.style.display = "none";
      elements.overlay.setAttribute("aria-hidden","true");
      elements.modalOk.onclick = null;
      elements.modalCancel.onclick = null;
      document.removeEventListener("keydown", onKey);
    };
    const onKey = (e)=>{ if(e.key==="Escape"){ cleanup(); resolve(false); } };

    elements.modalOk.onclick = ()=>{ cleanup(); resolve(true); };
    elements.modalCancel.onclick = ()=>{ cleanup(); resolve(false); };

    elements.overlay.style.display = "grid";
    elements.overlay.setAttribute("aria-hidden","false");
    document.addEventListener("keydown", onKey);
  });
}

async function confirmDelete(item){
  const ok = await confirmDialog({
    title:"메시지 삭제",
    body:`이 메시지를 삭제할까요?\n\n${item.message?.slice(0,120) || "(빈 메시지)"}${(item.message||"").length>120?"…":""}\n\n· timestamp: ${item.timestamp}`,
    okText:"삭제",
    cancelText:"취소",
    okType:"danger"
  });
  if(!ok) return;

  try{
    setStatus("삭제 중...");
    await api("delete", { timestamp: item.timestamp });
    state.items = state.items.filter(x=> x.timestamp !== item.timestamp);
    toast("삭제 완료", "ok");
    setStatus("삭제 완료");
    render();
  }catch(e){
    toast(`삭제 오류: ${e.message}`, "error");
    setStatus(`삭제 오류: ${e.message}`);
  }
}

// ====== 동작 ======
function setLoading(on){
  elements.loadSpin.style.display = on ? "inline-block" : "none";
  elements.loadTxt.textContent = on ? "불러오는 중..." : "대화 불러오기";
  elements.btnLoad.disabled = on;
  elements.btnRefresh.disabled = on;
}

async function loadList(){
  try{
    setLoading(true);
    setStatus("불러오는 중...");
    const ascending = elements.order.value === "asc";
    const data = await api("list", { ascending });
    const arr = normalizeListResponse(data).map(normalizeItem);
    state.items = sortItems(arr, elements.order.value);
    updateHeaderTags();
    render();
    setStatus("불러오기 완료");
    toast(`불러오기 완료 · ${state.items.length}개`, "ok");
    // 스크롤: 최신순이면 상단, 오래된순이면 하단으로
    requestAnimationFrame(()=>{
      if(elements.order.value === "asc"){
        window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
      }else{
        window.scrollTo({ top: 0, behavior: "instant" });
      }
    });
  }catch(e){
    toast(`불러오기 오류: ${e.message}`, "error");
    setStatus(`불러오기 오류: ${e.message}`);
  }finally{
    setLoading(false);
  }
}

async function sendMessage(){
  if(state.sending) return;
  const msg = (elements.message.value || "").trim();
  if(!msg) return;

  try{
    requireSettings();
  }catch(e){
    toast(e.message, "warn");
    setStatus(e.message);
    return;
  }

  state.sending = true;
  elements.btnSend.disabled = true;

  const timestamp = ts();
  try{
    setStatus("전송 중...");
    await api("create", { timestamp, data: { message: msg, sender: "user" }, overwrite: false });
    // 낙관적 UI 반영
    const newItem = normalizeItem({ userId: state.userId, timestamp, message: msg, sender: "user" });
    if(state.order === "desc"){
      state.items = [ newItem, ...state.items ];
    }else{
      state.items = [ ...state.items, newItem ];
    }
    state.items = sortItems(state.items, state.order);
    elements.message.value = "";
    render();
    updateHeaderTags();
    setStatus("전송 완료");
    toast("전송 완료", "ok");
  }catch(e){
    toast(`전송 오류: ${e.message}`, "error");
    setStatus(`전송 오류: ${e.message}`);
  }finally{
    state.sending = false;
    elements.btnSend.disabled = false;
  }
}

// ====== 이벤트 바인딩 & 초기화 ======
document.addEventListener("DOMContentLoaded", () => {
  // 요소 바인딩
  elements.baseUrl = $("#baseUrl");
  elements.userId = $("#userId");
  elements.order = $("#order");
  elements.btnLoad = $("#btnLoad");
  elements.btnSave = $("#btnSave");
  elements.btnClearLocal = $("#btnClearLocal");
  elements.btnRefresh = $("#btnRefresh");
  elements.loadSpin = $("#loadSpin");
  elements.loadTxt = $("#loadTxt");
  elements.status = $("#status");
  elements.msgList = $("#msgList");
  elements.message = $("#message");
  elements.btnSend = $("#btnSend");
  elements.tagUser = $("#tagUser");
  elements.tagCount = $("#tagCount");
  elements.toastwrap = $("#toastwrap");
  elements.overlay = $("#overlay");
  elements.modalTitle = $("#modalTitle");
  elements.modalBody = $("#modalBody");
  elements.modalOk = $("#modalOk");
  elements.modalCancel = $("#modalCancel");

  // 로컬 저장값 로드 (+ 기본 URL 자동 채움)
  loadSettings();

  // 이벤트 바인딩
  elements.btnSave.onclick = saveSettings;
  elements.btnClearLocal.onclick = ()=>{ state.items = []; render(); toast("화면 목록을 비웠습니다.", "ok"); updateHeaderTags(); };
  elements.btnLoad.onclick = loadList;
  elements.btnRefresh.onclick = loadList;

  elements.order.addEventListener("change", ()=>{
    state.order = elements.order.value;
    state.items = sortItems(state.items, state.order);
    render();
    updateHeaderTags();
  });

  elements.message.addEventListener("keydown", (e)=>{
    if(e.key === "Enter" && !e.shiftKey){
      e.preventDefault();
      sendMessage();
    }
  });
  elements.btnSend.onclick = sendMessage;

  // 초기 렌더
  render();
});
