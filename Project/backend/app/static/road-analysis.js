// Road-level analysis setup
const analysisTypeSelect = document.getElementById("analysisType");
const roadSelect = document.getElementById("roadSelect");
const roadControlsContainer = document.getElementById("roadControlsContainer");

// Extend state with road data
state.analysisType = "region";
state.roads = [];
state.selectedRoadId = null;
state.selectedRoadName = "";

// Load roads for selected region
async function loadRoads(regionId) {
  try {
    const res = await fetch(`/api/roads?region_id=${regionId}`);
    const json = await res.json();
    if (json.success) {
      state.roads = json.data || [];
      updateRoadSelect();
    }
  } catch (err) {
    console.error("Failed to load roads:", err);
  }
}

// Update road dropdown
function updateRoadSelect() {
  roadSelect.innerHTML = "";
  if (state.roads.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "도로 데이터 없음";
    roadSelect.appendChild(option);
  } else {
    state.roads.forEach((road) => {
      const option = document.createElement("option");
      option.value = road.road_id;
      option.textContent = `${road.road_name} (${road.road_type})`;
      roadSelect.appendChild(option);
    });
  }
}

// Handle analysis type change
analysisTypeSelect.addEventListener("change", (e) => {
  state.analysisType = e.target.value;
  if (e.target.value === "road") {
    roadControlsContainer.classList.remove("hidden");
    if (state.selectedRegionId) {
      loadRoads(state.selectedRegionId);
    }
  } else {
    roadControlsContainer.classList.add("hidden");
  }
});

// Handle road selection
roadSelect.addEventListener("change", (e) => {
  state.selectedRoadId = parseInt(e.target.value) || null;
  state.selectedRoadName = roadSelect.options[roadSelect.selectedIndex]?.text || "";
});

// Override regionSelect change to also load roads
const originalRegionSelectListener = regionSelect.addEventListener;
regionSelect.addEventListener = function (event, handler, ...args) {
  if (event === "change") {
    const wrappedHandler = function (e) {
      if (state.analysisType === "road") {
        loadRoads(parseInt(e.target.value) || null);
      }
      handler.call(this, e);
    };
    return originalRegionSelectListener.call(this, event, wrappedHandler, ...args);
  }
  return originalRegionSelectListener.call(this, event, handler, ...args);
};

// Analyze road risk
async function analyzeRoad() {
  if (!state.selectedRoadId) {
    statusText.textContent = "도로를 선택하세요.";
    return;
  }
  
  statusText.textContent = TXT.loading;
  
  try {
    const clientClock = getClientClock();
    const res = await fetch("/api/analyze-road-risk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        road_id: state.selectedRoadId,
        analysis_date: analysisDate.value || null,
        client_local_datetime: clientClock.datetime,
        client_timezone: clientClock.timezone,
        client_utc_offset_minutes: clientClock.offset,
      }),
    });
    
    const json = await res.json();
    if (json.success) {
      state.selectedAnalysis = json.data;
      const road = json.data.road;
      selectedRegionText.textContent = `도로: ${road.road_name}`;
      resultScore.textContent = json.data.analysis.total_risk_score.toFixed(1);
      resultLevel.textContent = json.data.analysis.risk_level;
      resultPriority.textContent = json.data.analysis.priority_rank || "-";
      resultCoords.textContent = road.road_address || "도로명 주소 확인 필요";
      
      if (json.data.analysis.client_local_time) {
        state.lastClientClock = json.data.analysis.client_local_time;
      }
      
      renderRoadMapMarker(road.center_lat, road.center_lon, json.data.analysis.total_risk_score);
      renderFactorChart(json.data.breakdown);
      statusText.textContent = TXT.analyzed;
    } else {
      statusText.textContent = `오류: ${json.error || "분석 실패"}`;
    }
  } catch (err) {
    console.error("Error analyzing road:", err);
    statusText.textContent = `오류: ${err.message}`;
  }
}

// Render marker on map for road
function renderRoadMapMarker(lat, lon, score) {
  state.analysisCoords = { lat, lon };
  
  // For demo map
  if (!demoMap.classList.contains("hidden")) {
    const svg = demoMap;
    const markers = svg.querySelectorAll("circle[data-is-marker]");
    markers.forEach((m) => m.remove());
    
    const viewBox = svg.viewBox.baseVal;
    const x = ((lon - 128.0) / 0.15) * viewBox.width;
    const y = ((35.2 - lat) / 0.15) * viewBox.height;
    
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", "8");
    circle.setAttribute("fill", getRiskColor(score));
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "2");
    circle.setAttribute("data-is-marker", "true");
    svg.appendChild(circle);
  }
  
  // For Google Map
  if (state.map && !googleMapDiv.classList.contains("hidden")) {
    if (state.mapMarker) {
      state.mapMarker.setMap(null);
    }
    state.mapMarker = new google.maps.Marker({
      position: { lat, lng: lon },
      map: state.map,
      title: state.selectedRoadName,
      icon: `http://maps.google.com/mapfiles/ms/icons/${getRiskColorHex(score)}.png`,
    });
  }
}

// Get color for risk score
function getRiskColor(score) {
  if (score >= 80) return "#FF4444";
  if (score >= 60) return "#FFA500";
  if (score >= 30) return "#FFFF00";
  return "#00CC00";
}

function getRiskColorHex(score) {
  if (score >= 80) return "red";
  if (score >= 60) return "orange";
  if (score >= 30) return "yellow";
  return "green";
}

// Override analyzeButton click to handle both region and road
const originalAnalyzeClick = analyzeButton.onclick;
analyzeButton.addEventListener("click", (e) => {
  if (state.analysisType === "road") {
    analyzeRoad();
  } else {
    originalAnalyzeClick?.call(analyzeButton, e);
  }
});

// Get current client clock
function getClientClock() {
  const now = new Date();
  return {
    datetime: now.toISOString(),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    offset: -now.getTimezoneOffset(),
  };
}
