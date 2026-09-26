const log = document.getElementById("log");
const empty = document.getElementById("empty");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const send = form.querySelector("button");
const chatList = document.getElementById("chat-list");
const newChat = document.getElementById("new-chat");
const chatTitle = document.getElementById("chat-title");

const STORAGE_KEY = "pap-chat-id";
let currentId = null;
let historyHasMore = false;
let historyPage = 1;
let loadingOlder = false;
let chatsHasMore = false;
let oldestChatUat = null;
let loadingChats = false;

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

const renderer = new marked.Renderer();
renderer.code = function ({ text, lang }) {
  if ((lang || "").trim() === "mermaid") {
    return `<div class="mermaid">${escapeHtml(text)}</div>`;
  }
  const language = (lang || "").trim();
  const cls = language ? ` class="language-${language}"` : "";
  return `<pre><code${cls}>${escapeHtml(text)}</code></pre>`;
};
renderer.html = function ({ text }) {
  return escapeHtml(text);
};
marked.use({ renderer, gfm: true, breaks: true });

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  themeVariables: {
    fontFamily: "IBM Plex Sans, sans-serif",
    primaryColor: "#d7e6dc",
    primaryTextColor: "#17241d",
    secondaryColor: "#e7eee9",
    lineColor: "#1f6a45",
    textColor: "#17241d",
  },
});

function labelOf(chat) {
  return chat.title || "Chat nuevo";
}

function addMessage(kind, node, at, options = {}) {
  empty.hidden = true;
  const article = document.createElement("article");
  article.className = `msg ${kind}`;

  const who = document.createElement("span");
  who.className = "sr";
  who.textContent = kind === "user" ? "Tú" : kind === "error" ? "Aviso" : "PAP";

  const body = document.createElement("div");
  body.className = "body";
  body.append(node);

  const time = document.createElement("time");
  const when = at ? new Date(at) : new Date();
  time.dateTime = when.toISOString();
  time.textContent = when.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });

  article.append(who, body, time);
  if (options.prepend) {
    const first = log.querySelector(".msg");
    if (first) log.insertBefore(article, first);
    else log.append(article);
  } else {
    log.append(article);
    if (options.stick !== false) log.scrollTop = log.scrollHeight;
  }
  return article;
}

function textNode(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node;
}

function typingNode() {
  const note = document.createElement("p");
  note.className = "pending";
  note.textContent = "Respondiendo";
  return note;
}

async function renderReply(markdown, at, options) {
  const node = document.createElement("div");
  node.className = "md";
  node.innerHTML = marked.parse(markdown);
  const article = addMessage("assistant", node, at, options);
  const diagrams = article.querySelectorAll(".mermaid");
  if (diagrams.length) {
    await mermaid.run({ nodes: diagrams, suppressErrors: true });
    if (!options?.prepend) log.scrollTop = log.scrollHeight;
  }
  return article;
}

function paintChat(message, options) {
  if (message.role === "user") return addMessage("user", textNode(message.body), message.cat, options);
  return renderReply(message.body, message.cat, options);
}

function clearLog() {
  log.querySelectorAll(".msg").forEach((node) => node.remove());
  empty.hidden = false;
  historyHasMore = false;
  historyPage = 1;
}

function setCurrent(chat) {
  currentId = chat.uid;
  sessionStorage.setItem(STORAGE_KEY, currentId);
  chatTitle.textContent = labelOf(chat);
  for (const button of chatList.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.uid === currentId);
  }
}

function appendChatButton(chat) {
  const item = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.uid = chat.uid;
  button.dataset.uat = chat.uat;
  button.textContent = labelOf(chat);
  button.classList.toggle("active", chat.uid === currentId);
  button.addEventListener("click", () => openChat(chat));
  item.append(button);
  chatList.append(item);
}

async function loadChats(before) {
  if (loadingChats) return;
  loadingChats = true;
  try {
    const params = new URLSearchParams({ limit: "20" });
    if (before) params.set("before", before);
    const response = await fetch(`/chats?${params}`);
    if (!response.ok) return;
    const data = await response.json();
    for (const chat of data.chats || []) appendChatButton(chat);
    chatsHasMore = Boolean(data.hasMore);
    const last = (data.chats || []).at(-1);
    if (last) oldestChatUat = last.uat;
    return data.chats || [];
  } finally {
    loadingChats = false;
  }
}

async function openChat(chat) {
  setCurrent(chat);
  clearLog();
  const response = await fetch(`/chat/${chat.uid}/history?page=1&limit=30`);
  if (!response.ok) return;
  const data = await response.json();
  historyHasMore = Boolean(data.hasMore);
  historyPage = data.page || 1;
  for (const message of data.messages || []) await paintChat(message);
  log.scrollTop = log.scrollHeight;
}

async function loadOlder() {
  if (!currentId || !historyHasMore || loadingOlder) return;
  loadingOlder = true;
  const previousHeight = log.scrollHeight;
  const nextPage = historyPage + 1;
  try {
    const response = await fetch(`/chat/${currentId}/history?page=${nextPage}&limit=30`);
    if (!response.ok) return;
    const data = await response.json();
    historyHasMore = Boolean(data.hasMore);
    historyPage = data.page || nextPage;
    const messages = data.messages || [];
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      await paintChat(messages[index], { prepend: true, stick: false });
    }
    log.scrollTop += log.scrollHeight - previousHeight;
  } finally {
    loadingOlder = false;
  }
}

function startNewChat() {
  currentId = null;
  sessionStorage.removeItem(STORAGE_KEY);
  clearLog();
  chatTitle.textContent = "Chat nuevo";
  for (const button of chatList.querySelectorAll("button")) button.classList.remove("active");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || send.disabled) return;

  addMessage("user", textNode(message));
  input.value = "";
  input.style.height = "auto";
  send.disabled = true;
  log.setAttribute("aria-busy", "true");

  const pending = addMessage("assistant", typingNode());
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, chat_id: currentId }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`El servidor respondió ${response.status}. Vuelve a intentar.`);
    }
    const data = await response.json();
    pending.remove();
    await renderReply(data.reply || "");
    if (!currentId && data.chat_id) {
      const chat = {
        uid: data.chat_id,
        title: data.title || null,
        uat: new Date().toISOString(),
      };
      appendChatButton(chat);
      const button = chatList.querySelector(`button[data-uid="${chat.uid}"]`);
      if (button) chatList.prepend(button.parentElement);
      setCurrent(chat);
    } else if (data.title) {
      chatTitle.textContent = data.title;
      const button = chatList.querySelector(`button[data-uid="${currentId}"]`);
      if (button) button.textContent = data.title;
    }
  } catch (error) {
    pending.remove();
    const timedOut = error.name === "AbortError";
    addMessage(
      "error",
      textNode(timedOut ? "La respuesta tardó más de 2 minutos. Vuelve a enviarla." : error.message),
    );
  } finally {
    clearTimeout(timer);
    send.disabled = false;
    log.removeAttribute("aria-busy");
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
});

log.addEventListener("scroll", () => {
  if (log.scrollTop <= 0 && historyHasMore && log.scrollHeight > log.clientHeight) loadOlder();
});

chatList.addEventListener("scroll", () => {
  if (chatList.scrollTop + chatList.clientHeight >= chatList.scrollHeight - 8 && chatsHasMore) {
    loadChats(oldestChatUat);
  }
});

newChat.addEventListener("click", startNewChat);

boot();

async function boot() {
  const chats = await loadChats();
  const saved = sessionStorage.getItem(STORAGE_KEY);
  const known = (chats || []).find((chat) => chat.uid === saved);
  if (known) await openChat(known);
  else if (chats && chats.length) await openChat(chats[0]);
  else startNewChat();
}
