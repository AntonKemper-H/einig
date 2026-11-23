// Invite button: after a tap it opens the phone's own share menu (Web Share API) with the
// invite link. Without that API (or without JavaScript) the page keeps its plain links to
// WhatsApp, Mail and SMS. This script sends nothing anywhere itself.
// The texts sit percent-encoded in the button's data attributes.

(function () {
  var button = document.getElementById("invite-button");
  var links = document.getElementById("invite-links");
  if (!button || !links || !navigator.share) {
    return; // Not on this page, or the browser cannot share: the links stay.
  }
  button.hidden = false;
  links.hidden = true;
  button.addEventListener("click", function () {
    navigator.share({
      title: decodeURIComponent(button.dataset.title),
      text: decodeURIComponent(button.dataset.text),
      url: decodeURIComponent(button.dataset.url),
    }).catch(function () {
      // The person closed the menu: nothing to do.
    });
  });
})();
