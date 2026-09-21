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

// Government hospital appointments are a real external workflow, not a
// ZENDOC-confirmed booking. Keep the handoff visible but explicit about where
// the booking is completed. ORS is the NIC common patient portal for
// participating Government of India hospitals.
const finderShell = document.querySelector(".finder-shell");
if (finderShell && !document.getElementById("government-ors-handoff")) {
  const panel = document.createElement("aside");
  panel.id = "government-ors-handoff";
  panel.className = "panel finder-source-summary";
  panel.setAttribute("aria-label", "Government hospital appointment handoff");
  panel.innerHTML = `
    <div class="panel-head">
      <div>
        <p class="eyebrow">Government hospital appointments</p>
        <h2>Need an OPD appointment at a participating government hospital?</h2>
        <p class="form-note">Open the official NIC Online Registration System (ORS). Availability depends on whether that hospital and department are onboarded. The appointment is completed on the government portal, not inside ZENDOC.</p>
      </div>
      <a class="secondary-action" href="https://ors.gov.in/" target="_blank" rel="noopener noreferrer">Book via official ORS</a>
    </div>`;
  finderShell.insertBefore(panel, finderShell.firstChild);
}
