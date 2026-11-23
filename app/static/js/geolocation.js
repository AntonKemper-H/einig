// Asks the browser for the location after a tap on "Use my location" and puts
// rounded coordinates into the hidden form fields "latitude" and "longitude".
// Rounding to 3 decimals (about 100 m) means the exact location never leaves the
// phone. The server rounds again, because it cannot trust the browser.
// Browsers only allow this over HTTPS (or on localhost).

(function () {
  var button = document.getElementById("use-location");
  var status = document.getElementById("location-status");
  var latitudeField = document.getElementById("latitude");
  var longitudeField = document.getElementById("longitude");
  if (!button || !status || !latitudeField || !longitudeField) {
    return; // The search form is not on this page.
  }

  function roundCoordinate(value) {
    return Math.round(value * 1000) / 1000;
  }

  button.addEventListener("click", function () {
    if (!navigator.geolocation) {
      status.textContent = "Your browser cannot share its location.";
      return;
    }
    status.textContent = "Getting your location …";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        latitudeField.value = roundCoordinate(position.coords.latitude);
        longitudeField.value = roundCoordinate(position.coords.longitude);
        status.textContent = "Location shared. You can now search.";
      },
      function (error) {
        // error.code tells us why it failed, so the message can say what to fix.
        switch (error.code) {
          case 1: // PERMISSION_DENIED
            status.textContent = "Location is blocked. Allow it for this site in your browser. On iPhone or iPad: Settings → Privacy & Security → Location Services → Safari Websites.";
            break;
          case 2: // POSITION_UNAVAILABLE
            status.textContent = "Your location could not be found. Please try again.";
            break;
          case 3: // TIMEOUT
            status.textContent = "Finding your location took too long. Please try again.";
            break;
          default:
            status.textContent = "Location not shared. Please allow location access and try again.";
        }
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
    );
  });
})();
