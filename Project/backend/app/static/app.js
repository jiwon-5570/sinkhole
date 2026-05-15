"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  mode: "scenario",
  analysisType: "region",
  regions: [],
  roads: [],
  topRisk: [],
  reports: [],
  selectedReports: new Set(),
  monitoringPoints: [],
  selectedRegionId: null,
  selectedRoadId: null,
  selectedRegionName: "",
  selectedRoadName: "",
  currentPayload: null,
  simulationRows: [],
  aiChatHistory: [],
  aiChatWelcomed: false,
  mapBounds: null,
  mapView: {
    latitude: 37.54,
    longitude: 127.04,
    zoom: 11,
  },
  mapPickActive: false,
  liveLocation: {
    name: "",
    latitude: null,
    longitude: null,
  },
};

let dashboardRefreshTimer = null;

const el = {
  pageTitle: $("pageTitle"),
  heroKicker: $("heroKicker"),
  heroHeadline: $("heroHeadline"),
  heroDescription: $("heroDescription"),
  controlsTitle: $("controlsTitle"),
  controlsDescription: $("controlsDescription"),
  statusText: $("statusText"),
  healthStatus: $("healthStatus"),
  metricDate: $("metricDate"),
  metricAverage: $("metricAverage"),
  metricRegionCount: $("metricRegionCount"),
  metricHighRisk: $("metricHighRisk"),
  metricMonitoring: $("metricMonitoring"),
  metricRecentCount: $("metricRecentCount"),
  averageRiskLabel: $("averageRiskLabel"),
  analysisType: $("analysisType"),
  regionSelect: $("regionSelect"),
  roadSelect: $("roadSelect"),
  roadControlsContainer: $("roadControlsContainer"),
  analysisDate: $("analysisDate"),
  liveControls: $("liveControls"),
  liveLocationInput: $("liveLocationInput"),
  selectedRegionText: $("selectedRegionText"),
  resultScore: $("resultScore"),
  resultLevel: $("resultLevel"),
  resultPriority: $("resultPriority"),
  resultCoords: $("resultCoords"),
  factorChart: $("factorChart"),
  topRiskBody: $("topRiskBody"),
  distributionChart: $("distributionChart"),
  trendChart: $("trendChart"),
  causeChart: $("causeChart"),
  reasonCards: $("reasonCards"),
  reportText: $("reportText"),
  reportList: $("reportList"),
  selectedReportsInfo: $("selectedReportsInfo"),
  selectAllReports: $("selectAllReports"),
  demoMap: $("demoMap"),
  googleMap: $("googleMap"),
  mapOverlay: $("mapOverlay"),
  mapPickLayer: $("mapPickLayer"),
  mapLegend: $("mapLegend"),
  mapNotes: $("mapNotes"),
  mapDescription: $("mapDescription"),
  modeBadge: $("modeBadge"),
  modeTitle: $("modeTitle"),
  languageSelect: $("languageSelect"),
  whatIfDrawer: $("whatIfDrawer"),
  whatIfPreset: $("whatIfPreset"),
  whatIfHorizon: $("whatIfHorizon"),
  whatIfRainfall: $("whatIfRainfall"),
  whatIfRainfallValue: $("whatIfRainfallValue"),
  whatIfGroundwater: $("whatIfGroundwater"),
  whatIfGroundwaterValue: $("whatIfGroundwaterValue"),
  whatIfDepth: $("whatIfDepth"),
  whatIfDepthValue: $("whatIfDepthValue"),
  whatIfDistance: $("whatIfDistance"),
  whatIfDistanceValue: $("whatIfDistanceValue"),
  whatIfGpr: $("whatIfGpr"),
  whatIfGprValue: $("whatIfGprValue"),
  whatIfFacility: $("whatIfFacility"),
  whatIfFacilityValue: $("whatIfFacilityValue"),
  whatIfPastSinkhole: $("whatIfPastSinkhole"),
  whatIfPastSinkholeValue: $("whatIfPastSinkholeValue"),
  whatIfEnvironment: $("whatIfEnvironment"),
  whatIfEnvironmentValue: $("whatIfEnvironmentValue"),
  whatIfConstruction: $("whatIfConstruction"),
  whatIfTargetOnly: $("whatIfTargetOnly"),
  whatIfMitigationGpr: $("whatIfMitigationGpr"),
  whatIfMitigationPipe: $("whatIfMitigationPipe"),
  whatIfMitigationDrainage: $("whatIfMitigationDrainage"),
  whatIfMitigationConstruction: $("whatIfMitigationConstruction"),
  whatIfMitigationMonitoring: $("whatIfMitigationMonitoring"),
  whatIfSummary: $("whatIfSummary"),
  whatIfResults: $("whatIfResults"),
  metricDetailDialog: $("metricDetailDialog"),
  metricDetailTitle: $("metricDetailTitle"),
  metricDetailSubtitle: $("metricDetailSubtitle"),
  metricDetailMap: $("metricDetailMap"),
  metricDetailList: $("metricDetailList"),
  metricDetailSummary: $("metricDetailSummary"),
  metricDetailActions: $("metricDetailActions"),
  metricDetailClose: $("metricDetailClose"),
  aiChatDialog: $("aiChatDialog"),
  aiChatMessages: $("aiChatMessages"),
  aiChatForm: $("aiChatForm"),
  aiChatInput: $("aiChatInput"),
  aiChatSendButton: $("aiChatSendButton"),
  aiChatClose: $("aiChatClose"),
};

const TEXT = {
  ko: {
    pageTitle: "Sinkhole Risk Dashboard",
    heroKicker: "대시보드",
    heroHeadline: "지반침하 위험 분석",
    heroDescription: "서울/수도권 지반침하 위험 현황과 지역별 분석을 한 화면에서 확인합니다.",
    controlsTitle: "분석 컨트롤",
    controlsDescription: "지역과 날짜를 선택한 뒤 위험도 분석 또는 AI 리포트를 실행합니다.",
    scenarioMode: "시나리오 모드",
    liveMode: "실시간 모드",
    analysisTypeRegion: "지역 단위",
    analysisTypeRoad: "도로 단위",
    noData: "데이터가 없습니다.",
    loading: "초기 데이터를 불러오는 중입니다.",
    ready: "대시보드가 준비되었습니다.",
    analyzed: "분석이 완료되었습니다.",
    reportDone: "리포트가 생성되었습니다.",
    reportEmpty: "리포트를 생성하면 이 영역에 요약이 표시됩니다.",
    selectedPdf: (count) => `선택된 PDF ${count}개`,
    liveMissing: "실시간 모드에서는 위치명을 입력해야 합니다.",
  },
  en: {
    pageTitle: "Sinkhole Risk Dashboard",
    heroKicker: "Dashboard",
    heroHeadline: "Sinkhole Risk Analysis",
    heroDescription: "Monitor sinkhole risk status and regional analysis in one dashboard.",
    controlsTitle: "Analysis Controls",
    controlsDescription: "Select a region/date, then run analysis or generate an AI report.",
    scenarioMode: "Scenario Mode",
    liveMode: "Live Mode",
    analysisTypeRegion: "Region",
    analysisTypeRoad: "Road",
    noData: "No data.",
    loading: "Loading initial data.",
    ready: "Dashboard is ready.",
    analyzed: "Analysis complete.",
    reportDone: "Report generated.",
    reportEmpty: "Generated report summary will appear here.",
    selectedPdf: (count) => `Selected PDFs: ${count}`,
    liveMissing: "Enter a location name in live mode.",
  },
};

function lang() {
  return localStorage.getItem("sinkhole_lang") || "ko";
}

function t() {
  return TEXT[lang()] || TEXT.ko;
}

function setText(node, value) {
  if (node) node.textContent = value;
}

function setStatus(message) {
  setText(el.statusText, message || "");
}

function setBusy(isBusy) {
  ["analyzeButton", "reportButton", "simulateRiskButton"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = Boolean(isBusy);
  });
}

function handleDelegatedAction(event) {
  const origin = event.target instanceof Element ? event.target : event.target?.parentElement;
  const button = origin?.closest("[data-action]");
  if (!button || button.disabled) return;

  switch (button.dataset.action) {
    case "analyze":
      event.preventDefault();
      runAnalysis();
      break;
    case "report":
      event.preventDefault();
      generateReport();
      break;
    default:
      break;
  }
}

function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  if (window.location.protocol === "file:") return `http://127.0.0.1:5000${path}`;
  return path;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), Number(options.timeoutMs || 12000));
  const init = {
    ...options,
    signal: options.signal || controller.signal,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  };
  try {
    const response = await fetch(apiUrl(path), init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.success === false) {
      throw new Error(payload.message || response.statusText || "Request failed.");
    }
    return Object.prototype.hasOwnProperty.call(payload, "data") ? payload.data : payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(lang() === "ko" ? "서버 응답 시간이 초과되었습니다. 백엔드 서버 상태를 확인해주세요." : "The server request timed out. Check the backend server.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function getClientClock() {
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const time = [
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join(":");
  const offsetMinutes = -now.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const offset = `UTC${sign}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  return {
    date,
    time,
    localDateTime: `${date}T${time}`,
    timezone,
    utcOffsetMinutes: offsetMinutes,
    label: `${date} ${time} (${timezone || offset})`,
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value, fraction = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toLocaleString(lang() === "ko" ? "ko-KR" : "en-US", {
    maximumFractionDigits: fraction,
    minimumFractionDigits: fraction,
  });
}

function formatBytes(size) {
  const number = Number(size || 0);
  if (number < 1024) return `${number} B`;
  if (number < 1024 * 1024) return `${(number / 1024).toFixed(1)} KB`;
  return `${(number / (1024 * 1024)).toFixed(1)} MB`;
}

function looksLikeCoordinates(value) {
  return /(^|[^\d.-])-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?($|[^\d.])/.test(String(value || "").trim());
}

function parseCoordinates(value) {
  const match = String(value || "").trim().match(/(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)/);
  if (!match) return null;
  const latitude = Number(match[1]);
  const longitude = Number(match[2]);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null;
  return { latitude, longitude };
}

function regionRoadAddress(region) {
  if (!region) return "도로명 주소 확인 필요";
  return region.road_address
    || REGION_ROAD_ADDRESSES[Number(region.region_id)]
    || region.address
    || region.region_name
    || "도로명 주소 확인 필요";
}

function roadRoadAddress(road) {
  if (!road) return "도로명 주소 확인 필요";
  const roadId = Number(road.road_id);
  const base = regionRoadAddress({ region_id: road.region_id });
  return road.road_address
    || ROAD_ROAD_ADDRESSES[roadId]
    || (base !== "도로명 주소 확인 필요" ? `${base} ${road.road_name || "도로"} 인근` : road.road_name)
    || "도로명 주소 확인 필요";
}

function nearestKnownRoadAddress(latitude, longitude) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  const points = [
    { latitude: 37.5640, longitude: 127.1738, address: REGION_ROAD_ADDRESSES[900001] },
    { latitude: 37.5239, longitude: 127.0264, address: REGION_ROAD_ADDRESSES[900002] },
    { latitude: 37.4778, longitude: 127.1242, address: REGION_ROAD_ADDRESSES[900003] },
    { latitude: 37.5223, longitude: 127.0762, address: REGION_ROAD_ADDRESSES[900004] },
    { latitude: 37.5254, longitude: 127.1235, address: REGION_ROAD_ADDRESSES[900005] },
    { latitude: 37.5666, longitude: 126.8312, address: REGION_ROAD_ADDRESSES[900006] },
    { latitude: 37.5275, longitude: 126.9269, address: REGION_ROAD_ADDRESSES[900007] },
    { latitude: 37.4780, longitude: 127.0265, address: REGION_ROAD_ADDRESSES[900008] },
    { latitude: 37.5724, longitude: 127.0268, address: REGION_ROAD_ADDRESSES[900009] },
    { latitude: 37.5734, longitude: 126.8783, address: REGION_ROAD_ADDRESSES[900010] },
    { latitude: 37.5246, longitude: 126.9693, address: REGION_ROAD_ADDRESSES[900011] },
    { latitude: 37.5239, longitude: 126.8805, address: REGION_ROAD_ADDRESSES[900012] },
  ];
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "도로명 주소 확인 필요";
  const nearest = points
    .map((point) => ({
      ...point,
      distance: Math.pow(lat - point.latitude, 2) + Math.pow(lng - point.longitude, 2),
    }))
    .sort((a, b) => a.distance - b.distance)[0];
  return nearest ? nearest.address : "도로명 주소 확인 필요";
}

function locationRoadAddress(location) {
  const value = [
    location?.road_address,
    location?.address,
    location?.formatted_address,
    location?.location_name,
    state.liveLocation.address,
    state.liveLocation.name,
  ].find((candidate) => candidate && !looksLikeCoordinates(candidate));
  if (value) return value;
  return nearestKnownRoadAddress(location?.latitude, location?.longitude);
}

function targetRoadAddress(target) {
  const value = [target?.road_address, target?.address, target?.name, target?.label]
    .find((candidate) => candidate && !looksLikeCoordinates(candidate));
  if (value) return value;
  return nearestKnownRoadAddress(target?.latitude, target?.longitude);
}

async function reverseGeocodeAddress(latitude, longitude) {
  const fallback = nearestKnownRoadAddress(latitude, longitude);
  try {
    const data = await api(`/api/geocode/reverse?lat=${encodeURIComponent(latitude)}&lng=${encodeURIComponent(longitude)}`, {
      timeoutMs: 9000,
    });
    const address = data?.address;
    if (address && !looksLikeCoordinates(address)) return address;
  } catch (error) {
    console.warn("reverse geocode failed", error);
  }
  return fallback;
}

async function geocodeLocationByAddress(address) {
  const query = String(address || "").trim();
  if (!query) throw new Error(t().liveMissing);
  const data = await api(`/api/geocode/search?q=${encodeURIComponent(query)}`, {
    timeoutMs: 12000,
  });
  const latitude = Number(data?.latitude);
  const longitude = Number(data?.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new Error("입력한 위치의 지도 좌표를 찾지 못했습니다. 도로명 주소를 더 구체적으로 입력해 주세요.");
  }
  const resolvedAddress = data?.address && !looksLikeCoordinates(data.address)
    ? data.address
    : query;
  return {
    address: resolvedAddress,
    latitude,
    longitude,
    source: data?.source || "geocode",
  };
}

function riskMeta(level, score) {
  const raw = String(level || "").toLowerCase();
  const value = Number(score || 0);
  let key = "low";
  if (raw.includes("very") || raw.includes("매우") || value >= 80) key = "very-high";
  else if (raw.includes("high") || raw.includes("높") || raw.includes("위험") || value >= 60) key = "high";
  else if (raw.includes("moderate") || raw.includes("medium") || raw.includes("중") || raw.includes("보통") || value >= 35) key = "mid";

  const labels = lang() === "ko"
    ? { "very-high": "매우 높음", high: "높음", mid: "중간", low: "낮음" }
    : { "very-high": "Very High", high: "High", mid: "Moderate", low: "Low" };
  const colors = {
    "very-high": "#ff5d5d",
    high: "#fb7b35",
    mid: "#f6b93b",
    low: "#33d17a",
  };
  return { key, label: labels[key], color: colors[key] };
}

function riskFillClass(meta) {
  if (meta.key === "very-high") return "very-high";
  if (meta.key === "high") return "high";
  if (meta.key === "mid") return "mid";
  return "low";
}

const DETAIL_FACTOR_LABELS = {
  past_sinkhole: "과거 침하 이력",
  gpr: "GPR/공동 탐사",
  facility: "시설물 노후도",
  rainfall: "강우 영향",
  groundwater: "지하수 변동",
  environment: "지형/환경",
  construction: "공사 영향",
};

const REGION_ROAD_ADDRESSES = {
  900001: "서울특별시 강동구 천호대로 1095 인근",
  900002: "서울특별시 강남구 테헤란로 152 인근",
  900003: "서울특별시 송파구 송파대로 167 인근",
  900004: "서울특별시 송파구 올림픽로 300 인근",
  900005: "서울특별시 송파구 중대로 135 인근",
  900006: "서울특별시 강서구 마곡중앙로 161 인근",
  900007: "서울특별시 영등포구 국회대로 608 인근",
  900008: "서울특별시 서초구 서초대로 396 인근",
  900009: "서울특별시 성동구 왕십리로 222 인근",
  900010: "서울특별시 마포구 월드컵북로 400 인근",
  900011: "서울특별시 용산구 한강대로 405 인근",
  900012: "서울특별시 구로구 디지털로 300 인근",
};

const ROAD_ROAD_ADDRESSES = {
  1001: "서울특별시 강남구 테헤란로 인근",
  1002: "서울특별시 송파구 송파대로 인근",
  1003: "서울특별시 강동구 천호대로 인근",
  1004: "서울특별시 강서구 마곡중앙로 인근",
  1005: "서울특별시 영등포구 국회대로 인근",
  1006: "서울특별시 서초구 서초대로 인근",
  1007: "서울특별시 마포구 월드컵북로 인근",
};

const RECENT_DETECTIONS = [];

function applyLanguage(code = lang()) {
  const next = TEXT[code] ? code : "ko";
  localStorage.setItem("sinkhole_lang", next);
  if (el.languageSelect) el.languageSelect.value = next;

  setText(el.pageTitle, t().pageTitle);
  setText(el.heroKicker, t().heroKicker);
  setText(el.heroHeadline, state.selectedRegionName ? `${state.selectedRegionName} 지반침하 위험 분석` : t().heroHeadline);
  setText(el.heroDescription, t().heroDescription);
  setText(el.controlsTitle, t().controlsTitle);
  setText(el.controlsDescription, t().controlsDescription);
  setText($("helpDemoModeButton"), t().scenarioMode);
  setText($("helpLiveModeButton"), t().liveMode);
  if (el.analysisType?.options?.length >= 2) {
    el.analysisType.options[0].textContent = t().analysisTypeRegion;
    el.analysisType.options[1].textContent = t().analysisTypeRoad;
  }
  setText($("locationSearchLabel"), next === "ko" ? "위치 검색" : "Location Search");
  setText($("applyLocationLabel"), next === "ko" ? "위치 적용" : "Apply Location");
  setText($("applyLocationButton"), next === "ko" ? "지도에 적용" : "Apply");
  updatePickOnMapButton();
  setMode(state.mode, { silent: true });
  renderReportSelection();
  if (state.currentPayload) {
    const payload = state.currentPayload;
    const name = payload.region?.region_name || payload.road?.road_name || payload.location?.location_name || state.selectedRegionName;
    renderResult(name, payload);
  }
}

function updateClock() {
  const clock = getClientClock();
  if (el.analysisDate && !el.analysisDate.value) el.analysisDate.value = clock.date;
  setText(el.metricDate, clock.label);
  return clock;
}

function setMode(mode, options = {}) {
  state.mode = mode === "live" ? "live" : "scenario";
  const scenario = state.mode === "scenario";
  el.liveControls?.classList.toggle("hidden", scenario);
  el.whatIfDrawer?.classList.toggle("hidden", !scenario);
  $("scenarioModeMenuButton")?.classList.toggle("active", scenario);
  $("liveModeMenuButton")?.classList.toggle("active", !scenario);
  updateAnalysisTypeControls();
  renderMap();
  if (!options.silent) {
    setStatus(scenario ? "시나리오 모드로 전환했습니다." : "실시간 모드로 전환했습니다.");
  }
}

function updateAnalysisTypeControls() {
  state.analysisType = el.analysisType?.value === "road" ? "road" : "region";
  const roadMode = state.mode === "scenario" && state.analysisType === "road";
  el.roadControlsContainer?.classList.toggle("hidden", !roadMode);
  setText($("top5Title"), roadMode ? "우선 점검 도로 TOP 5" : "우선 점검 TOP 5");
  setText($("top5Description"), roadMode ? "최신 도로 위험 점수 기준 정렬" : "최신 위험 점수 기준 정렬");
}

function mountWhatIfPanel() {
  const panel = el.whatIfDrawer;
  const controlPanel = document.querySelector(".control-panel");
  if (!panel || !controlPanel || panel.dataset.embedded === "1") return;
  panel.dataset.embedded = "1";
  panel.classList.add("embedded");
  controlPanel.insertAdjacentElement("afterend", panel);
}

function updatePickOnMapButton() {
  const button = $("pickOnMapButton");
  if (!button) return;
  button.textContent = state.mapPickActive
    ? (lang() === "ko" ? "지도 클릭 대기" : "Click Map")
    : (lang() === "ko" ? "지도에서 선택" : "Pick on Map");
  button.classList.toggle("primary", state.mapPickActive);
  button.classList.toggle("secondary", !state.mapPickActive);
}

function setMapPickActive(active) {
  state.mapPickActive = Boolean(active);
  if (state.mapPickActive) {
    renderMap({ forceMapFrame: true });
    setStatus(lang() === "ko" ? "\uC9C0\uB3C4\uC5D0\uC11C \uC120\uD0DD\uD560 \uC704\uCE58\uB97C \uD074\uB9AD\uD558\uC138\uC694." : "Click the map to choose a location.");
  }
  el.mapPickLayer?.classList.toggle("hidden", !state.mapPickActive);
  updatePickOnMapButton();
}

async function checkHealth() {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);
  try {
    const payload = await fetch(apiUrl("/api/health"), { signal: controller.signal }).then((res) => res.json());
    setText(el.healthStatus, payload.success === false ? "오류" : "정상");
  } catch {
    setText(el.healthStatus, "오프라인");
  } finally {
    window.clearTimeout(timeout);
  }
}

async function loadRegions() {
  const rows = await api("/api/regions");
  state.regions = Array.isArray(rows) ? rows : [];
  if (!el.regionSelect) return;
  el.regionSelect.innerHTML = "";
  state.regions.forEach((region) => {
    const option = document.createElement("option");
    option.value = String(region.region_id);
    option.textContent = region.region_name;
    el.regionSelect.appendChild(option);
  });
  if (state.regions.length) {
    state.selectedRegionId = Number(state.regions[0].region_id);
    state.selectedRegionName = state.regions[0].region_name;
    el.regionSelect.value = String(state.selectedRegionId);
    setText(el.heroHeadline, `${state.selectedRegionName} 지반침하 위험 분석`);
  }
}

async function loadRoads(regionId = state.selectedRegionId) {
  if (!regionId || state.mode !== "scenario") {
    state.roads = [];
    return;
  }
  const rows = await api(`/api/roads?region_id=${Number(regionId)}`);
  state.roads = Array.isArray(rows) ? rows : [];
  if (!el.roadSelect) return;
  el.roadSelect.innerHTML = "";
  if (!state.roads.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "도로 데이터 없음";
    el.roadSelect.appendChild(option);
    state.selectedRoadId = null;
    return;
  }
  state.roads.forEach((road) => {
    const option = document.createElement("option");
    option.value = String(road.road_id);
    option.textContent = `${road.road_name} (${road.road_type || "-"})`;
    el.roadSelect.appendChild(option);
  });
  state.selectedRoadId = Number(state.roads[0].road_id);
  state.selectedRoadName = state.roads[0].road_name;
  el.roadSelect.value = String(state.selectedRoadId);
}

function renderMetrics(summary = {}) {
  const average = Number(summary.average_risk_score || 0);
  const meta = riskMeta("", average);
  setText(el.metricAverage, formatNumber(average, 0));
  setText(el.averageRiskLabel, meta.label);
  setText(el.metricRegionCount, formatNumber(summary.region_count || state.regions.length || 0));
  setText(el.metricHighRisk, formatNumber(summary.high_risk_count || 0));
  setText(el.metricMonitoring, formatNumber(summary.monitoring_point_count ?? state.monitoringPoints.length ?? 0));
  setText(el.metricRecentCount, formatNumber(Math.max(Number(summary.recent_detection_count || 0), recentMonitoringRows().length)));
  document.documentElement.style.setProperty("--risk", String(Math.max(0, Math.min(100, average || 0))));
  setText($("overviewWatchCount"), formatNumber(Math.max(0, Number(summary.region_count || 0) - Number(summary.high_risk_count || 0))));
  setText($("overviewWarnCount"), formatNumber(summary.high_risk_count || 0));
  setText($("overviewHighCount"), formatNumber(summary.very_high_risk_count || 0));
}

function renderTopRisk(rows = []) {
  state.topRisk = Array.isArray(rows) ? rows : [];
  if (!el.topRiskBody) return;
  el.topRiskBody.innerHTML = "";
  if (!state.topRisk.length) {
    el.topRiskBody.innerHTML = `<tr><td colspan="4">${escapeHtml(t().noData)}</td></tr>`;
    return;
  }
  state.topRisk.slice(0, 5).forEach((row, index) => {
    const score = Number(row.total_risk_score || 0);
    const meta = riskMeta(row.risk_level, score);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.priority_rank ?? index + 1)}</td>
      <td>${escapeHtml(row.road_name || row.region_name || "-")}</td>
      <td>${formatNumber(score, 1)}</td>
      <td><span class="tag ${riskFillClass(meta)}">${escapeHtml(meta.label)}</span></td>
    `;
    tr.addEventListener("click", async () => {
      if (row.road_id) {
        el.analysisType.value = "road";
        updateAnalysisTypeControls();
        if (row.region_id) {
          state.selectedRegionId = Number(row.region_id);
          el.regionSelect.value = String(row.region_id);
          await loadRoads(row.region_id);
        }
        state.selectedRoadId = Number(row.road_id);
        if (el.roadSelect) el.roadSelect.value = String(row.road_id);
        await runRoadAnalysis();
      } else if (row.region_id) {
        state.selectedRegionId = Number(row.region_id);
        el.regionSelect.value = String(row.region_id);
        await runScenarioAnalysis();
      }
    });
    el.topRiskBody.appendChild(tr);
  });
}

function renderDistribution(rows = []) {
  renderBarRows(el.distributionChart, rows.map((row) => {
    const count = Number(row.count || 0);
    const meta = riskMeta(row.risk_level, 0);
    return {
      label: meta.label || row.risk_level || "-",
      value: count,
      className: riskFillClass(meta),
    };
  }), "count");
}

function renderBarRows(container, rows = [], mode = "score") {
  if (!container) return;
  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(t().noData)}</div>`;
    return;
  }
  const max = Math.max(...rows.map((row) => Number(row.value || 0)), 1);
  rows.forEach((row) => {
    const value = Number(row.value || 0);
    const item = document.createElement("div");
    item.className = mode === "cause" ? "cause-row" : mode === "count" ? "distribution-row" : "factor-row";
    item.innerHTML = `
      <span title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
      <div class="bar-track"><div class="bar-fill ${escapeHtml(row.className || "")}" style="width:${Math.max(4, (value / max) * 100)}%"></div></div>
      <strong>${mode === "score" ? formatNumber(value, 1) : formatNumber(value, 0)}</strong>
    `;
    container.appendChild(item);
  });
}

function renderFactors(breakdown = {}) {
  const rows = [
    { label: "과거 사고", value: breakdown.past_sinkhole },
    { label: "GPR/탐사", value: breakdown.gpr },
    { label: "시설물", value: breakdown.facility },
    { label: "강우", value: breakdown.rainfall },
    { label: "지하수", value: breakdown.groundwater },
    { label: "환경", value: breakdown.environment },
    { label: "공사 영향", value: breakdown.construction },
  ].map((row) => {
    const meta = riskMeta("", Number(row.value || 0) * 4);
    return { ...row, className: riskFillClass(meta) };
  });
  renderBarRows(el.factorChart, rows, "score");
}

function renderReasonCards(cards = []) {
  if (!el.reasonCards) return;
  el.reasonCards.innerHTML = "";
  const safeCards = Array.isArray(cards) ? cards : [];
  if (!safeCards.length) {
    const card = document.createElement("article");
    card.className = "reason-card";
    card.innerHTML = `
      <div class="reason-card-badge">AI</div>
      <h4>분석 대기</h4>
      <p>위험도 분석을 실행하면 점수 산정 근거가 이 영역에 표시됩니다.</p>
    `;
    el.reasonCards.appendChild(card);
    return;
  }
  safeCards.slice(0, 3).forEach((source) => {
    const card = document.createElement("article");
    card.className = "reason-card";
    if (source.badge) {
      const badge = document.createElement("div");
      badge.className = "reason-card-badge";
      badge.textContent = String(source.badge);
      card.appendChild(badge);
    }
    const title = document.createElement("h4");
    title.textContent = String(source.title || "AI 분석 근거");
    const body = document.createElement("p");
    body.textContent = String(source.body || "");
    card.append(title, body);
    if (Array.isArray(source.meta) && source.meta.length) {
      const meta = document.createElement("div");
      meta.className = "reason-card-meta";
      source.meta.slice(0, 4).forEach((row) => {
        const chip = document.createElement("span");
        chip.textContent = `${row?.label ? `${row.label}: ` : ""}${row?.value ?? ""}`;
        meta.appendChild(chip);
      });
      card.appendChild(meta);
    }
    el.reasonCards.appendChild(card);
  });
}

function renderResult(name, payload) {
  state.currentPayload = payload;
  const analysis = payload.analysis || {};
  const score = Number(analysis.total_risk_score || 0);
  const meta = riskMeta(analysis.risk_level, score);
  const address = payload.region
    ? regionRoadAddress(payload.region)
    : payload.road
      ? roadRoadAddress(payload.road)
      : payload.location
        ? locationRoadAddress(payload.location)
        : "-";
  const locationDisplayName = payload.location ? address : "";
  const safeName = name && !looksLikeCoordinates(name) ? name : "";
  const displayName = payload.region
    ? (safeName || payload.region.region_name || "-")
    : payload.road
      ? (safeName || payload.road.road_name || "-")
      : (locationDisplayName || safeName || "-");
  const headlineName = payload.region
    ? (payload.region.region_name || displayName)
    : payload.road
      ? (payload.road.road_name || displayName)
      : (locationDisplayName || displayName);
  state.selectedRegionName = headlineName;

  setText(el.selectedRegionText, displayName);
  setText(el.resultScore, Number.isFinite(score) ? score.toFixed(1) : "-");
  setText(el.resultLevel, meta.label);
  setText(el.resultPriority, analysis.priority_rank ?? "-");
  setText(el.heroHeadline, `${headlineName} 위험 분석`);
  setText(el.resultCoords, address);
  document.querySelector(".score-ring")?.style.setProperty("--score-value", String(Math.max(0, Math.min(100, score))));
  document.querySelector(".score-ring")?.style.setProperty("--score-color", meta.color);
  renderFactors(payload.breakdown || {});
  renderReasonCards(payload.reason_cards || []);
  renderMap();
}

function renderTrendChart(rows = [], type = "risk") {
  if (!el.trendChart) return;
  const data = (Array.isArray(rows) ? rows : [])
    .map((row) => ({
      label: String(row.analysis_date || row.month || "-"),
      value: Number(row.total_risk_score ?? row.count ?? 0),
    }))
    .filter((row) => Number.isFinite(row.value));

  if (!data.length) {
    el.trendChart.innerHTML = `<div class="trend-empty">${escapeHtml(t().noData)}</div>`;
    return;
  }

  const values = data.map((row) => row.value);
  const max = Math.max(100, ...values);
  const min = 0;
  const width = 640;
  const height = 240;
  const left = 42;
  const right = width - 20;
  const top = 22;
  const bottom = height - 42;
  const point = (idx, value) => {
    const x = data.length === 1 ? (left + right) / 2 : left + (idx / (data.length - 1)) * (right - left);
    const y = bottom - ((value - min) / (max - min || 1)) * (bottom - top);
    return { x, y };
  };
  const points = data.map((row, idx) => point(idx, row.value));
  const line = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${left},${bottom} ${line} ${right},${bottom}`;
  const markers = points.map((p, idx) => {
    const row = data[idx];
    return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#f6b93b"><title>${escapeHtml(`${row.label} ${row.value.toFixed(type === "risk" ? 1 : 0)}`)}</title></circle>`;
  }).join("");
  const labels = [0, Math.floor((data.length - 1) / 2), data.length - 1]
    .filter((idx, pos, arr) => idx >= 0 && arr.indexOf(idx) === pos)
    .map((idx) => `<text x="${points[idx].x.toFixed(1)}" y="${height - 14}" text-anchor="middle" fill="#94a9c8" font-size="12">${escapeHtml(data[idx].label.slice(-5))}</text>`)
    .join("");
  const grid = [0, 25, 50, 75, 100].map((tick) => {
    const y = point(0, tick).y;
    return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${right}" y2="${y.toFixed(1)}" stroke="rgba(148,169,200,.15)" /><text x="${left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end" fill="#94a9c8" font-size="11">${tick}</text>`;
  }).join("");
  const latest = values[values.length - 1] || 0;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;

  el.trendChart.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="위험도 추이 차트">
      ${grid}
      <polygon points="${area}" fill="rgba(246,185,59,.14)"></polygon>
      <polyline points="${line}" fill="none" stroke="#f6b93b" stroke-width="3"></polyline>
      ${markers}
      ${labels}
    </svg>
    <div class="trend-meta">
      <span>Latest ${latest.toFixed(1)}</span>
      <span>Average ${avg.toFixed(1)}</span>
      <span>Points ${data.length}</span>
    </div>
  `;
}

function renderCauseDistribution(rows = []) {
  const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0);
  renderBarRows(el.causeChart, rows.map((row) => ({
    label: row.cause_type || "미상",
    value: Number(row.count || 0),
    className: "mid",
  })), "cause");
  if (el.causeChart && rows.length) {
    const note = document.createElement("p");
    note.className = "data-source";
    const fallback = rows.some((row) => row.scope === "all_regions_fallback");
    note.textContent = fallback
      ? `선택 지역 사고 이력 없음 · 서울/수도권 전체 ${formatNumber(total)}건 기준`
      : `총 ${formatNumber(total)}건 기준`;
    el.causeChart.appendChild(note);
  }
}

async function refreshRegionalCharts() {
  if (state.mode !== "scenario" || !state.selectedRegionId || state.analysisType !== "region") {
    renderTrendChart([]);
    renderCauseDistribution([]);
    return;
  }
  const regionId = Number(state.selectedRegionId);
  const [trend, cause] = await Promise.allSettled([
    api(`/api/charts/risk-trend?region_id=${regionId}`),
    api(`/api/charts/sinkhole-cause-distribution?region_id=${regionId}`),
  ]);
  if (trend.status === "fulfilled" && trend.value.length) {
    renderTrendChart(trend.value, "risk");
  } else {
    const fallback = await api(`/api/charts/sinkhole-occurrence-trend?region_id=${regionId}&months=24`).catch(() => []);
    renderTrendChart(fallback, "occurrence");
  }
  renderCauseDistribution(cause.status === "fulfilled" ? cause.value : []);
}

function computeMapBounds(points) {
  const coords = points
    .map((item) => ({ lat: Number(item.latitude ?? item.center_lat), lng: Number(item.longitude ?? item.center_lon) }))
    .filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lng));
  if (!coords.length) {
    return { minLat: 34.9, maxLat: 35.3, minLng: 127.95, maxLng: 128.21 };
  }
  let minLat = Math.min(...coords.map((item) => item.lat));
  let maxLat = Math.max(...coords.map((item) => item.lat));
  let minLng = Math.min(...coords.map((item) => item.lng));
  let maxLng = Math.max(...coords.map((item) => item.lng));
  const latPad = Math.max((maxLat - minLat) * 0.25, 0.03);
  const lngPad = Math.max((maxLng - minLng) * 0.25, 0.03);
  minLat -= latPad;
  maxLat += latPad;
  minLng -= lngPad;
  maxLng += lngPad;
  return { minLat, maxLat, minLng, maxLng };
}

function projectToMap(lat, lng, bounds = state.mapBounds) {
  const x = 80 + ((Number(lng) - bounds.minLng) / (bounds.maxLng - bounds.minLng || 1)) * 600;
  const y = 450 - ((Number(lat) - bounds.minLat) / (bounds.maxLat - bounds.minLat || 1)) * 360;
  return {
    x: Math.max(54, Math.min(706, x)),
    y: Math.max(54, Math.min(486, y)),
  };
}

function scoreForRegion(region) {
  const simulated = state.simulationRows.find((row) => Number(row.region_id) === Number(region.region_id));
  if (simulated) return { score: Number(simulated.simulated_score || 0), level: simulated.new_risk_level };
  const top = state.topRisk.find((row) => Number(row.region_id) === Number(region.region_id));
  if (top) return { score: Number(top.total_risk_score || 0), level: top.risk_level };
  if (state.currentPayload?.region?.region_id === region.region_id) {
    return {
      score: Number(state.currentPayload.analysis?.total_risk_score || 0),
      level: state.currentPayload.analysis?.risk_level,
    };
  }
  return { score: 28, level: "낮음" };
}

function findRegionById(regionId) {
  return state.regions.find((region) => Number(region.region_id) === Number(regionId));
}

function regionPoint(region, extra = {}) {
  if (!region) return null;
  const risk = scoreForRegion(region);
  const score = Number(extra.score ?? risk.score ?? 0);
  const meta = riskMeta(extra.level || risk.level, score);
  return {
    label: extra.label || region.region_name || "-",
    address: extra.address || regionRoadAddress(region),
    latitude: Number(region.latitude),
    longitude: Number(region.longitude),
    score,
    riskClass: riskFillClass(meta),
  };
}

function monitoringPointRisk(point) {
  const score = Number(point?.risk_score ?? 0);
  return riskMeta(point?.risk_level, score);
}

function monitoringPointLabel(point) {
  return point?.address || point?.name || `모니터링 지점 ${point?.id || ""}`.trim();
}

function monitoringPointMapPoint(point) {
  const score = Number(point?.risk_score ?? 0);
  const meta = monitoringPointRisk(point);
  return {
    label: point?.name || point?.address || `지점 ${point?.id || ""}`.trim(),
    address: monitoringPointLabel(point),
    latitude: Number(point?.latitude),
    longitude: Number(point?.longitude),
    score,
    riskClass: riskFillClass(meta),
  };
}

function highRiskRegionRows() {
  const rows = state.topRisk
    .filter((row) => Number(row.total_risk_score || 0) >= 60)
    .sort((a, b) => Number(b.total_risk_score || 0) - Number(a.total_risk_score || 0));
  return rows.length ? rows : state.topRisk.slice(0, 3);
}

function recentMonitoringRows() {
  const cutoff = Date.now() - (24 * 60 * 60 * 1000);
  return state.monitoringPoints
    .filter((point) => point?.last_checked_at && point?.risk_score !== null && point?.risk_score !== undefined)
    .filter((point) => {
      const checkedAt = Date.parse(String(point.last_checked_at).replace(" ", "T"));
      return !Number.isFinite(checkedAt) || checkedAt >= cutoff;
    })
    .map((point) => {
      const score = Number(point.risk_score || 0);
      const meta = monitoringPointRisk(point);
      const title = point.name || point.address || `모니터링 지점 ${point.id || ""}`.trim();
      return {
        title,
        address: point.address || title,
        latitude: Number(point.latitude),
        longitude: Number(point.longitude),
        score,
        time: point.last_checked_at,
        type: "모니터링 지점",
        status: point.last_error ? "갱신 오류" : `${meta.label} 위험도 갱신`,
      };
    });
}

function recentDetectionRows() {
  if (RECENT_DETECTIONS.length) return RECENT_DETECTIONS;
  return recentMonitoringRows();
}

function metricDetailPoints(kind) {
  if (kind === "highRiskRegions") {
    return highRiskRegionRows().map((row) => {
      const region = findRegionById(row.region_id);
      return regionPoint(region, {
        label: row.region_name,
        score: Number(row.total_risk_score || 0),
        level: row.risk_level,
      });
    }).filter(Boolean);
  }
  if (kind === "recentDetections") {
    return recentDetectionRows().map((row) => ({
      label: row.title,
      address: row.address || nearestKnownRoadAddress(row.latitude, row.longitude),
      latitude: row.latitude,
      longitude: row.longitude,
      score: row.score,
      riskClass: riskFillClass(riskMeta("", row.score)),
    }));
  }
  if (kind === "monitoringPoints") {
    return state.monitoringPoints.map(monitoringPointMapPoint).filter(Boolean);
  }
  return state.regions.map((region) => regionPoint(region)).filter(Boolean);
}

function topBreakdownItems(payload) {
  const breakdown = payload?.breakdown || {};
  return Object.entries(breakdown)
    .filter(([key]) => key !== "total")
    .map(([key, value]) => ({
      label: DETAIL_FACTOR_LABELS[key] || key,
      value: Number(value || 0),
    }))
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => b.value - a.value)
    .slice(0, 4);
}

function metricDetailGoogleTarget(points) {
  const primary = [...points].sort((a, b) => Number(b.score || 0) - Number(a.score || 0))[0];
  const latitude = Number(primary?.latitude);
  const longitude = Number(primary?.longitude);
  const hasCoords = Number.isFinite(latitude) && Number.isFinite(longitude);
  const query = encodeURIComponent(hasCoords ? `${latitude},${longitude}` : primary?.label || "Seoul");
  const center = hasCoords ? `&ll=${encodeURIComponent(`${latitude},${longitude}`)}` : "";
  const zoom = points.length > 3 ? 12 : 14;
  return {
    label: primary?.label || "선택 지역",
    addressText: targetRoadAddress(primary),
    src: `https://maps.google.com/maps?q=${query}${center}&z=${zoom}&output=embed`,
    openUrl: `https://www.google.com/maps/search/?api=1&query=${query}`,
  };
}

function metricDetailMapHtml(points = []) {
  const valid = points
    .filter((point) => Number.isFinite(Number(point.latitude)) && Number.isFinite(Number(point.longitude)))
    .slice(0, 12);
  if (!valid.length) {
    return `
      <div class="fallback-target">
        <span></span>
        <strong>표시할 위치 데이터가 없습니다.</strong>
        <small>분석 지역을 선택하면 지도 지점이 표시됩니다.</small>
      </div>
    `;
  }
  const bounds = computeMapBounds(valid);
  const target = metricDetailGoogleTarget(valid);
  const markers = valid.map((point) => {
    const x = 8 + ((Number(point.longitude) - bounds.minLng) / (bounds.maxLng - bounds.minLng || 1)) * 84;
    const y = 92 - ((Number(point.latitude) - bounds.minLat) / (bounds.maxLat - bounds.minLat || 1)) * 84;
    return `
      <span class="detail-map-pin ${escapeHtml(point.riskClass || "low")}" style="left:${x.toFixed(2)}%; top:${y.toFixed(2)}%"></span>
      <span class="detail-map-label" style="left:${x.toFixed(2)}%; top:${y.toFixed(2)}%">${escapeHtml(point.label)} ${Number(point.score || 0).toFixed(1)}</span>
    `;
  }).join("");
  return `
    <div class="google-map-fallback metric-detail-map-fallback">
      <div class="fallback-grid"></div>
      <div class="fallback-target">
        <span></span>
        <strong>${escapeHtml(target.label)}</strong>
        <small>${escapeHtml(target.addressText)}</small>
      </div>
    </div>
    <iframe
      class="detail-google-frame"
      title="Google Maps - ${escapeHtml(target.label)}"
      loading="lazy"
      allowfullscreen
      referrerpolicy="no-referrer-when-downgrade"
      src="${target.src}">
    </iframe>
    <div class="detail-map-overlay">${markers}</div>
    <a class="map-open-link detail-map-open-link" href="${target.openUrl}" target="_blank" rel="noreferrer">Google 지도 새 창</a>
  `;
}

function monitoringDetailListHtml() {
  const count = state.monitoringPoints.length;
  const disabled = count >= 10 ? "disabled" : "";
  const rows = state.monitoringPoints.map((point) => {
    const score = Number(point.risk_score || 0);
    const meta = monitoringPointRisk(point);
    const value = point.last_error
      ? "갱신 오류"
      : point.last_checked_at
        ? `${formatNumber(score, 1)} ${meta.label}`
        : "갱신 대기";
    return `
      <article class="metric-detail-row monitoring-point-row">
        <div>
          <strong>${escapeHtml(point.name || point.address || `모니터링 지점 ${point.id}`)}</strong>
          <span>${escapeHtml(point.address || "-")}</span>
          <small>${escapeHtml(point.last_error || (point.last_checked_at ? `마지막 갱신 ${point.last_checked_at}` : "자동 갱신 대기"))}</small>
        </div>
        <div class="monitoring-row-actions">
          <b>${escapeHtml(value)}</b>
          <button type="button" class="secondary" data-monitoring-remove="${escapeHtml(point.id)}">해제</button>
        </div>
      </article>
    `;
  }).join("");

  return `
    <div class="monitoring-point-controls">
      <div class="monitoring-count">
        <strong>${formatNumber(count)} / 10</strong>
        <span>등록된 모니터링 지점</span>
      </div>
      <div class="monitoring-add-row">
        <input id="monitoringPointInput" type="text" placeholder="예: 서울특별시 송파구 송파대로 167" ${disabled}>
        <button id="monitoringPointAddButton" class="primary" type="button" ${disabled}>지점 추가</button>
      </div>
      <div class="monitoring-action-row">
        <button id="monitoringCurrentButton" class="secondary" type="button" ${disabled}>현재 선택 위치 추가</button>
        <button id="monitoringRefreshButton" class="secondary" type="button">전체 갱신</button>
      </div>
      ${count >= 10 ? `<p class="monitoring-note">최대 10개까지 등록할 수 있습니다. 새 지점을 추가하려면 기존 지점을 해제하세요.</p>` : ""}
    </div>
    <div class="monitoring-point-list">
      ${rows || `<div class="empty-state">등록된 지점이 없습니다.</div>`}
    </div>
  `;
}

async function loadMonitoringPoints(options = {}) {
  const shouldRefresh = Boolean(options.refresh);
  const path = shouldRefresh
    ? `/api/monitoring-points/refresh${options.force ? "?force=true" : ""}`
    : "/api/monitoring-points";
  const data = await api(path, {
    method: shouldRefresh ? "POST" : "GET",
    timeoutMs: shouldRefresh ? 45000 : 12000,
  });
  state.monitoringPoints = Array.isArray(data?.points) ? data.points : [];
  setText(el.metricMonitoring, formatNumber(state.monitoringPoints.length));
  return state.monitoringPoints;
}

async function refreshMonitoringDetail(options = {}) {
  await loadMonitoringPoints({ refresh: true, force: Boolean(options.force) });
  renderMetricDetail(buildMetricDetail("monitoringPoints", {
    monitoring_point_count: state.monitoringPoints.length,
  }));
  await refreshSummaryPanels();
}

async function addMonitoringPoint(inputValue) {
  const raw = String(inputValue || "").trim();
  if (!raw) {
    setStatus("모니터링할 도로명 주소를 입력해 주세요.");
    return;
  }
  if (state.monitoringPoints.length >= 10) {
    setStatus("모니터링 지점은 최대 10개까지 등록할 수 있습니다.");
    return;
  }
  setStatus("모니터링 지점 위치를 확인하는 중입니다.");
  const coordinates = parseCoordinates(raw);
  const resolved = coordinates
    ? {
        ...coordinates,
        address: await reverseGeocodeAddress(coordinates.latitude, coordinates.longitude),
      }
    : await geocodeLocationByAddress(raw);
  const address = resolved.address || raw;
  await api("/api/monitoring-points", {
    method: "POST",
    timeoutMs: 45000,
    body: JSON.stringify({
      name: address,
      address,
      latitude: Number(resolved.latitude),
      longitude: Number(resolved.longitude),
    }),
  });
  await refreshMonitoringDetail({ force: false });
  setStatus(`모니터링 지점을 추가했습니다: ${address}`);
}

async function addCurrentMapTargetAsMonitoringPoint() {
  const target = selectedMapTarget();
  const latitude = Number(target?.latitude);
  const longitude = Number(target?.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    setStatus("현재 추가할 수 있는 지도 위치가 없습니다.");
    return;
  }
  const address = targetRoadAddress(target) || target.name || "선택 위치";
  await api("/api/monitoring-points", {
    method: "POST",
    timeoutMs: 45000,
    body: JSON.stringify({
      name: address,
      address,
      latitude,
      longitude,
    }),
  });
  await refreshMonitoringDetail({ force: false });
  setStatus(`현재 선택 위치를 모니터링 지점으로 추가했습니다: ${address}`);
}

function bindMonitoringDetailControls() {
  $("monitoringPointAddButton")?.addEventListener("click", async () => {
    const button = $("monitoringPointAddButton");
    if (button) button.disabled = true;
    try {
      await addMonitoringPoint($("monitoringPointInput")?.value);
    } catch (error) {
      setStatus(error.message);
    } finally {
      if (button) button.disabled = state.monitoringPoints.length >= 10;
    }
  });
  $("monitoringPointInput")?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    try {
      await addMonitoringPoint(event.currentTarget.value);
    } catch (error) {
      setStatus(error.message);
    }
  });
  $("monitoringCurrentButton")?.addEventListener("click", async () => {
    try {
      await addCurrentMapTargetAsMonitoringPoint();
    } catch (error) {
      setStatus(error.message);
    }
  });
  $("monitoringRefreshButton")?.addEventListener("click", async () => {
    const button = $("monitoringRefreshButton");
    if (button) button.disabled = true;
    setStatus("모니터링 지점을 갱신하는 중입니다.");
    try {
      await refreshMonitoringDetail({ force: true });
      setStatus("모니터링 지점 갱신이 완료되었습니다.");
    } catch (error) {
      setStatus(error.message);
    } finally {
      if (button) button.disabled = false;
    }
  });
  document.querySelectorAll("[data-monitoring-remove]").forEach((button) => {
    button.addEventListener("click", async () => {
      const pointId = button.getAttribute("data-monitoring-remove");
      if (!pointId) return;
      button.disabled = true;
      try {
        await api(`/api/monitoring-points/${encodeURIComponent(pointId)}`, {
          method: "DELETE",
          timeoutMs: 12000,
        });
        await refreshMonitoringDetail({ force: false });
        setStatus("모니터링 지점을 해제했습니다.");
      } catch (error) {
        setStatus(error.message);
      }
    });
  });
}

function renderMetricDetail(detail) {
  setText(el.metricDetailTitle, detail.title);
  setText(el.metricDetailSubtitle, detail.subtitle);
  if (el.metricDetailMap) el.metricDetailMap.innerHTML = metricDetailMapHtml(detail.points);
  if (el.metricDetailList) {
    if (detail.kind === "monitoringPoints") {
      el.metricDetailList.innerHTML = monitoringDetailListHtml();
      bindMonitoringDetailControls();
    } else {
      el.metricDetailList.innerHTML = detail.rows.map((row) => `
        <article class="metric-detail-row">
          <div>
            <strong>${escapeHtml(row.title)}</strong>
            <span>${escapeHtml(row.meta)}</span>
          </div>
          <b>${escapeHtml(row.value)}</b>
        </article>
      `).join("");
    }
  }
  if (el.metricDetailSummary) {
    el.metricDetailSummary.innerHTML = `
      <h4>${escapeHtml(detail.summaryTitle)}</h4>
      ${detail.summary.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
    `;
  }
  if (el.metricDetailActions) {
    el.metricDetailActions.innerHTML = `
      <ol>
        ${detail.actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ol>
    `;
  }
}

function buildMetricDetail(kind, payload = null) {
  const average = Number(el.metricAverage?.textContent?.replace(/[^\d.]/g, "") || 0);
  const regionCount = state.regions.length;
  const highRows = highRiskRegionRows();
  const monitoringCount = Number(payload?.monitoring_point_count || 0);
  const currentRegion = payload?.region || findRegionById(highRows[0]?.region_id) || findRegionById(state.selectedRegionId) || state.regions[0];
  const factors = topBreakdownItems(payload);
  const factorText = factors.length
    ? factors.map((item) => `${item.label} ${item.value.toFixed(1)}점`).join(", ")
    : "과거 침하 이력, GPR 탐사 결과, 시설물 노후도, 강우/지하수 변동";

  if (kind === "averageRisk") {
    return {
      title: "서울/수도권 평균 위험도 상세",
      subtitle: `현재 평균 위험도는 ${formatNumber(average, 0)}점이며 등록된 서울/수도권 분석 대상의 위험 수준을 종합한 지표입니다.`,
      points: metricDetailPoints(kind),
      rows: state.regions.slice(0, 5).map((region) => {
        const risk = scoreForRegion(region);
        return { title: region.region_name, meta: "분석 대상 지역", value: formatNumber(risk.score, 1) };
      }),
      summaryTitle: "AI 종합 판단",
      summary: [
        `평균 위험도 ${formatNumber(average, 0)}점은 서울/수도권 분석 대상의 위험 점수를 합산해 본 운영 관점의 대표 지표입니다.`,
        "평균값은 낮아 보여도 일부 고위험 지역이 존재하면 현장 대응 우선순위는 고위험 지역 중심으로 잡아야 합니다.",
      ],
      actions: [
        "상위 위험 지역의 GPR 재탐사와 지하시설물 점검을 먼저 완료합니다.",
        "반복 탐지 지역은 점검 주기를 단축하고 강우 이후 재평가를 자동화합니다.",
        "고위험 원인 항목을 낮추면 평균 점수도 함께 내려갑니다.",
      ],
    };
  }

  if (kind === "forecastRegions") {
    return {
      title: "예측 지역 수 상세",
      subtitle: `${regionCount}개 지역이 현재 위험도 예측 및 우선순위 산정 대상입니다.`,
      points: metricDetailPoints(kind),
      rows: state.regions.map((region) => {
        const risk = scoreForRegion(region);
        return { title: region.region_name, meta: `${region.sido || ""} ${region.sigungu || ""}`.trim() || "예측 대상", value: formatNumber(risk.score, 1) };
      }),
      summaryTitle: "AI 예측 범위 판단",
      summary: [
        "예측 지역 수는 현재 모델이 위험 점수와 우선순위를 산정하는 공간 범위입니다.",
        "지역 수가 늘어날수록 누락 위험은 줄어들지만, 데이터 최신성 관리와 센서 품질 검증이 중요해집니다.",
      ],
      actions: [
        "지역별 최신 GPR/침하/공사/강우 데이터를 같은 기준으로 갱신합니다.",
        "데이터 공백 지역은 임시 점검 등급을 부여하고 현장 확인 후 모델에 반영합니다.",
        "위험도 상위 지역부터 예산과 점검 인력을 배정해 전체 예측 신뢰도를 높입니다.",
      ],
    };
  }

  if (kind === "highRiskRegions") {
    const targetName = currentRegion?.region_name || highRows[0]?.region_name || "고위험 지역";
    return {
      title: "높은 위험 지역 상세",
      subtitle: `${highRows.length}개 지역이 고위험 이상으로 분류되었습니다. 대표 지역: ${targetName}`,
      points: metricDetailPoints(kind),
      rows: highRows.map((row) => ({
        title: row.region_name || "-",
        meta: `위험 단계 ${row.risk_level || "-"} / 우선순위 ${row.priority_rank || "-"}`,
        value: formatNumber(row.total_risk_score, 1),
      })),
      summaryTitle: "AI 고위험 판단 근거",
      summary: [
        `${targetName}은 ${factorText} 항목이 위험 점수 상승에 크게 기여해 고위험으로 판단됩니다.`,
        payload?.reason_cards?.[0]?.body || "고위험 지역은 단일 원인보다 과거 침하, 지중 공동 탐지, 노후 시설물, 강우 또는 공사 영향이 겹칠 때 점수가 빠르게 올라갑니다.",
      ],
      actions: [
        "GPR 재탐사로 공동 위치와 규모를 확정하고, 이상 신호가 큰 구간부터 보수합니다.",
        "노후 관로와 지하시설물 누수 여부를 점검해 시설물 노후도 점수를 낮춥니다.",
        "강우 직후 배수 상태와 지하수위 변동을 재측정해 급격한 지반 약화 가능성을 줄입니다.",
        "공사장 인접 구간은 굴착 깊이, 흙막이 상태, 진동 기록을 관리해 공사 영향 점수를 낮춥니다.",
      ],
    };
  }

  if (kind === "monitoringPoints") {
    const count = state.monitoringPoints.length;
    const checked = state.monitoringPoints.filter((point) => point.last_checked_at).length;
    const errorCount = state.monitoringPoints.filter((point) => point.last_error).length;
    return {
      kind,
      title: "모니터링 지점 상세",
      subtitle: `${formatNumber(count)}개 지점을 등록했습니다. 최대 10개까지 직접 지정할 수 있고, 해제 전까지 접속 시 자동 갱신됩니다.`,
      points: metricDetailPoints(kind),
      rows: state.monitoringPoints.map((point) => {
        const score = Number(point.risk_score || 0);
        const meta = monitoringPointRisk(point);
        return {
          title: point.name || point.address || `모니터링 지점 ${point.id}`,
          meta: `${point.address || "-"} / ${point.last_checked_at ? `갱신 ${point.last_checked_at}` : "갱신 대기"}`,
          value: point.last_error ? "오류" : `${formatNumber(score, 1)} ${meta.label}`,
          id: point.id,
        };
      }),
      summaryTitle: "AI 모니터링 판단",
      summary: [
        count
          ? `${formatNumber(count)}개 지점 중 ${formatNumber(checked)}개가 최근 위험도 계산을 완료했습니다.${errorCount ? ` ${formatNumber(errorCount)}개 지점은 갱신 오류가 있습니다.` : ""}`
          : "등록된 모니터링 지점이 없습니다. 주소를 입력해 지점을 추가하면 이후 접속 시 자동 갱신됩니다.",
        "현재 모니터링은 사용자가 지정한 위치를 기준으로 근접 공공데이터 분석 지점과 최신 강우를 결합해 위험도를 갱신합니다.",
      ],
      actions: [
        "위험도가 높은 지점은 현장 점검 또는 GPR 탐사 대상으로 지정합니다.",
        "주소가 부정확한 지점은 해제 후 도로명 주소로 다시 등록합니다.",
        "사용하지 않는 지점은 해제해 자동 갱신 대상에서 제외합니다.",
      ],
    };
  }

  const recentRows = recentDetectionRows();
  const hasSourceDetections = RECENT_DETECTIONS.length > 0;

  return {
    title: "최근 탐지 건수 상세",
    subtitle: recentRows.length
      ? `최근 24시간 기준 ${recentRows.length}건의 탐지 또는 모니터링 갱신 이벤트가 있습니다.`
      : "현재 원본 데이터 또는 모니터링 지점에 등록된 최근 이벤트가 없습니다.",
    points: metricDetailPoints(kind),
    rows: recentRows.map((row) => ({
      title: row.title,
      meta: `${row.time} / ${row.type} / ${row.status}`,
      value: formatNumber(row.score, 0),
    })),
    summaryTitle: "AI 탐지 이벤트 판단",
    summary: recentRows.length
      ? [
          hasSourceDetections
            ? "최근 탐지 건수는 단기 위험 변화와 현장 대응 필요성을 보여주는 운영 지표입니다."
            : "원본 탐지 이벤트가 없을 때는 최근 갱신된 모니터링 지점을 운영 이벤트로 집계합니다.",
          "위험도 계산이 최근 24시간 안에 완료된 지점은 대시보드 접속 때마다 자동 갱신 대상으로 관리됩니다.",
        ]
      : [
          "실제 탐지 이벤트 원본 데이터와 최근 갱신된 모니터링 지점이 모두 없어 0건으로 표시합니다.",
          "임의 이벤트를 생성하지 않고, 출처가 확인된 탐지 또는 사용자가 등록한 모니터링 갱신만 반영합니다.",
        ],
    actions: recentRows.length
      ? [
          "위험도가 높은 모니터링 지점은 현장 확인 또는 GPR 탐사 대상으로 지정합니다.",
          "동일 주소에서 반복 갱신 또는 점수 상승이 발생하면 원인 분석 카드와 연결해 점수를 재산정합니다.",
          "오탐으로 확인된 이벤트는 모델 학습 데이터에 반영해 불필요한 경보를 줄입니다.",
        ]
      : [
          "탐지 센서, 현장 신고, 점검 이벤트 원본 API를 연동합니다.",
          "모니터링 지점을 등록하면 접속 시 자동 갱신되어 최근 24시간 건수에 반영됩니다.",
          "출처와 수집 시각이 확인된 이벤트만 최근 탐지 목록에 표시합니다.",
        ],
  };
}

function openMetricDialog() {
  const dialog = el.metricDetailDialog;
  if (!dialog || dialog.open) return;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeMetricDialog() {
  const dialog = el.metricDetailDialog;
  if (!dialog) return;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

async function openMetricDetail(kind) {
  if (kind === "monitoringPoints") {
    try {
      await loadMonitoringPoints({ refresh: true });
    } catch (error) {
      setStatus(error.message);
    }
  }
  const initialDetail = buildMetricDetail(kind);
  renderMetricDetail(initialDetail);
  openMetricDialog();

  if (kind !== "highRiskRegions") return;
  const target = highRiskRegionRows()[0] || {};
  const regionId = Number(target.region_id || state.selectedRegionId);
  if (!regionId) return;
  try {
    const payload = await api("/api/analyze-risk", {
      method: "POST",
      timeoutMs: 10000,
      body: JSON.stringify({
        region_id: regionId,
        analysis_date: el.analysisDate?.value || getClientClock().date,
      }),
    });
    renderMetricDetail(buildMetricDetail(kind, payload));
  } catch (error) {
    renderMetricDetail({
      ...initialDetail,
      summary: [...initialDetail.summary, `상세 분석 API 응답을 가져오지 못했습니다: ${error.message}`],
    });
  }
}

function svgNode(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function renderMap() {
  if (!el.demoMap) return;
  el.googleMap?.classList.add("hidden");
  el.demoMap.classList.remove("hidden");
  el.mapOverlay.innerHTML = "";

  const livePoint = state.mode === "live" && state.liveLocation.latitude != null
    ? [{ latitude: state.liveLocation.latitude, longitude: state.liveLocation.longitude }]
    : [];
  const points = state.regions.length ? state.regions : livePoint;
  state.mapBounds = computeMapBounds(points.length ? [...points, ...livePoint] : []);

  el.demoMap.innerHTML = `
    <defs>
      <radialGradient id="heat-red"><stop offset="0%" stop-color="#ff5d5d" stop-opacity=".72"/><stop offset="100%" stop-color="#ff5d5d" stop-opacity="0"/></radialGradient>
      <radialGradient id="heat-amber"><stop offset="0%" stop-color="#f6b93b" stop-opacity=".58"/><stop offset="100%" stop-color="#f6b93b" stop-opacity="0"/></radialGradient>
      <radialGradient id="heat-blue"><stop offset="0%" stop-color="#3b82f6" stop-opacity=".5"/><stop offset="100%" stop-color="#3b82f6" stop-opacity="0"/></radialGradient>
    </defs>
    <rect x="0" y="0" width="760" height="520" fill="#071422"></rect>
    <path class="map-land" d="M158 88 C230 38 333 38 430 73 C534 110 613 188 630 283 C646 374 583 442 485 466 C385 491 266 474 188 410 C109 346 82 249 104 171 C114 134 130 111 158 88 Z"></path>
    <path class="map-road" d="M154 385 C245 302 354 274 596 231"></path>
    <path class="map-road" d="M210 122 C264 209 348 287 506 423"></path>
    <path class="map-road" d="M129 249 C258 222 409 215 621 286"></path>
    <text class="map-label" x="124" y="420">서부권</text>
    <text class="map-label" x="594" y="202">동부권</text>
    <text class="map-label" x="356" y="486">남부권</text>
  `;

  const topRows = state.topRisk.slice(0, 5);
  const heatGroup = svgNode("g");
  const pinsGroup = svgNode("g");
  el.demoMap.append(heatGroup, pinsGroup);

  state.regions.forEach((region, index) => {
    const lat = Number(region.latitude);
    const lng = Number(region.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const pos = projectToMap(lat, lng);
    const risk = scoreForRegion(region);
    const meta = riskMeta(risk.level, risk.score);
    const isSelected = Number(region.region_id) === Number(state.selectedRegionId);
    const isTop = topRows.some((row) => Number(row.region_id) === Number(region.region_id));

    if (isSelected || isTop || meta.key === "very-high" || meta.key === "high") {
      const heat = svgNode("circle", {
        cx: pos.x,
        cy: pos.y,
        r: isSelected ? 76 : meta.key === "very-high" ? 68 : 54,
        fill: meta.key === "very-high" || meta.key === "high" ? "url(#heat-red)" : "url(#heat-amber)",
      });
      heatGroup.appendChild(heat);
    }

    const pin = svgNode("g", { class: `map-pin ${isSelected ? "selected" : ""}` });
    const radius = isSelected ? 9 : isTop ? 7 : 5;
    const circle = svgNode("circle", {
      cx: pos.x,
      cy: pos.y,
      r: radius,
      fill: meta.color,
    });
    const title = svgNode("title");
    title.textContent = `${region.region_name} | ${meta.label} ${formatNumber(risk.score, 1)}`;
    pin.append(title, circle);
    if (isSelected || isTop || index < 8) {
      const label = svgNode("text", { x: pos.x, y: pos.y - radius - 9 });
      label.textContent = String(region.region_name || "").replace(/\s+/g, " ").slice(0, 10);
      pin.appendChild(label);
    }
    pin.addEventListener("click", async () => {
      state.mode = "scenario";
      state.selectedRegionId = Number(region.region_id);
      state.selectedRegionName = region.region_name;
      if (el.regionSelect) el.regionSelect.value = String(region.region_id);
      setMode("scenario", { silent: true });
      await runScenarioAnalysis();
    });
    pinsGroup.appendChild(pin);
  });

  if (state.mode === "live" && state.liveLocation.latitude != null && state.liveLocation.longitude != null) {
    const pos = projectToMap(state.liveLocation.latitude, state.liveLocation.longitude);
    heatGroup.appendChild(svgNode("circle", { cx: pos.x, cy: pos.y, r: 78, fill: "url(#heat-blue)" }));
    const pin = svgNode("g", { class: "map-pin selected" });
    pin.appendChild(svgNode("circle", { cx: pos.x, cy: pos.y, r: 10, fill: "#3b82f6" }));
    const label = svgNode("text", { x: pos.x, y: pos.y - 20 });
    label.textContent = locationRoadAddress(state.liveLocation) || "실시간 위치";
    pin.appendChild(label);
    pinsGroup.appendChild(pin);
  }

  el.mapLegend.innerHTML = `
    <span><i class="legend-dot very-high"></i>매우 높음</span>
    <span><i class="legend-dot high"></i>높음</span>
    <span><i class="legend-dot mid"></i>중간</span>
    <span><i class="legend-dot low"></i>낮음</span>
    <span><i class="legend-dot selected"></i>선택</span>
  `;

  if (!state.simulationRows.length) {
    setText(el.mapNotes, state.mode === "live" ? "실시간 위치 분석 결과를 지도에 표시합니다." : "지도 위 점을 선택하면 해당 지역 분석을 실행합니다.");
  }
}

function selectedMapTarget() {
  if (state.mode === "live" && state.liveLocation.latitude != null && state.liveLocation.longitude != null) {
    const address = locationRoadAddress(state.liveLocation);
    return {
      name: address || "선택 위치",
      address,
      latitude: Number(state.liveLocation.latitude),
      longitude: Number(state.liveLocation.longitude),
      zoom: 15,
    };
  }

  if (state.currentPayload?.location) {
    const location = state.currentPayload.location;
    const address = locationRoadAddress(location);
    return {
      name: address || "실시간 분석 위치",
      address,
      latitude: Number(location.latitude),
      longitude: Number(location.longitude),
      zoom: 15,
    };
  }

  if (state.currentPayload?.road) {
    const road = state.currentPayload.road;
    return {
      name: road.road_name || "선택 도로",
      address: roadRoadAddress(road),
      latitude: Number(road.center_lat),
      longitude: Number(road.center_lon),
      zoom: 16,
    };
  }

  if (state.currentPayload?.region) {
    const region = state.currentPayload.region;
    return {
      name: region.region_name || "선택 지역",
      address: regionRoadAddress(region),
      latitude: Number(region.latitude),
      longitude: Number(region.longitude),
      zoom: 15,
    };
  }

  const selected = state.regions.find((region) => Number(region.region_id) === Number(state.selectedRegionId)) || state.regions[0];
  if (selected) {
    return {
      name: selected.region_name || "선택 지역",
      address: regionRoadAddress(selected),
      latitude: Number(selected.latitude),
      longitude: Number(selected.longitude),
      zoom: 14,
    };
  }

  return {
    name: "Seoul Metropolitan Risk Center",
    address: "서울특별시 강남구 테헤란로 152 인근",
    latitude: 37.5239,
    longitude: 127.0264,
    zoom: 12,
  };
}

function renderGoogleMapFrame(target, force = false) {
  if (!el.googleMap) return;
  const latitude = Number(target.latitude);
  const longitude = Number(target.longitude);
  const hasCoords = Number.isFinite(latitude) && Number.isFinite(longitude);
  const requestedZoom = Number(target.zoom);
  const zoomLevel = Number.isFinite(requestedZoom) ? requestedZoom : 14;
  const query = encodeURIComponent(hasCoords ? `${latitude},${longitude}` : target.name || "Seoul");
  const center = hasCoords ? `&ll=${encodeURIComponent(`${latitude},${longitude}`)}` : "";
  const zoom = encodeURIComponent(String(zoomLevel));
  const src = `https://maps.google.com/maps?q=${query}${center}&z=${zoom}&output=embed`;
  const openUrl = `https://www.google.com/maps/search/?api=1&query=${query}`;

  if (hasCoords) {
    state.mapView = { latitude, longitude, zoom: zoomLevel };
  }

  if (force || el.googleMap.dataset.src !== src) {
    el.googleMap.dataset.src = src;
    el.googleMap.classList.remove("is-loaded", "use-fallback");
    const addressText = targetRoadAddress(target);
    const displayName = escapeHtml(addressText || target.name || "선택 위치");
    el.googleMap.innerHTML = `
      <div class="google-map-fallback">
        <div class="fallback-grid"></div>
        <div class="fallback-target">
          <span></span>
          <strong>${displayName}</strong>
          <small>${escapeHtml(addressText)}</small>
        </div>
        <a class="map-open-link" href="${openUrl}" target="_blank" rel="noreferrer">Google 지도 새 창</a>
      </div>
      <iframe
        title="Google Maps - ${escapeHtml(addressText || target.name || "Sinkhole map")}"
        loading="lazy"
        allowfullscreen
        referrerpolicy="no-referrer-when-downgrade"
        src="${src}">
      </iframe>
    `;
    const iframe = el.googleMap.querySelector("iframe");
    const loadToken = String(Date.now());
    el.googleMap.dataset.loadToken = loadToken;
    iframe?.addEventListener("load", () => {
      if (el.googleMap?.dataset.loadToken === loadToken) {
        el.googleMap.classList.add("is-loaded");
        el.googleMap.classList.remove("use-fallback");
      }
    }, { once: true });
    window.setTimeout(() => {
      if (el.googleMap?.dataset.loadToken === loadToken && !el.googleMap.classList.contains("is-loaded")) {
        el.googleMap.classList.add("use-fallback");
      }
    }, 3500);
  }
}

function renderMap(options = {}) {
  if (!el.googleMap) return;
  const target = selectedMapTarget();
  state.mapBounds = computeMapBounds([
    ...state.regions,
    { latitude: target.latitude, longitude: target.longitude },
  ]);

  el.demoMap?.classList.add("hidden");
  el.googleMap.classList.remove("hidden");
  if (el.mapOverlay) el.mapOverlay.innerHTML = "";
  renderGoogleMapFrame(target, Boolean(options.forceMapFrame));

  el.mapLegend.innerHTML = `
    <span><i class="legend-dot very-high"></i>매우 높음</span>
    <span><i class="legend-dot high"></i>높음</span>
    <span><i class="legend-dot mid"></i>중간</span>
    <span><i class="legend-dot low"></i>낮음</span>
    <span><i class="legend-dot selected"></i>선택 위치</span>
  `;

  if (!state.simulationRows.length) {
    setText(el.mapNotes, `${targetRoadAddress(target)} 중심의 Google 지도를 표시합니다.`);
  }
}

async function refreshSummaryPanels() {
  const topPath = state.mode === "scenario" && state.analysisType === "road" ? "/api/top-risk-roads" : "/api/top-risk-regions";
  const [summary, topRisk, distribution] = await Promise.allSettled([
    api("/api/summary"),
    api(topPath),
    api("/api/charts/risk-distribution"),
  ]);
  if (summary.status === "fulfilled") renderMetrics(summary.value);
  if (topRisk.status === "fulfilled") renderTopRisk(topRisk.value);
  else renderTopRisk([]);
  if (distribution.status === "fulfilled") renderDistribution(distribution.value);
  else renderDistribution([]);
  renderMap();
}

function startDashboardAutoRefresh() {
  if (dashboardRefreshTimer) return;
  dashboardRefreshTimer = window.setInterval(async () => {
    if (document.hidden) return;
    try {
      await loadMonitoringPoints({ refresh: true });
      await refreshSummaryPanels();
    } catch (error) {
      console.warn("dashboard auto refresh failed", error);
    }
  }, 60000);
}

async function runScenarioAnalysis(clock = getClientClock(), options = {}) {
  if (!state.selectedRegionId) return;
  const manageBusy = options.manageBusy !== false;
  if (manageBusy) setBusy(true);
  setStatus("지역 위험도를 분석하는 중입니다.");
  try {
    const payload = await api("/api/analyze-risk", {
      method: "POST",
      body: JSON.stringify({
        region_id: Number(state.selectedRegionId),
        analysis_date: el.analysisDate?.value || clock.date,
        client_local_datetime: clock.localDateTime,
        client_timezone: clock.timezone,
        client_utc_offset_minutes: clock.utcOffsetMinutes,
      }),
    });
    state.selectedRegionName = payload.region?.region_name || state.selectedRegionName;
    renderResult(`${payload.region.region_name} (${payload.region.sido || ""} ${payload.region.sigungu || ""})`.trim(), payload);
    await Promise.allSettled([refreshRegionalCharts(), refreshSummaryPanels()]);
    setStatus(`${t().analyzed} (${clock.label})`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    if (manageBusy) setBusy(false);
  }
}

async function runRoadAnalysis(clock = getClientClock(), options = {}) {
  if (!state.selectedRoadId) {
    setStatus("도로를 선택해 주세요.");
    return;
  }
  const manageBusy = options.manageBusy !== false;
  if (manageBusy) setBusy(true);
  setStatus("도로 위험도를 분석하는 중입니다.");
  try {
    const payload = await api("/api/analyze-road-risk", {
      method: "POST",
      body: JSON.stringify({
        road_id: Number(state.selectedRoadId),
        analysis_date: el.analysisDate?.value || clock.date,
        client_local_datetime: clock.localDateTime,
        client_timezone: clock.timezone,
        client_utc_offset_minutes: clock.utcOffsetMinutes,
      }),
    });
    renderResult(`도로: ${payload.road.road_name}`, payload);
    renderTrendChart([]);
    renderCauseDistribution([]);
    await refreshSummaryPanels();
    setStatus(`${t().analyzed} (${clock.label})`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    if (manageBusy) setBusy(false);
  }
}

async function runLiveAnalysis(clock = getClientClock()) {
  const inputName = (state.liveLocation.name || el.liveLocationInput?.value || "").trim();
  const name = looksLikeCoordinates(inputName)
    ? locationRoadAddress(state.liveLocation)
    : inputName;
  if (!name) throw new Error(t().liveMissing);
  setStatus("실시간 위치 위험도를 분석하는 중입니다.");
  const payload = await api("/api/commercial/analyze", {
    method: "POST",
    body: JSON.stringify({
      location_name: name,
      latitude: state.liveLocation.latitude,
      longitude: state.liveLocation.longitude,
      client_local_datetime: clock.localDateTime,
      client_timezone: clock.timezone,
      client_utc_offset_minutes: clock.utcOffsetMinutes,
    }),
  });
  const address = locationRoadAddress({
    ...payload.location,
    address: payload.location?.address || state.liveLocation.address,
    road_address: payload.location?.road_address || state.liveLocation.address,
  });
  const displayPayload = {
    ...payload,
    location: {
      ...payload.location,
      location_name: address,
      address,
      road_address: address,
    },
  };
  state.liveLocation = {
    name: address,
    address,
    latitude: Number(payload.location.latitude),
    longitude: Number(payload.location.longitude),
  };
  if (el.liveLocationInput) el.liveLocationInput.value = address;
  renderResult(address, displayPayload);
  renderTrendChart([]);
  renderCauseDistribution([]);
}

async function runAnalysis() {
  const clock = updateClock();
  setBusy(true);
  try {
    if (state.mode === "live") await runLiveAnalysis(clock);
    else if (state.analysisType === "road") await runRoadAnalysis(clock, { manageBusy: false });
    else await runScenarioAnalysis(clock, { manageBusy: false });
    await refreshSummaryPanels();
    setStatus(`${t().analyzed} (${clock.label})`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function generateReport() {
  const clock = updateClock();
  setBusy(true);
  setStatus("AI 리포트를 생성하는 중입니다.");
  try {
    let payload;
    if (state.mode === "live") {
      const inputName = (state.liveLocation.name || el.liveLocationInput?.value || "").trim();
      const name = looksLikeCoordinates(inputName)
        ? locationRoadAddress(state.liveLocation)
        : inputName;
      if (!name) throw new Error(t().liveMissing);
      payload = await api("/api/commercial/report", {
        method: "POST",
        body: JSON.stringify({
          location_name: name,
          latitude: state.liveLocation.latitude,
          longitude: state.liveLocation.longitude,
          language: lang(),
          client_local_datetime: clock.localDateTime,
          client_timezone: clock.timezone,
          client_utc_offset_minutes: clock.utcOffsetMinutes,
        }),
      });
    } else if (state.analysisType === "road") {
      setStatus("도로 단위 PDF 리포트는 현재 지역 단위에서 생성할 수 있습니다.");
      return;
    } else {
      payload = await api("/api/generate-report", {
        method: "POST",
        body: JSON.stringify({
          region_id: Number(state.selectedRegionId),
          analysis_date: el.analysisDate?.value || clock.date,
          language: lang(),
          client_local_datetime: clock.localDateTime,
          client_timezone: clock.timezone,
          client_utc_offset_minutes: clock.utcOffsetMinutes,
        }),
      });
    }
    setText(el.reportText, payload.report || "-");
    await refreshReportList();
    setStatus(`${t().reportDone}${payload.pdf?.file_name ? ` (${payload.pdf.file_name})` : ""}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

async function refreshReportList() {
  try {
    const rows = await api("/api/reports");
    state.reports = Array.isArray(rows) ? rows : [];
    renderReportList();
  } catch (error) {
    if (el.reportList) el.reportList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderReportSelection() {
  setText(el.selectedReportsInfo, t().selectedPdf(state.selectedReports.size));
  if (el.selectAllReports) {
    el.selectAllReports.checked = Boolean(state.reports.length && state.selectedReports.size === state.reports.length);
  }
}

function renderReportList() {
  if (!el.reportList) return;
  el.reportList.innerHTML = "";
  if (!state.reports.length) {
    el.reportList.innerHTML = `<div class="empty-state">${escapeHtml(t().noData)}</div>`;
    renderReportSelection();
    return;
  }
  state.reports.forEach((row) => {
    const item = document.createElement("label");
    item.className = "report-row";
    const checked = state.selectedReports.has(row.file_name);
    item.innerHTML = `
      <input type="checkbox" ${checked ? "checked" : ""}>
      <span>
        <strong>${escapeHtml(row.file_name)}</strong>
        <span>${escapeHtml(row.created_at || "-")} · ${formatBytes(row.size)}</span>
      </span>
      <a class="secondary small" href="${escapeHtml(apiUrl(row.url))}" target="_blank" rel="noreferrer">열기</a>
    `;
    item.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedReports.add(row.file_name);
      else state.selectedReports.delete(row.file_name);
      renderReportSelection();
    });
    el.reportList.appendChild(item);
  });
  renderReportSelection();
}

function selectedReportRows() {
  return state.reports.filter((row) => state.selectedReports.has(row.file_name));
}

function openSelectedReports() {
  selectedReportRows().forEach((row) => window.open(apiUrl(row.url), "_blank", "noreferrer"));
}

function downloadSelectedReports() {
  selectedReportRows().forEach((row) => {
    const link = document.createElement("a");
    link.href = apiUrl(row.url);
    link.download = row.file_name;
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
}

async function deleteSelectedReports() {
  const rows = selectedReportRows();
  if (!rows.length) return;
  if (!window.confirm(`${rows.length}개 PDF를 삭제할까요?`)) return;
  try {
    await api("/api/reports/delete", {
      method: "POST",
      body: JSON.stringify({ file_names: rows.map((row) => row.file_name) }),
    });
    state.selectedReports = new Set();
    await refreshReportList();
    setStatus("선택한 PDF를 삭제했습니다.");
  } catch (error) {
    setStatus(error.message);
  }
}

function updateWhatIfControls() {
  const rainfall = Number(el.whatIfRainfall?.value || 0);
  const construction = Boolean(el.whatIfConstruction?.checked);
  setText(el.whatIfRainfallValue, `${rainfall}mm`);
  setText(el.whatIfSummary, `추가 강우 ${rainfall}mm / ${construction ? "대규모 공사 반영" : "대규모 공사 없음"}`);
}

function renderWhatIfResults(rows = []) {
  if (!el.whatIfResults) return;
  el.whatIfResults.innerHTML = "";
  if (!rows.length) {
    el.whatIfResults.innerHTML = `<div class="empty-state">시뮬레이션 실행 후 결과가 표시됩니다.</div>`;
    return;
  }

  rows.slice(0, 6).forEach((row) => {
    const original = Number(row.original_score || 0);
    const simulated = Number(row.simulated_score || 0);
    const diff = Number(row.score_diff || 0);
    const drivers = Array.isArray(row.drivers) ? row.drivers.slice(0, 4) : [];
    const actions = Array.isArray(row.recommendations) ? row.recommendations.slice(0, 3) : [];
    const card = document.createElement("article");
    card.className = `whatif-result-card ${diff >= 8 ? "elevated" : ""}`;
    card.innerHTML = `
      <div class="whatif-result-head">
        <strong>${escapeHtml(row.region_name || "-")}</strong>
        <span>${formatNumber(simulated, 1)}</span>
      </div>
      <div class="scenario-score-compare">
        <div>
          <small>현재</small>
          <b>${formatNumber(original, 1)}</b>
          <i style="width:${Math.max(2, Math.min(100, original))}%"></i>
        </div>
        <div>
          <small>시나리오</small>
          <b>${formatNumber(simulated, 1)} (${diff >= 0 ? "+" : ""}${formatNumber(diff, 1)})</b>
          <i class="scenario-bar" style="width:${Math.max(2, Math.min(100, simulated))}%"></i>
        </div>
      </div>
      <div class="whatif-result-meta">
        <span>${escapeHtml(row.original_level || "-")} → ${escapeHtml(row.new_risk_level || "-")}</span>
        <span>조치 ${escapeHtml(row.action_level || "-")}</span>
        <span>신뢰도 ${escapeHtml(row.confidence?.label || "-")}</span>
      </div>
      <div class="whatif-drivers">
        ${drivers.length ? drivers.map((driver) => `<span>${escapeHtml(driver.label)} +${formatNumber(driver.delta, 1)}</span>`).join("") : "<span>추가 상승 요인 없음</span>"}
      </div>
      <div class="whatif-actions">
        ${actions.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
    `;
    el.whatIfResults.appendChild(card);
  });
}

async function runWhatIfSimulation() {
  if (state.mode !== "scenario") setMode("scenario", { silent: true });
  updateWhatIfControls();
  setBusy(true);
  setStatus("What-If 시뮬레이션을 실행하는 중입니다.");
  try {
    const rows = await api("/api/simulate-risk", {
      method: "POST",
      body: JSON.stringify({
        extra_rainfall_mm: Number(el.whatIfRainfall?.value || 0),
        is_major_construction: Boolean(el.whatIfConstruction?.checked),
      }),
    });
    state.simulationRows = Array.isArray(rows) ? rows : [];
    renderMap();
    const top = [...state.simulationRows]
      .sort((a, b) => Number(b.score_diff || 0) - Number(a.score_diff || 0))
      .slice(0, 4);
    if (top.length) {
      el.mapNotes.innerHTML = `
        <strong>What-If 결과</strong>
        <div class="map-note-list">
          ${top.map((row) => `<span class="map-note-chip">${escapeHtml(row.region_name)} ${formatNumber(row.simulated_score, 1)} (${Number(row.score_diff || 0) >= 0 ? "+" : ""}${formatNumber(row.score_diff, 1)})</span>`).join("")}
        </div>
      `;
    }
    setStatus(`What-If 시뮬레이션 완료: ${state.simulationRows.length}개 지역 갱신`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function openWhatIfPanel() {
  if (state.mode !== "scenario") setMode("scenario", { silent: true });
  mountWhatIfPanel();
  updateWhatIfControls();
  el.whatIfDrawer?.classList.remove("hidden");
  el.whatIfDrawer?.scrollIntoView({ behavior: "smooth", block: "start" });
}

const WHAT_IF_PRESETS = {
  custom: {},
  heavy_rain: { horizon: 24, rainfall: 120, groundwater: 0.4, construction: false, depth: 0, distance: 500, gpr: 0, facility: 0 },
  typhoon: { horizon: 72, rainfall: 220, groundwater: 0.8, construction: false, depth: 0, distance: 500, gpr: 0, facility: 0 },
  excavation: { horizon: 168, rainfall: 20, groundwater: 0.1, construction: true, depth: 12, distance: 80, gpr: 1, facility: 0 },
  groundwater: { horizon: 72, rainfall: 40, groundwater: 1.5, construction: false, depth: 0, distance: 500, gpr: 0, facility: 0 },
  pipe_damage: { horizon: 24, rainfall: 30, groundwater: 0.7, construction: false, depth: 0, distance: 500, gpr: 2, facility: 20 },
  old_building: { horizon: 72, rainfall: 20, groundwater: 0.2, construction: false, depth: 0, distance: 500, gpr: 0, facility: 30, past: 0, environment: 2 },
  compound: { horizon: 72, rainfall: 120, groundwater: 0.8, construction: true, depth: 10, distance: 120, gpr: 2, facility: 20, past: 1, environment: 2.5 },
};

function applyWhatIfPreset() {
  const preset = WHAT_IF_PRESETS[el.whatIfPreset?.value || "custom"];
  if (!preset || !Object.keys(preset).length) {
    updateWhatIfControls();
    return;
  }
  if (el.whatIfHorizon) el.whatIfHorizon.value = String(preset.horizon);
  if (el.whatIfRainfall) el.whatIfRainfall.value = String(preset.rainfall);
  if (el.whatIfGroundwater) el.whatIfGroundwater.value = String(preset.groundwater);
  if (el.whatIfConstruction) el.whatIfConstruction.checked = Boolean(preset.construction);
  if (el.whatIfDepth) el.whatIfDepth.value = String(preset.depth);
  if (el.whatIfDistance) el.whatIfDistance.value = String(preset.distance);
  if (el.whatIfGpr) el.whatIfGpr.value = String(preset.gpr);
  if (el.whatIfFacility) el.whatIfFacility.value = String(preset.facility);
  if (el.whatIfPastSinkhole) el.whatIfPastSinkhole.value = String(preset.past || 0);
  if (el.whatIfEnvironment) el.whatIfEnvironment.value = String(preset.environment || 0);
  updateWhatIfControls();
}

function updateWhatIfControls() {
  const rainfall = Number(el.whatIfRainfall?.value || 0);
  const groundwater = Number(el.whatIfGroundwater?.value || 0);
  const depth = Number(el.whatIfDepth?.value || 0);
  const distance = Number(el.whatIfDistance?.value || 0);
  const gpr = Number(el.whatIfGpr?.value || 0);
  const facility = Number(el.whatIfFacility?.value || 0);
  const horizon = Number(el.whatIfHorizon?.value || 24);
  const construction = Boolean(el.whatIfConstruction?.checked);
  setText(el.whatIfRainfallValue, `${rainfall}mm`);
  setText(el.whatIfGroundwaterValue, `${groundwater.toFixed(1)}m`);
  setText(el.whatIfDepthValue, `${depth}m`);
  setText(el.whatIfDistanceValue, `${distance}m`);
  setText(el.whatIfGprValue, `${gpr}개`);
  setText(el.whatIfFacilityValue, `${facility}점`);
  setText(
    el.whatIfSummary,
    `${horizon}시간 예측 / 강우 ${rainfall}mm / 지하수 ${groundwater.toFixed(1)}m / ${construction ? "대규모 공사 반영" : "대규모 공사 없음"}`,
  );
}

function updateWhatIfControls() {
  const rainfall = Number(el.whatIfRainfall?.value || 0);
  const groundwater = Number(el.whatIfGroundwater?.value || 0);
  const depth = Number(el.whatIfDepth?.value || 0);
  const distance = Number(el.whatIfDistance?.value || 0);
  const gpr = Number(el.whatIfGpr?.value || 0);
  const facility = Number(el.whatIfFacility?.value || 0);
  const past = Number(el.whatIfPastSinkhole?.value || 0);
  const environment = Number(el.whatIfEnvironment?.value || 0);
  const horizon = Number(el.whatIfHorizon?.value || 24);
  const construction = Boolean(el.whatIfConstruction?.checked);
  const targetOnly = Boolean(el.whatIfTargetOnly?.checked);
  const mitigationCount = [
    el.whatIfMitigationGpr,
    el.whatIfMitigationPipe,
    el.whatIfMitigationDrainage,
    el.whatIfMitigationConstruction,
    el.whatIfMitigationMonitoring,
  ].filter((item) => Boolean(item?.checked)).length;
  setText(el.whatIfRainfallValue, `${rainfall}mm`);
  setText(el.whatIfGroundwaterValue, `${groundwater.toFixed(1)}m`);
  setText(el.whatIfDepthValue, `${depth}m`);
  setText(el.whatIfDistanceValue, `${distance}m`);
  setText(el.whatIfGprValue, `${gpr}개`);
  setText(el.whatIfFacilityValue, `${facility}점`);
  setText(el.whatIfPastSinkholeValue, `${past}건`);
  setText(el.whatIfEnvironmentValue, `${environment.toFixed(1)}점`);
  setText(
    el.whatIfSummary,
    `${horizon}시간 예측 / 강우 ${rainfall}mm / 지하수 ${groundwater.toFixed(1)}m / GPR ${gpr}개 / ${construction ? "공사 반영" : "공사 없음"} / ${targetOnly ? "선택 지역만" : "전체 지역"}`,
  );
}

function renderWhatIfResults(rows = []) {
  if (!el.whatIfResults) return;
  el.whatIfResults.innerHTML = "";
  if (!rows.length) {
    el.whatIfResults.innerHTML = `<div class="empty-state">시뮬레이션 결과가 없습니다.</div>`;
    return;
  }
  rows.slice(0, 5).forEach((row) => {
    const diff = Number(row.score_diff || 0);
    const drivers = Array.isArray(row.drivers) ? row.drivers.slice(0, 3) : [];
    const actions = Array.isArray(row.recommendations) ? row.recommendations.slice(0, 2) : [];
    const card = document.createElement("article");
    card.className = "whatif-result-card";
    card.innerHTML = `
      <div class="whatif-result-head">
        <strong>${escapeHtml(row.region_name || "-")}</strong>
        <span>${formatNumber(row.simulated_score, 1)}</span>
      </div>
      <div class="whatif-result-meta">
        <span>${escapeHtml(row.original_level || "-")} -> ${escapeHtml(row.new_risk_level || "-")}</span>
        <span>${diff >= 0 ? "+" : ""}${formatNumber(diff, 1)}점</span>
        <span>신뢰도 ${escapeHtml(row.confidence?.label || "-")}</span>
        <span>조치 ${escapeHtml(row.action_level || "-")}</span>
      </div>
      <div class="whatif-drivers">
        ${drivers.map((driver) => `<span>${escapeHtml(driver.label)} +${formatNumber(driver.delta, 1)}</span>`).join("")}
      </div>
      <div class="whatif-actions">
        ${actions.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
    `;
    el.whatIfResults.appendChild(card);
  });
}

async function runWhatIfSimulation() {
  if (state.mode !== "scenario") setMode("scenario", { silent: true });
  updateWhatIfControls();
  setBusy(true);
  setStatus("What-If 시뮬레이션을 실행하는 중입니다.");
  try {
    const payload = await api("/api/simulate-risk", {
      method: "POST",
      body: JSON.stringify({
        scenario_preset: el.whatIfPreset?.value || "custom",
        forecast_horizon_hours: Number(el.whatIfHorizon?.value || 24),
        extra_rainfall_mm: Number(el.whatIfRainfall?.value || 0),
        groundwater_delta_m: Number(el.whatIfGroundwater?.value || 0),
        is_major_construction: Boolean(el.whatIfConstruction?.checked),
        excavation_depth_m: Number(el.whatIfDepth?.value || 0),
        construction_distance_m: Number(el.whatIfDistance?.value || 500),
        gpr_anomaly_count: Number(el.whatIfGpr?.value || 0),
        facility_aging_delta: Number(el.whatIfFacility?.value || 0),
        past_sinkhole_delta_count: Number(el.whatIfPastSinkhole?.value || 0),
        environment_delta_score: Number(el.whatIfEnvironment?.value || 0),
        mitigation_gpr_survey: Boolean(el.whatIfMitigationGpr?.checked),
        mitigation_pipe_repair: Boolean(el.whatIfMitigationPipe?.checked),
        mitigation_drainage: Boolean(el.whatIfMitigationDrainage?.checked),
        mitigation_construction_control: Boolean(el.whatIfMitigationConstruction?.checked),
        mitigation_monitoring: Boolean(el.whatIfMitigationMonitoring?.checked),
        target_region_id: el.whatIfTargetOnly?.checked ? state.selectedRegionId : null,
      }),
    });
    const rows = Array.isArray(payload) ? payload : payload.results || [];
    state.simulationRows = Array.isArray(rows) ? rows : [];
    renderWhatIfResults(state.simulationRows);
    renderMap();
    const top = [...state.simulationRows]
      .sort((a, b) => Number(b.score_diff || 0) - Number(a.score_diff || 0))
      .slice(0, 4);
    if (top.length) {
      el.mapNotes.innerHTML = `
        <strong>What-If 결과</strong>
        <div class="map-note-list">
          ${top.map((row) => `<span class="map-note-chip">${escapeHtml(row.region_name)} ${formatNumber(row.simulated_score, 1)} (${Number(row.score_diff || 0) >= 0 ? "+" : ""}${formatNumber(row.score_diff, 1)})</span>`).join("")}
        </div>
      `;
    }
    setStatus(`What-If 시뮬레이션 완료: ${state.simulationRows.length}개 지역 갱신`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function closeWhatIfPanel() {
  el.whatIfDrawer?.classList.add("hidden");
}

function openHelp() {
  const dialog = $("helpDialog");
  if (!dialog || dialog.open) return;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeHelp() {
  const dialog = $("helpDialog");
  if (!dialog) return;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function appendAiChatMessage(role, content, options = {}) {
  if (!el.aiChatMessages) return null;
  const article = document.createElement("article");
  article.className = `ai-chat-message ${role === "user" ? "user" : "assistant"}`;
  const label = role === "user" ? "나" : "AI 직원";
  article.innerHTML = `
    <span>${escapeHtml(label)}</span>
    <p>${escapeHtml(content).replace(/\n/g, "<br>")}</p>
  `;
  el.aiChatMessages.appendChild(article);
  el.aiChatMessages.scrollTop = el.aiChatMessages.scrollHeight;
  if (!options.skipHistory) {
    state.aiChatHistory.push({ role: role === "user" ? "user" : "assistant", content: String(content || "") });
    state.aiChatHistory = state.aiChatHistory.slice(-20);
  }
  return article;
}

function ensureAiChatWelcome() {
  if (state.aiChatWelcomed) return;
  appendAiChatMessage(
    "assistant",
    "안녕하세요. 현재 대시보드의 분석 데이터를 기준으로 싱크홀 위험 지역, 위험한 이유, 관리 방법, 점수 낮추는 방법을 설명드리겠습니다. 예를 들어 '현재 가장 위험한 지역이 어디야?'처럼 물어보시면 됩니다.",
    { skipHistory: true },
  );
  state.aiChatWelcomed = true;
}

function setAiChatBusy(isBusy) {
  if (el.aiChatInput) el.aiChatInput.disabled = Boolean(isBusy);
  if (el.aiChatSendButton) {
    el.aiChatSendButton.disabled = Boolean(isBusy);
    el.aiChatSendButton.textContent = isBusy ? "분석 중" : "전송";
  }
}

function openAiChat() {
  const dialog = el.aiChatDialog;
  if (!dialog) return;
  ensureAiChatWelcome();
  if (!dialog.open) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }
  window.setTimeout(() => el.aiChatInput?.focus(), 80);
}

function closeAiChat() {
  const dialog = el.aiChatDialog;
  if (!dialog) return;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

async function sendAiChatMessage(prompt) {
  const message = String(prompt ?? el.aiChatInput?.value ?? "").trim();
  if (!message) return;
  if (el.aiChatInput) el.aiChatInput.value = "";
  appendAiChatMessage("user", message);
  setAiChatBusy(true);
  const pending = appendAiChatMessage("assistant", "현재 분석 데이터를 확인하고 답변을 작성하는 중입니다.", { skipHistory: true });
  try {
    const data = await api("/api/ai-chat", {
      method: "POST",
      timeoutMs: 12000,
      body: JSON.stringify({
        message,
        history: state.aiChatHistory.slice(-12),
      }),
    });
    pending?.remove();
    appendAiChatMessage("assistant", data.answer || "답변을 생성하지 못했습니다.");
  } catch (error) {
    pending?.remove();
    appendAiChatMessage("assistant", `답변을 가져오지 못했습니다. 서버 상태를 확인해 주세요. (${error.message})`);
  } finally {
    setAiChatBusy(false);
    el.aiChatInput?.focus();
  }
}

function toggleQuickMenu() {
  const panel = $("quickMenuPanel");
  const button = $("quickMenuButton");
  if (!panel || !button) return;
  const open = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !open);
  button.setAttribute("aria-expanded", String(open));
}

function closeQuickMenu() {
  $("quickMenuPanel")?.classList.add("hidden");
  $("quickMenuButton")?.setAttribute("aria-expanded", "false");
}

async function applyLiveLocation() {
  const rawName = (el.liveLocationInput?.value || "").trim();
  if (!rawName) {
    setStatus(t().liveMissing);
    return;
  }

  const button = $("applyLocationButton");
  if (button) button.disabled = true;
  setStatus("입력한 도로명 주소의 지도 위치를 찾는 중입니다.");
  try {
    const coordinates = parseCoordinates(rawName);
    const resolved = coordinates
      ? {
          ...coordinates,
          address: await reverseGeocodeAddress(coordinates.latitude, coordinates.longitude),
          source: "coordinates",
        }
      : await geocodeLocationByAddress(rawName);
    const address = resolved.address || rawName;

    state.liveLocation = {
      name: address,
      address,
      road_address: address,
      formatted_address: address,
      location_name: address,
      latitude: Number(resolved.latitude),
      longitude: Number(resolved.longitude),
      source: resolved.source,
    };
    state.selectedRegionName = address;
    if (el.liveLocationInput) el.liveLocationInput.value = address;
    setText(el.heroHeadline, `${address} 위험 분석`);
    setText(el.selectedRegionText, address);
    setText(el.resultCoords, address);
    setMode("live", { silent: true });
    renderMap({ forceMapFrame: true });
    setStatus(`지도 위치를 적용했습니다: ${address}. 위험도 분석을 실행하면 이 위치 기준으로 계산합니다.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function clampValue(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeLongitude(longitude) {
  return ((((longitude + 180) % 360) + 360) % 360) - 180;
}

function latLngToWorldPoint(latitude, longitude) {
  const lat = clampValue(Number(latitude), -85.05112878, 85.05112878);
  const lng = normalizeLongitude(Number(longitude));
  const sinLat = Math.sin((lat * Math.PI) / 180);
  return {
    x: (lng + 180) / 360,
    y: 0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI),
  };
}

function worldPointToLatLng(x, y) {
  const wrappedX = ((x % 1) + 1) % 1;
  const n = Math.PI - 2 * Math.PI * y;
  return {
    latitude: clampValue((180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), -85.05112878, 85.05112878),
    longitude: normalizeLongitude(wrappedX * 360 - 180),
  };
}

function mapPointFromClick(event) {
  const rect = el.mapPickLayer.getBoundingClientRect();
  const centerTarget = state.mapView || selectedMapTarget();
  const centerLatitude = Number(centerTarget.latitude);
  const centerLongitude = Number(centerTarget.longitude);
  const zoom = clampValue(Number(centerTarget.zoom || 14), 1, 21);

  if (!Number.isFinite(centerLatitude) || !Number.isFinite(centerLongitude) || !rect.width || !rect.height) {
    return selectedMapTarget();
  }

  const clickX = clampValue(event.clientX - rect.left, 0, rect.width);
  const clickY = clampValue(event.clientY - rect.top, 0, rect.height);
  const center = latLngToWorldPoint(centerLatitude, centerLongitude);
  const pixelsPerWorld = 256 * Math.pow(2, zoom);
  const worldX = center.x + (clickX - rect.width / 2) / pixelsPerWorld;
  const worldY = center.y + (clickY - rect.height / 2) / pixelsPerWorld;

  return worldPointToLatLng(worldX, worldY);
}

function bindEvents() {
  document.addEventListener("click", handleDelegatedAction);
  $("dashboardLink")?.addEventListener("click", (event) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("apiDocsLink")?.addEventListener("click", (event) => {
    if (window.location.protocol !== "file:") return;
    event.currentTarget.href = "http://127.0.0.1:5000/docs";
  });
  document.querySelectorAll("[data-section]").forEach((button) => {
    button.addEventListener("click", () => {
      closeQuickMenu();
      $(button.dataset.section)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
  document.querySelectorAll("[data-metric-detail]").forEach((card) => {
    card.addEventListener("click", () => openMetricDetail(card.dataset.metricDetail));
    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openMetricDetail(card.dataset.metricDetail);
    });
  });
  $("scenarioModeMenuButton")?.addEventListener("click", () => {
    setMode("scenario");
    closeQuickMenu();
  });
  $("liveModeMenuButton")?.addEventListener("click", () => {
    setMode("live");
    closeQuickMenu();
  });
  $("refreshReportsButton")?.addEventListener("click", refreshReportList);
  $("openSelectedReportsButton")?.addEventListener("click", openSelectedReports);
  $("downloadSelectedReportsButton")?.addEventListener("click", downloadSelectedReports);
  $("deleteSelectedReportsButton")?.addEventListener("click", deleteSelectedReports);
  $("quickMenuButton")?.addEventListener("click", toggleQuickMenu);
  $("helpToggle")?.addEventListener("click", openHelp);
  $("helpToggleTop")?.addEventListener("click", openHelp);
  $("helpClose")?.addEventListener("click", closeHelp);
  $("openAiChatButton")?.addEventListener("click", openAiChat);
  el.aiChatClose?.addEventListener("click", closeAiChat);
  el.aiChatDialog?.addEventListener("click", (event) => {
    if (event.target === el.aiChatDialog) closeAiChat();
  });
  el.aiChatForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendAiChatMessage();
  });
  document.querySelectorAll("[data-chat-prompt]").forEach((button) => {
    button.addEventListener("click", () => sendAiChatMessage(button.dataset.chatPrompt));
  });
  el.metricDetailClose?.addEventListener("click", closeMetricDialog);
  el.metricDetailDialog?.addEventListener("click", (event) => {
    if (event.target === el.metricDetailDialog) closeMetricDialog();
  });
  $("helpDemoModeButton")?.addEventListener("click", () => setMode("scenario"));
  $("helpLiveModeButton")?.addEventListener("click", () => setMode("live"));
  $("applyLanguageButton")?.addEventListener("click", () => applyLanguage(el.languageSelect?.value || "ko"));
  $("openWhatIfPanelButton")?.addEventListener("click", openWhatIfPanel);
  $("closeWhatIfPanelButton")?.addEventListener("click", closeWhatIfPanel);
  $("simulateRiskButton")?.addEventListener("click", runWhatIfSimulation);
  el.whatIfPreset?.addEventListener("change", applyWhatIfPreset);
  el.whatIfHorizon?.addEventListener("change", updateWhatIfControls);
  el.whatIfRainfall?.addEventListener("input", updateWhatIfControls);
  el.whatIfGroundwater?.addEventListener("input", updateWhatIfControls);
  el.whatIfDepth?.addEventListener("input", updateWhatIfControls);
  el.whatIfDistance?.addEventListener("input", updateWhatIfControls);
  el.whatIfGpr?.addEventListener("input", updateWhatIfControls);
  el.whatIfFacility?.addEventListener("input", updateWhatIfControls);
  el.whatIfPastSinkhole?.addEventListener("input", updateWhatIfControls);
  el.whatIfEnvironment?.addEventListener("input", updateWhatIfControls);
  el.whatIfConstruction?.addEventListener("change", updateWhatIfControls);
  el.whatIfTargetOnly?.addEventListener("change", updateWhatIfControls);
  el.whatIfMitigationGpr?.addEventListener("change", updateWhatIfControls);
  el.whatIfMitigationPipe?.addEventListener("change", updateWhatIfControls);
  el.whatIfMitigationDrainage?.addEventListener("change", updateWhatIfControls);
  el.whatIfMitigationConstruction?.addEventListener("change", updateWhatIfControls);
  el.whatIfMitigationMonitoring?.addEventListener("change", updateWhatIfControls);
  el.selectAllReports?.addEventListener("change", () => {
    state.selectedReports = el.selectAllReports.checked
      ? new Set(state.reports.map((row) => row.file_name))
      : new Set();
    renderReportList();
  });
  el.analysisType?.addEventListener("change", async () => {
    updateAnalysisTypeControls();
    await loadRoads();
    await refreshSummaryPanels();
  });
  el.regionSelect?.addEventListener("change", async () => {
    state.selectedRegionId = Number(el.regionSelect.value);
    const selected = state.regions.find((region) => Number(region.region_id) === state.selectedRegionId);
    state.selectedRegionName = selected?.region_name || "";
    await loadRoads(state.selectedRegionId);
    renderMap();
    if (state.mode === "scenario" && state.analysisType === "region") await runScenarioAnalysis();
  });
  el.roadSelect?.addEventListener("change", () => {
    state.selectedRoadId = Number(el.roadSelect.value) || null;
    const road = state.roads.find((item) => Number(item.road_id) === state.selectedRoadId);
    state.selectedRoadName = road?.road_name || "";
  });
  $("applyLocationButton")?.addEventListener("click", applyLiveLocation);
  $("pickOnMapButton")?.addEventListener("click", () => setMapPickActive(!state.mapPickActive));
  el.mapPickLayer?.addEventListener("click", async (event) => {
    const point = mapPointFromClick(event);
    const fallbackAddress = nearestKnownRoadAddress(point.latitude, point.longitude);
    state.liveLocation = {
      name: fallbackAddress,
      address: fallbackAddress,
      latitude: point.latitude,
      longitude: point.longitude,
    };
    if (el.liveLocationInput) el.liveLocationInput.value = state.liveLocation.name;
    setMapPickActive(false);
    setMode("live", { silent: true });
    renderMap();
    setStatus("지도에서 선택한 위치의 도로명 주소를 확인하는 중입니다.");
    const address = await reverseGeocodeAddress(point.latitude, point.longitude);
    state.liveLocation.name = address;
    state.liveLocation.address = address;
    if (el.liveLocationInput) el.liveLocationInput.value = address;
    renderMap();
    setStatus(`지도에서 위치를 선택했습니다: ${address}`);
  });
  document.addEventListener("click", (event) => {
    if (!$("quickMenu")?.contains(event.target)) closeQuickMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "F1") {
      event.preventDefault();
      openHelp();
    }
    if (event.key === "Escape") {
      closeHelp();
      closeQuickMenu();
      closeWhatIfPanel();
      closeMetricDialog();
      closeAiChat();
      setMapPickActive(false);
    }
  });
}

async function bootstrap() {
  bindEvents();
  mountWhatIfPanel();
  setStatus(t().loading);
  applyLanguage(localStorage.getItem("sinkhole_lang") || "ko");
  const clock = updateClock();
  renderReasonCards([]);
  renderTrendChart([]);
  renderCauseDistribution([]);
  await checkHealth();
  try {
    await loadRegions();
    await loadRoads();
    await loadMonitoringPoints({ refresh: true, force: true }).catch((error) => console.warn("monitoring refresh failed", error));
    await refreshSummaryPanels();
    startDashboardAutoRefresh();
    setMode("scenario", { silent: true });
    updateWhatIfControls();
    renderWhatIfResults(state.simulationRows);
    if (state.selectedRegionId) await runScenarioAnalysis(clock, { manageBusy: false });
    await refreshReportList();
    setStatus(t().ready);
  } catch (error) {
    setStatus(error.message);
    renderMap();
  }
}

window.openHelp = openHelp;
window.closeHelp = closeHelp;
window.openAiChat = openAiChat;
window.closeAiChat = closeAiChat;
updateWhatIfControls = function () {
  const rainfall = Number(el.whatIfRainfall?.value || 0);
  const groundwater = Number(el.whatIfGroundwater?.value || 0);
  const depth = Number(el.whatIfDepth?.value || 0);
  const distance = Number(el.whatIfDistance?.value || 0);
  const gpr = Number(el.whatIfGpr?.value || 0);
  const facility = Number(el.whatIfFacility?.value || 0);
  const past = Number(el.whatIfPastSinkhole?.value || 0);
  const environment = Number(el.whatIfEnvironment?.value || 0);
  const horizon = Number(el.whatIfHorizon?.value || 24);
  const construction = Boolean(el.whatIfConstruction?.checked);
  const targetOnly = Boolean(el.whatIfTargetOnly?.checked);
  const mitigationCount = [
    el.whatIfMitigationGpr,
    el.whatIfMitigationPipe,
    el.whatIfMitigationDrainage,
    el.whatIfMitigationConstruction,
    el.whatIfMitigationMonitoring,
  ].filter((item) => Boolean(item?.checked)).length;
  setText(el.whatIfRainfallValue, `${rainfall}mm`);
  setText(el.whatIfGroundwaterValue, `${groundwater.toFixed(1)}m`);
  setText(el.whatIfDepthValue, `${depth}m`);
  setText(el.whatIfDistanceValue, `${distance}m`);
  setText(el.whatIfGprValue, `${gpr}개`);
  setText(el.whatIfFacilityValue, `${facility}점`);
  setText(el.whatIfPastSinkholeValue, `${past}건`);
  setText(el.whatIfEnvironmentValue, `${environment.toFixed(1)}점`);
  setText(
    el.whatIfSummary,
    `${horizon}시간 예측 / 강우 ${rainfall}mm / 지하수 ${groundwater.toFixed(1)}m / GPR ${gpr}개 / ${construction ? "공사 반영" : "공사 없음"} / 관리 조치 ${mitigationCount}개 / ${targetOnly ? "선택 지역만" : "전체 지역"}`,
  );
};
renderWhatIfResults = function (rows = []) {
  if (!el.whatIfResults) return;
  el.whatIfResults.innerHTML = "";
  if (!rows.length) {
    el.whatIfResults.innerHTML = `<div class="empty-state">시뮬레이션 실행 후 결과가 표시됩니다.</div>`;
    return;
  }

  rows.slice(0, 6).forEach((row) => {
    const original = Number(row.original_score || 0);
    const scenarioScore = Number(row.scenario_score_before_mitigation ?? row.simulated_score ?? 0);
    const simulated = Number(row.simulated_score || 0);
    const diff = Number(row.score_diff || 0);
    const scenarioDiff = Number(row.scenario_score_diff ?? (scenarioScore - original));
    const mitigationReduction = Number(row.mitigation_reduction || 0);
    const drivers = Array.isArray(row.drivers) ? row.drivers.slice(0, 4) : [];
    const factorChanges = Array.isArray(row.factor_changes) ? row.factor_changes : [];
    const mitigations = Array.isArray(row.mitigation_effects) ? row.mitigation_effects : [];
    const mitigationNotes = Array.isArray(row.mitigation_notes) ? row.mitigation_notes : [];
    const actions = Array.isArray(row.recommendations) ? row.recommendations.slice(0, 3) : [];
    const quality = row.data_quality || {};
    const aiCommentary = row.ai_commentary || "시뮬레이션 결과를 기준으로 점검 우선순위를 검토하세요.";
    const mitigationHtml = mitigations.length || mitigationNotes.length
      ? `
        <div class="whatif-mitigation-result">
          ${mitigations.map((item) => `<span>${escapeHtml(item.action_label || "관리 조치")} · ${escapeHtml(item.factor_label || "-")} -${formatNumber(item.reduction, 1)}점</span>`).join("")}
          ${mitigationNotes.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
        </div>
      `
      : "";
    const card = document.createElement("article");
    card.className = `whatif-result-card ${diff >= 8 ? "elevated" : ""}`;
    card.innerHTML = `
      <div class="whatif-result-head">
        <strong>${escapeHtml(row.region_name || "-")}</strong>
        <span>${formatNumber(simulated, 1)}</span>
      </div>
      <div class="scenario-score-compare">
        <div>
          <small>현재</small>
          <b>${formatNumber(original, 1)}</b>
          <i style="width:${Math.max(2, Math.min(100, original))}%"></i>
        </div>
        <div>
          <small>악화조건</small>
          <b>${formatNumber(scenarioScore, 1)} (${scenarioDiff >= 0 ? "+" : ""}${formatNumber(scenarioDiff, 1)})</b>
          <i class="scenario-bar" style="width:${Math.max(2, Math.min(100, scenarioScore))}%"></i>
        </div>
        <div>
          <small>조치 후</small>
          <b>${formatNumber(simulated, 1)} (${diff >= 0 ? "+" : ""}${formatNumber(diff, 1)})</b>
          <i class="mitigation-bar" style="width:${Math.max(2, Math.min(100, simulated))}%"></i>
        </div>
      </div>
      <div class="whatif-result-meta">
        <span>${escapeHtml(row.original_level || "-")} → ${escapeHtml(row.new_risk_level || "-")}</span>
        <span>조치 ${escapeHtml(row.action_level || "-")}</span>
        <span>신뢰도 ${escapeHtml(row.confidence?.label || "-")}</span>
        <span>관리 감점 ${formatNumber(mitigationReduction, 1)}점</span>
      </div>
      <div class="whatif-drivers">
        ${drivers.length ? drivers.map((driver) => `<span>${escapeHtml(driver.label)} +${formatNumber(driver.delta, 1)}</span>`).join("") : "<span>추가 상승 요인 없음</span>"}
      </div>
      <div class="whatif-factor-table">
        ${factorChanges.map((item) => `
          <div>
            <span>${escapeHtml(item.label || item.factor || "-")}</span>
            <b>${formatNumber(item.base, 1)} → ${formatNumber(item.scenario, 1)} → ${formatNumber(item.final, 1)}</b>
            <i><em style="width:${Math.max(2, Math.min(100, Number(item.final || 0) * 5))}%"></em></i>
            <small>상승 ${Number(item.increase || 0) >= 0 ? "+" : ""}${formatNumber(item.increase, 1)} / 조치 -${formatNumber(item.mitigation, 1)}</small>
          </div>
        `).join("")}
      </div>
      ${mitigationHtml}
      <div class="whatif-ai-card">
        <strong>AI 해석</strong>
        <p>${escapeHtml(aiCommentary)}</p>
      </div>
      <div class="whatif-quality">
        <span>데이터 충분성 ${escapeHtml(quality.label || "-")}</span>
        <span>${escapeHtml(quality.basis || "근거 데이터 요약 없음")}</span>
      </div>
      <div class="whatif-actions">
        ${actions.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
    `;
    el.whatIfResults.appendChild(card);
  });
};
window.__sinkholeActions = {
  analyze: runAnalysis,
  report: generateReport,
  simulate: runWhatIfSimulation,
  openHelp,
  closeHelp,
  openWhatIfPanel,
  closeWhatIfPanel,
  openAiChat,
  closeAiChat,
};
window.__sinkholeAppReady = true;
window.__sinkholeAssetVersion = "20260514-help-update";

bootstrap().catch((error) => {
  console.error(error);
  setBusy(false);
  setStatus(error?.message || "초기화 중 오류가 발생했습니다.");
});
