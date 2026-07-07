(function () {
  const canvas = document.getElementById("topologyCanvas");
  const caption = document.getElementById("topologyCaption");
  const buttons = Array.from(document.querySelectorAll("[data-topology]"));
  const signalWord = document.getElementById("signalWord");

  if (!canvas || !caption || buttons.length === 0) {
    return;
  }

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }

  const palette = {
    text: "#f6f1e4",
    muted: "rgba(246, 241, 228, 0.52)",
    line: "rgba(246, 241, 228, 0.18)",
    teal: "#39d4c5",
    green: "#8fe388",
    amber: "#f0b84a",
    coral: "#f06f5f"
  };

  const topologies = {
    vps: {
      caption: "A VPS can publish clearnet, Tor, I2P, Gemini, and Reticulum outputs from one AMPG plan.",
      nodes: [
        ["source", "source site", 0.16, 0.42, "amber"],
        ["ampg", "AMPG", 0.34, 0.42, "teal"],
        ["vps", "VPS", 0.52, 0.42, "green"],
        ["web", "clearnet", 0.72, 0.22, "teal"],
        ["tor", "Tor", 0.78, 0.39, "coral"],
        ["i2p", "I2P", 0.76, 0.56, "amber"],
        ["gemini", "Gemini", 0.66, 0.72, "green"],
        ["reticulum", "Reticulum", 0.84, 0.72, "coral"]
      ],
      links: [
        ["source", "ampg"],
        ["ampg", "vps"],
        ["vps", "web"],
        ["vps", "tor"],
        ["vps", "i2p"],
        ["vps", "gemini"],
        ["vps", "reticulum"]
      ]
    },
    router: {
      caption: "Behind a router, clearnet may need DNS and port choices; Tor, I2P, and Reticulum can avoid depending on inbound web ports.",
      nodes: [
        ["visitor", "visitor", 0.13, 0.33, "green"],
        ["dns", "DNS/DDNS", 0.3, 0.24, "amber"],
        ["router", "router", 0.45, 0.38, "coral"],
        ["host", "home host", 0.61, 0.38, "teal"],
        ["ampg", "AMPG", 0.76, 0.38, "teal"],
        ["tor", "Tor", 0.64, 0.66, "coral"],
        ["i2p", "I2P", 0.78, 0.66, "amber"],
        ["reticulum", "Reticulum", 0.9, 0.54, "green"]
      ],
      links: [
        ["visitor", "dns"],
        ["dns", "router"],
        ["router", "host"],
        ["host", "ampg"],
        ["ampg", "tor"],
        ["ampg", "i2p"],
        ["ampg", "reticulum"],
        ["visitor", "tor"],
        ["visitor", "i2p"],
        ["visitor", "reticulum"]
      ]
    },
    phone: {
      caption: "A spare Android phone can run Termux packages, AMPG state, and user-space transport services.",
      nodes: [
        ["phone", "Android", 0.24, 0.45, "green"],
        ["pkg", "pkg", 0.43, 0.26, "amber"],
        ["ampg", "AMPG", 0.45, 0.45, "teal"],
        ["state", "state", 0.43, 0.64, "coral"],
        ["services", "services", 0.64, 0.45, "green"],
        ["routes", "routes", 0.82, 0.45, "teal"]
      ],
      links: [
        ["phone", "pkg"],
        ["phone", "ampg"],
        ["phone", "state"],
        ["pkg", "services"],
        ["ampg", "services"],
        ["state", "services"],
        ["services", "routes"]
      ]
    },
    browser: {
      caption: "Fixture manifests let AMPB or another checker verify every route through the expected transport profile.",
      nodes: [
        ["site", "site", 0.17, 0.5, "amber"],
        ["ampg", "AMPG", 0.33, 0.5, "teal"],
        ["manifest", "manifest", 0.5, 0.5, "green"],
        ["ampb", "AMPB", 0.66, 0.5, "coral"],
        ["transport", "transport", 0.82, 0.5, "teal"]
      ],
      links: [
        ["site", "ampg"],
        ["ampg", "manifest"],
        ["manifest", "ampb"],
        ["ampb", "transport"],
        ["transport", "ampb"]
      ]
    }
  };

  const words = ["clearnet", "Tor", "I2P", "Gemini", "IPFS", "Reticulum"];
  let wordIndex = 0;
  let active = "vps";
  let width = 0;
  let height = 0;
  let start = performance.now();

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function nodeMap(topology) {
    return new Map(topology.nodes.map((node) => [node[0], node]));
  }

  function draw(now) {
    const topology = topologies[active];
    const nodes = nodeMap(topology);
    const tick = (now - start) / 1000;
    ctx.clearRect(0, 0, width, height);
    drawField(tick);
    topology.links.forEach((link, index) => drawLink(nodes.get(link[0]), nodes.get(link[1]), tick, index));
    topology.nodes.forEach((node, index) => drawNode(node, tick, index));
    requestAnimationFrame(draw);
  }

  function drawField(tick) {
    ctx.save();
    ctx.globalAlpha = 0.38;
    for (let i = 0; i < 36; i += 1) {
      const x = ((i * 137 + tick * 16) % (width + 120)) - 60;
      const y = ((i * 71 + tick * 9) % (height + 120)) - 60;
      ctx.fillStyle = i % 3 === 0 ? palette.teal : i % 3 === 1 ? palette.amber : palette.green;
      ctx.beginPath();
      ctx.arc(x, y, i % 2 === 0 ? 1.6 : 1, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawLink(from, to, tick, index) {
    if (!from || !to) return;
    const ax = from[2] * width;
    const ay = from[3] * height;
    const bx = to[2] * width;
    const by = to[3] * height;
    ctx.save();
    ctx.strokeStyle = palette.line;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();

    const progress = (tick * 0.22 + index * 0.13) % 1;
    const px = ax + (bx - ax) * progress;
    const py = ay + (by - ay) * progress;
    ctx.fillStyle = index % 2 === 0 ? palette.teal : palette.amber;
    ctx.beginPath();
    ctx.arc(px, py, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawNode(node, tick, index) {
    const [, label, nx, ny, colorKey] = node;
    const x = nx * width;
    const y = ny * height;
    const pulse = Math.sin(tick * 2.2 + index) * 2;
    const color = palette[colorKey] || palette.teal;
    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = 20;
    ctx.fillStyle = "rgba(16, 16, 15, 0.86)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(x - 58, y - 23, 116, 46, 8);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = palette.text;
    ctx.font = "700 13px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, x, y + pulse * 0.25);
    ctx.restore();
  }

  function setTopology(name) {
    if (!topologies[name]) return;
    active = name;
    caption.textContent = topologies[name].caption;
    buttons.forEach((button) => {
      const selected = button.dataset.topology === name;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => setTopology(button.dataset.topology));
  });

  if (signalWord) {
    window.setInterval(() => {
      wordIndex = (wordIndex + 1) % words.length;
      signalWord.textContent = words[wordIndex];
      signalWord.classList.remove("swap");
      void signalWord.offsetWidth;
      signalWord.classList.add("swap");
    }, 1800);
  }

  if (!CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
      this.beginPath();
      this.moveTo(x + r, y);
      this.lineTo(x + w - r, y);
      this.quadraticCurveTo(x + w, y, x + w, y + r);
      this.lineTo(x + w, y + h - r);
      this.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      this.lineTo(x + r, y + h);
      this.quadraticCurveTo(x, y + h, x, y + h - r);
      this.lineTo(x, y + r);
      this.quadraticCurveTo(x, y, x + r, y);
      this.closePath();
    };
  }

  window.addEventListener("resize", resize);
  resize();
  setTopology(active);
  requestAnimationFrame(draw);
})();
