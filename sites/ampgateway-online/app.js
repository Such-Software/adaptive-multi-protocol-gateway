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
      caption: "A VPS shape starts with one source tree, renders transport outputs, then hands them to service-specific daemons on the host.",
      nodes: [
        ["source", "source\nsite", 0.11, 0.48, "amber"],
        ["build", "AMPG\nbuild", 0.27, 0.48, "teal"],
        ["outputs", "rendered\noutputs", 0.42, 0.3, "green"],
        ["state", "deploy\nstate", 0.42, 0.62, "amber"],
        ["vps", "VPS\nhost", 0.56, 0.46, "green"],
        ["web", "HTTPS\nnginx", 0.73, 0.23, "teal"],
        ["tor", "Tor\nonion", 0.76, 0.42, "coral"],
        ["i2p", "I2P\ntunnel", 0.73, 0.61, "amber"],
        ["gemini", "Gemini\ncapsule", 0.6, 0.78, "green"],
        ["reticulum", "RNS\nnode", 0.88, 0.73, "coral"]
      ],
      links: [
        ["source", "build"],
        ["build", "outputs", -0.08],
        ["build", "state", 0.08],
        ["outputs", "vps"],
        ["state", "vps"],
        ["vps", "web", -0.08],
        ["vps", "tor"],
        ["vps", "i2p", 0.04],
        ["vps", "gemini", 0.1],
        ["vps", "reticulum", 0.12]
      ]
    },
    router: {
      caption: "Behind a router, clearnet depends on DNS and a chosen inbound path; onion, I2P, and Reticulum routes can publish without exposing normal web ports.",
      nodes: [
        ["visitor", "visitor", 0.1, 0.42, "green"],
        ["dns", "DNS /\nDDNS", 0.25, 0.24, "amber"],
        ["router", "router\nNAT", 0.4, 0.42, "coral"],
        ["host", "home\nhost", 0.55, 0.42, "teal"],
        ["ampg", "AMPG", 0.7, 0.42, "teal"],
        ["clearnet", "port\nforward", 0.55, 0.22, "green"],
        ["onion", "Tor\nonion", 0.68, 0.69, "coral"],
        ["i2p", "I2P\nserver\ntunnel", 0.84, 0.61, "amber"],
        ["rns", "RNS\npeer", 0.88, 0.3, "green"]
      ],
      links: [
        ["visitor", "dns"],
        ["dns", "router"],
        ["router", "host"],
        ["host", "ampg"],
        ["ampg", "clearnet", -0.04],
        ["clearnet", "router"],
        ["ampg", "onion", 0.05],
        ["ampg", "i2p", 0.04],
        ["ampg", "rns", -0.05],
        ["visitor", "onion", 0.16],
        ["visitor", "i2p", 0.12],
        ["visitor", "rns", -0.14]
      ]
    },
    phone: {
      caption: "A spare Android phone can run Termux packages, local AMPG state, and user-space daemons for small always-on sites.",
      nodes: [
        ["phone", "Android\nphone", 0.14, 0.46, "green"],
        ["termux", "Termux\npackages", 0.31, 0.28, "amber"],
        ["state", "AMPG\nstate", 0.31, 0.64, "coral"],
        ["ampg", "AMPG\nbuild", 0.48, 0.46, "teal"],
        ["daemons", "user-space\ndaemons", 0.65, 0.46, "green"],
        ["network", "Wi-Fi /\ncell", 0.79, 0.28, "amber"],
        ["routes", "published\nroutes", 0.86, 0.58, "teal"],
        ["power", "power /\nstorage", 0.5, 0.78, "coral"]
      ],
      links: [
        ["phone", "termux", -0.05],
        ["phone", "state"],
        ["phone", "power", 0.08],
        ["termux", "ampg"],
        ["state", "ampg"],
        ["ampg", "daemons"],
        ["daemons", "network", -0.05],
        ["daemons", "routes", 0.05],
        ["power", "routes", -0.1]
      ]
    },
    browser: {
      caption: "Browser validation consumes AMPG fixture manifests, chooses an adapter, then verifies each route through the intended transport profile.",
      nodes: [
        ["manifest", "fixture\nmanifest", 0.12, 0.43, "amber"],
        ["ampb", "AMPB", 0.29, 0.43, "teal"],
        ["policy", "route\npolicy", 0.45, 0.25, "green"],
        ["adapters", "transport\nadapters", 0.5, 0.53, "coral"],
        ["existing", "existing\ndaemon", 0.67, 0.32, "green"],
        ["managed", "managed\ndaemon", 0.67, 0.64, "amber"],
        ["context", "browser\ncontext", 0.82, 0.47, "teal"],
        ["result", "health\nresult", 0.93, 0.47, "green"]
      ],
      links: [
        ["manifest", "ampb"],
        ["ampb", "policy", -0.08],
        ["ampb", "adapters", 0.06],
        ["policy", "adapters"],
        ["adapters", "existing", -0.08],
        ["adapters", "managed", 0.08],
        ["existing", "context"],
        ["managed", "context"],
        ["context", "result"],
        ["result", "ampb", 0.16]
      ]
    }
  };

  const protocolTopologies = {
    clearnet: {
      caption: "Clearnet splits into a DNS discovery path and an HTTPS request path before the web server reads AMPG output.",
      nodes: [
        ["client", "visitor\nbrowser", 0.11, 0.48, "green"],
        ["resolver", "recursive\nDNS", 0.29, 0.25, "amber"],
        ["auth", "authoritative\nDNS", 0.5, 0.18, "amber"],
        ["ip", "public\naddress", 0.49, 0.42, "teal"],
        ["tls", "TLS\nhandshake", 0.34, 0.66, "green"],
        ["ingress", "HTTPS\ningress", 0.57, 0.62, "teal"],
        ["proxy", "nginx /\nproxy", 0.72, 0.42, "coral"],
        ["output", "AMPG\nclearnet\nfiles", 0.86, 0.56, "teal"],
        ["health", "public\nhealth\ncheck", 0.82, 0.23, "green"]
      ],
      links: [
        ["client", "resolver", -0.1],
        ["resolver", "auth", -0.06],
        ["auth", "ip"],
        ["resolver", "client", 0.1],
        ["client", "tls", 0.08],
        ["tls", "ingress"],
        ["ingress", "proxy"],
        ["proxy", "output", 0.05],
        ["health", "ingress"],
        ["health", "output", 0.05]
      ]
    },
    tor: {
      caption: "Tor onion traffic builds client and service circuits through relays; the rendezvous point joins them without revealing the origin.",
      nodes: [
        ["browser", "Tor\nBrowser", 0.09, 0.5, "green"],
        ["hsdir", "HSDir\nrelays", 0.28, 0.2, "amber"],
        ["descriptor", "onion\nservice\ndescriptor", 0.48, 0.2, "amber"],
        ["guard", "client\nguard", 0.28, 0.48, "teal"],
        ["middle", "middle\nrelay", 0.46, 0.6, "coral"],
        ["rendezvous", "rendezvous\nrelay", 0.62, 0.46, "teal"],
        ["intro", "intro\npoints", 0.68, 0.24, "green"],
        ["service", "onion\nservice", 0.78, 0.52, "coral"],
        ["local", "local\nHTTP", 0.88, 0.36, "teal"],
        ["output", "AMPG\nprivacy\nHTML", 0.88, 0.69, "teal"]
      ],
      links: [
        ["browser", "hsdir", -0.1],
        ["hsdir", "descriptor"],
        ["descriptor", "intro"],
        ["browser", "guard"],
        ["guard", "middle", 0.05],
        ["middle", "rendezvous", 0.05],
        ["intro", "service", 0.08],
        ["service", "rendezvous", -0.1],
        ["service", "local"],
        ["service", "output"]
      ]
    },
    i2p: {
      caption: "I2P uses netDb LeaseSets and one-way tunnels; client outbound tunnels meet server inbound tunnels inside the I2P network.",
      nodes: [
        ["browser", "I2P\nbrowser", 0.09, 0.52, "green"],
        ["address", "b32 /\naddressbook", 0.25, 0.26, "amber"],
        ["floodfill", "floodfill\nnetDb", 0.46, 0.22, "amber"],
        ["leaseset", "LeaseSet", 0.64, 0.24, "green"],
        ["outbound", "client\noutbound\ntunnel", 0.3, 0.6, "teal"],
        ["routers", "I2P\ntransit\nrouters", 0.5, 0.66, "coral"],
        ["inbound", "server\ninbound\ntunnel", 0.7, 0.6, "teal"],
        ["server", "i2pd\nserver\ntunnel", 0.84, 0.42, "coral"],
        ["output", "AMPG\nprivacy\nHTML", 0.9, 0.67, "teal"]
      ],
      links: [
        ["browser", "address", -0.08],
        ["address", "floodfill"],
        ["floodfill", "leaseset"],
        ["leaseset", "server", -0.06],
        ["browser", "outbound", 0.05],
        ["outbound", "routers", 0.04],
        ["routers", "inbound", 0.04],
        ["inbound", "server"],
        ["server", "output", 0.05]
      ]
    },
    gemini: {
      caption: "Gemini is intentionally simple: resolve the capsule, open TLS on 1965, and serve text-first AMPG Gemtext.",
      nodes: [
        ["client", "Gemini\nclient", 0.12, 0.5, "green"],
        ["name", "capsule\nname", 0.28, 0.24, "amber"],
        ["cert", "server\ncertificate", 0.48, 0.2, "green"],
        ["tcp", "TCP\n1965", 0.42, 0.5, "teal"],
        ["daemon", "Gemini\ndaemon", 0.62, 0.5, "coral"],
        ["gemtext", "Gemtext\ntree", 0.78, 0.3, "teal"],
        ["output", "AMPG\nGemtext", 0.86, 0.58, "green"],
        ["links", "capsule\nlinks", 0.62, 0.73, "amber"]
      ],
      links: [
        ["client", "name", -0.07],
        ["name", "tcp"],
        ["client", "tcp"],
        ["cert", "tcp"],
        ["tcp", "daemon"],
        ["daemon", "gemtext", -0.08],
        ["daemon", "output"],
        ["output", "links", 0.07],
        ["links", "client", 0.16]
      ]
    },
    reticulum: {
      caption: "Reticulum routes to destination identities across known paths and peers; it is transport-flexible, not automatically anonymous.",
      nodes: [
        ["client", "RNS\nclient", 0.1, 0.5, "green"],
        ["cache", "path\ncache", 0.28, 0.24, "amber"],
        ["request", "path\nrequest", 0.29, 0.61, "teal"],
        ["mesh", "Reticulum\nmesh\npeers", 0.49, 0.44, "coral"],
        ["transport", "transport\nnode", 0.62, 0.2, "green"],
        ["identity", "destination\nidentity", 0.72, 0.44, "amber"],
        ["nomad", "NomadNet\nnode", 0.84, 0.33, "teal"],
        ["output", "AMPG\nMicron", 0.88, 0.62, "green"]
      ],
      links: [
        ["client", "cache", -0.08],
        ["client", "request", 0.08],
        ["request", "mesh"],
        ["cache", "mesh"],
        ["mesh", "transport", -0.06],
        ["mesh", "identity"],
        ["transport", "identity", 0.06],
        ["identity", "nomad"],
        ["nomad", "output"],
        ["output", "client", 0.16]
      ]
    },
    ipfs: {
      caption: "IPFS-style publishing addresses AMPG output by content hash, then discovers providers and fetches blocks from peers or gateways.",
      nodes: [
        ["browser", "browser\nor gateway", 0.1, 0.5, "green"],
        ["name", "CID /\nIPNS", 0.28, 0.24, "amber"],
        ["dnslink", "DNSLink", 0.27, 0.65, "amber"],
        ["dht", "DHT\nprovider\nrecords", 0.49, 0.44, "coral"],
        ["routing", "peer\nrouting", 0.63, 0.22, "green"],
        ["bitswap", "Bitswap /\nGraphsync", 0.66, 0.58, "teal"],
        ["peers", "IPFS\npeer\ncluster", 0.8, 0.4, "coral"],
        ["blocks", "content\nblocks", 0.89, 0.23, "teal"],
        ["output", "AMPG\nstatic\ntree", 0.9, 0.65, "green"]
      ],
      links: [
        ["browser", "name", -0.08],
        ["browser", "dnslink", 0.08],
        ["name", "dht"],
        ["dnslink", "dht"],
        ["dht", "routing", -0.05],
        ["dht", "bitswap", 0.05],
        ["routing", "peers"],
        ["bitswap", "peers"],
        ["peers", "blocks", -0.05],
        ["peers", "output", 0.05],
        ["output", "browser", 0.16]
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
    const caption = options.captionId ? document.getElementById(options.captionId) : null;
    const buttons = options.buttonSelector ? Array.from(document.querySelectorAll(options.buttonSelector)) : [];
    if (!canvas) return;

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
        drawLink(nodes.get(link[0]), nodes.get(link[1]), tick, index, link[2] || 0);
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

    function drawLink(from, to, tick, index, curveOffset) {
      if (!from || !to) return;
      const fromPosition = nodePosition(from);
      const toPosition = nodePosition(to);
      const ax = fromPosition.x;
      const ay = fromPosition.y;
      const bx = toPosition.x;
      const by = toPosition.y;
      const curve = Number(curveOffset) || 0;
      const cx = (ax + bx) / 2 - (by - ay) * curve;
      const cy = (ay + by) / 2 + (bx - ax) * curve;
      ctx.save();
      ctx.strokeStyle = palette.line;
      ctx.lineWidth = options.lineWidth || 1;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      if (curve) {
        ctx.quadraticCurveTo(cx, cy, bx, by);
      } else {
        ctx.lineTo(bx, by);
      }
      ctx.stroke();

      const progress = (tick * 0.22 + index * 0.13) % 1;
      const inverse = 1 - progress;
      const px = curve
        ? inverse * inverse * ax + 2 * inverse * progress * cx + progress * progress * bx
        : ax + (bx - ax) * progress;
      const py = curve
        ? inverse * inverse * ay + 2 * inverse * progress * cy + progress * progress * by
        : ay + (by - ay) * progress;
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
      if (width < 520) return Math.max(104, Math.min(baseWidth, width * 0.38));
      if (width < 720) return Math.max(104, Math.min(baseWidth, width * 0.28));
      if (width < 980) return Math.max(112, Math.min(baseWidth, width * 0.18));
      return baseWidth;
    }

    function nodePosition(node) {
      if (!options.wrapNodes || width >= 760) {
        return { x: node[2] * width, y: node[3] * height };
      }
      const topology = graphSet[active];
      const index = topology.nodes.findIndex((candidate) => candidate[0] === node[0]);
      const columns = width < 520 ? 2 : 3;
      const rows = Math.max(1, Math.ceil(topology.nodes.length / columns));
      const col = index % columns;
      const row = Math.floor(index / columns);
      const x = (col + 0.5) / columns;
      const y = rows === 1 ? 0.34 : 0.15 + (row / (rows - 1)) * 0.48;
      return { x: x * width, y: y * height };
    }

    function setTopology(name) {
      if (!graphSet[name]) return;
      active = name;
      if (caption) {
        caption.textContent = graphSet[name].caption;
      }
      buttons.forEach((button) => {
        const selected = button.dataset[options.dataKey] === name;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => setTopology(button.dataset[options.dataKey]));
    });

    if (options.autoCycleMs) {
      const names = Object.keys(graphSet);
      window.setInterval(() => {
        const currentIndex = names.indexOf(active);
        setTopology(names[(currentIndex + 1) % names.length]);
      }, options.autoCycleMs);
    }

    window.addEventListener("resize", resize);
    resize();
    setTopology(active);
    requestAnimationFrame(draw);
  }

  function createMapModeTabs() {
    const tabs = Array.from(document.querySelectorAll("[data-map-mode]"));
    const title = document.getElementById("map-stage-title");
    const eyebrow = document.getElementById("map-stage-eyebrow");
    const description = document.getElementById("map-stage-description");
    if (tabs.length === 0) return;

    function setMode(mode) {
      tabs.forEach((tab) => {
        const selected = tab.dataset.mapMode === mode;
        tab.classList.toggle("active", selected);
        tab.setAttribute("aria-selected", selected ? "true" : "false");
        if (selected) {
          title.textContent = tab.dataset.mapTitle;
          eyebrow.textContent = tab.dataset.mapEyebrow;
          description.textContent = tab.dataset.mapDescription;
        }
      });

      document.querySelectorAll(".map-canvas").forEach((canvas) => {
        canvas.classList.toggle(
          "active",
          (mode === "deployment" && canvas.id === "cleanTopologyCanvas") ||
            (mode === "protocol" && canvas.id === "protocolTopologyCanvas")
        );
      });

      document.querySelectorAll("[data-map-controls]").forEach((panel) => {
        const selected = panel.dataset.mapControls === mode;
        panel.hidden = !selected;
        panel.classList.toggle("active", selected);
      });

      window.dispatchEvent(new Event("resize"));
    }

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => setMode(tab.dataset.mapMode));
    });
    setMode("deployment");
  }

  createTopologyMap({
    canvasId: "topologyCanvas",
    initial: "vps",
    autoCycleMs: 4600
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
    shadowBlur: 26,
    wrapNodes: true
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

  createMapModeTabs();

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
