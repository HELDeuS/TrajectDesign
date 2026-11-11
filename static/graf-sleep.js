(function () {
  "use strict";
  var svg = document.querySelector("svg[data-sleepbaar]");
  if (!svg) return;

  var MARGE = parseInt(svg.dataset.marge, 10);
  var BREEDTE = parseInt(svg.dataset.breedte, 10);
  var HOOGTE = parseInt(svg.dataset.hoogte, 10);
  var nodes = Array.prototype.slice.call(svg.querySelectorAll("a.graf-node"));

  function svgPunt(e) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }

  function nodeOp(punt, exclusief) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n === exclusief) continue;
      var x = parseFloat(n.dataset.x), y = parseFloat(n.dataset.y);
      if (punt.x >= x && punt.x <= x + BREEDTE && punt.y >= y && punt.y <= y + HOOGTE) return n;
    }
    return null;
  }

  function stuur(data) {
    var body = new URLSearchParams();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    return fetch(svg.dataset.verplaatsUrl, { method: "POST", body: body, credentials: "same-origin" })
      .then(function () { window.location.reload(); });
  }

  nodes.forEach(function (node) {
    var start = null, verplaatst = false;

    node.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      start = { punt: svgPunt(e) };
      verplaatst = false;
      node.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    node.addEventListener("pointermove", function (e) {
      if (!start) return;
      var p = svgPunt(e);
      var dx = p.x - start.punt.x, dy = p.y - start.punt.y;
      if (!verplaatst && Math.hypot(dx, dy) < 6) return;
      verplaatst = true;
      node.classList.add("sleepend");
      node.setAttribute("transform", "translate(" + dx + "," + dy + ")");
    });

    node.addEventListener("pointerup", function (e) {
      if (!start) return;
      var p = svgPunt(e);
      start = null;
      node.classList.remove("sleepend");
      node.removeAttribute("transform");
      if (!verplaatst) return;
      e.preventDefault();

      var doel = nodeOp(p, node);
      if (doel) {
        stuur({ module_id: node.dataset.mid, doel_module_id: doel.dataset.mid });
        return;
      }

      var y = parseFloat(node.dataset.y);
      var rij = nodes.filter(function (n) { return parseFloat(n.dataset.y) === y && n !== node; })
                     .sort(function (a, b) { return parseFloat(a.dataset.x) - parseFloat(b.dataset.x); });
      var index = Math.round((p.x - MARGE) / (BREEDTE + MARGE));
      index = Math.max(0, Math.min(rij.length, index));
      var volgorde = rij.slice(0, index).concat([node], rij.slice(index))
                        .map(function (n) { return n.dataset.mid; });
      stuur({ module_id: node.dataset.mid, volgorde: volgorde.join(",") });
    });

    node.addEventListener("click", function (e) {
      if (verplaatst) e.preventDefault();
    });
  });
})();
