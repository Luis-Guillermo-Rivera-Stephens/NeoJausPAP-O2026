const log = document.getElementById("log");
const empty = document.getElementById("empty");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const send = form.querySelector("button");

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

function addMessage(kind, node) {
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
  const now = new Date();
  time.dateTime = now.toISOString();
  time.textContent = now.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });

  article.append(who, body, time);
  log.append(article);
  log.scrollTop = log.scrollHeight;
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

async function renderReply(markdown) {
  const node = document.createElement("div");
  node.className = "md";
  node.innerHTML = marked.parse(markdown);
  const article = addMessage("assistant", node);
  const diagrams = article.querySelectorAll(".mermaid");
  if (diagrams.length) {
    await mermaid.run({ nodes: diagrams, suppressErrors: true });
    log.scrollTop = log.scrollHeight;
  }
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
      body: JSON.stringify({ message }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`El servidor respondió ${response.status}. Vuelve a intentar.`);
    }
    const data = await response.json();
    pending.remove();
    await renderReply(data.reply || "");
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
