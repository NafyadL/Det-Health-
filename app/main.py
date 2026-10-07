"""Local FastAPI application for importing and exploring Apple Health exports."""

import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, AsyncIterator, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from app.apple_health import (
    ImportFileError,
    ImportSizeLimitError,
    iter_health_records,
)
from app.database import check_database, initialize_database
from app.determinants import (
    ACTIVITY_METRICS,
    DETERMINANT_DOMAINS,
    HEALTH_INDICATOR_METRICS,
)
from app.evidence import EVIDENCE_CATALOG
from app.security import (
    PASSWORD_VERIFIER,
    decrypt,
    derive_key,
    encrypt,
    valid_username,
    verifier_matches,
)

DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "det_health.sqlite3"
)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(Credentials):
    password: str = Field(min_length=12, max_length=1024)


class TrendsRequest(Credentials):
    metric_type: str = Field(min_length=1, max_length=200)
    bucket: Literal["day", "week", "month"] = "day"
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "TrendsRequest":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must be on or before end_date.")
        return self


class BehaviorEntry(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=1024)
    category: Literal["activity", "sleep", "tobacco", "alcohol", "nutrition"]
    reported_on: date
    values: dict[str, object]


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Det(Health) — local health data</title>
  <style>
    :root { color-scheme: light; font: 16px/1.55 Inter, ui-sans-serif, system-ui, sans-serif; color: #173331; background: #f3f7f5; }
    * { box-sizing: border-box; }
    body { max-width: 1100px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    h1, h2, h3, h4 { line-height: 1.2; letter-spacing: -.02em; }
    h1 { font-size: clamp(2.25rem, 6vw, 3.8rem); margin: .25rem 0; }
    h2 { font-size: 1.55rem; margin: 0 0 .6rem; }
    h3 { font-size: 1.15rem; margin: .2rem 0 .5rem; }
    p { max-width: 75ch; }
    header { padding: 2rem; color: white; border-radius: 22px; background: linear-gradient(120deg, #143c37, #267766 70%, #65a88d); box-shadow: 0 16px 40px #17333122; }
    header p { color: #e1f2ea; }
    .eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: .76rem; font-weight: 750; opacity: .85; }
    fieldset, section { border: 1px solid #dce7e2; border-radius: 16px; padding: clamp(1rem, 3vw, 1.5rem); margin: 1.1rem 0; background: #fff; box-shadow: 0 5px 18px #1733310a; }
    label { display: inline-grid; gap: .35rem; margin: .4rem .8rem .4rem 0; font-size: .91rem; font-weight: 600; }
    input, select, button { font: inherit; padding: .62rem .75rem; border: 1px solid #c8d7d1; border-radius: 9px; background: white; color: #173331; }
    input:focus, select:focus, button:focus-visible, a:focus-visible { outline: 3px solid #84cbb0; outline-offset: 2px; }
    button { cursor: pointer; border-color: #246c5e; background: #246c5e; color: white; font-weight: 700; transition: transform .15s, background .15s; }
    button:hover { background: #174f45; transform: translateY(-1px); }
    button.secondary { background: #eef6f2; color: #205e52; }
    .note { background: #e7f2ed; padding: .85rem 1rem; border-radius: 10px; }
    .section-intro { color: #58716a; }
    .domain-grid, .insight-grid, .evidence-grid, .signal-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 270px), 1fr)); margin-top: 1rem; }
    .domain-card, .insight-card, .evidence-card, .signal-card, .indicator-card { padding: 1rem; border: 1px solid #dce7e2; border-radius: 13px; background: #fbfdfc; }
    .domain-card { border-top: 4px solid #7ba995; }
    .domain-card.available { border-top-color: #26826d; }
    .domain-card.uncollected { background: #f7f8f7; color: #667670; }
    .status { display: inline-block; padding: .18rem .55rem; border-radius: 999px; background: #e8f2ed; color: #28634f; font-size: .78rem; font-weight: 700; }
    .status.muted { background: #edf0ef; color: #5d6b66; }
    .insight-card { background: #f0f8f4; border-color: #cfe5d8; }
    .insight-card strong { color: #185d4d; }
    .sparkline { display: flex; align-items: end; gap: 4px; height: 45px; margin: .5rem 0; }
    .sparkline span { flex: 1; min-width: 3px; background: #56a489; border-radius: 4px 4px 0 0; }
    .evidence-card { background: #f9faf8; }
    .evidence-card a, a { color: #176853; font-weight: 650; }
    .tag { display: inline-block; padding: .15rem .45rem; margin: .12rem; border-radius: 5px; background: #edf3f0; font-size: .8rem; }
    .muted { color: #62756e; }
    #message { position: sticky; bottom: .5rem; padding: .65rem 1rem; border-radius: 10px; background: #173e37; color: white; min-height: 1em; white-space: pre-wrap; }
    table { border-collapse: collapse; width: 100%; margin-top: .8rem; }
    th, td { text-align: left; border-bottom: 1px solid #d5dfdc; padding: .6rem; }
    @media (max-width: 600px) { body { padding: 1rem .8rem 3rem; } header { padding: 1.4rem; } }
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">Your data, on your device</div>
    <h1>Det(Health)</h1>
    <p>Understand the context around your health data. Private by design,
    descriptive by intent.</p>
  </header>
  <p class="note">Local prototype. Imported health records are encrypted before
  storage. Personal patterns are descriptive; population evidence is context,
  not an individual prediction or medical advice.</p>
  <fieldset>
    <legend>Local account</legend>
    <label>Username <input id="username" autocomplete="username" minlength="3" maxlength="32"></label>
    <label>Password <input id="password" type="password" autocomplete="off" minlength="12" maxlength="1024"></label>
    <button id="create-account" type="button">Create account</button>
  </fieldset>
  <section>
    <h2>Import Apple Health export</h2>
    <p>Select the unzipped <code>export.xml</code> or the original Apple Health
    export <code>.zip</code> file (maximum 100 MiB compressed).</p>
    <input id="health-file" type="file" accept=".xml,.zip">
    <button id="import-file" type="button">Import file</button>
    <button id="load-metrics" type="button">Load available metrics</button>
  </section>
  <section>
    <h2>Explore trends</h2>
    <label>Metric <select id="metric" disabled><option value="">Load metrics first</option></select></label>
    <label>Group by
      <select id="bucket"><option value="day">Day</option><option value="week">Week</option><option value="month">Month</option></select>
    </label>
    <button id="analyze" type="button">Show trend</button>
    <div id="results"></div>
  </section>
  <section>
    <h2>Your determinants-of-health map</h2>
    <p class="section-intro">See what your data can describe, how it fits into
    broader health determinants, and what population research says about those
    domains. Personal observations and research context are shown separately.</p>
    <button id="load-determinants" type="button">Refresh my insights</button>
    <div id="determinant-results"></div>
  </section>
  <section>
    <h2>Behavioral context (optional)</h2>
    <p>These entries are self-reported and encrypted locally. They are not
    diagnoses and are not used to calculate personal risk.</p>
    <label>Factor
      <select id="behavior-category">
        <option value="activity">Physical activity</option>
        <option value="sleep">Sleep</option>
        <option value="tobacco">Tobacco / second-hand smoke</option>
        <option value="alcohol">Alcohol</option>
        <option value="nutrition">Nutrition</option>
      </select>
    </label>
    <label>Date <input id="behavior-date" type="date"></label>
    <div id="behavior-fields"></div>
    <button id="save-behavior" type="button">Save private entry</button>
    <button id="load-behavior" type="button">View my entries</button>
    <div id="behavior-results"></div>
  </section>
  <section>
    <h2>Evidence guide: population-level associations</h2>
    <p>These summaries describe population-level evidence from the linked
    public-health sources. They do not estimate your personal risk, establish
    that an individual outcome was caused by a behavior, or provide medical advice.
    Sources can be opened when internet access is available; no source is fetched
    automatically by this app.</p>
    <div id="evidence-cards"></div>
  </section>
  <p id="message" role="status" aria-live="polite"></p>
  <script>
    const byId = (id) => document.getElementById(id);
    const credentials = () => ({username: byId("username").value, password: byId("password").value});
    const message = (text) => { byId("message").textContent = text; };
    async function responseData(response) {
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Request failed.");
      return data;
    }
    const behaviorFields = {
      activity: [
        ["moderate_minutes", "Moderate activity (minutes; optional)", "number", "0", "1440"],
        ["vigorous_minutes", "Vigorous activity (minutes; optional)", "number", "0", "1440"]
      ],
      sleep: [["duration_hours", "Sleep duration (hours)", "number", "0.1", "24"]],
      tobacco: [
        ["status", "Tobacco use status", "select", "never", "current", "former"],
        ["secondhand_exposure", "Second-hand smoke exposure today", "checkbox"]
      ],
      alcohol: [
        ["drinks", "Number of drinks (your own unit)", "number", "0", "100"],
        ["drink_unit", "Describe your drink unit (for example, local serving)", "text"]
      ],
      nutrition: [
        ["fruit_vegetable_servings", "Fruit and vegetable servings (self-counted)", "number", "0", "50"]
      ]
    };
    function renderBehaviorFields() {
      const container = byId("behavior-fields");
      container.replaceChildren();
      for (const [name, label, type, min, max, ...options] of behaviorFields[byId("behavior-category").value]) {
        const wrapper = document.createElement("label");
        wrapper.textContent = label;
        let input;
        if (type === "select") {
          input = document.createElement("select");
          for (const value of options) {
            const option = document.createElement("option");
            option.value = value; option.textContent = value; input.append(option);
          }
        } else {
          input = document.createElement("input");
          input.type = type;
          if (min) input.min = min;
          if (max) input.max = max;
          if (type === "number") input.step = "any";
        }
        input.id = `behavior-${name}`;
        wrapper.append(input);
        container.append(wrapper);
      }
    }
    function readBehaviorValues() {
      const category = byId("behavior-category").value;
      const values = {};
      for (const [name, , type] of behaviorFields[category]) {
        const input = byId(`behavior-${name}`);
        if (type === "checkbox") values[name] = input.checked;
        else if (type === "number" && input.value !== "") values[name] = Number(input.value);
        else if (input.value !== "") values[name] = input.value;
      }
      return values;
    }
    function renderEvidence(cards) {
      const container = byId("evidence-cards");
      container.replaceChildren();
      container.className = "evidence-grid";
      for (const item of cards) {
        const article = document.createElement("article");
        article.className = "evidence-card";
        const title = document.createElement("h3");
        title.textContent = item.title;
        const summary = document.createElement("p");
        summary.textContent = item.summary;
        const domains = document.createElement("p");
        domains.textContent = `Health domains discussed: ${item.health_domains.join(", ")}.`;
        const source = document.createElement("a");
        source.href = item.source_url;
        source.textContent = item.source_name;
        source.rel = "noreferrer";
        source.target = "_blank";
        article.append(title, summary, domains, source);
        container.append(article);
      }
    }
    async function loadBehaviorEntries() {
      const data = await responseData(await fetch("/behaviors", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(credentials())
      }));
      const target = byId("behavior-results");
      target.replaceChildren();
      if (!data.entries.length) {
        target.textContent = "No behavioral entries recorded yet.";
        return;
      }
      for (const entry of data.entries) {
        const paragraph = document.createElement("p");
        paragraph.textContent = `${entry.reported_on} — ${entry.category}: ${Object.entries(entry.values).map(([key, value]) => `${key.replaceAll("_", " ")} ${value}`).join(", ")}`;
        target.append(paragraph);
      }
    }
    function renderDeterminantMap(result) {
      const target = byId("determinant-results");
      target.replaceChildren();
      const overview = document.createElement("p");
      overview.className = "note";
      const availableCount = result.domains.filter(domain => domain.status === "data_available").length;
      overview.textContent = `${availableCount} of ${result.domains.length} determinant domains have data in this prototype. This map describes your records; it does not infer causes or predict outcomes.`;
      target.append(overview);
      const domainGrid = document.createElement("div");
      domainGrid.className = "domain-grid";
      for (const domain of result.domains) {
        const article = document.createElement("article");
        article.className = `domain-card ${domain.status === "not_collected" ? "uncollected" : "available"}`;
        const title = document.createElement("h3");
        title.textContent = domain.name;
        const definition = document.createElement("p");
        definition.className = "muted";
        definition.textContent = domain.definition;
        const status = document.createElement("span");
        status.className = `status ${domain.status === "not_collected" ? "muted" : ""}`;
        status.textContent = domain.status === "not_collected"
          ? "Not collected"
          : domain.status === "no_records_yet"
            ? "No records yet"
            : `${domain.signals.length} signal type${domain.signals.length === 1 ? "" : "s"} found`;
        article.append(title, definition, status);
        if (domain.insights.length) {
          const insightHeading = document.createElement("h4");
          insightHeading.textContent = "What your records show";
          article.append(insightHeading);
          const insightGrid = document.createElement("div");
          insightGrid.className = "insight-grid";
          for (const insight of domain.insights) {
            const card = document.createElement("div");
            card.className = "insight-card";
            const insightTitle = document.createElement("strong");
            insightTitle.textContent = insight.title;
            const insightText = document.createElement("p");
            insightText.textContent = insight.text;
            card.append(insightTitle, insightText);
            insightGrid.append(card);
          }
          article.append(insightGrid);
        }
        for (const signal of domain.signals) {
          const signalCard = document.createElement("div");
          signalCard.className = "signal-card";
          const heading = document.createElement("h4");
          heading.textContent = signal.label;
          const source = document.createElement("span");
          source.className = "tag";
          source.textContent = signal.source;
          const details = document.createElement("p");
          details.textContent = signal.description;
          signalCard.append(heading, source, details);
          if (signal.daily_values) {
            const values = Object.entries(signal.daily_values).slice(-14);
            if (values.length > 1) {
              const chart = document.createElement("div");
              chart.className = "sparkline";
              chart.setAttribute("role", "img");
              chart.setAttribute("aria-label", `${signal.label} daily values over time`);
              const maxValue = Math.max(...values.map(([, value]) => Number(value)), 1);
              for (const [day, value] of values) {
                const bar = document.createElement("span");
                bar.style.height = `${Math.max(5, Number(value) / maxValue * 100)}%`;
                bar.title = `${day}: ${value} ${signal.unit}`;
                chart.append(bar);
              }
              signalCard.append(chart);
            }
          }
          if (signal.latest_entries) {
            for (const entry of signal.latest_entries) {
              const line = document.createElement("p");
              line.textContent = `${entry.reported_on}: ${Object.entries(entry.values).map(([key, value]) => `${key.replaceAll("_", " ")} ${value}`).join(", ")}`;
              signalCard.append(line);
            }
          }
          article.append(signalCard);
        }
        for (const source of domain.evidence) {
          const evidenceCard = document.createElement("div");
          evidenceCard.className = "evidence-card";
          const evidenceTitle = document.createElement("strong");
          evidenceTitle.textContent = source.title;
          const evidenceSummary = document.createElement("p");
          evidenceSummary.textContent = source.summary;
          const link = document.createElement("a");
          link.href = source.source_url;
          link.textContent = `Read ${source.source_name}`;
          link.rel = "noreferrer";
          link.target = "_blank";
          evidenceCard.append(evidenceTitle, evidenceSummary, link);
          article.append(evidenceCard);
        }
        domainGrid.append(article);
      }
      target.append(domainGrid);
      for (const [headingText, measures] of [
        ["Health indicators (not determinant domains)", result.health_indicators],
        ["Imported measures not mapped yet", result.unmapped_measures]
      ]) {
        const article = document.createElement("article");
        article.className = "indicator-card";
        const heading = document.createElement("h3");
        heading.textContent = headingText;
        article.append(heading);
        if (!measures.length) {
          const empty = document.createElement("p");
          empty.textContent = "No records.";
          article.append(empty);
        }
        for (const measure of measures) {
          const card = document.createElement("div");
          card.className = "signal-card";
          const label = document.createElement("strong");
          label.textContent = measure.label;
          const line = document.createElement("p");
          line.textContent = measure.description;
          card.append(label, line);
          if (measure.insight) {
            const insight = document.createElement("p");
            insight.className = "insight-card";
            insight.textContent = measure.insight;
            card.append(insight);
          }
          article.append(card);
        }
        target.append(article);
      }
    }
    byId("behavior-category").addEventListener("change", renderBehaviorFields);
    byId("create-account").addEventListener("click", async () => {
      try {
        await responseData(await fetch("/users", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(credentials())
        }));
        message("Account created on this device.");
      } catch (error) {
        message(error.message.includes("already exists")
          ? "This account already exists. Enter its existing username and password to continue; account creation is not sign-in."
          : error.message);
      }
    });
    byId("import-file").addEventListener("click", async () => {
      const file = byId("health-file").files[0];
      if (!file) { message("Choose an Apple Health export file first."); return; }
      const body = new FormData();
      body.append("file", file);
      body.append("username", byId("username").value);
      body.append("password", byId("password").value);
      try {
        const result = await responseData(await fetch("/imports/apple-health", {method: "POST", body}));
        message(result.imported === 0 && result.duplicates > 0
          ? `Import succeeded: all ${result.duplicates} quantity records were already present; no new records added. ${result.skipped} unsupported records skipped.`
          : `Import complete: ${result.imported} added, ${result.duplicates} duplicates ignored, ${result.skipped} unsupported records skipped.`);
      } catch (error) { message(error.message); }
    });
    byId("load-metrics").addEventListener("click", async () => {
      try {
        const data = await responseData(await fetch("/metrics", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(credentials())
        }));
        const select = byId("metric");
        select.replaceChildren();
        for (const item of data.metrics) {
          const option = document.createElement("option");
          option.value = item.type;
          option.textContent = `${item.type} (${item.units.join(", ")}; ${item.count} records)`;
          select.append(option);
        }
        select.disabled = data.metrics.length === 0;
        if (!data.metrics.length) {
          const option = document.createElement("option");
          option.textContent = "No imported metrics";
          select.append(option);
        }
        message(`Loaded ${data.metrics.length} metric types.`);
      } catch (error) { message(error.message); }
    });
    byId("analyze").addEventListener("click", async () => {
      if (!byId("metric").value) { message("Load metrics and choose a metric first."); return; }
      try {
        const data = await responseData(await fetch("/trends", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({...credentials(), metric_type: byId("metric").value, bucket: byId("bucket").value})
        }));
        const target = byId("results");
        target.replaceChildren();
        const table = document.createElement("table");
        const head = document.createElement("tr");
        for (const title of ["Period", "Unit", "Count", "Average", "Minimum", "Maximum"]) {
          const cell = document.createElement("th"); cell.textContent = title; head.append(cell);
        }
        const thead = document.createElement("thead"); thead.append(head); table.append(thead);
        const tbody = document.createElement("tbody");
        for (const row of data.trends) {
          const tr = document.createElement("tr");
          for (const value of [row.period, row.unit, row.count, row.average, row.minimum, row.maximum]) {
            const cell = document.createElement("td"); cell.textContent = String(value); tr.append(cell);
          }
          tbody.append(tr);
        }
        table.append(tbody); target.append(table);
        message(`Showing ${data.trends.length} descriptive ${byId("bucket").value} summaries.`);
      } catch (error) { message(error.message); }
    });
    byId("save-behavior").addEventListener("click", async () => {
      const category = byId("behavior-category").value;
      const values = readBehaviorValues();
      if (!byId("behavior-date").value) { message("Select the date for this entry."); return; }
      if (!Object.keys(values).length || (category === "activity" && !Object.keys(values).length)) {
        message("Enter at least one value for this factor."); return;
      }
      try {
        const result = await responseData(await fetch("/behaviors/entry", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({...credentials(), category, reported_on: byId("behavior-date").value, values})
        }));
        message(result.duplicate
          ? "This exact behavioral entry was already saved; no additional copy was stored."
          : "Behavioral entry encrypted and saved locally.");
      } catch (error) { message(error.message); }
    });
    byId("load-behavior").addEventListener("click", async () => {
      try { await loadBehaviorEntries(); message("Loaded your private behavioral entries."); }
      catch (error) { message(error.message); }
    });
    byId("load-determinants").addEventListener("click", async () => {
      try {
        const result = await responseData(await fetch("/determinants", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(credentials())
        }));
        renderDeterminantMap(result);
        message("Built your determinant-domain map from locally stored records.");
      } catch (error) { message(error.message); }
    });
    renderBehaviorFields();
    byId("behavior-date").value = new Date().toISOString().slice(0, 10);
    fetch("/evidence").then(responseData).then(data => renderEvidence(data.evidence))
      .catch(error => message(`Could not load the local evidence guide: ${error.message}`));
  </script>
</body>
</html>"""


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _authenticated_user(
    connection: sqlite3.Connection, username: str, password: str
) -> tuple[int, bytes]:
    user = connection.execute(
        "SELECT id, salt, verifier FROM users WHERE username = ?", (username,)
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    key = derive_key(password, user["salt"])
    if not verifier_matches(key, user["verifier"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return int(user["id"]), key


def _fingerprint(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def _decode_record(key: bytes, encrypted_payload: bytes) -> dict[str, object]:
    return json.loads(decrypt(key, encrypted_payload))


def _validate_behavior_values(
    category: str, values: dict[str, object]
) -> dict[str, object]:
    allowed_fields = {
        "activity": {"moderate_minutes", "vigorous_minutes"},
        "sleep": {"duration_hours"},
        "tobacco": {"status", "secondhand_exposure"},
        "alcohol": {"drinks", "drink_unit"},
        "nutrition": {"fruit_vegetable_servings"},
    }
    if not values or not set(values) <= allowed_fields[category]:
        raise HTTPException(
            status_code=422,
            detail="Provide supported, non-empty values for the selected factor.",
        )
    required_fields = {
        "activity": set(),
        "sleep": {"duration_hours"},
        "tobacco": {"status"},
        "alcohol": {"drinks", "drink_unit"},
        "nutrition": {"fruit_vegetable_servings"},
    }
    if not required_fields[category] <= set(values):
        raise HTTPException(
            status_code=422,
            detail="Complete the required fields for the selected factor.",
        )

    numeric_ranges = {
        "activity": {
            "moderate_minutes": (0, 1440),
            "vigorous_minutes": (0, 1440),
        },
        "sleep": {"duration_hours": (0.1, 24)},
        "alcohol": {"drinks": (0, 100)},
        "nutrition": {"fruit_vegetable_servings": (0, 100)},
    }
    for name, bounds in numeric_ranges.get(category, {}).items():
        if name not in values:
            continue
        value = values[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not bounds[0] <= value <= bounds[1]
        ):
            raise HTTPException(
                status_code=422,
                detail=f"{name} must be a number between {bounds[0]} and {bounds[1]}.",
            )

    if category == "tobacco":
        if values.get("status") not in {"never", "former", "current"}:
            raise HTTPException(
                status_code=422,
                detail="Tobacco status must be never, former, or current.",
            )
        if "secondhand_exposure" in values and not isinstance(
            values["secondhand_exposure"], bool
        ):
            raise HTTPException(
                status_code=422,
                detail="secondhand_exposure must be true or false.",
            )
    if category == "alcohol":
        drink_unit = values.get("drink_unit")
        if (
            not isinstance(drink_unit, str)
            or not drink_unit.strip()
            or len(drink_unit) > 40
        ):
            raise HTTPException(
                status_code=422,
                detail="Describe the drink unit in 1-40 characters.",
            )
        values["drink_unit"] = drink_unit.strip()
        if "drinks" not in values:
            raise HTTPException(
                status_code=422, detail="Provide a number of drinks."
            )
    return values


def _bucket_period(timestamp: str, bucket: Literal["day", "week", "month"]) -> str:
    value = datetime.fromisoformat(timestamp)
    if bucket == "day":
        return value.date().isoformat()
    if bucket == "week":
        return (value.date() - timedelta(days=value.weekday())).isoformat()
    return value.strftime("%Y-%m")


def create_app(database_path: Path | str | None = None) -> FastAPI:
    """Create the app, optionally using a database path supplied by a test."""
    path = Path(
        database_path
        if database_path is not None
        else os.environ.get("DET_HEALTH_DB", DEFAULT_DATABASE_PATH)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(path)
        yield

    application = FastAPI(
        title="Det(Health)",
        description="Local-first health-data prototype.",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> str:
        return INDEX_HTML

    @application.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        try:
            check_database(path)
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=503,
                detail="The local database is unavailable.",
            ) from exc
        return {"status": "ok", "storage": "sqlite"}

    @application.get("/evidence", tags=["evidence"])
    def evidence_guide() -> dict[str, object]:
        return {
            "interpretation": (
                "Population-level evidence notes only. These summaries do not "
                "estimate personal risk or establish individual causation."
            ),
            "evidence": EVIDENCE_CATALOG,
        }

    @application.post("/determinants", tags=["analysis"])
    def get_determinant_map(
        request: Credentials,
    ) -> dict[str, object]:
        with closing(_connect(path)) as connection:
            with connection:
                user_id, key = _authenticated_user(
                    connection, request.username, request.password
                )
                wearable_rows = connection.execute(
                    """
                    SELECT encrypted_payload FROM health_records
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchall()
                behavior_rows = connection.execute(
                    """
                    SELECT encrypted_payload FROM behavior_entries
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchall()

        behavior_by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in behavior_rows:
            entry = _decode_record(key, row["encrypted_payload"])
            behavior_by_category[str(entry["category"])].append(entry)

        grouped_metrics: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(
            list
        )
        for row in wearable_rows:
            record = _decode_record(key, row["encrypted_payload"])
            grouped_metrics[(str(record["type"]), str(record["unit"]))].append(
                record
            )

        def summarize_metric(
            metric_type: str, unit: str, records: list[dict[str, object]]
        ) -> dict[str, object]:
            by_day: dict[str, list[float]] = defaultdict(list)
            for record in records:
                observed_date = datetime.fromisoformat(
                    str(record["start_date"])
                ).date().isoformat()
                by_day[observed_date].append(float(record["value"]))
            daily_total_metrics = ACTIVITY_METRICS.keys()
            daily_values = {
                day: sum(values) if metric_type in daily_total_metrics else
                sum(values) / len(values)
                for day, values in by_day.items()
            }
            dates = sorted(daily_values)
            values = list(daily_values.values())
            label = (
                ACTIVITY_METRICS.get(metric_type)
                or HEALTH_INDICATOR_METRICS.get(metric_type)
                or metric_type.removeprefix("HKQuantityTypeIdentifier")
            )
            change_insight = None
            if len(dates) >= 2:
                first_value = daily_values[dates[0]]
                last_value = daily_values[dates[-1]]
                if first_value != 0:
                    change_percent = (last_value - first_value) / abs(first_value) * 100
                    if abs(change_percent) >= 5:
                        direction = "higher" if change_percent > 0 else "lower"
                        change_insight = (
                            f"Your daily {label.lower()} was {abs(change_percent):.0f}% "
                            f"{direction} on {dates[-1]} than on {dates[0]} "
                            f"({last_value:g} vs {first_value:g} {unit}/day)."
                        )
                    else:
                        change_insight = (
                            f"Your daily {label.lower()} was similar on the first "
                            f"and last recorded days ({first_value:g} and "
                            f"{last_value:g} {unit}/day)."
                        )
            return {
                "metric_type": metric_type,
                "label": label,
                "unit": unit,
                "count": len(records),
                "days": len(dates),
                "first_seen": dates[0],
                "last_seen": dates[-1],
                "average": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
                "daily_values": daily_values,
                "insight": change_insight,
                "description": (
                    f"{len(records)} imported measurements across {len(dates)} "
                    f"recorded days. Daily {label.lower()} in {unit}/day ranged "
                    f"from {min(values):g} to {max(values):g}; average "
                    f"{sum(values) / len(values):g}."
                ),
            }

        activity_measures = []
        health_indicators = []
        unmapped_measures = []
        for (metric_type, unit), records in sorted(grouped_metrics.items()):
            summary = summarize_metric(metric_type, unit, records)
            if metric_type in ACTIVITY_METRICS:
                activity_measures.append(summary)
            elif metric_type in HEALTH_INDICATOR_METRICS:
                health_indicators.append(summary)
            else:
                unmapped_measures.append(summary)

        evidence_by_category = {
            str(item["category"]): item for item in EVIDENCE_CATALOG
        }
        behavior_insights: list[dict[str, str]] = []
        category_labels = {
            "activity": "physical activity",
            "sleep": "sleep duration",
            "tobacco": "tobacco use",
            "alcohol": "alcohol",
            "nutrition": "fruit and vegetable servings",
        }
        for category, entries in sorted(behavior_by_category.items()):
            ordered_entries = sorted(
                entries, key=lambda entry: str(entry["reported_on"])
            )
            numeric_series: dict[str, list[float]] = defaultdict(list)
            for entry in ordered_entries:
                for name, value in dict(entry["values"]).items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        numeric_series[name].append(float(value))
            for field_name, values in numeric_series.items():
                label = field_name.replace("_", " ")
                average = sum(values) / len(values)
                behavior_insights.append(
                    {
                        "title": f"Your logged {category_labels[category]}",
                        "text": (
                            f"You recorded {len(values)} {label} entries. Their "
                            f"average was {average:g}; the range was "
                            f"{min(values):g}–{max(values):g}. This describes "
                            "your entries only."
                        ),
                        "kind": "personal_summary",
                    }
                )

        step_days_by_user: dict[str, float] = {}
        for metric in activity_measures:
            if metric["metric_type"] == "HKQuantityTypeIdentifierStepCount":
                step_days_by_user.update(metric["daily_values"])
        activity_entries_by_day: dict[str, list[float]] = defaultdict(list)
        for entry in behavior_by_category.get("activity", []):
            minutes = sum(
                float(value)
                for name, value in dict(entry["values"]).items()
                if name in {"moderate_minutes", "vigorous_minutes"}
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            activity_entries_by_day[str(entry["reported_on"])].append(minutes)
        paired_activity = [
            (sum(minutes) / len(minutes), step_days_by_user[day])
            for day, minutes in activity_entries_by_day.items()
            if day in step_days_by_user
        ]
        if len(paired_activity) >= 5:
            self_reported = [pair[0] for pair in paired_activity]
            step_counts = [pair[1] for pair in paired_activity]
            mean_self = sum(self_reported) / len(self_reported)
            mean_steps = sum(step_counts) / len(step_counts)
            covariance = sum(
                (self_reported[index] - mean_self)
                * (step_counts[index] - mean_steps)
                for index in range(len(paired_activity))
            )
            self_variance = sum((value - mean_self) ** 2 for value in self_reported)
            step_variance = sum((value - mean_steps) ** 2 for value in step_counts)
            if self_variance > 0 and step_variance > 0:
                correlation = covariance / math.sqrt(self_variance * step_variance)
                behavior_insights.append(
                    {
                        "title": "Logged activity and step counts",
                        "text": (
                            f"Across {len(paired_activity)} dates with both an "
                            f"activity entry and step data, the values had a "
                            f"Pearson correlation of {correlation:.2f} "
                            f"(ranging from -1 to 1). This is an exploratory "
                            "within-person pattern; it does not establish cause "
                            "or health impact."
                        ),
                        "kind": "paired_observation",
                    }
                )

        domain_results = []
        for definition in DETERMINANT_DOMAINS:
            signals: list[dict[str, object]] = []
            domain_id = str(definition["id"])
            domain_evidence: list[dict[str, object]] = []
            if domain_id == "behavioral":
                domain_insights = list(behavior_insights)
                for metric in activity_measures:
                    signals.append(
                        {
                            "label": str(metric["label"]),
                            "source": "Apple Health import",
                            "unit": str(metric["unit"]),
                            "description": str(metric["description"]),
                            "daily_values": metric["daily_values"],
                            "insight": metric["insight"],
                        }
                    )
                    if metric["insight"]:
                        domain_insights.append(
                            {
                                "title": f"{metric['label']} over time",
                                "text": str(metric["insight"]),
                                "kind": "personal_trend",
                            }
                        )
                category_labels = {
                    "activity": "Self-reported physical activity",
                    "sleep": "Self-reported sleep duration",
                    "tobacco": "Self-reported tobacco / smoke exposure",
                    "alcohol": "Self-reported alcohol",
                    "nutrition": "Self-reported fruit and vegetable servings",
                }
                for category, entries in sorted(behavior_by_category.items()):
                    entries.sort(
                        key=lambda entry: str(entry["reported_on"]), reverse=True
                    )
                    signals.append(
                        {
                            "label": category_labels.get(category, category),
                            "source": "Self-report",
                            "count": len(entries),
                            "first_seen": min(
                                str(entry["reported_on"]) for entry in entries
                            ),
                            "last_seen": max(
                                str(entry["reported_on"]) for entry in entries
                            ),
                            "description": (
                                f"{len(entries)} dated self-reported entries; "
                                f"latest {entries[0]['reported_on']}."
                            ),
                            "summary": (
                                f"Latest entry: "
                                f"{json.dumps(entries[0]['values'], sort_keys=True)}."
                            ),
                            "latest_entries": [
                                {
                                    "reported_on": entry["reported_on"],
                                    "values": entry["values"],
                                }
                                for entry in entries[:5]
                            ],
                        }
                    )
                    evidence = evidence_by_category.get(category)
                    if evidence is not None:
                        domain_evidence.append(evidence)
                activity_evidence = evidence_by_category.get("activity")
                if activity_measures and activity_evidence is not None:
                    domain_evidence.append(activity_evidence)
                domain_evidence = list(
                    {
                        str(item["category"]): item for item in domain_evidence
                    }.values()
                )
                status = "data_available" if signals else "no_records_yet"
            else:
                status = "not_collected"

            domain_results.append(
                {
                    "id": domain_id,
                    "name": definition["name"],
                    "definition": definition["definition"],
                    "status": status,
                    "signals": signals,
                    "insights": domain_insights if domain_id == "behavioral" else [],
                    "evidence": domain_evidence,
                }
            )

        return {
            "framework": {
                "name": "WHO-style determinants of health domains",
                "source_name": "World Health Organization — Social determinants of health",
                "source_url": (
                    "https://www.who.int/health-topics/social-determinants-of-health"
                ),
            },
            "interpretation": (
                "This map groups available observations by domain. It does not "
                "estimate individual risk, prove causation, or imply that a "
                "wearable measure is itself a determinant."
            ),
            "domains": domain_results,
            "health_indicators": health_indicators,
            "unmapped_measures": unmapped_measures,
        }

    @application.post("/users", status_code=201, tags=["accounts"])
    def create_user(request: RegisterRequest) -> dict[str, str]:
        if not valid_username(request.username):
            raise HTTPException(
                status_code=422,
                detail="Username must be 3-32 letters, numbers, dots, dashes, or underscores.",
            )
        salt = secrets.token_bytes(16)
        key = derive_key(request.password, salt)
        verifier = encrypt(key, PASSWORD_VERIFIER)
        try:
            with closing(_connect(path)) as connection:
                with connection:
                    connection.execute(
                        "INSERT INTO users (username, salt, verifier) VALUES (?, ?, ?)",
                        (request.username, salt, verifier),
                    )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="That local username already exists."
            ) from exc
        return {"username": request.username, "status": "created"}

    @application.post("/behaviors/entry", tags=["behavior"])
    def create_behavior_entry(request: BehaviorEntry) -> dict[str, object]:
        values = _validate_behavior_values(request.category, request.values.copy())
        entry_json = json.dumps(
            {
                "category": request.category,
                "reported_on": request.reported_on.isoformat(),
                "values": values,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with closing(_connect(path)) as connection:
            with connection:
                user_id, key = _authenticated_user(
                    connection, request.username, request.password
                )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO behavior_entries
                        (user_id, fingerprint, encrypted_payload)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, _fingerprint(key, entry_json), encrypt(key, entry_json)),
                )
        duplicate = cursor.rowcount == 0
        return {
            "status": "already_saved" if duplicate else "saved",
            "duplicate": duplicate,
        }

    @application.post("/behaviors", tags=["behavior"])
    def list_behavior_entries(
        request: Credentials,
    ) -> dict[str, list[dict[str, object]]]:
        with closing(_connect(path)) as connection:
            with connection:
                user_id, key = _authenticated_user(
                    connection, request.username, request.password
                )
                rows = connection.execute(
                    """
                    SELECT encrypted_payload FROM behavior_entries
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchall()
        entries = [_decode_record(key, row["encrypted_payload"]) for row in rows]
        entries.sort(
            key=lambda entry: (
                str(entry["reported_on"]),
                str(entry["category"]),
            ),
            reverse=True,
        )
        return {"entries": entries[:1000]}

    @application.post("/imports/apple-health", tags=["imports"])
    def import_apple_health(
        file: Annotated[UploadFile, File()],
        username: Annotated[str, Form(min_length=3, max_length=32)],
        password: Annotated[str, Form(min_length=1, max_length=1024)],
    ) -> dict[str, int]:
        try:
            with closing(_connect(path)) as connection:
                with connection:
                    user_id, key = _authenticated_user(
                        connection, username, password
                    )
                    records, parse_stats = iter_health_records(
                        file.file, file.filename or ""
                    )
                    imported = 0
                    duplicates = 0
                    for record in records:
                        record_json = json.dumps(
                            {
                                "type": record.metric_type,
                                "unit": record.unit,
                                "value": record.value,
                                "start_date": record.start_date,
                                "end_date": record.end_date,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                        cursor = connection.execute(
                            """
                            INSERT OR IGNORE INTO health_records
                                (user_id, fingerprint, encrypted_payload)
                            VALUES (?, ?, ?)
                            """,
                            (
                                user_id,
                                _fingerprint(key, record_json),
                                encrypt(key, record_json),
                            ),
                        )
                        if cursor.rowcount:
                            imported += 1
                        else:
                            duplicates += 1
                    if parse_stats.imported_candidates == 0:
                        raise HTTPException(
                            status_code=422,
                            detail="No numeric Apple Health quantity records were found.",
                        )
                    connection.execute(
                        """
                        INSERT INTO import_batches
                            (user_id, imported_count, duplicate_count, skipped_count)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            imported,
                            duplicates,
                            parse_stats.skipped_records,
                        ),
                    )
        except ImportSizeLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ImportFileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            file.file.close()
        return {
            "imported": imported,
            "duplicates": duplicates,
            "skipped": parse_stats.skipped_records,
        }

    @application.post("/metrics", tags=["analysis"])
    def list_metrics(request: Credentials) -> dict[str, list[dict[str, object]]]:
        with closing(_connect(path)) as connection:
            with connection:
                user_id, key = _authenticated_user(
                    connection, request.username, request.password
                )
                records = connection.execute(
                    "SELECT encrypted_payload FROM health_records WHERE user_id = ?",
                    (user_id,),
                )
                summary: dict[tuple[str, str], dict[str, object]] = {}
                for row in records:
                    record = _decode_record(key, row["encrypted_payload"])
                    metric = (str(record["type"]), str(record["unit"]))
                    item = summary.setdefault(
                        metric,
                        {
                            "type": metric[0],
                            "units": set(),
                            "count": 0,
                            "first_seen": str(record["start_date"]),
                            "last_seen": str(record["start_date"]),
                        },
                    )
                    item["count"] = int(item["count"]) + 1
                    item["first_seen"] = min(
                        str(item["first_seen"]), str(record["start_date"])
                    )
                    item["last_seen"] = max(
                        str(item["last_seen"]), str(record["start_date"])
                    )
                    units = item["units"]
                    assert isinstance(units, set)
                    units.add(metric[1])
                metrics = []
                for item in summary.values():
                    item["units"] = sorted(item["units"])
                    metrics.append(item)
        metrics.sort(key=lambda item: (str(item["type"]), str(item["units"])))
        return {"metrics": metrics}

    @application.post("/trends", tags=["analysis"])
    def get_trends(request: TrendsRequest) -> dict[str, list[dict[str, object]]]:
        with closing(_connect(path)) as connection:
            with connection:
                user_id, key = _authenticated_user(
                    connection, request.username, request.password
                )
                records = connection.execute(
                    "SELECT encrypted_payload FROM health_records WHERE user_id = ?",
                    (user_id,),
                )
                aggregates: dict[tuple[str, str], list[float]] = defaultdict(list)
                for row in records:
                    record = _decode_record(key, row["encrypted_payload"])
                    if record["type"] != request.metric_type:
                        continue
                    timestamp = str(record["start_date"])
                    record_date = datetime.fromisoformat(timestamp).date()
                    if request.start_date and record_date < request.start_date:
                        continue
                    if request.end_date and record_date > request.end_date:
                        continue
                    period = _bucket_period(timestamp, request.bucket)
                    aggregates[(period, str(record["unit"]))].append(
                        float(record["value"])
                    )
        trends = []
        for (period, unit), values in sorted(aggregates.items()):
            trends.append(
                {
                    "period": period,
                    "unit": unit,
                    "count": len(values),
                    "average": sum(values) / len(values),
                    "minimum": min(values),
                    "maximum": max(values),
                }
            )
        return {"trends": trends}

    return application


app = create_app()
