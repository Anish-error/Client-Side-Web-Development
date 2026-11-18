
(() => {
  const stationDataElement = document.getElementById("station-data");
  const mapElement = document.getElementById("station-map");
  const statusElement = document.getElementById("map-status");

  const stations = stationDataElement
    ? JSON.parse(stationDataElement.textContent || "[]")
    : [];

  // ---------------- MAP ----------------
  if (!mapElement || !statusElement) return;

  if (typeof L === "undefined") {
    statusElement.textContent =
      "Leaflet could not load. Check your internet connection and script tags.";
    return;
  }

  {
    // Initial map position: Pune
    const map = L.map(mapElement).setView([18.5204, 73.8567], 12);

    // Free OpenStreetMap map tiles

    L.tileLayer(
      "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png",
      {
        maxZoom: 20,
        attribution:
          '&copy; <a href="https://stadiamaps.com/attribution/">Stadia Maps</a> ' +
          '&copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> ' +
          // '&copy; <a href="https://www.openstreetmap.org/copyright">' +
          'OpenStreetMap</a> contributors'
      }
    ).addTo(map);


    const stationBounds = [];
    const stationMarkers = new Map();
    const stationPositions = [];

    function createOrUpdateMarker(station) {
      const lat = Number(station.latitude);
      const lng = Number(station.longitude);

      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;

      const position = [lat, lng];
      const stationId = String(station.id);

      let marker = stationMarkers.get(stationId);

      if (!marker) {
        const bikeIcon = L.divIcon({
          className: "ecoride-bike-marker",
          html: '<span style="font-size:28px;">🚲</span>',
          iconSize: [36, 36],
          iconAnchor: [18, 18],
        });

        marker = L.marker(position, {
          icon: bikeIcon,
          title: station.name,
        }).addTo(map);

        stationMarkers.set(stationId, marker);
      } else {
        marker.setLatLng(position);
        marker.options.title = station.name;
      }

      const popup = document.createElement("div");
      popup.className = "eco-map-popup";

      const title = document.createElement("strong");
      title.textContent = station.name || "EcoRide Station";
      popup.appendChild(title);

      const address = document.createElement("p");
      address.textContent = station.address || "";
      popup.appendChild(address);

      const availability = document.createElement("p");
      availability.textContent =
        `${Number(station.available_count) || 0} bikes available`;
      popup.appendChild(availability);

      const stationLink = document.createElement("a");
      stationLink.textContent = "View bikes";
      stationLink.href = new URL(
        station.url,
        window.location.origin
      ).href;
      popup.appendChild(stationLink);

      popup.appendChild(document.createTextNode(" · "));

      const directionsLink = document.createElement("a");
      directionsLink.textContent = "Directions";
      directionsLink.href =
        `https://www.openstreetmap.org/directions?from=&to=${lat}%2C${lng}`;
      directionsLink.target = "_blank";
      directionsLink.rel = "noopener noreferrer";
      popup.appendChild(directionsLink);

      marker.bindPopup(popup);
    }

    // Display each station
    // Display each station
    stations.forEach((station) => {
      const lat = Number(station.latitude);
      const lng = Number(station.longitude);

      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;

      const position = [lat, lng];

      stationPositions.push(position);
      stationBounds.push(position);

      createOrUpdateMarker(station);
    });





    // Fit the map around all valid station coordinates
    if (stationBounds.length > 1) {
      map.fitBounds(stationBounds, { padding: [30, 30] });
    } else if (stationBounds.length === 1) {
      map.setView(stationBounds[0], 14);
    }

    // ---------------- CURRENT LOCATION ----------------
    const locationButton = document.getElementById("my-location-btn");
    let userMarker = null;
    let userAccuracyCircle = null;

    locationButton?.addEventListener("click", () => {
      if (!navigator.geolocation) {
        statusElement.textContent =
          "Your browser does not support location services.";
        return;
      }

      statusElement.textContent = "Finding your current location...";

      navigator.geolocation.getCurrentPosition(
        (position) => {
          const userLat = position.coords.latitude;
          const userLng = position.coords.longitude;
          const userPosition = [userLat, userLng];

          if (userMarker) map.removeLayer(userMarker);
          if (userAccuracyCircle) map.removeLayer(userAccuracyCircle);

          userMarker = L.marker(userPosition, {
            title: "Your Current Location",
          }).addTo(map);

          userMarker.bindPopup("📍 You are here").openPopup();

          userAccuracyCircle = L.circle(userPosition, {
            radius: position.coords.accuracy,
            color: "#2878d0",
            fillColor: "#2878d0",
            fillOpacity: 0.12,
          }).addTo(map);

          map.setView(userPosition, 16);

          statusElement.textContent =
            "Your current location is displayed on the map.";
        },
        (error) => {
          const messages = {
            1: "Location permission denied. Allow location access in your browser.",
            2: "Your current location is unavailable.",
            3: "Location request timed out. Please try again.",
          };

          statusElement.textContent =
            messages[error.code] || "Unable to retrieve your location.";
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 0,
        }
      );
    });

    statusElement.textContent =
      `Showing ${stationPositions.length} EcoRide station(s) on the map.`;

    // Helps the map render correctly inside a layout or panel.
    setTimeout(() => map.invalidateSize(), 100);
    // ---------------- AUTOMATIC STATION REFRESH ----------------
    async function refreshStationMarkers() {
      try {
        const response = await fetch(mapElement.dataset.mapDataUrl, {
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("Could not load station data.");
        }

        const latestStations = await response.json();

        const activeStationIds = new Set(
          latestStations.map((station) => String(station.id))
        );

        // Add new stations and update existing markers.
        latestStations.forEach((station) => {
          createOrUpdateMarker(station);
        });

        // Remove markers for deactivated stations.
        stationMarkers.forEach((marker, stationId) => {
          if (!activeStationIds.has(stationId)) {
            map.removeLayer(marker);
            stationMarkers.delete(stationId);
          }
        });

        statusElement.textContent =
          `Showing ${stationMarkers.size} EcoRide station(s) on the map.`;
      } catch (error) {
        console.error("Station map refresh failed:", error);
      }
    }

    // Refresh every 15 seconds.
    setInterval(refreshStationMarkers, 15000);
  }

  // ---------------- SEARCH AND FILTERS ----------------
  const search = document.getElementById("station-search");
  const cards = Array.from(
    document.querySelectorAll("[data-station-card]")
  );
  const resultCount = document.getElementById("station-result-count");
  const noResults = document.getElementById("station-no-results");
  const filters = Array.from(
    document.querySelectorAll("[data-station-filter]")
  );

  let activeFilter = "all";

  function filterStations() {
    const query = (search?.value || "").trim().toLowerCase();
    let visibleCount = 0;

    cards.forEach((card) => {
      const matchesText =
        (card.dataset.name || "").includes(query) ||
        (card.dataset.address || "").includes(query);

      const matchesAvailability =
        activeFilter === "all" ||
        Number(card.dataset.available) > 0;

      const visible = matchesText && matchesAvailability;
      card.hidden = !visible;

      if (visible) visibleCount += 1;
    });

    if (resultCount) {
      resultCount.textContent =
        `${visibleCount} ${visibleCount === 1 ? "station" : "stations"} found`;
    }

    if (noResults) noResults.hidden = visibleCount > 0;
  }

  search?.addEventListener("input", filterStations);

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.stationFilter;

      filters.forEach((item) => {
        const selected = item === button;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-pressed", String(selected));
      });

      filterStations();
    });
  });
})();
