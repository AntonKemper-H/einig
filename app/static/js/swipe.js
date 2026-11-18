// A10 (D16): swipe the rating card. Right = "Rather yes", up = "Fine with me", left = "Rather not".
// This script only presses the rating button that is already on the page; the normal form
// does the rest. Without this script the page works the same, with the buttons.
(function () {
  "use strict";

  var SWIPE_DISTANCE = 110;  // pixels the card must be moved before a swipe counts
  var FLY_OUT_MS = 200;      // length of the fly-out animation before the button is pressed

  var card = document.querySelector("[data-swipe-card]");
  if (!card) {
    return;  // not the one-card rating view: nothing to do
  }
  var area = card.querySelector("[data-swipe-area]");
  var buttons = {
    yes: card.querySelector('button[name="rating"][value="yes"]'),
    ok: card.querySelector('button[name="rating"][value="ok"]'),
    no: card.querySelector('button[name="rating"][value="no"]')
  };
  if (!area || !buttons.yes || !buttons.ok || !buttons.no) {
    return;
  }

  // Show the hint only now that swiping works.
  var hint = document.querySelector("[data-swipe-hint]");
  if (hint) {
    hint.hidden = false;
  }

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var start = null;   // where the finger went down, or null when not dragging
  var done = false;   // true after one swipe counted: ignore everything until the next page

  // Which rating a movement would give, or null. Down gives nothing.
  function choiceFor(dx, dy) {
    if (Math.abs(dx) > Math.abs(dy)) {
      if (dx >= SWIPE_DISTANCE) { return "yes"; }
      if (dx <= -SWIPE_DISTANCE) { return "no"; }
    } else if (dy <= -SWIPE_DISTANCE) {
      return "ok";
    }
    return null;
  }

  // Move and tilt the card with the finger, and show the label of the rating it would give.
  function moveCard(dx, dy) {
    card.style.transform = "translate(" + dx + "px, " + dy + "px) rotate(" + dx / 20 + "deg)";
    var choice = choiceFor(dx, dy);
    if (choice) {
      card.setAttribute("data-swipe-choice", choice);
    } else {
      card.removeAttribute("data-swipe-choice");
    }
  }

  // Put the card back where it was; nothing is sent.
  function springBack() {
    card.classList.remove("is-dragging");
    card.style.transform = "";
    card.removeAttribute("data-swipe-choice");
  }

  area.addEventListener("pointerdown", function (event) {
    if (done) { return; }
    start = { x: event.clientX, y: event.clientY };
    card.classList.add("is-dragging");
    area.setPointerCapture(event.pointerId);
  });

  area.addEventListener("pointermove", function (event) {
    if (start === null) { return; }
    moveCard(event.clientX - start.x, event.clientY - start.y);
  });

  area.addEventListener("pointerup", function (event) {
    if (start === null) { return; }
    var choice = choiceFor(event.clientX - start.x, event.clientY - start.y);
    start = null;
    if (!choice) {
      springBack();
      return;
    }
    done = true;
    card.classList.remove("is-dragging");
    if (reduceMotion) {
      buttons[choice].click();
      return;
    }
    // Let the card fly out in the swipe direction, then press the matching button.
    var away = { yes: "translate(150%, 0) rotate(20deg)", ok: "translate(0, -150%)", no: "translate(-150%, 0) rotate(-20deg)" };
    card.style.transform = away[choice];
    window.setTimeout(function () { buttons[choice].click(); }, FLY_OUT_MS);
  });

  area.addEventListener("pointercancel", function () {
    start = null;
    springBack();
  });

  // After one swipe, ignore further taps on the card's buttons (no double rating).
  card.addEventListener("click", function (event) {
    if (done && event.isTrusted) {
      event.preventDefault();
    }
  }, true);
})();
