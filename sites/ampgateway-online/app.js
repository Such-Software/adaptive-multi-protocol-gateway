(function () {
  const signalWord = document.getElementById("signalWord");

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

  const protocolTopologies = {
    clearnet: {
      caption: "Clearnet requests resolve DNS, reach HTTPS ingress, and read AMPG clearnet output.",
      nodes: [
        ["browser", "Visitor\nbrowser", 0.12, 0.44, "green"],
        ["dns", "DNS", 0.31, 0.32, "amber"],
        ["ingress", "HTTPS\ningress", 0.5, 0.44, "teal"],
        ["server", "web\nserver", 0.69, 0.32, "coral"],
        ["output", "AMPG\nclearnet", 0.88, 0.44, "teal"]
      ],
      links: [
        ["browser", "dns"],
        ["dns", "ingress"],
        ["ingress", "server"],
        ["server", "output"]
      ]
    },
    tor: {
      caption: "Tor clients use onion-service descriptors and circuits before the local hidden service reaches AMPG privacy HTML.",
      nodes: [
        ["browser", "Tor\nBrowser", 0.12, 0.44, "green"],
        ["descriptor", "onion\nservice\ndescriptor", 0.31, 0.32, "amber"],
        ["circuits", "Tor\ncircuits", 0.5, 0.44, "coral"],
        ["service", "onion\nservice", 0.69, 0.32, "teal"],
        ["output", "AMPG\nprivacy\nHTML", 0.88, 0.44, "teal"]
      ],
      links: [
        ["browser", "descriptor"],
        ["descriptor", "circuits"],
        ["circuits", "service"],
        ["service", "output"]
      ]
    },
    i2p: {
      caption: "I2P clients resolve a b32 destination, fetch routing data, and traverse tunnels to the server tunnel.",
      nodes: [
        ["browser", "I2P\nbrowser", 0.12, 0.44, "green"],
        ["b32", "b32\ndestination", 0.31, 0.32, "amber"],
        ["leaseset", "LeaseSet\nlookup", 0.5, 0.44, "coral"],
        ["tunnel", "I2P\nserver\ntunnel", 0.69, 0.32, "teal"],
        ["output", "AMPG\nprivacy\nHTML", 0.88, 0.44, "teal"]
      ],
      links: [
        ["browser", "b32"],
        ["b32", "leaseset"],
        ["leaseset", "tunnel"],
        ["tunnel", "output"]
      ]
    },
    gemini: {
      caption: "Gemini clients open a TLS capsule request and receive AMPG-rendered Gemtext.",
      nodes: [
        ["client", "Gemini\nclient", 0.12, 0.44, "green"],
        ["address", "capsule\naddress", 0.31, 0.32, "amber"],
        ["tls", "TLS\nrequest", 0.5, 0.44, "teal"],
        ["daemon", "Gemini\ndaemon", 0.69, 0.32, "coral"],
        ["output", "AMPG\nGemtext", 0.88, 0.44, "teal"]
      ],
      links: [
        ["client", "address"],
        ["address", "tls"],
        ["tls", "daemon"],
        ["daemon", "output"]
      ]
    },
    reticulum: {
      caption: "Reticulum clients route to a destination hash; NomadNet-style nodes can serve compact AMPG Micron output.",
      nodes: [
        ["client", "RNS\nclient", 0.12, 0.44, "green"],
        ["path", "path\ndiscovery", 0.31, 0.32, "amber"],
        ["mesh", "Reticulum\nmesh", 0.5, 0.44, "coral"],
        ["node", "NomadNet\nnode", 0.69, 0.32, "teal"],
        ["output", "AMPG\nMicron", 0.88, 0.44, "teal"]
      ],
      links: [
        ["client", "path"],
        ["path", "mesh"],
        ["mesh", "node"],
        ["node", "output"]
      ]
    },
    ipfs: {
      caption: "IPFS-style publishing addresses content by CID or IPNS and distributes AMPG static output through peers or gateways.",
      nodes: [
        ["browser", "browser\nor gateway", 0.12, 0.44, "green"],
        ["name", "CID\nor IPNS", 0.31, 0.32, "amber"],
        ["routing", "DHT\nproviders", 0.5, 0.44, "coral"],
        ["peers", "IPFS\npeers", 0.69, 0.32, "teal"],
        ["output", "AMPG\nstatic\ntree", 0.88, 0.44, "teal"]
      ],
      links: [
        ["browser", "name"],
        ["name", "routing"],
        ["routing", "peers"],
        ["peers", "output"]
      ]
    }
  };

  if (window.CanvasRenderingContext2D && !CanvasRenderingContext2D.prototype.roundRect) {
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

  function createTopologyMap(options) {
    const graphSet = options.graphSet || topologies;
    const canvas = document.getElementById(options.canvasId);
    const caption = document.getElementById(options.captionId);
    const buttons = Array.from(document.querySelectorAll(options.buttonSelector));
    if (!canvas || !caption || buttons.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let active = options.initial || "vps";
    let width = 0;
    let height = 0;
    const start = performance.now();

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
      const topology = graphSet[active];
      const nodes = nodeMap(topology);
      const tick = (now - start) / 1000;
      ctx.clearRect(0, 0, width, height);
      drawField(tick);
      topology.links.forEach((link, index) => {
        drawLink(nodes.get(link[0]), nodes.get(link[1]), tick, index);
      });
      topology.nodes.forEach((node, index) => drawNode(node, tick, index));
      requestAnimationFrame(draw);
    }

    function drawField(tick) {
      ctx.save();
      ctx.globalAlpha = options.fieldAlpha || 0.38;
      const dotCount = options.dotCount || 36;
      for (let i = 0; i < dotCount; i += 1) {
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
      const fromPosition = nodePosition(from);
      const toPosition = nodePosition(to);
      const ax = fromPosition.x;
      const ay = fromPosition.y;
      const bx = toPosition.x;
      const by = toPosition.y;
      ctx.save();
      ctx.strokeStyle = palette.line;
      ctx.lineWidth = options.lineWidth || 1;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();

      const progress = (tick * 0.22 + index * 0.13) % 1;
      const px = ax + (bx - ax) * progress;
      const py = ay + (by - ay) * progress;
      ctx.fillStyle = index % 2 === 0 ? palette.teal : palette.amber;
      ctx.beginPath();
      ctx.arc(px, py, options.packetRadius || 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    function drawNode(node, tick, index) {
      const [, label, nx, ny, colorKey] = node;
      const position = nodePosition(node);
      const x = position.x;
      const y = position.y;
      const lines = String(label).split("\n");
      const boxWidth = responsiveNodeWidth(options.nodeWidth || 116);
      const lineHeight = options.lineHeight || 15;
      const boxHeight = Math.max(options.nodeHeight || 46, lines.length * lineHeight + 22);
      const pulse = Math.sin(tick * 2.2 + index) * 2;
      const color = palette[colorKey] || palette.teal;
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = options.shadowBlur || 20;
      ctx.fillStyle = "rgba(16, 16, 15, 0.86)";
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(x - boxWidth / 2, y - boxHeight / 2, boxWidth, boxHeight, 8);
      ctx.fill();
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = palette.text;
      ctx.font = `${options.fontWeight || 700} ${options.fontSize || 13}px system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const firstLineY = y - ((lines.length - 1) * lineHeight) / 2;
      lines.forEach((line, lineIndex) => {
        ctx.fillText(line, x, firstLineY + lineIndex * lineHeight + pulse * 0.25);
      });
      ctx.restore();
    }

    function responsiveNodeWidth(baseWidth) {
      if (width < 720) return Math.max(86, Math.min(baseWidth, width * 0.24));
      if (width < 980) return Math.max(112, Math.min(baseWidth, width * 0.17));
      return baseWidth;
    }

    function nodePosition(node) {
      if (!options.wrapNodes || width >= 760) {
        return { x: node[2] * width, y: node[3] * height };
      }
      const topology = graphSet[active];
      const index = topology.nodes.findIndex((candidate) => candidate[0] === node[0]);
      const wrapped = [
        [0.18, 0.28],
        [0.5, 0.28],
        [0.82, 0.28],
        [0.34, 0.55],
        [0.66, 0.55],
        [0.5, 0.76]
      ][index] || [node[2], node[3]];
      return { x: wrapped[0] * width, y: wrapped[1] * height };
    }

    function setTopology(name) {
      if (!graphSet[name]) return;
      active = name;
      caption.textContent = graphSet[name].caption;
      buttons.forEach((button) => {
        const selected = button.dataset[options.dataKey] === name;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => setTopology(button.dataset[options.dataKey]));
    });

    window.addEventListener("resize", resize);
    resize();
    setTopology(active);
    requestAnimationFrame(draw);
  }

  createTopologyMap({
    canvasId: "topologyCanvas",
    captionId: "topologyCaption",
    buttonSelector: "[data-topology]",
    dataKey: "topology",
    initial: "vps"
  });

  createTopologyMap({
    canvasId: "cleanTopologyCanvas",
    captionId: "cleanTopologyCaption",
    buttonSelector: "[data-clean-topology]",
    dataKey: "cleanTopology",
    initial: "vps",
    dotCount: 70,
    fieldAlpha: 0.5,
    lineWidth: 1.4,
    packetRadius: 4.5,
    nodeWidth: 144,
    nodeHeight: 54,
    fontSize: 15,
    fontWeight: 800,
    shadowBlur: 26
  });

  createTopologyMap({
    canvasId: "protocolTopologyCanvas",
    captionId: "protocolTopologyCaption",
    buttonSelector: "[data-protocol-topology]",
    dataKey: "protocolTopology",
    initial: "clearnet",
    graphSet: protocolTopologies,
    dotCount: 65,
    fieldAlpha: 0.48,
    lineWidth: 1.5,
    packetRadius: 4.5,
    nodeWidth: 138,
    nodeHeight: 58,
    fontSize: 14,
    lineHeight: 14,
    fontWeight: 800,
    shadowBlur: 24,
    wrapNodes: true
  });

  if (signalWord) {
    const words = ["clearnet", "Tor", "I2P", "Gemini", "IPFS", "Reticulum"];
    let wordIndex = 0;
    window.setInterval(() => {
      wordIndex = (wordIndex + 1) % words.length;
      signalWord.textContent = words[wordIndex];
      signalWord.classList.remove("swap");
      void signalWord.offsetWidth;
      signalWord.classList.add("swap");
    }, 1800);
  }
})();
