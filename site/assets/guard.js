// Market Watch is meant to be seen inside RCFE Deal Room's own sites: rcfedealroom.com (and its Marblism
// preview) and the RCFE Deal Room community. Opened anywhere else, the page points people to
// rcfedealroom.com instead. This is a nudge, not a lock: the address and the data files are public.
(function () {
  var ALLOWED = /^https:\/\/((www\.)?rcfedealroom\.com|community\.rcfedealroom\.com|rcfe-deal-room\.marblism\.me|rcfe-community\.dale-35c\.workers\.dev)$/;
  var HOME = "https://www.rcfedealroom.com/market-watch";
  var host = location.hostname;
  if (host === "localhost" || host === "127.0.0.1") return; // Local preview.

  if (window.self !== window.top) {
    var parents = [];
    var a = location.ancestorOrigins;
    if (a && a.length) { for (var i = 0; i < a.length; i++) parents.push(a[i]); }
    else if (document.referrer) { try { parents.push(new URL(document.referrer).origin); } catch (e) { /* unreadable */ } }
    // A browser that can't say who the parent is gets the benefit of the doubt.
    if (!parents.length) return;
    var ok = true;
    for (var j = 0; j < parents.length; j++) if (!ALLOWED.test(parents[j])) ok = false;
    if (ok) return;
  }

  document.documentElement.classList.add("outside");
  document.addEventListener("DOMContentLoaded", function () {
    document.title = "RCFE Deal Room Market Watch";
    var main = document.createElement("main");
    main.className = "outside-note";
    var h1 = document.createElement("h1");
    h1.textContent = "RCFE Deal Room Market Watch";
    var p = document.createElement("p");
    p.textContent = "Market Watch is available on RCFE Deal Room.";
    var link = document.createElement("a");
    link.href = HOME;
    link.textContent = "View Market Watch on rcfedealroom.com";
    var p2 = document.createElement("p");
    p2.appendChild(link);
    main.appendChild(h1); main.appendChild(p); main.appendChild(p2);
    document.body.appendChild(main);
  });
})();
