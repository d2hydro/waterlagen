const { extent, geoMercator, geoPath } = window.d3;
const root = document.getElementById("run-map-preview");
const q = (s) => root.querySelector(s);
const data = await loadApplication();
let filePath = "",
  fileLayer = "",
  fileFeature = null,
  boundsFeature = null,
  savedDrawing = "";
q(".top").insertBefore(q(".tools"), q(".tag"));
q(".map").append(q(".selection"));
q(".map").append(q(".backgrounds"));
const formContent = document.createElement("div");
formContent.className = "form-content";
while (q(".form").firstChild) {
  formContent.append(q(".form").firstChild);
}
q(".form").append(formContent, q(".footer"));
const mapCredits = document.createElement("div");
mapCredits.className = "map-credits";
mapCredits.append(q(".legend"), q(".attribution"));
q(".map").append(mapCredits);

for (const icon of root.querySelectorAll("[data-icon]")) {
  const source = `url("${data.icons[icon.dataset.icon]}")`;
  icon.style.maskImage = source;
  icon.style.webkitMaskImage = source;
}
q("#rm-logo").src = "data:image/png;base64," + data.logo;
const features = data.authorities.features.sort((a, b) =>
  a.properties.name.localeCompare(b.properties.name, "nl"),
);
const projection = geoMercator().fitExtent(
  [
    [12, 35],
    [388, 491],
  ],
  data.country,
);
q("#rm-map").setAttribute("viewBox", "0 0 400 530");
const path = geoPath(projection).digits(8),
  ns = "http://www.w3.org/2000/svg";
let selected = new Set(["12"]),
  mode = "authorities",
  drawingShape = "polygon",
  points = [],
  finished = false,
  fileLoaded = false,
  zoom = 1;
let suppressMapClick = false,
  panStart = null,
  rectangleStart = null;
function svgElement(tag, attrs, parent) {
  const el = document.createElementNS(ns, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  parent.append(el);
  return el;
}
const geo = q("#rm-geography"),
  drawing = q("#rm-drawing");
const country = svgElement("path", { d: path(data.country), class: "country" }, geo);
const boundaryCasings = svgElement("g", { "aria-hidden": "true", "pointer-events": "none" }, geo);
const paths = new Map();
for (const f of features) {
  const outline = path(f);
  svgElement("path", { d: outline, class: "authority-casing" }, boundaryCasings);
  const el = svgElement(
    "path",
    { d: outline, class: "authority", "data-code": f.properties.code },
    geo,
  );
  const title = svgElement("title", {}, el);
  title.textContent = f.properties.name;
  el.addEventListener("click", () => {
    if (mode === "authorities") {
      toggle(f.properties.code);
    }
  });
  el.addEventListener("mouseenter", () => {
    if (mode === "authorities") {
      q("#rm-map-hint").textContent = f.properties.name;
    }
  });
  paths.set(f.properties.code, el);
  const row = document.createElement("label");
  row.className = "authority-row";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.value = f.properties.code;
  input.addEventListener("change", () => toggle(f.properties.code));
  row.append(input, document.createTextNode(f.properties.name));
  q("#rm-list").append(row);
}
function addInfoIcon(link) {
  const icon = svgElement("svg", {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "1.7", "stroke-linecap": "round", "aria-hidden": "true",
  }, link);
  svgElement("circle", { cx: 12, cy: 12, r: 9 }, icon);
  svgElement("path", { d: "M12 11v6m0-10v.5" }, icon);
}
function addFileIcon(button, description) {
  button.replaceChildren();
  button.classList.add("file-browse");
  button.setAttribute("aria-label", description);
  const icon = svgElement("svg", {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round",
    "aria-hidden": "true",
  }, button);
  svgElement("path", { d: "M3 19V5h7l2 3h9v3M3 19h16l3-8H6Z" }, icon);
}
addFileIcon(q("#rm-file-demo"), "Bestand openen");
const layers = data.layers;
for (const [key, name] of layers) {
  const row = document.createElement("div");
  row.className = "layer";
  const label = document.createElement("label");
  const check = document.createElement("input");
  check.type = "checkbox";
  check.value = key;
  check.checked = key === "dem";
  check.addEventListener("change", render);
  label.append(check, document.createTextNode(" " + name));
  row.append(label);
  const info = document.createElement("a");
  info.href = data.layer_help[key].url;
  info.target = "_blank";
  info.rel = "noopener";
  info.className = "info";
  addInfoIcon(info);
  info.title = "Open de handleiding: " + name;
  info.setAttribute("aria-label", "Handleiding: " + name);
  const layerName = document.createElement("div");
  layerName.className = "layer-name";
  layerName.append(label, info);
  row.append(layerName);
  const extra = document.createElement("button");
  extra.className = "extra";
  const settingsIcon = svgElement("svg", {
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "1.7", "stroke-linecap": "round", "aria-hidden": "true",
  }, extra);
  svgElement("path", { d: "M4 7h3m6 0h7M4 17h7m6 0h3" }, settingsIcon);
  svgElement("circle", { cx: 10, cy: 7, r: 3 }, settingsIcon);
  svgElement("circle", { cx: 14, cy: 17, r: 3 }, settingsIcon);
  extra.append(document.createTextNode("Opties"));
  extra.title = "Extra opties voor " + name;
  extra.setAttribute("aria-label", "Extra opties voor " + name);
  row.append(extra);
  if (key === "dem") {
    const status = document.createElement("div");
    status.id = "rm-dem-landuse-status";
    status.className = "dem-landuse-status";
    status.setAttribute("aria-live", "polite");
    row.append(status);
  }
  q("#rm-layers").append(row);
}
function toggle(code) {
  if (selected.has(code)) {
    selected.delete(code);
  } else {
    selected.add(code);
  }
  render();
  remember();
}
let messageTimer;
let messageAnchor;
function positionMessage() {
  const notice = q("#rm-message");
  if (notice.hidden || !messageAnchor) {
    return;
  }
  const frame = root.getBoundingClientRect();
  const button = messageAnchor.getBoundingClientRect();
  const group = messageAnchor.closest(".footer, .top")?.getBoundingClientRect() ?? button;
  const width = notice.offsetWidth;
  const height = notice.offsetHeight;
  const left = Math.max(12, Math.min(button.right - frame.left - width, frame.width - width - 12));
  const above = group.top - frame.top - height - 8;
  const below = group.bottom - frame.top + 8;
  const top = above >= 12 ? above : Math.max(12, Math.min(below, frame.height - height - 12));
  notice.style.left = `${left}px`;
  notice.style.top = `${top}px`;
}
function message(text, { anchor = null, detail = "", success = false } = {}) {
  const notice = q("#rm-message");
  clearTimeout(messageTimer);
  messageAnchor = anchor;
  notice.classList.toggle("toast-anchored", Boolean(anchor));
  notice.classList.toggle("toast-success", success);
  notice.style.removeProperty("left");
  notice.style.removeProperty("top");
  const heading = document.createElement(detail ? "strong" : "span");
  heading.textContent = text;
  notice.replaceChildren(heading);
  if (detail) {
    const description = document.createElement("span");
    description.className = "toast-detail";
    description.textContent = detail;
    notice.append(description);
  }
  if (success) {
    messageTimer = setTimeout(() => (notice.hidden = true), 6000);
  } else {
    const close = document.createElement("button");
    close.className = "toast-close";
    close.textContent = "\u00d7";
    close.setAttribute("aria-label", "Melding sluiten");
    close.onclick = () => (notice.hidden = true);
    notice.append(close);
  }
  notice.hidden = false;
  positionMessage();
}
window.addEventListener("resize", positionMessage);
root.addEventListener("scroll", positionMessage, true);

function showRunNotice(text, path, anchor) {
  message(text, { anchor, detail: path.split(/[\\/]/).pop(), success: true });
}
function remember() {}
let viewCenter = [200, 265];
let countryOverview = true;
const maximumZoom = 16384;
function setZoom(value, center = viewCenter) {
  countryOverview = false;
  zoom = Math.min(maximumZoom, Math.max(0.7, value));
  viewCenter = center;
  const transform = `translate(${200 - center[0] * zoom} ${265 - center[1] * zoom}) scale(${zoom})`;
  geo.setAttribute("transform", transform);
  drawing.setAttribute("transform", transform);
  renderDrawingControls();
}
// Gebruik de volledige kaartbreedte en -hoogte, met een kleine rand.
function fitCountry() {
  const rectangle = q("#rm-map").getBoundingClientRect();
  const width = rectangle.width || 400;
  const height = rectangle.height || 530;
  const screenScale = Math.min(width / 400, height / 530);
  const [[left, top], [right, bottom]] = path.bounds(data.country);
  const factor = Math.min(
    Math.max(1, width - 16) / (screenScale * (right - left)),
    Math.max(1, height - 84) / (screenScale * (bottom - top)),
  );
  setZoom(factor, [(left + right) / 2, (top + bottom) / 2 - 22 / (screenScale * factor)]);
  countryOverview = true;
}
q("#rm-zoom-in").onclick = () => setZoom(zoom * 1.4);
q("#rm-zoom-out").onclick = () => setZoom(zoom / 1.4);
q("#rm-reset").onclick = () => fitCountry();
q(".map").addEventListener(
  "wheel",
  (event) => {
    if (event.target.closest(".area-popover, .selection, .drawing-toolbar")) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const svg = q("#rm-map"),
      pointer = svg.createSVGPoint();
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    const position = pointer.matrixTransform(svg.getScreenCTM().inverse());
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1);
    const nextZoom = Math.min(
      maximumZoom,
      Math.max(0.7, zoom * Math.exp(-Math.max(-160, Math.min(160, delta)) * 0.0015)),
    );
    const worldX = (position.x - 200) / zoom + viewCenter[0],
      worldY = (position.y - 265) / zoom + viewCenter[1];
    setZoom(nextZoom, [
      worldX - (position.x - 200) / nextZoom,
      worldY - (position.y - 265) / nextZoom,
    ]);
  },
  { passive: false },
);
q("#rm-mode").onchange = (e) => {
  mode = e.target.value;
  rectangleStart = null;
  q("#rm-message").hidden = true;
  if (mode === "country") {
    fitCountry();
  }
  render();
  remember();
};
function mapPosition(event, element = geo) {
  const point = q("#rm-map").createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(element.getScreenCTM().inverse());
}
function nearFirstPoint(event) {
  if (points.length < 3) {
    return false;
  }
  const point = q("#rm-map").createSVGPoint();
  [point.x, point.y] = points[0];
  const screen = point.matrixTransform(geo.getScreenCTM());
  return Math.hypot(event.clientX - screen.x, event.clientY - screen.y) <= 13;
}
function finishPolygon() {
  if (points.length < 3) {
    return;
  }
  finished = true;
  render();
  closeAreaPopovers();
  q("#rm-message").hidden = true;
  remember();
}
function rectanglePoints(first, last) {
  return [first, [last[0], first[1]], last, [first[0], last[1]]];
}
function finishRectangle(first, last) {
  if (first[0] === last[0] || first[1] === last[1]) {
    return;
  }
  points = rectanglePoints(first, last);
  finishPolygon();
}
function previewRectangle(first, last) {
  let preview = q("#rm-rectangle-preview");
  if (!preview) {
    preview = svgElement(
      "polygon",
      { id: "rm-rectangle-preview", class: "drawing-guide" },
      drawing,
    );
  }
  preview.setAttribute(
    "points",
    rectanglePoints(first, last)
      .map((point) => point.join(","))
      .join(" "),
  );
}
q("#rm-map").addEventListener("click", (event) => {
  if (suppressMapClick || mode !== "draw" || finished || event.detail > 1) {
    return;
  }
  if (drawingShape === "rectangle") {
    const position = mapPosition(event);
    const corner = [position.x, position.y];
    if (points.length) {
      finishRectangle(points[0], corner);
    } else {
      points = [corner];
      render();
    }
    return;
  }
  if (nearFirstPoint(event)) {
    finishPolygon();
    return;
  }
  const pos = mapPosition(event);
  points.push([+pos.x.toFixed(8), +pos.y.toFixed(8)]);
  render();
  remember();
});
q("#rm-map").addEventListener("dblclick", (event) => {
  if (mode === "draw" && drawingShape === "polygon" && !finished) {
    event.preventDefault();
    finishPolygon();
  }
});
q("#rm-map").addEventListener("pointerdown", (event) => {
  if (event.button !== 0 && event.button !== 1) {
    return;
  }
  suppressMapClick = false;
  if (mode === "draw" && drawingShape === "rectangle" && !finished && event.button === 0) {
    const position = mapPosition(event);
    rectangleStart = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      corner: points[0] || [position.x, position.y],
    };
    q("#rm-map").setPointerCapture(event.pointerId);
    return;
  }
  const position = mapPosition(event, q("#rm-map"));
  panStart = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    position,
    center: [...viewCenter],
    zoom,
  };
});
q("#rm-map").addEventListener("pointermove", (event) => {
  if (mode === "draw" && drawingShape === "rectangle" && !finished && !panStart) {
    const first = rectangleStart?.corner || points[0];
    if (first) {
      const position = mapPosition(event);
      previewRectangle(first, [position.x, position.y]);
    }
    return;
  }
  if (panStart && panStart.id === event.pointerId) {
    if (
      !suppressMapClick &&
      Math.hypot(event.clientX - panStart.x, event.clientY - panStart.y) < 5
    ) {
      return;
    }
    suppressMapClick = true;
    root.classList.add("is-panning");
    q("#rm-map").setPointerCapture(event.pointerId);
    const position = mapPosition(event, q("#rm-map"));
    setZoom(panStart.zoom, [
      panStart.center[0] - (position.x - panStart.position.x) / panStart.zoom,
      panStart.center[1] - (position.y - panStart.position.y) / panStart.zoom,
    ]);
    return;
  }
  if (mode === "draw" && !finished && points.length) {
    const guide = q("#rm-drawing-guide"),
      position = nearFirstPoint(event) ? { x: points[0][0], y: points[0][1] } : mapPosition(event),
      last = points[points.length - 1];
    if (guide) {
      guide.setAttribute("points", `${last[0]},${last[1]} ${position.x},${position.y}`);
    }
  }
});
q("#rm-map").addEventListener("pointerup", (event) => {
  if (rectangleStart?.id !== event.pointerId) {
    return;
  }
  const start = rectangleStart;
  rectangleStart = null;
  if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) {
    const position = mapPosition(event);
    suppressMapClick = true;
    finishRectangle(start.corner, [position.x, position.y]);
  }
  if (q("#rm-map").hasPointerCapture(event.pointerId)) {
    q("#rm-map").releasePointerCapture(event.pointerId);
  }
});
q("#rm-map").addEventListener("pointercancel", () => {
  rectangleStart = null;
  q("#rm-rectangle-preview")?.remove();
});
function stopPanning(event) {
  if (panStart?.id !== event.pointerId) {
    return;
  }
  panStart = null;
  root.classList.remove("is-panning");
  if (q("#rm-map").hasPointerCapture(event.pointerId)) {
    q("#rm-map").releasePointerCapture(event.pointerId);
  }
}
q("#rm-map").addEventListener("pointerup", stopPanning);
q("#rm-map").addEventListener("pointercancel", stopPanning);
q("#rm-map").addEventListener("lostpointercapture", stopPanning);
q("#rm-map").addEventListener("pointerleave", () => {
  if (!panStart) {
    q("#rm-drawing-guide")?.setAttribute("points", "");
  }
});
q("#rm-map").addEventListener(
  "click",
  (event) => {
    if (suppressMapClick) {
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  },
  true,
);
q("#rm-undo").onclick = () => {
  if (finished) {
    finished = false;
  } else {
    points.pop();
  }
  q("#rm-message").hidden = true;
  render();
  remember();
};
q("#rm-finish").onclick = finishPolygon;
const picker = q("#rm-authority-panel"),
  popup = q("#rm-picker-popup");
const optionPanels = new Map(),
  optionButtons = new Map();
function groupDrainageOptions(fields) {
  const groups = [
    ["HyDAMO en Rijkswateren", ["eigen-hydamo", "rijkswateren-url"]],
    ["Afstroming en duikers", ["dem-resampling", "duiker-tolerance", "max-aansluitlengte",
      "max-complex-routelengte", "overige-waterschappen"]],
  ];
  for (const [name, flags] of groups) {
    const details = document.createElement("details");
    details.className = "option-group";
    const summary = document.createElement("summary");
    summary.textContent = name;
    const grid = document.createElement("div");
    grid.className = "option-grid";
    for (const flag of flags) {
      const field = fields.querySelector(`[data-flag="${flag}"]`);
      grid.append(field.closest("label"));
    }
    details.append(summary, grid);
    fields.append(details);
  }
}

function closeOptions() {
  for (const [key, panel] of optionPanels) {
    panel.hidden = true;
    optionButtons.get(key).setAttribute("aria-expanded", "false");
  }
}
function toggleOptions(key) {
  const panel = optionPanels.get(key),
    show = panel.hidden;
  closeOptions();
  if (show) {
    closeAreaPopovers();
    closeSelectionPopup();
    panel.hidden = false;
    optionButtons.get(key).setAttribute("aria-expanded", "true");
    panel.querySelector("header button").focus();
  }
}
for (const [index, [key, name]] of layers.entries()) {
  const row = q("#rm-layers").children[index];
  const button = row.querySelector(".extra");
  const panel = document.createElement("section");
  panel.id = "rm-extra-" + key;
  panel.className = "extra-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Extra opties " + name);
  const header = document.createElement("header"),
    title = document.createElement("h3"),
    close = document.createElement("button"),
    fields = document.createElement("div");
  title.textContent = name;
  title.id = panel.id + "-title";
  panel.setAttribute("aria-labelledby", title.id);
  close.textContent = "×";
  close.setAttribute("aria-label", "Extra opties sluiten");
  fields.className = "extra-fields";
  close.onclick = () => {
    closeOptions();
    button.focus();
  };
  header.append(title, close);
  panel.append(header, fields);
  for (const option of data.options[key] || []) {
    const label = document.createElement("label");
    label.className = option.kind === "boolean" ? "boolean" : "field";
    if (["file", "directory", "toml", "text", "boolean"].includes(option.kind)) {
      label.classList.add("option-wide");
    }
    const caption = document.createElement("span");
    caption.textContent = option.label;
    const help = document.createElement("a");
    help.className = "info";
    addInfoIcon(help);
    help.href = option.url;
    help.target = "_blank";
    help.rel = "noopener";
    help.title = option.help.summary;
    help.setAttribute("aria-label", "Uitleg: " + option.label);
    caption.append(help);
    let input;
    if (option.kind === "choice") {
      input = document.createElement("select");
      for (const value of option.choices) {
        const choice = document.createElement("option");
        choice.value = value;
        choice.textContent = value;
        input.append(choice);
      }
    } else {
      input = document.createElement("input");
      input.type =
        option.kind === "boolean"
          ? "checkbox"
          : ["number", "integer"].includes(option.kind)
            ? "number"
            : "text";
    }
    input.dataset.flag = option.flag;
    input.dataset.layer = key;
    input.dataset.kind = option.kind;
    input.dataset.authority = String(option.authority_only);
    input.dataset.default = String(option.default);
    if (option.kind === "boolean") {
      input.checked = !!option.default;
      label.append(input, caption);
    } else {
      input.value = option.default;
      input.step = option.kind === "integer" ? "1" : "any";
      if (option.minimum !== null) {
        input.min = option.minimum;
      }
      if (option.maximum !== null) {
        input.max = option.maximum;
      }
      label.append(caption, input);
    }
    fields.append(label);
    addOptionActions(label, input, option, key);
    if (option.hint) {
      const hint = document.createElement("div");
      hint.className = "hint";
      hint.textContent = option.hint;
      hint.id = `rm-hint-${key}-${option.flag}`;
      input.setAttribute("aria-describedby", hint.id);
      label.append(hint);
    }
  }
  if (key === "afwateringseenheden") {
    groupDrainageOptions(fields);
  }
  root.append(panel);
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", panel.id);
  button.onclick = () => toggleOptions(key);
  optionPanels.set(key, panel);
  optionButtons.set(key, button);
}
document.addEventListener("pointerdown", (event) => {
  if (
    ![...optionPanels.values(), ...optionButtons.values()].some((element) =>
      element.contains(event.target),
    )
  ) {
    closeOptions();
  }
});
root.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    for (const [key, panel] of optionPanels) {
      if (!panel.hidden) {
        closeOptions();
        optionButtons.get(key).focus();
        break;
      }
    }
  }
});
function closePicker() {
  popup.hidden = true;
  q("#rm-picker").setAttribute("aria-expanded", "false");
}
q("#rm-picker").onclick = () => {
  popup.hidden = !popup.hidden;
  q("#rm-picker").setAttribute("aria-expanded", String(!popup.hidden));
};
// Sluiten loopt via het hele gebiedsvenster, niet via muisbewegingen in de lijst.
function render() {
  renderForm();
  const names = features
    .filter((f) => selected.has(f.properties.code))
    .map((f) => f.properties.name);
  q("#rm-picker-label").textContent =
    names.length === 1 ? names[0] : names.length + " geselecteerd";
  q("#rm-picker").title = names.join(", ");
  renderSelectionOutline();
  renderDrawingControls();
  updateSelectionDetails();
  scheduleLandusePreview();
}

const selectionOutline = svgElement("g", { "pointer-events": "none", "aria-hidden": "true" }, geo);
function renderSelectionOutline() {
  selectionOutline.replaceChildren();
  const chosen =
    mode === "country"
      ? [data.country]
      : mode === "authorities"
        ? features.filter((feature) => selected.has(feature.properties.code))
        : mode === "file" && fileFeature
          ? [fileFeature]
          : mode === "bounds" && boundsFeature
            ? [boundsFeature]
            : [];
  const parent = mode === "file" || mode === "bounds" ? drawing : selectionOutline;
  for (const feature of chosen)
    svgElement("path", { d: path(feature), class: "selection-outline selection-halo" }, parent);
  for (const feature of chosen)
    svgElement("path", { d: path(feature), class: "selection-outline selection-color" }, parent);
}
function setBackground(kind) {
  for (const button of root.querySelectorAll("[data-background]"))
    button.setAttribute("aria-pressed", String(button.dataset.background === kind));
  root.classList.toggle("with-basemap", kind !== "plain");
  root.classList.toggle("satellite-map", kind === "satellite");
  const label = q("#rm-attribution");
  label.replaceChildren();
  if (kind === "plain") {
    label.textContent = "Achtergrond zonder straten";
    return;
  }
  const link = document.createElement("a");
  link.target = "_blank";
  link.rel = "noopener";
  link.href =
    kind === "streets"
      ? "https://www.openstreetmap.org/copyright"
      : "https://www.pdok.nl/introductie/-/article/pdok-luchtfoto-rgb-open-";
  link.textContent =
    kind === "streets" ? "© OpenStreetMap contributors" : "PDOK · Beeldmateriaal Nederland";
  label.append(link, document.createTextNode(" · overzichtsbeeld"));
}
for (const button of root.querySelectorAll("[data-background]"))
  button.onclick = () => setBackground(button.dataset.background);
const areaPopovers = new Map([
  ["choose", q("#rm-area-menu")],
  ["custom", q("#rm-custom-menu")],
  ["file", q("#rm-file-panel")],
  ["bounds", q("#rm-bounds-panel")],
]);
q("#rm-authority-slot").append(picker);
for (const [key, title] of [
  ["file", "Gebied uit bestand"],
  ["bounds", "Coördinaten invoeren"],
]) {
  const panel = areaPopovers.get(key);
  panel.classList.add("area-popover");
  panel.setAttribute("aria-label", title);
  const header = document.createElement("header");
  const heading = document.createElement("h3");
  heading.textContent = title;
  const close = document.createElement("button");
  close.textContent = "×";
  close.setAttribute("aria-label", "Sluiten");
  close.onclick = closeAreaPopovers;
  header.append(heading, close);
  panel.prepend(header);
}
const coordinateHint = document.createElement("p");
coordinateHint.className = "muted";
coordinateHint.textContent = data.crs + " · coördinaten in meters";
q("#rm-bounds-panel").append(coordinateHint);
function closeAreaPopovers() {
  for (const panel of areaPopovers.values()) {
    panel.hidden = true;
  }
  q("#rm-choose-area").setAttribute("aria-expanded", "false");
  q("#rm-custom-area").setAttribute("aria-expanded", "false");
  closePicker();
}
function openAreaPopover(key) {
  closeAreaPopovers();
  closeOptions();
  closeSelectionPopup();
  areaPopovers.get(key).hidden = false;
  q(key === "choose" ? "#rm-choose-area" : "#rm-custom-area").setAttribute("aria-expanded", "true");
}
for (const [id, key] of [
  ["rm-choose-area", "choose"],
  ["rm-custom-area", "custom"],
]) {
  const trigger = q("#" + id);
  trigger.onclick = () => {
    if (key === "custom" && mode === "draw" && drawingIsSaved() && !drawingToolbar.hidden) {
      closeAreaPopovers();
      setDrawingToolsCollapsed(true);
      return;
    }
    if (trigger.getAttribute("aria-expanded") === "true") {
      closeAreaPopovers();
    } else {
      openAreaPopover(key);
    }
  };
}
for (const button of root.querySelectorAll("[data-close-area]")) {
  button.onclick = closeAreaPopovers;
}
function chooseAreaMode(value) {
  q("#rm-mode").value = value;
  q("#rm-mode").dispatchEvent(new Event("change", { bubbles: true }));
}
for (const radio of root.querySelectorAll('[name="area-kind"]')) {
  radio.onchange = () => {
    chooseAreaMode(radio.value);
    if (radio.value === "authorities") {
      openAreaPopover("choose");
      popup.hidden = false;
      q("#rm-picker").setAttribute("aria-expanded", "true");
    }
  };
}
for (const button of root.querySelectorAll("[data-area-mode]")) {
  button.onclick = () => {
    if (button.dataset.shape && drawingShape !== button.dataset.shape) {
      points = [];
      finished = false;
      drawingShape = button.dataset.shape;
    }
    chooseAreaMode(button.dataset.areaMode);
  };
}
q("#rm-mode").addEventListener("change", () => {
  closeAreaPopovers();
  if (mode === "file" || mode === "bounds") {
    openAreaPopover(mode);
  }
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".area-popover, .area-toolbar")) {
    closeAreaPopovers();
  }
});
root.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const open = [...areaPopovers.values()].find((panel) => !panel.hidden);
    if (open) {
      const button = open.id === "rm-area-menu" ? q("#rm-choose-area") : q("#rm-custom-area");
      closeAreaPopovers();
      button.focus();
    }
  }
});
const useBounds = document.createElement("button");
useBounds.textContent = "Gebied gebruiken";
useBounds.className = "primary";
useBounds.onclick = readBounds;
q("#rm-bounds-panel").append(useBounds);
let drawingToolsCollapsed = false;
const drawingToolbar = document.createElement("div");
drawingToolbar.id = "rm-drawing-toolbar";
drawingToolbar.className = "drawing-toolbar";
drawingToolbar.hidden = true;
drawingToolbar.setAttribute("role", "region");
drawingToolbar.setAttribute("aria-labelledby", "rm-drawing-title");
const drawingHeader = document.createElement("header");
const drawingTitle = document.createElement("h3");
drawingTitle.id = "rm-drawing-title";
const drawingStatus = document.createElement("span");
drawingStatus.className = "drawing-status";
drawingStatus.setAttribute("aria-live", "polite");
drawingHeader.append(drawingTitle, drawingStatus);
const drawingActions = document.createElement("div");
drawingActions.className = "drawing-actions";
const undoDrawing = document.createElement("button");
undoDrawing.textContent = "Punt terug";
undoDrawing.onclick = () => q("#rm-undo").click();
const closeDrawing = document.createElement("button");
closeDrawing.textContent = "Polygoon sluiten";
closeDrawing.className = "primary";
closeDrawing.onclick = finishPolygon;
const saveDrawing = document.createElement("button");
saveDrawing.textContent = "Opslaan als GeoPackage…";
saveDrawing.className = "primary save-drawing";
saveDrawing.onclick = saveDrawnArea;
const restartDrawing = document.createElement("button");
restartDrawing.textContent = "Opnieuw tekenen";
restartDrawing.onclick = () => {
  points = [];
  finished = false;
  render();
  remember();
};
drawingActions.append(undoDrawing, closeDrawing, saveDrawing, restartDrawing);
const drawingHint = document.createElement("p");
drawingHint.textContent = "Klik voor punten · sleep om te verschuiven · muiswiel om te zoomen";
drawingToolbar.append(drawingHeader, drawingHint, drawingActions);
q(".map").append(drawingToolbar);
function renderDrawingControls() {
  const active = mode === "draw" && !finished;
  root.classList.toggle("is-drawing", active);
  const saved = drawingIsSaved();
  drawingToolbar.hidden = mode !== "draw" || (saved && drawingToolsCollapsed);
  undoDrawing.hidden = drawingShape === "rectangle";
  closeDrawing.hidden = finished || drawingShape === "rectangle";
  saveDrawing.hidden = !finished;
  restartDrawing.hidden = !finished && drawingShape !== "rectangle";
  undoDrawing.disabled = !points.length;
  closeDrawing.disabled = points.length < 3;
  undoDrawing.title = finished ? "Sluiting ongedaan maken" : "Laatste punt verwijderen";
  drawingTitle.textContent = drawingShape === "rectangle" ? "Rechthoek tekenen" : "Polygoon tekenen";
  drawingStatus.textContent = finished
    ? saved ? "Opgeslagen" : "Gesloten"
    : points.length + (points.length === 1 ? " punt" : " punten");
  drawingStatus.classList.toggle("is-complete", !!saved);
  if (finished) {
    drawingTitle.textContent = saved ? "Gebied opgeslagen" : "Gebied opslaan";
    drawingHint.textContent = saved
      ? "Je gebied is klaar voor de run."
      : "Bewaar je gebied als GeoPackage om het voor de run te gebruiken.";
  } else if (drawingShape === "rectangle") {
    drawingHint.textContent = "Sleep op de kaart of klik twee tegenoverliggende hoeken.";
  } else {
    drawingHint.textContent = points.length < 3
      ? "Klik op de kaart om minstens drie hoekpunten te plaatsen."
      : "Voeg punten toe of sluit het gebied met de knop hieronder.";
  }
  drawing.querySelector(".first-point")?.remove();
  q("#rm-drawing-guide")?.remove();
  const matrix = geo.getScreenCTM();
  if (!matrix) {
    return;
  }
  const scale = Math.hypot(matrix.a, matrix.b);
  for (const point of drawing.querySelectorAll(".point")) point.setAttribute("r", 3.5 / scale);
  if (active && points.length && drawingShape === "polygon") {
    svgElement(
      "circle",
      { cx: points[0][0], cy: points[0][1], r: 6 / scale, class: "first-point" },
      drawing,
    );
    svgElement("polyline", { id: "rm-drawing-guide", points: "", class: "drawing-guide" }, drawing);
  }
}
let selectionExpanded = false;
const selectionCard = q(".selection");
const selectionIcon = document.createElement("span");
selectionIcon.className = "selection-icon";
selectionIcon.setAttribute("aria-hidden", "true");
const mapIcon = document.createElement("span");
mapIcon.style.maskImage = `url("${data.icons.map}")`;
mapIcon.style.webkitMaskImage = `url("${data.icons.map}")`;
selectionIcon.append(mapIcon);
const selectionText = document.createElement("div");
selectionText.className = "selection-text";
selectionText.append(q("#rm-selection-title"), q("#rm-selection-detail"));
selectionCard.append(selectionIcon, selectionText);
const selectionToggle = document.createElement("button");
selectionToggle.className = "selection-toggle";
selectionToggle.setAttribute("aria-controls", "rm-selection-popup");
const drawingToolsToggle = document.createElement("button");
drawingToolsToggle.className = "selection-toggle";
drawingToolsToggle.hidden = true;
drawingToolsToggle.setAttribute("aria-controls", drawingToolbar.id);
drawingToolsToggle.onclick = () => setDrawingToolsCollapsed(!drawingToolsCollapsed);
function setDrawingToolsCollapsed(collapsed) {
  drawingToolsCollapsed = collapsed;
  renderDrawingControls();
  updateSelectionDetails();
}
selectionText.append(selectionToggle, drawingToolsToggle);
const selectionPopup = document.createElement("section");
selectionPopup.id = "rm-selection-popup";
selectionPopup.className = "selection-popup";
selectionPopup.hidden = true;
selectionPopup.setAttribute("role", "dialog");
selectionPopup.setAttribute("aria-label", "Volledige gebiedsselectie");
const popupHeader = document.createElement("header"),
  popupTitle = document.createElement("h3"),
  popupClose = document.createElement("button"),
  popupList = document.createElement("ul");
popupClose.textContent = "×";
popupClose.setAttribute("aria-label", "Selectie sluiten");
popupHeader.append(popupTitle, popupClose);
selectionPopup.append(popupHeader, popupList);
q(".map").append(selectionPopup);
function updateSelectionDetails() {
  const detail = q("#rm-selection-detail");
  drawingToolsToggle.hidden = mode !== "draw" || !drawingIsSaved();
  drawingToolsToggle.textContent = drawingToolsCollapsed ? "Gebied bewerken" : "Tekenpaneel inklappen";
  drawingToolsToggle.setAttribute("aria-expanded", String(!drawingToolbar.hidden));
  q(".selection").classList.remove("expanded");
  selectionToggle.hidden =
    !selectionExpanded &&
    !(mode === "authorities" && selected.size > 1) &&
    !(mode === "draw" && finished) &&
    detail.scrollHeight <= detail.clientHeight + 1 &&
    detail.scrollWidth <= detail.clientWidth + 1;
  selectionToggle.textContent = selectionExpanded ? "Selectie sluiten ↑" : "Bekijk selectie ↑";
  const cardHeight = selectionCard.getBoundingClientRect().height;
  if (cardHeight) {
    selectionPopup.style.bottom = cardHeight + 44 + "px";
  }
  selectionToggle.setAttribute("aria-expanded", String(selectionExpanded));
  selectionPopup.hidden = !selectionExpanded;
  popupTitle.textContent = q("#rm-selection-title").textContent;
  popupList.replaceChildren();
  const names =
    mode === "authorities"
      ? features
          .filter((feature) => selected.has(feature.properties.code))
          .map((feature) => feature.properties.name)
      : [detail.textContent];
  for (const name of names) {
    const item = document.createElement("li");
    item.textContent = name;
    popupList.append(item);
  }
}
function closeSelectionPopup() {
  selectionExpanded = false;
  updateSelectionDetails();
}
popupClose.onclick = closeSelectionPopup;
document.addEventListener("pointerdown", (event) => {
  if (
    selectionExpanded &&
    !selectionPopup.contains(event.target) &&
    !selectionToggle.contains(event.target)
  ) {
    closeSelectionPopup();
  }
});
root.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && selectionExpanded) {
    closeSelectionPopup();
    selectionToggle.focus();
  }
});
q("#rm-mode").addEventListener("change", closeSelectionPopup);
selectionToggle.onclick = () => {
  const show = !selectionExpanded;
  closeAreaPopovers();
  closeOptions();
  selectionExpanded = show;
  if (show && mode === "draw" && finished) {
    const [left, right] = extent(points, ([x]) => x);
    const [top, bottom] = extent(points, ([, y]) => y);
    fitProjectedBounds([[left, top], [right, bottom]]);
  }
  updateSelectionDetails();
};
new ResizeObserver(updateSelectionDetails).observe(selectionCard);

// Haal alleen tegels op voor het zichtbare kaartgebied.
const liveTiles = svgElement("g", { class: "map-tiles", "pointer-events": "none" }, geo);
geo.insertBefore(liveTiles, country);
let tileProvider = "streets",
  tileTimer,
  tileVersion = 0,
  tileSignature = "";
const tileNotice = document.createElement("button");
tileNotice.type = "button";
tileNotice.className = "live-map-status";
tileNotice.hidden = true;
q(".map").append(tileNotice);

function tileXY(longitude, latitude, level) {
  const count = 2 ** level;
  const radians = (Math.max(-85.05112878, Math.min(85.05112878, latitude)) * Math.PI) / 180;
  return [
    ((longitude + 180) / 360) * count,
    ((1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2) * count,
  ];
}
function tileCorner(x, y, level) {
  const count = 2 ** level;
  return projection([
    (x / count) * 360 - 180,
    (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / count))) * 180) / Math.PI,
  ]);
}
function scheduleTiles() {
  clearTimeout(tileTimer);
  const matrix = geo.getScreenCTM();
  if (!matrix) {
    return;
  }
  const screenScale = Math.hypot(matrix.a, matrix.b);
  // De zichtbare schaal bepaalt het contrast, ook op een scherm met hoge pixeldichtheid.
  const displayLevel = Math.log2((2 * Math.PI * projection.scale() * screenScale) / 256);
  const detail = Math.max(0, Math.min(1, (displayLevel - 8) / 6));
  liveTiles.style.opacity = String(0.30 + 0.70 * detail);
  tileTimer = setTimeout(() => updateTiles(displayLevel), 160);
}
function updateTiles(displayLevel) {
  const matrix = geo.getScreenCTM(),
    rectangle = q("#rm-map").getBoundingClientRect();
  if (!matrix || rectangle.width === 0 || rectangle.height === 0) {
    return;
  }
  const maximumLevel = tileProvider === "satellite" ? 21 : 19;
  const level = Math.max(
    0,
    Math.min(maximumLevel, Math.ceil(displayLevel + Math.log2(window.devicePixelRatio))),
  );
  const point = q("#rm-map").createSVGPoint();
  point.x = rectangle.left;
  point.y = rectangle.top;
  const northwest = point.matrixTransform(matrix.inverse());
  point.x = rectangle.right;
  point.y = rectangle.bottom;
  const southeast = point.matrixTransform(matrix.inverse());
  const [west, north] = projection.invert([northwest.x, northwest.y]);
  const [east, south] = projection.invert([southeast.x, southeast.y]);
  const first = tileXY(west, north, level),
    last = tileXY(east, south, level);
  const count = 2 ** level;
  const xmin = Math.max(0, Math.floor(first[0])),
    xmax = Math.min(count - 1, Math.floor(last[0]));
  const ymin = Math.max(0, Math.floor(first[1])),
    ymax = Math.min(count - 1, Math.floor(last[1]));
  const signature = [tileProvider, level, xmin, ymin, xmax, ymax].join("/");
  if (signature === tileSignature) {
    return;
  }
  tileSignature = signature;
  const version = ++tileVersion;
  const group = svgElement("g", { "data-level": level, "data-provider": tileProvider }, liveTiles);
  const total = (xmax - xmin + 1) * (ymax - ymin + 1);
  let completed = 0,
    failed = 0;
  tileNotice.hidden = true;
  function tileDone(success) {
    completed += 1;
    if (!success) {
      failed += 1;
    }
    if (version !== tileVersion) {
      group.remove();
      return;
    }
    if (completed !== total) {
      return;
    }
    if (failed) {
      tileNotice.textContent = "Kaartdetail opnieuw laden";
      tileNotice.hidden = false;
    } else {
      for (const older of [...liveTiles.children])
        if (older !== group) {
          older.remove();
        }
    }
  }
  for (let y = ymin; y <= ymax; y++) {
    for (let x = xmin; x <= xmax; x++) {
      const upperLeft = tileCorner(x, y, level),
        lowerRight = tileCorner(x + 1, y + 1, level);
      const image = svgElement(
        "image",
        {
          x: upperLeft[0],
          y: upperLeft[1],
          width: lowerRight[0] - upperLeft[0],
          height: lowerRight[1] - upperLeft[1],
          preserveAspectRatio: "none",
        },
        group,
      );
      image.addEventListener("load", () => tileDone(true), { once: true });
      image.addEventListener("error", () => tileDone(false), { once: true });
      const source = tileProvider === "satellite" ? "aerial" : "streets";
      image.setAttribute("href", `tiles/${source}/${level}/${x}/${y}`);
    }
  }
}
tileNotice.onclick = () => {
  tileSignature = "";
  scheduleTiles();
};
const staticSetZoom = setZoom;
setZoom = function (value, center = viewCenter) {
  staticSetZoom(value, center);
  scheduleTiles();
};
const staticSetBackground = setBackground;
setBackground = function (kind) {
  staticSetBackground(kind);
  tileProvider = kind;
  tileVersion += 1;
  tileSignature = "";
  liveTiles.replaceChildren();
  q("#rm-attribution").lastChild.textContent =
    kind === "satellite" ? " · actueel · 5–8 cm" : " · detail per zoomniveau";
  scheduleTiles();
};
new ResizeObserver(() => {
  if (countryOverview) {
    fitCountry();
  }
  scheduleTiles();
}).observe(q("#rm-map"));
setBackground("streets");

// Dezelfde keuzes maken zowel het voorbeeldcommando als het opgeslagen BAT-bestand.
let actionPending = false,
  drawingPath = "",
  boundsSignature = "";

async function api(action, values = {}) {
  let response;
  try {
    response = await fetch("api/" + action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
  } catch {
    throw new Error("Run maken is niet bereikbaar. Open run-maken.bat opnieuw.");
  }
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "De opdracht kon niet worden uitgevoerd.");
  }
  return result;
}

async function loadApplication() {
  setInterval(() => api("heartbeat").catch(() => {}), 15000);
  try {
    const [settings, appearance] = await Promise.all([
      api("bootstrap"),
      fetch("appearance.json").then((response) => response.json()),
    ]);
    return { ...settings, ...appearance };
  } catch (error) {
    const loading = document.getElementById("loading");
    loading.textContent = error.message + " ";
    const retry = document.createElement("button");
    retry.textContent = "Opnieuw proberen";
    retry.onclick = () => location.reload();
    loading.append(retry);
    throw error;
  }
}

async function act(button, operation) {
  const runAction = button && ["rm-save", "rm-start", "rm-load", "rm-update"].includes(button.id);
  if (runAction && actionPending) {
    message("Rond de huidige run-opdracht eerst af.", { anchor: button });
    return;
  }
  if (runAction) {
    actionPending = true;
  }
  q("#rm-message").hidden = true;
  if (button) {
    button.disabled = true;
  }
  try {
    await operation();
  } catch (error) {
    message(error.message, { anchor: button });
  } finally {
    if (runAction) {
      actionPending = false;
    }
    if (button) {
      button.disabled = false;
    }
  }
}

function drawingIsSaved() {
  return finished && drawingPath && savedDrawing === JSON.stringify(points);
}

function collectValues() {
  if (mode === "draw" && !drawingIsSaved()) {
    throw new Error("Sluit de polygoon en sla hem eerst op als GeoPackage.");
  }
  const bounds = [...q(".bounds-fields").querySelectorAll("input")].map((input) => input.value);
  if (mode === "bounds" && boundsSignature !== JSON.stringify(bounds)) {
    throw new Error("Klik eerst op Gebied gebruiken om de rechthoek te controleren.");
  }
  if (mode === "file" && !fileFeature) {
    throw new Error("Kies een polygoonbestand en een laag.");
  }
  const extra_options = [];
  for (const input of root.querySelectorAll("[data-flag]")) {
    if (!input.disabled) {
      extra_options.push({
        layer: input.dataset.layer,
        flag: input.dataset.flag,
        value: input.type === "checkbox" ? input.checked : input.value,
      });
    }
  }
  return {
    mode,
    authorities: [...selected],
    bounds,
    area_file: mode === "draw" ? drawingPath : filePath,
    area_layer: mode === "draw" ? "gebied" : fileLayer,
    drawing_saved: !!drawingIsSaved(),
    dem_landuse_mode: q("#rm-dem-landuse-mode").value,
    layers: [...q("#rm-layers").querySelectorAll("input:checked")].map((input) => input.value),
    run_id: q("#rm-run-name").value,
    workers: q("#rm-workers").value,
    run_mode: q("#rm-run-mode").value,
    refresh_sources: q("#rm-refresh").checked,
    debug: q("#rm-debug").checked,
    extra_options,
  };
}

function renderForm() {
  q("#rm-authority-panel").hidden = mode !== "authorities";
  for (const radio of root.querySelectorAll('[name="area-kind"]')) {
    radio.checked = mode === radio.value;
  }
  for (const [code, element] of paths) {
    element.classList.toggle("selected", mode === "authorities" && selected.has(code));
  }
  country.classList.toggle("selected", mode === "country");
  for (const input of q("#rm-list").querySelectorAll("input")) {
    input.checked = selected.has(input.value);
  }
  drawing.replaceChildren();
  let title = "",
    detail = "";
  if (mode === "authorities") {
    title = selected.size + " waterschap" + (selected.size === 1 ? "" : "pen") + " geselecteerd";
    detail =
      features
        .filter((feature) => selected.has(feature.properties.code))
        .map((feature) => feature.properties.name)
        .join(" · ") || "Kies minstens één waterschap.";
  } else if (mode === "country") {
    title = "Heel Nederland geselecteerd";
    detail = "Eén landelijk productiegebied";
  } else if (mode === "draw") {
    title = finished ? "Getekend gebied" : "Gebied tekenen";
    detail = drawingIsSaved() ? drawingPath + " → gebied" : "Nog niet opgeslagen";
    if (points.length) {
      svgElement(
        finished ? "polygon" : "polyline",
        { points: points.map((point) => point.join(",")).join(" "), class: "overlay" },
        drawing,
      );
      for (const [cx, cy] of points) {
        svgElement("circle", { cx, cy, r: 3 / zoom, class: "point" }, drawing);
      }
    }
  } else if (mode === "file") {
    title = fileFeature ? "Polygoonbestand geselecteerd" : "Polygoonbestand kiezen";
    detail = fileFeature
      ? filePath +
        " → " +
        fileLayer +
        " · Alle polygonen samen vormen één gebied; alleen de buitenrand wordt getoond."
      : "Kies een bestand en de gewenste laag.";
  } else if (mode === "bounds") {
    title = "Eigen rechthoek";
    detail =
      [...q(".bounds-fields").querySelectorAll("input")].map((input) => input.value).join(", ") +
      " · " +
      data.crs;
  }
  q("#rm-selection-title").textContent = title;
  q("#rm-selection-detail").textContent = detail;
  q("#rm-draw-status").textContent =
    points.length + " punten" + (finished ? " · gesloten" : " · nog niet gesloten");
  q("#rm-finish").disabled = points.length < 3 || finished;
  q("#rm-undo").disabled = !points.length;
  q("#rm-file-name").textContent = filePath ? filePath.split(/[\\/]/).pop() : "Geen bestand gekozen";
  q("#rm-file-name").title = filePath ? "Volledig pad bekijken: " + filePath : "Kies een gebiedsbestand";
  q("#rm-file-path").textContent = filePath || "Nog geen bestand gekozen.";
  const fileAction = filePath ? "Ander bestand openen" : "Bestand openen";
  q("#rm-file-demo").setAttribute("aria-label", fileAction);
  q("#rm-file-demo").dataset.tooltip = fileAction;
  q("#rm-file-status").textContent = fileFeature
    ? "Alle polygonen in deze laag vormen samen het gebied."
    : filePath ? "Kies een laag om het gebied op de kaart te zien." : "Kies een bestand en daarna een laag.";
  q("#rm-file-layer").disabled = !filePath;
  for (const input of root.querySelectorAll("[data-flag]")) {
    // Opties mogen vooraf worden ingevuld, ook als de basislaag nog uit staat.
    input.disabled = input.dataset.authority === "true" && mode !== "authorities";
    if (input.dataset.layer === "dem" && input.dataset.flag === "landuse-run") {
      input.disabled = q("#rm-dem-landuse-mode").value === "auto";
    }
    for (const button of input.closest("label").querySelectorAll(".option-actions button")) {
      button.disabled = input.disabled;
    }
  }
}

function fitFeature(feature) {
  fitProjectedBounds(path.bounds(feature));
}

function fitProjectedBounds([[left, top], [right, bottom]]) {
  const factor = Math.min(
    350 / Math.max(right - left, 0.0001),
    450 / Math.max(bottom - top, 0.0001),
  );
  setZoom(factor, [(left + right) / 2, (top + bottom) / 2]);
}

let fileRequestVersion = 0;

function showLayerChoices(names, selectedLayer = "") {
  const select = q("#rm-file-layer");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Kies een laag…";
  placeholder.disabled = true;
  select.append(placeholder);
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.append(option);
  }
  select.value = selectedLayer;
}

async function showFileLayer(layer) {
  const version = ++fileRequestVersion;
  const chosenPath = filePath;
  fileFeature = null;
  fileLoaded = false;
  fileLayer = layer;
  render();
  if (!layer) {
    return;
  }
  q("#rm-file-status").textContent = "Laag laden…";
  try {
    const result = await api("polygon_layer", { path: chosenPath, layer });
    // Een later gekozen bestand of laag heeft voorrang op dit resultaat.
    if (version !== fileRequestVersion) {
      return;
    }
    fileFeature = result.feature;
    fileLoaded = true;
    showLayerChoices(result.layers, layer);
    render();
    if (mode === "file") {
      fitFeature(fileFeature);
      closeAreaPopovers();
    }
  } catch (error) {
    if (version === fileRequestVersion) {
      render();
      if (mode === "file") {
        openAreaPopover("file");
      }
      message(error.message);
    }
  }
}

async function choosePolygon() {
  q("#rm-message").hidden = true;
  const result = await api("polygon_file");
  if (result.cancelled) {
    return;
  }
  fileRequestVersion += 1;
  filePath = result.path;
  q("#rm-file-location").open = false;
  fileLayer = "";
  fileFeature = null;
  fileLoaded = false;
  // Eerst alleen de lagenlijst tonen; pas na een keuze de geometrie lezen.
  showLayerChoices(result.layers);
  render();
  if (mode === "file") {
    openAreaPopover("file");
  }
}

async function readBounds() {
  await act(useBounds, async () => {
    const bounds = [...q(".bounds-fields").querySelectorAll("input")].map((input) => input.value);
    const result = await api("bounds", { bounds });
    boundsFeature = result.feature;
    boundsSignature = JSON.stringify(bounds);
    render();
    fitFeature(boundsFeature);
    closeAreaPopovers();
  });
}

async function saveDrawnArea() {
  await act(saveDrawing, async () => {
    if (!finished) {
      throw new Error("Sluit eerst de polygoon.");
    }
    const result = await api("draw_save", {
      coordinates: points.map((point) => projection.invert(point)),
    });
    if (result.cancelled) {
      return;
    }
    drawingPath = result.path;
    savedDrawing = JSON.stringify(points);
    drawingToolsCollapsed = true;
    render();
    if (!drawingToolsToggle.hidden) {
      drawingToolsToggle.focus();
    }
  });
}

function addOptionActions(label, input, option, layer) {
  if (!["file", "directory", "toml"].includes(option.kind)) {
    return;
  }
  const actions = document.createElement("div");
  actions.className = "option-actions file-control";
  const choose = document.createElement("button");
  choose.type = "button";
  const actionName = option.kind === "directory" ? "Map openen" : option.kind === "toml" ? "TOML laden" : "Bestand openen";
  addFileIcon(choose, actionName + ": " + option.label);
  const feedback = document.createElement("div");
  feedback.className = "file-error";
  feedback.id = `rm-error-${layer}-${option.flag}`;
  feedback.setAttribute("aria-live", "polite");
  input.setAttribute("aria-describedby", feedback.id);
  const showError = (text = "") => {
    feedback.textContent = text;
    input.setAttribute("aria-invalid", String(Boolean(text)));
  };
  input.addEventListener("input", () => showError());
  input.addEventListener("change", () => {
    const value = input.value;
    if (!value.trim()) {
      return;
    }
    act(null, async () => {
      const result = await api("validate_path", { layer, flag: option.flag, path: value.trim() });
      if (input.value === value) {
        showError(result.error);
      }
    });
  });
  choose.onclick = () =>
    act(choose, async () => {
      const result = await api("browse", { layer, flag: option.flag });
      if (!result.cancelled) {
        input.value = result.path;
        showError(result.error);
        scheduleLandusePreview();
      }
    });
  actions.append(input, choose);
  label.append(actions, feedback);
  if (option.kind === "toml") {
    addBrandlagenControls(label, input, choose, actions);
  }
  if (layer === "dem" && option.flag === "landuse-run") {
    addLanduseControls(label, input, choose, actions);
  }
}

function addLanduseControls(label, input, choose, actions) {
  const group = document.createElement("section");
  group.className = "dem-landuse-group option-wide";
  const heading = document.createElement("label");
  heading.htmlFor = "rm-dem-landuse-mode";
  heading.textContent = "Landgebruik als basis";
  const explanation = document.createElement("p");
  explanation.className = "dem-landuse-explanation";
  explanation.textContent = "DEM gebruikt gebouwen en de tegelindeling uit een landgebruikrun.";
  const mode = document.createElement("select");
  mode.id = "rm-dem-landuse-mode";
  for (const [value, text] of [["auto", "Automatisch"], ["manual", "Zelf kiezen"]]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    mode.append(option);
  }
  const hint = document.createElement("p");
  hint.className = "dem-landuse-explanation";
  hint.textContent = "Gebruikt een geschikte afgeronde run. Ontbreekt die, dan wordt landgebruik eerst berekend.";
  label.replaceWith(group);
  group.append(heading, explanation, mode, hint, label);
  choose.classList.remove("file-browse");
  choose.textContent = "Landgebruikrun kiezen";
  actions.classList.remove("file-control");
  actions.classList.add("landuse-file-choice");
  label.querySelector("span").hidden = true;
  input.setAttribute("aria-label", "Map van de landgebruikrun");
  const update = () => {
    label.hidden = mode.value === "auto";
    hint.hidden = mode.value !== "auto";
    input.disabled = label.hidden;
    choose.disabled = label.hidden;
  };
  mode.addEventListener("change", () => {
    update();
    scheduleLandusePreview();
  });
  group.updateMode = update;
  update();
}

let landuseTimer;
let landuseRequest = 0;
let landuseSignature = "";
let landuseBusy = false;
let landusePending = null;

function scheduleLandusePreview(force = false) {
  const status = q("#rm-dem-landuse-status");
  if (!status || !q("#rm-dem-landuse-mode")) {
    return;
  }
  const enabled = q('#rm-layers input[value="dem"]').checked;
  status.hidden = !enabled;
  if (!enabled) {
    landuseRequest += 1;
    landuseSignature = "";
    landusePending = null;
    clearTimeout(landuseTimer);
    return;
  }
  let values;
  try {
    values = collectValues();
  } catch (error) {
    landuseRequest += 1;
    landuseSignature = "";
    landusePending = null;
    clearTimeout(landuseTimer);
    status.textContent = error.message;
    status.removeAttribute("title");
    return;
  }
  const signature = JSON.stringify(values);
  if (!force && signature === landuseSignature) {
    return;
  }
  landuseSignature = signature;
  landusePending = { values, version: ++landuseRequest };
  status.textContent = "Landgebruik controleren…";
  status.dataset.state = "checking";
  status.removeAttribute("title");
  clearTimeout(landuseTimer);
  landuseTimer = setTimeout(updateLandusePreview, 350);
}

async function updateLandusePreview() {
  if (landuseBusy || !landusePending) {
    return;
  }
  landuseBusy = true;
  const { values, version } = landusePending;
  landusePending = null;
  const status = q("#rm-dem-landuse-status");
  try {
    const result = await api("dem_landuse", values);
    if (version === landuseRequest) {
      status.textContent = result.message;
      status.dataset.state = result.state;
      status.title = [result.path, "Bij uitvoering wordt de keuze opnieuw gecontroleerd."].filter(Boolean).join("\n");
    }
  } catch (error) {
    if (version === landuseRequest) {
      status.textContent = error.message;
      status.dataset.state = "error";
    }
  } finally {
    landuseBusy = false;
    if (landusePending) {
      updateLandusePreview();
    }
  }
}

function addBrandlagenControls(label, input, choose, actions) {
  const group = document.createElement("div");
  group.className = "brandlagen-group option-wide";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "brandlagen-toggle";
  toggle.textContent = "Brandlagen instellen";
  toggle.setAttribute("aria-expanded", "false");
  const content = document.createElement("div");
  content.id = `rm-brandlagen-${input.dataset.layer}`;
  content.className = "brandlagen-content";
  content.hidden = true;
  toggle.setAttribute("aria-controls", content.id);
  toggle.onclick = () => {
    content.hidden = !content.hidden;
    toggle.setAttribute("aria-expanded", String(!content.hidden));
  };
  label.replaceWith(group);
  const create = document.createElement("button");
  create.type = "button";
  create.textContent = "Nieuw maken";
  const createActions = document.createElement("div");
  createActions.className = "brandlagen-choices";
  createActions.append(create, choose);
  label.querySelector("span").remove();
  input.setAttribute("aria-label", "Brandlagenbestand (.toml)");
  actions.classList.remove("file-control");
  actions.classList.add("brandlagen-file");
  choose.className = "";
  choose.removeAttribute("aria-label");
  choose.textContent = "TOML kiezen";
  input.placeholder = "Geen extra brandlagen gekozen";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.textContent = "Bewerken";
  edit.setAttribute("aria-label", "Gekozen brandlagen bewerken");
  const selectedFile = document.createElement("div");
  selectedFile.className = "brandlagen-selected";
  const update = () => {
    const selected = Boolean(input.value.trim());
    selectedFile.hidden = !selected;
    edit.hidden = !selected;
  };
  input.addEventListener("input", update);
  input.addEventListener("change", update);
  const openEditor = (button, path) => act(button, async () => {
    const result = await api("brand_edit", { path });
    if (result.path) {
      input.value = result.path;
      input.dispatchEvent(new Event("input"));
      input.dispatchEvent(new Event("change"));
    }
  });
  create.onclick = () => openEditor(create, "");
  edit.onclick = () => openEditor(edit, input.value);
  const browse = choose.onclick;
  choose.onclick = async () => {
    await browse();
    update();
  };
  const editorActions = document.createElement("div");
  editorActions.className = "option-actions";
  editorActions.append(edit);
  selectedFile.append(label, editorActions);
  content.append(createActions, selectedFile);
  group.append(toggle, content);
  update();
}

async function loadRun() {
  const run = await api("run_load");
  if (run.cancelled) {
    return;
  }
  mode = run.mode;
  selected = new Set(run.authorities);
  q("#rm-mode").value = mode;
  q("#rm-run-name").value = run.run_id;
  q("#rm-workers").value = run.workers;
  q("#rm-run-mode").value = run.run_mode;
  q("#rm-refresh").checked = run.refresh_sources;
  q("#rm-debug").checked = run.debug;
  for (const input of q("#rm-layers").querySelectorAll("input")) {
    input.checked = run.layers.includes(input.value);
  }
  for (const input of root.querySelectorAll("[data-flag]")) {
    const saved = run.extra_options.find(
      (option) => option.layer === input.dataset.layer && option.flag === input.dataset.flag,
    );
    if (input.type === "checkbox") {
      input.checked = saved ? saved.value : input.dataset.default === "true";
    } else {
      input.value = saved ? saved.value : input.dataset.default;
      input.dispatchEvent(new Event("input"));
    }
  }
  for (const group of root.querySelectorAll("details.option-group")) {
    group.open = [...group.querySelectorAll("[data-flag]")].some((input) => {
      const value = input.type === "checkbox" ? String(input.checked) : input.value;
      return value !== input.dataset.default;
    });
  }
  const landuseInput = q('[data-layer="dem"][data-flag="landuse-run"]');
  q("#rm-dem-landuse-mode").value = landuseInput.value.trim() ? "manual" : "auto";
  landuseInput.closest(".dem-landuse-group").updateMode();
  if (mode === "file") {
    filePath = run.area_file;
    await showFileLayer(run.area_layer);
  } else if (mode === "bounds") {
    [...q(".bounds-fields").querySelectorAll("input")].forEach(
      (input, index) => (input.value = run.bounds[index]),
    );
    const result = await api("bounds", { bounds: run.bounds });
    boundsFeature = result.feature;
    boundsSignature = JSON.stringify(run.bounds);
    fitFeature(boundsFeature);
  } else {
    fitCountry();
  }
  closeAreaPopovers();
  closeOptions();
  render();
}

async function saveRun(start) {
  const result = await api("save", { ...collectValues(), start });
  if (!result.cancelled) {
    showRunNotice(
      result.started ? "Opgeslagen en gestart" : "Opgeslagen",
      result.path,
      q(start ? "#rm-start" : "#rm-save"),
    );
  }
}

function initializeForm() {
  root.addEventListener("input", () => scheduleLandusePreview());
  root.addEventListener("change", () => scheduleLandusePreview());
  window.addEventListener("focus", () => scheduleLandusePreview(true));
  q("#rm-run-name").value = data.run_id;
  q("#rm-file-demo").onclick = () => act(q("#rm-file-demo"), choosePolygon);
  q("#rm-file-layer").onchange = () => act(null, () => showFileLayer(q("#rm-file-layer").value));
  q("#rm-load").onclick = () => act(q("#rm-load"), loadRun);
  q("#rm-save").onclick = () => act(q("#rm-save"), () => saveRun(false));
  q("#rm-start").onclick = () => act(q("#rm-start"), () => saveRun(true));
  const preview = q("#rm-script-preview");
  const previewButton = q("#rm-preview");
  q("#rm-script-close").onclick = () => preview.close();
  preview.addEventListener("close", () => previewButton.focus());
  preview.addEventListener("click", (event) => {
    if (event.target === preview) {
      preview.close();
    }
  });
  previewButton.onclick = () =>
    act(previewButton, async () => {
      const result = await api("preview", collectValues());
      q("#rm-message").hidden = true;
      preview.querySelector("pre").textContent = result.commands.join("\n\n");
      preview.showModal();
    });
  q("#rm-update").onclick = () =>
    act(q("#rm-update"), async () => {
      await api("update");
      message("Code bijwerken is gestart", {
        anchor: q("#rm-update"),
        detail: "Open Run maken opnieuw na het bijwerken.",
      });
      for (const button of root.querySelectorAll("button")) {
        button.disabled = true;
      }
    });

  for (const input of q(".bounds-fields").querySelectorAll("input")) {
    input.addEventListener("input", () => {
      boundsFeature = null;
      render();
    });
  }
  document.getElementById("loading").remove();
  root.hidden = false;
  render();
  fitCountry();
  scheduleTiles();
}

initializeForm();
