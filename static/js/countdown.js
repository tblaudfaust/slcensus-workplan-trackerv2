(function () {
  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function tick(el) {
    var target = new Date(el.dataset.countdownTarget + "T00:00:00");
    var now = new Date();
    var diffMs = target - now;
    var dayEl = el.querySelector("[data-cd-days]");
    var clockEl = el.querySelector("[data-cd-clock]");
    var labelEl = el.querySelector("[data-cd-label]");

    if (isNaN(target.getTime())) {
      return;
    }

    if (diffMs <= 0) {
      var pastDays = Math.floor(-diffMs / 86400000);
      if (dayEl) dayEl.textContent = pastDays === 0 ? "Today" : pastDays;
      if (clockEl) clockEl.textContent = "";
      if (labelEl) labelEl.textContent = pastDays === 0 ? "Census Day is today" : "days since Census Day";
      el.classList.add("countdown-elapsed");
      return;
    }

    var totalSeconds = Math.floor(diffMs / 1000);
    var days = Math.floor(totalSeconds / 86400);
    var hours = Math.floor((totalSeconds % 86400) / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;

    if (dayEl) dayEl.textContent = days;
    if (clockEl) clockEl.textContent = pad(hours) + ":" + pad(minutes) + ":" + pad(seconds);
    if (labelEl) labelEl.textContent = "days to Census Day";
  }

  function start() {
    var elements = document.querySelectorAll("[data-countdown-target]");
    if (!elements.length) return;
    elements.forEach(function (el) {
      tick(el);
    });
    setInterval(function () {
      elements.forEach(function (el) {
        tick(el);
      });
    }, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
