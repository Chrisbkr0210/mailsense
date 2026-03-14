/* MailSense V3 — Client JS */

// ── Utilitaires ──────────────────────────────────────────────────────────────

function getToken() {
  const params = new URLSearchParams(window.location.search);
  return params.get("token") || "";
}

function formatNum(n) {
  return Number(n).toLocaleString("fr-FR");
}

function catLabel(cat) {
  const labels = {
    ADMINISTRATIF:         "Administratif",
    BANQUE_FINANCE:        "Banque & Finance",
    FACTURES_PAIEMENTS:    "Factures & Paiements",
    CONTRATS_ABONNEMENTS:  "Contrats & Abonnements",
    EMPLOI_PRO:            "Emploi & Pro",
    SANTE:                 "Santé",
    TRANSPORT_VOYAGE:      "Transport & Voyage",
    NEWSLETTERS_MARKETING: "Newsletters",
    RESEAUX_SOCIAUX:       "Réseaux Sociaux",
    PERSONNEL:             "Personnel",
    SPAM_PHISHING:         "Spam & Phishing",
  };
  return labels[cat] || cat;
}

const ALL_CATS = [
  "ADMINISTRATIF","BANQUE_FINANCE","FACTURES_PAIEMENTS","CONTRATS_ABONNEMENTS",
  "EMPLOI_PRO","SANTE","TRANSPORT_VOYAGE","NEWSLETTERS_MARKETING",
  "RESEAUX_SOCIAUX","PERSONNEL","SPAM_PHISHING",
];

// ── Page : Preview ───────────────────────────────────────────────────────────

async function initPreview() {
  const token = getToken();
  if (!token) { window.location.href = "/"; return; }

  const loadingEl  = document.getElementById("loading");
  const contentEl  = document.getElementById("content");
  const totalEl    = document.getElementById("total-count");
  const tableBody  = document.getElementById("email-table-body");
  const startBtn   = document.getElementById("start-btn");
  const corrections = {};

  try {
    const res  = await fetch("/api/preview/" + token);
    if (!res.ok) throw new Error("Erreur serveur " + res.status);
    const data = await res.json();

    totalEl.textContent = formatNum(data.total);
    loadingEl.style.display = "none";
    contentEl.style.display = "block";

    data.emails.forEach(function(em) {
      const tr = document.createElement("tr");

      const selectOpts = ALL_CATS.map(function(c) {
        return '<option value="' + c + '"' + (c === em.category ? " selected" : "") + '>' + catLabel(c) + '</option>';
      }).join("");

      tr.innerHTML =
        '<td><div class="email-sender">' + escHtml(em.sender) + '</div></td>' +
        '<td><div class="email-subject">' + escHtml(em.subject) + '</div></td>' +
        '<td><span class="badge cat-' + em.category + '">' + catLabel(em.category) + '</span></td>' +
        '<td><select class="cat-select" data-id="' + em.id + '">' + selectOpts + '</select></td>';

      tableBody.appendChild(tr);

      tr.querySelector("select").addEventListener("change", function(e) {
        corrections[em.id] = e.target.value;
        const badge = tr.querySelector(".badge");
        badge.className = "badge cat-" + e.target.value;
        badge.textContent = catLabel(e.target.value);
      });
    });

    startBtn.addEventListener("click", async function() {
      startBtn.disabled = true;
      startBtn.textContent = "Démarrage…";

      if (Object.keys(corrections).length > 0) {
        await fetch("/api/corrections/" + token, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ corrections }),
        });
      }

      window.location.href = "/processing?token=" + token;
    });

  } catch (err) {
    loadingEl.innerHTML = '<div class="state-icon">⚠️</div><p>Erreur : ' + err.message + '</p>';
  }
}

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Page : Processing ────────────────────────────────────────────────────────

function initProcessing() {
  const token = getToken();
  if (!token) { window.location.href = "/"; return; }

  const pctEl      = document.getElementById("pct");
  const fillEl     = document.getElementById("bar-fill");
  const countEl    = document.getElementById("count-text");
  const catGridEl  = document.getElementById("cat-grid");
  const statusEl   = document.getElementById("status-text");

  function updateUI(data) {
    const pct = data.total > 0 ? Math.round(data.processed / data.total * 100) : 0;
    pctEl.textContent    = pct + "%";
    fillEl.style.width   = pct + "%";
    countEl.textContent  = formatNum(data.processed) + " / " + formatNum(data.total) + " emails traités";

    if (data.categories) {
      catGridEl.innerHTML = "";
      ALL_CATS.forEach(function(cat) {
        const n = data.categories[cat] || 0;
        if (n === 0) return;
        const div = document.createElement("div");
        div.className = "cat-item";
        div.innerHTML =
          '<span class="cat-name">' + catLabel(cat) + '</span>' +
          '<span class="cat-count">' + formatNum(n) + '</span>';
        catGridEl.appendChild(div);
      });
    }

    if (data.status === "done") {
      window.location.href = "/result?token=" + token;
    }
    if (data.status === "error") {
      statusEl.textContent = "Erreur : " + (data.error || "inconnue");
    }
  }

  // SSE
  const evtSource = new EventSource("/api/process/" + token);
  evtSource.onmessage = function(e) {
    try {
      const data = JSON.parse(e.data);
      updateUI(data);
    } catch (_) {}
  };
  evtSource.onerror = function() {
    // Fallback polling si SSE coupe
    evtSource.close();
    pollStatus(token, updateUI);
  };
}

function pollStatus(token, cb) {
  const interval = setInterval(async function() {
    try {
      const res  = await fetch("/api/status/" + token);
      const data = await res.json();
      cb(data);
      if (data.status === "done" || data.status === "error") {
        clearInterval(interval);
      }
    } catch (_) {}
  }, 2000);
}

// ── Page : Result ────────────────────────────────────────────────────────────

async function initResult() {
  const token = getToken();
  if (!token) { window.location.href = "/"; return; }

  try {
    const res  = await fetch("/api/status/" + token);
    const data = await res.json();

    if (data.status !== "done") {
      window.location.href = "/processing?token=" + token;
      return;
    }

    document.getElementById("total-done").textContent = formatNum(data.total);
    document.getElementById("user-email").textContent = data.email || "";

    const catListEl = document.getElementById("cat-list");
    let max = 0;
    ALL_CATS.forEach(function(cat) {
      const n = data.categories[cat] || 0;
      if (n > max) max = n;
    });

    ALL_CATS.forEach(function(cat) {
      const n = data.categories[cat] || 0;
      if (n === 0) return;
      const pct = max > 0 ? Math.round(n / max * 100) : 0;
      const div = document.createElement("div");
      div.style.marginBottom = "12px";
      div.innerHTML =
        '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
          '<span class="badge cat-' + cat + '">' + catLabel(cat) + '</span>' +
          '<span style="font-weight:700">' + formatNum(n) + '</span>' +
        '</div>' +
        '<div class="progress-bar-bg" style="height:8px">' +
          '<div class="progress-bar-fill" style="width:' + pct + '%"></div>' +
        '</div>';
      catListEl.appendChild(div);
    });

  } catch (err) {
    document.getElementById("total-done").textContent = "?";
  }
}

// ── Auto-init ─────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
  const path = window.location.pathname;
  if (path === "/preview")    initPreview();
  if (path === "/processing") initProcessing();
  if (path === "/result")     initResult();
});
