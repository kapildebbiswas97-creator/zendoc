const button = document.getElementById("use-location");
const statusNode = document.getElementById("location-status");

if (button) {
  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      statusNode.textContent = "Geolocation is not supported by this browser. Please enter a manual location.";
      return;
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    statusNode.textContent = "Requesting location permission...";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const form = button.closest("form");
        const latitude = position.coords.latitude.toFixed(6);
        const longitude = position.coords.longitude.toFixed(6);

        const latitudeInputs = form
          ? form.querySelectorAll("input[name='latitude']")
          : document.querySelectorAll("input[name='latitude']");
        const longitudeInputs = form
          ? form.querySelectorAll("input[name='longitude']")
          : document.querySelectorAll("input[name='longitude']");

        latitudeInputs.forEach((node) => {
          node.value = latitude;
        });
        longitudeInputs.forEach((node) => {
          node.value = longitude;
        });

        statusNode.textContent = "Location found. Searching nearby care...";
        button.disabled = false;
        button.removeAttribute("aria-busy");

        // One tap should complete the nearby-search action. The old behavior
        // only filled hidden coordinates and required a second manual submit,
        // which looked like a broken location button on mobile.
        if (form) {
          if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
          } else {
            form.submit();
          }
        }
      },
      () => {
        statusNode.textContent = "Location permission was denied or unavailable. You can enter a location manually.";
        button.disabled = false;
        button.removeAttribute("aria-busy");
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
    );
  });
}


(() => {
  const panel = document.getElementById("finder-map-panel");
  const map = document.getElementById("finder-map");
  const tilesNode = document.getElementById("finder-map-tiles");
  const markersNode = document.getElementById("finder-map-markers");
  const mapStatus = document.getElementById("finder-map-status");
  const fitButton = document.getElementById("finder-map-fit");
  const zoomInButton = document.getElementById("finder-map-zoom-in");
  const zoomOutButton = document.getElementById("finder-map-zoom-out");
  const selected = document.getElementById("finder-map-selected");
  const selectedName = document.getElementById("finder-map-selected-name");
  const selectedSource = document.getElementById("finder-map-selected-source");
  const selectedLink = document.getElementById("finder-map-selected-link");

  if (!panel || !map || !tilesNode || !markersNode || !mapStatus ||
      !fitButton || !zoomInButton || !zoomOutButton) {
    return;
  }

  const points = Array.from(document.querySelectorAll("#finder-map-data .finder-map-point"))
    .map((node) => ({
      lat: Number(node.dataset.lat),
      lng: Number(node.dataset.lng),
      name: String(node.dataset.name || "Healthcare result"),
      source: String(node.dataset.source || "external"),
      origin: node.dataset.origin === "1",
      href: String(node.dataset.href || ""),
    }))
    .filter((point) => (
      Number.isFinite(point.lat) &&
      Number.isFinite(point.lng) &&
      point.lat >= -90 &&
      point.lat <= 90 &&
      point.lng >= -180 &&
      point.lng <= 180
    ));

  if (!points.length) {
    panel.hidden = true;
    return;
  }

  const TILE_SIZE = 256;
  const MIN_ZOOM = 2;
  const MAX_ZOOM = 17;
  const tileTemplate = String(panel.dataset.tileTemplate || "").trim();
  const state = {
    centerLat: points.reduce((sum, point) => sum + point.lat, 0) / points.length,
    centerLng: circularMeanLongitude(points.map((point) => point.lng)),
    zoom: 11,
  };

  function circularMeanLongitude(longitudes) {
    let sinSum = 0;
    let cosSum = 0;
    longitudes.forEach((lng) => {
      const radians = lng * Math.PI / 180;
      sinSum += Math.sin(radians);
      cosSum += Math.cos(radians);
    });
    if (sinSum === 0 && cosSum === 0) {
      return longitudes[0] || 0;
    }
    return Math.atan2(sinSum, cosSum) * 180 / Math.PI;
  }

  function clampLatitude(lat) {
    return Math.max(-85.05112878, Math.min(85.05112878, lat));
  }

  function worldPixel(lat, lng, zoom) {
    const scale = TILE_SIZE * Math.pow(2, zoom);
    const clampedLat = clampLatitude(lat);
    const sinLat = Math.sin(clampedLat * Math.PI / 180);
    return {
      x: ((lng + 180) / 360) * scale,
      y: (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale,
      scale: scale,
    };
  }

  function wrappedDeltaX(x, centerX, worldSize) {
    let delta = x - centerX;
    if (delta > worldSize / 2) delta -= worldSize;
    if (delta < -worldSize / 2) delta += worldSize;
    return delta;
  }

  function tileUrl(z, x, y) {
    if (!tileTemplate || !tileTemplate.startsWith("https://")) {
      return "";
    }
    return tileTemplate
      .replaceAll("{z}", String(z))
      .replaceAll("{x}", String(x))
      .replaceAll("{y}", String(y));
  }

  function safeHref(value) {
    if (value.startsWith("/")) return value;
    try {
      const parsed = new URL(value, window.location.origin);
      return parsed.protocol === "https:" ? parsed.href : "";
    } catch (_error) {
      return "";
    }
  }

  function sourceLabel(source, origin) {
    if (origin) return "Your search location";
    const labels = {
      zendoc_provider_network: "ZENDOC reviewed provider",
      official_public_directory: "Official/public directory",
      openstreetmap_nominatim: "OpenStreetMap external listing",
      openstreetmap_overpass: "OpenStreetMap external listing",
      google_places: "Google Places external listing",
    };
    return labels[source] || "External healthcare listing";
  }

  function selectPoint(point) {
    if (!selected || !selectedName || !selectedSource || !selectedLink) return;
    selected.hidden = false;
    selectedName.textContent = point.name;
    selectedSource.textContent = sourceLabel(point.source, point.origin);

    const href = safeHref(point.href);
    if (href) {
      selectedLink.hidden = false;
      selectedLink.href = href;
      if (point.href.startsWith("/")) {
        selectedLink.removeAttribute("target");
      } else {
        selectedLink.target = "_blank";
      }
    } else {
      selectedLink.hidden = true;
      selectedLink.removeAttribute("href");
    }
  }

  function renderTiles(center, width, height) {
    tilesNode.replaceChildren();
    map.classList.remove("finder-map--tiles-unavailable");

    if (!tileTemplate || !tileTemplate.startsWith("https://")) {
      map.classList.add("finder-map--tiles-unavailable");
      mapStatus.textContent = "Map background is not configured. Result markers and directions remain usable.";
      return;
    }

    const topLeftX = center.x - width / 2;
    const topLeftY = center.y - height / 2;
    const minTileX = Math.floor(topLeftX / TILE_SIZE);
    const maxTileX = Math.floor((topLeftX + width) / TILE_SIZE);
    const minTileY = Math.floor(topLeftY / TILE_SIZE);
    const maxTileY = Math.floor((topLeftY + height) / TILE_SIZE);
    const tileCount = Math.pow(2, state.zoom);
    let total = 0;
    let loaded = 0;
    let failed = 0;

    const updateTileHealth = () => {
      if (loaded > 0) {
        mapStatus.textContent = String(points.length) + " mapped result" +
          (points.length === 1 ? "" : "s") + ". Select a marker for details.";
      }
      if (total > 0 && failed === total) {
        map.classList.add("finder-map--tiles-unavailable");
        mapStatus.textContent = "Map background is temporarily unavailable. Result markers and directions remain usable.";
      } else if (failed > 0 && loaded > 0) {
        mapStatus.textContent = "Some map tiles did not load. Result markers and directions remain usable.";
      }
    };

    for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
      if (tileY < 0 || tileY >= tileCount) continue;
      for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
        const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
        const src = tileUrl(state.zoom, wrappedX, tileY);
        if (!src) continue;

        total += 1;
        const image = document.createElement("img");
        image.className = "finder-map-tile";
        image.alt = "";
        image.decoding = "async";
        image.loading = "eager";
        image.src = src;
        image.style.left = String(tileX * TILE_SIZE - topLeftX) + "px";
        image.style.top = String(tileY * TILE_SIZE - topLeftY) + "px";
        image.addEventListener("load", () => {
          loaded += 1;
          updateTileHealth();
        }, { once: true });
        image.addEventListener("error", () => {
          failed += 1;
          image.remove();
          updateTileHealth();
        }, { once: true });
        tilesNode.appendChild(image);
      }
    }
  }

  function renderMarkers(center, width, height) {
    markersNode.replaceChildren();
    points.forEach((point, position) => {
      const projected = worldPixel(point.lat, point.lng, state.zoom);
      const left = width / 2 + wrappedDeltaX(projected.x, center.x, projected.scale);
      const top = height / 2 + projected.y - center.y;
      if (left < -30 || left > width + 30 || top < -30 || top > height + 30) return;

      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = "finder-map-marker";
      if (point.origin) {
        marker.classList.add("finder-map-marker--origin");
      } else if (point.source === "zendoc_provider_network") {
        marker.classList.add("finder-map-marker--verified");
      }
      marker.style.left = String(left) + "px";
      marker.style.top = String(top) + "px";
      marker.setAttribute(
        "aria-label",
        point.name + ". " + sourceLabel(point.source, point.origin) + "."
      );
      marker.title = point.name;
      marker.textContent = point.origin ? "◎" : String(position + 1);
      marker.addEventListener("click", () => selectPoint(point));
      markersNode.appendChild(marker);
    });
  }

  function renderMap() {
    const width = Math.max(300, map.clientWidth || 760);
    const height = Math.max(280, map.clientHeight || 420);
    const center = worldPixel(state.centerLat, state.centerLng, state.zoom);
    mapStatus.textContent = "Loading map…";
    renderTiles(center, width, height);
    renderMarkers(center, width, height);
    zoomInButton.disabled = state.zoom >= MAX_ZOOM;
    zoomOutButton.disabled = state.zoom <= MIN_ZOOM;
  }

  function fitResults() {
    const width = Math.max(300, map.clientWidth || 760);
    const height = Math.max(280, map.clientHeight || 420);
    state.centerLat = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
    state.centerLng = circularMeanLongitude(points.map((point) => point.lng));

    let fitted = MIN_ZOOM;
    for (let zoom = MAX_ZOOM; zoom >= MIN_ZOOM; zoom -= 1) {
      const center = worldPixel(state.centerLat, state.centerLng, zoom);
      const availableX = Math.max(40, width / 2 - 54);
      const availableY = Math.max(40, height / 2 - 54);
      const fits = points.every((point) => {
        const projected = worldPixel(point.lat, point.lng, zoom);
        const dx = Math.abs(wrappedDeltaX(projected.x, center.x, projected.scale));
        const dy = Math.abs(projected.y - center.y);
        return dx <= availableX && dy <= availableY;
      });
      if (fits) {
        fitted = zoom;
        break;
      }
    }
    state.zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, fitted));
    renderMap();
  }

  fitButton.addEventListener("click", fitResults);
  zoomInButton.addEventListener("click", () => {
    state.zoom = Math.min(MAX_ZOOM, state.zoom + 1);
    renderMap();
  });
  zoomOutButton.addEventListener("click", () => {
    state.zoom = Math.max(MIN_ZOOM, state.zoom - 1);
    renderMap();
  });

  let resizeTimer = null;
  const scheduleResize = () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderMap, 120);
  };
  if ("ResizeObserver" in window) {
    new ResizeObserver(scheduleResize).observe(map);
  } else {
    window.addEventListener("resize", scheduleResize, { passive: true });
  }

  fitResults();
})();
