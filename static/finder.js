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
