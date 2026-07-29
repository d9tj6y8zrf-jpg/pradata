const dataPaths = {
  records: "./data/records.json",
  history: "./data/history.json",
  status: "./data/status.json",
};

const state = {
  records: [],
  history: [],
  sources: [],
};

const labels = {
  topics: {
    administracio: "Administració",
    municipi: "Municipi",
    contractacio: "Contractació",
    subvencions: "Subvencions",
    pressupost: "Pressupost",
    urbanisme_i_obres: "Urbanisme i obres",
    terminis_i_propietats: "Terminis i propietats",
    territori: "Territori",
    govern: "Govern",
    personal: "Personal",
  },
  priorities: {
    critica: "Atenció prioritària",
    alta: "Important",
    informativa: "Informativa",
  },
  sourceStates: {
    ok: "Consulta correcta",
    warning: "Consulta parcial",
    error: "No disponible",
  },
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value = "") {
  try {
    const url = new URL(value, window.location.href);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function formatDate(value, includeTime = false) {
  if (!value) return "Data no extreta";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ca-ES", {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" } : {}),
  }).format(date);
}

function normalize(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`No s'ha pogut carregar ${path}`);
  return response.json();
}

function setOptions(elementId, values, labelMap = {}) {
  const select = document.getElementById(elementId);
  for (const value of [...new Set(values.filter(Boolean))].sort()) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelMap[value] || value;
    select.append(option);
  }
}

function renderRecords() {
  const list = document.getElementById("records-list");
  const query = normalize(document.getElementById("search").value);
  const topic = document.getElementById("topic").value;
  const source = document.getElementById("source").value;
  const filtered = state.records.filter((record) => {
    const haystack = normalize(
      [
        record.title,
        record.summary,
        record.source_name,
        record.registry,
        record.topic,
      ].join(" "),
    );
    return (
      (!query || haystack.includes(query)) &&
      (!topic || record.topic === topic) &&
      (!source || record.source_name === source)
    );
  });

  document.getElementById("results-summary").textContent =
    `${filtered.length} referència${filtered.length === 1 ? "" : "s"} trobada${filtered.length === 1 ? "" : "es"}.`;

  if (!filtered.length) {
    list.innerHTML =
      '<p class="empty">No hi ha coincidències amb aquests filtres. Prova una cerca més general.</p>';
    return;
  }

  list.innerHTML = filtered
    .slice(0, 120)
    .map((record) => {
      const topicLabel = labels.topics[record.topic] || record.topic || "Informació";
      const priority = record.priority || "informativa";
      const priorityLabel = labels.priorities[priority] || priority;
      const statusLabel =
        record.status === "verificat" ? "Verificat amb font" : "Detecció automàtica";
      return `
        <article class="record-card">
          <div class="record-meta">
            <span class="pill">${escapeHtml(topicLabel)}</span>
            <span class="pill priority-${escapeHtml(priority)}">${escapeHtml(priorityLabel)}</span>
            <span class="pill">${escapeHtml(statusLabel)}</span>
          </div>
          <h3>${escapeHtml(record.title)}</h3>
          <p>${escapeHtml(record.summary || "Consulteu la font original.")}</p>
          <div class="record-footer">
            <div class="record-source">
              <strong>${escapeHtml(record.source_name)}</strong>
              <span>${escapeHtml(record.date ? formatDate(record.date) : `Detectat ${formatDate(record.detected_at)}`)}</span>
              ${record.registry ? `<span> · ${escapeHtml(record.registry)}</span>` : ""}
            </div>
            <a href="${safeUrl(record.url)}" target="_blank" rel="noopener noreferrer">
              Font oficial <span aria-hidden="true">↗</span>
            </a>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderChanges() {
  const list = document.getElementById("changes-list");
  const visible = state.history
    .filter((event) => !["seed", "baseline"].includes(event.type))
    .slice(0, 12);
  if (!visible.length) {
    list.innerHTML =
      '<p class="empty">Encara no hi ha canvis automàtics registrats. La primera execució crearà la línia de base.</p>';
    return;
  }
  list.innerHTML = visible
    .map(
      (event) => `
        <article class="change">
          <time datetime="${escapeHtml(event.detected_at)}">${escapeHtml(formatDate(event.detected_at, true))}</time>
          <div>
            <h3>${escapeHtml(event.title)}</h3>
            <p>${escapeHtml(event.description)}</p>
          </div>
          <a href="${safeUrl(event.url)}" target="_blank" rel="noopener noreferrer">
            Comprovar <span aria-hidden="true">↗</span>
          </a>
        </article>
      `,
    )
    .join("");
}

function renderSources() {
  const list = document.getElementById("sources-list");
  if (!state.sources.length) {
    list.innerHTML = '<p class="empty">Encara no hi ha una execució registrada.</p>';
    return;
  }
  list.innerHTML = state.sources
    .map(
      (source) => `
        <article class="source-card ${escapeHtml(source.state)}">
          <div class="source-state">
            <span class="state-dot" aria-hidden="true"></span>
            ${escapeHtml(labels.sourceStates[source.state] || source.state)}
          </div>
          <h3>${escapeHtml(source.name)}</h3>
          <p>${escapeHtml(source.message)} Detectades en aquesta lectura: ${Number(source.item_count) || 0}.</p>
          <a href="${safeUrl(source.url)}" target="_blank" rel="noopener noreferrer">
            Obrir la font <span aria-hidden="true">↗</span>
          </a>
        </article>
      `,
    )
    .join("");
}

function showLoadError(error) {
  const message =
    "No s'han pogut carregar les dades. Torna-ho a provar o consulta els fitxers JSON i CSV.";
  for (const id of ["changes-list", "records-list", "sources-list"]) {
    document.getElementById(id).innerHTML =
      `<p class="error-message">${escapeHtml(message)}</p>`;
  }
  console.error(error);
}

async function init() {
  try {
    const [recordsDoc, historyDoc, statusDoc] = await Promise.all([
      getJson(dataPaths.records),
      getJson(dataPaths.history),
      getJson(dataPaths.status),
    ]);
    state.records = recordsDoc.records || [];
    state.history = historyDoc.events || [];
    state.sources = statusDoc.sources || [];

    document.getElementById("record-count").textContent = state.records.length;
    document.getElementById("source-count").textContent = state.sources.length;
    document.getElementById("last-updated").textContent = formatDate(
      recordsDoc.meta?.updated_at,
      true,
    );

    setOptions(
      "topic",
      state.records.map((record) => record.topic),
      labels.topics,
    );
    setOptions(
      "source",
      state.records.map((record) => record.source_name),
    );

    renderChanges();
    renderRecords();
    renderSources();

    for (const id of ["search", "topic", "source"]) {
      document.getElementById(id).addEventListener("input", renderRecords);
      document.getElementById(id).addEventListener("change", renderRecords);
    }
    document.getElementById("filters").addEventListener("submit", (event) => {
      event.preventDefault();
      renderRecords();
    });
  } catch (error) {
    showLoadError(error);
  }
}

init();
