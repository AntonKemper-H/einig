// A10 (D16, D20): swipe the front of the rating card. Right = "Rather yes", up = "Fine with me",
// left = "Rather not", down = asks whether to use the joker. A tap turns the card; on the back,
// a tap turns it back and the dots follow the page you scrolled to.
// This script only presses buttons that are already on the page; the normal forms do the rest.
// Without this script the page works the same, with the (visually hidden) buttons.
(function () {
  "use strict";

  var SWIPE_DISTANCE = 110;  // pixels the card must be moved before a swipe counts
  var TAP_DISTANCE = 10;     // a touch that moves less than this is a tap: it turns the card (D19)
  var FLY_OUT_MS = 200;      // length of the fly-out animation before the button is pressed

  var card = document.querySelector("[data-swipe-card]");
  if (!card) {
    return;  // not the one-card rating view: nothing to do
  }
  var area = card.querySelector("[data-swipe-area]");
  var flipToggle = card.querySelector("[data-flip-toggle]");  // only on Google cards with details
  var back = card.querySelector("[data-card-back]");         // only on Google cards with details
  var pages = card.querySelector(".card-pages");
  var dots = card.querySelectorAll("[data-card-dot]");
  var question = card.querySelector("[data-joker-question]");  // only while the joker is still free
  var jokerButton = card.querySelector('form[action$="/veto"] button');
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

  // Which rating a movement would give, or null. Down gives nothing here: it asks about the joker.
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
    // A touch that starts on a link (e.g. the photo author) is left alone: the link works normally.
    if (event.target.closest("a")) { return; }
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
    var dx = event.clientX - start.x;
    var dy = event.clientY - start.y;
    var choice = choiceFor(dx, dy);
    start = null;
    // Down: do not use the joker at once, it cannot be undone. Ask first; nothing is sent yet.
    if (!choice && question && dy >= SWIPE_DISTANCE && Math.abs(dy) > Math.abs(dx)) {
      springBack();
      question.hidden = false;
      return;
    }
    if (!choice && flipToggle && Math.abs(dx) < TAP_DISTANCE && Math.abs(dy) < TAP_DISTANCE) {
      springBack();
      flipToggle.click();  // a short tap turns the card; nothing is rated
      return;
    }
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

  // The joker question: "Use joker" presses the joker button that is already in the page.
  if (question && jokerButton) {
    question.querySelector("[data-joker-confirm]").addEventListener("click", function () {
      done = true;
      jokerButton.click();
    });
    question.querySelector("[data-joker-cancel]").addEventListener("click", function () {
      question.hidden = true;
    });
  }

  // The back has no rating gestures. A short tap on a free spot turns the card back to the front;
  // links, dots and buttons keep their own behaviour, and a drag (page change, scrolling) is no tap.
  if (back && flipToggle) {
    var backStart = null;
    back.addEventListener("pointerdown", function (event) {
      backStart = { x: event.clientX, y: event.clientY };
    });
    back.addEventListener("pointerup", function (event) {
      if (backStart === null) { return; }
      var moved = Math.abs(event.clientX - backStart.x) >= TAP_DISTANCE ||
                  Math.abs(event.clientY - backStart.y) >= TAP_DISTANCE;
      backStart = null;
      if (moved || event.target.closest("a, button, label, [data-card-dot]")) { return; }
      flipToggle.click();
    });
    back.addEventListener("pointercancel", function () { backStart = null; });
  }

  // Mark the dot of the page that is in view (without this script the first dot stays marked).
  if (pages && dots.length) {
    pages.addEventListener("scroll", function () {
      var current = Math.round(pages.scrollLeft / pages.clientWidth);
      for (var i = 0; i < dots.length; i++) {
        if (i === current) {
          dots[i].setAttribute("aria-current", "true");
        } else {
          dots[i].removeAttribute("aria-current");
        }
      }
    });
  }

  // After one swipe, ignore further taps on the card's buttons (no double rating).
  card.addEventListener("click", function (event) {
    if (done && event.isTrusted) {
      event.preventDefault();
    }
  }, true);
})();
