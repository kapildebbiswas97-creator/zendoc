const button = document.getElementById("use-location");
const statusNode = document.getElementById("location-status");

if (button) {
  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      statusNode.textContent = "Geolocation is not supported by this browser. Please enter a manual location.";
      return;
    }
    statusNode.textContent = "Requesting location permission...";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        document.querySelector("input[name='latitude']").value = position.coords.latitude.toFixed(6);
        document.querySelector("input[name='longitude']").value = position.coords.longitude.toFixed(6);
        statusNode.textContent = "Location added. Submit the search when ready.";
      },
      () => {
        statusNode.textContent = "Location permission was denied or unavailable. You can enter a location manually.";
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
    );
  });
}
