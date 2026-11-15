// ============================================================================
// AstroHealth - 3D Holographic Human Anatomy Engine (body3d.js)
// Cockpit viewport, high-density wireframe skeleton & vascular tree,
// 3D beating anatomical heart, bioluminescent green sensor nodes,
// floating gyroscopic hologram floor rings, and futuristic sci-fi HUD overlays.
// ============================================================================
'use strict';

window.Body3D = (function() {
  let animId = null;
  let angleY = 0;
  let angleX = 0.06;
  let dragAngleY = 0;
  let dragAngleX = 0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let lastInteraction = 0;
  let activeOrgan = 'cardio';

  // Stars in deep space background
  const stars = [];
  for (let i = 0; i < 75; i++) {
    stars.push({
      x: (Math.random() - 0.5) * 600,
      y: (Math.random() - 0.5) * 450,
      r: Math.random() * 1.4 + 0.3,
      alpha: Math.random() * 0.7 + 0.3,
      twinkleSpeed: Math.random() * 2 + 1
    });
  }

  // Build 3D Human Anatomy Wireframe Geometry
  const vertices = [];
  const edges = [];
  const vascularLines = [];
  const greenSensorNodes = [];

  function addV(x, y, z, group = 'body') {
    const idx = vertices.length;
    vertices.push({ x, y, z, group });
    return idx;
  }

  function addEdge(i1, i2, group = 'wire') {
    edges.push([i1, i2, group]);
  }

  function addVascular(vFrom, vTo, group = 'vascular') {
    vascularLines.push([vFrom, vTo, group]);
  }

  function addSensorNode(vIdx, label) {
    greenSensorNodes.push({ idx: vIdx, label });
  }

  // 1. Skull & Cranium Dome (Latitudinal concentric contour rings)
  const skullLevels = [
    { y: -188, rx: 8, rz: 10, n: 8 },
    { y: -176, rx: 17, rz: 19, n: 12 },
    { y: -160, rx: 23, rz: 25, n: 16 },
    { y: -144, rx: 24, rz: 26, n: 16 },
    { y: -128, rx: 20, rz: 22, n: 14 },
    { y: -116, rx: 14, rz: 16, n: 10 },
    { y: -106, rx: 9, rz: 12, n: 8 } // Chin & jaw
  ];
  const skullRings = [];
  skullLevels.forEach(lvl => {
    const ring = [];
    for (let i = 0; i < lvl.n; i++) {
      const a = (i / lvl.n) * Math.PI * 2;
      ring.push(addV(Math.cos(a) * lvl.rx, lvl.y, Math.sin(a) * lvl.rz, 'neuro'));
    }
    for (let i = 0; i < lvl.n; i++) {
      addEdge(ring[i], ring[(i + 1) % lvl.n], 'neuro');
    }
    skullRings.push(ring);
  });
  for (let r = 0; r < skullRings.length - 1; r++) {
    const c1 = skullRings[r], c2 = skullRings[r + 1];
    const len = Math.min(c1.length, c2.length);
    for (let i = 0; i < len; i += 2) {
      addEdge(c1[i], c2[Math.floor((i / c1.length) * c2.length)], 'neuro');
    }
  }

  // Facial Profile Contours
  const noseTip = addV(0, -135, 27, 'neuro');
  const chin = addV(0, -106, 15, 'neuro');
  const browCenter = addV(0, -148, 25, 'neuro');
  addEdge(browCenter, noseTip, 'neuro');
  addEdge(noseTip, chin, 'neuro');

  // Head Sensor Nodes
  const lTemple = addV(-18, -155, 12, 'neuro');
  const rTemple = addV(18, -155, 12, 'neuro');
  addSensorNode(lTemple, 'EEG-L');
  addSensorNode(rTemple, 'EEG-R');

  // 2. Neck
  const neckTop = addV(0, -104, 2, 'neuro');
  const neckBase = addV(0, -92, 4, 'musculoskeletal');
  addEdge(neckTop, neckBase, 'musculoskeletal');
  const lCarotid = addV(-10, -96, 6, 'cardio');
  const rCarotid = addV(10, -96, 6, 'cardio');
  addSensorNode(lCarotid, 'CAROTID-L');
  addSensorNode(rCarotid, 'CAROTID-R');

  // 3. Full Spine Column (Vertebrae segments with transverse spurs)
  const spineNodes = [];
  for (let y = -92; y <= 45; y += 9) {
    const s = addV(0, y, -8, 'musculoskeletal');
    spineNodes.push(s);
    const sl = addV(-8, y, -7, 'musculoskeletal');
    const sr = addV(8, y, -7, 'musculoskeletal');
    addEdge(sl, sr, 'musculoskeletal');
    if (spineNodes.length > 1) {
      addEdge(spineNodes[spineNodes.length - 2], s, 'musculoskeletal');
    }
  }

  // 4. Clavicles, Sternum & Ribcage
  const sternumTop = addV(0, -88, 16, 'musculoskeletal');
  const sternumMid = addV(0, -60, 18, 'musculoskeletal');
  const sternumXiph = addV(0, -32, 14, 'musculoskeletal');
  addEdge(sternumTop, sternumMid, 'musculoskeletal');
  addEdge(sternumMid, sternumXiph, 'musculoskeletal');

  const lShoulder = addV(-54, -88, 2, 'musculoskeletal');
  const rShoulder = addV(54, -88, 2, 'musculoskeletal');
  addEdge(sternumTop, lShoulder, 'musculoskeletal');
  addEdge(sternumTop, rShoulder, 'musculoskeletal');
  addSensorNode(lShoulder, 'SHOULDER-L');
  addSensorNode(rShoulder, 'SHOULDER-R');

  // Anatomical Curved Ribs (8 pairs)
  const ribLevels = [
    { y: -82, rx: 32, rz: 18 },
    { y: -74, rx: 40, rz: 22 },
    { y: -66, rx: 44, rz: 24 },
    { y: -58, rx: 45, rz: 24 },
    { y: -50, rx: 44, rz: 23 },
    { y: -42, rx: 41, rz: 21 },
    { y: -34, rx: 36, rz: 18 },
    { y: -26, rx: 30, rz: 15 }
  ];
  ribLevels.forEach((lvl, idx) => {
    const l1 = addV(-lvl.rx * 0.35, lvl.y - 2, -6, 'resp');
    const l2 = addV(-lvl.rx, lvl.y + 1, 0, 'resp');
    const l3 = addV(-lvl.rx * 0.7, lvl.y + 4, lvl.rz * 0.7, 'resp');
    const sPt = addV(0, lvl.y + 4, lvl.rz, 'resp');
    const r1 = addV(lvl.rx * 0.35, lvl.y - 2, -6, 'resp');
    const r2 = addV(lvl.rx, lvl.y + 1, 0, 'resp');
    const r3 = addV(lvl.rx * 0.7, lvl.y + 4, lvl.rz * 0.7, 'resp');

    addEdge(l1, l2, 'resp');
    addEdge(l2, l3, 'resp');
    addEdge(l3, sPt, 'resp');
    addEdge(r1, r2, 'resp');
    addEdge(r2, r3, 'resp');
    addEdge(r3, sPt, 'resp');

    if (idx === 2) {
      addSensorNode(l2, 'PULMO-L');
      addSensorNode(r2, 'PULMO-R');
    }
  });

  // 5. 3D Anatomical Beating Heart
  const heartCenter = addV(-12, -60, 13, 'cardio');
  const hPoints = [
    addV(-8, -68, 14, 'cardio'),
    addV(-18, -68, 14, 'cardio'),
    addV(-22, -60, 11, 'cardio'),
    addV(-14, -48, 12, 'cardio'),
    addV(-6, -60, 12, 'cardio')
  ];
  for (let i = 0; i < hPoints.length; i++) {
    addEdge(heartCenter, hPoints[i], 'cardio');
    addEdge(hPoints[i], hPoints[(i + 1) % hPoints.length], 'cardio');
  }

  // 6. Vascular / Neural Tree (Branching arterial network)
  // Carotid arteries
  addVascular(heartCenter, lCarotid, 'cardio');
  addVascular(heartCenter, rCarotid, 'cardio');
  addVascular(lCarotid, lTemple, 'neuro');
  addVascular(rCarotid, rTemple, 'neuro');

  // Abdominal aorta running down
  const solarPlexus = addV(0, -18, 10, 'cardio');
  addSensorNode(solarPlexus, 'CELIAC');
  addVascular(heartCenter, solarPlexus, 'cardio');

  // 7. Upper Limbs (Arms, Forearms, Hands)
  const lElbow = addV(-68, -35, 4, 'musculoskeletal');
  const lWrist = addV(-78, 18, 8, 'musculoskeletal');
  const lHand = addV(-84, 46, 10, 'musculoskeletal');
  addEdge(lShoulder, lElbow, 'musculoskeletal');
  addEdge(lElbow, lWrist, 'musculoskeletal');
  addEdge(lWrist, lHand, 'musculoskeletal');
  addSensorNode(lElbow, 'ELBOW-L');
  addSensorNode(lWrist, 'WRIST-L');
  addSensorNode(lHand, 'RADIAL-L');

  const rElbow = addV(68, -35, 4, 'musculoskeletal');
  const rWrist = addV(78, 18, 8, 'musculoskeletal');
  const rHand = addV(84, 46, 10, 'musculoskeletal');
  addEdge(rShoulder, rElbow, 'musculoskeletal');
  addEdge(rElbow, rWrist, 'musculoskeletal');
  addEdge(rWrist, rHand, 'musculoskeletal');
  addSensorNode(rElbow, 'ELBOW-R');
  addSensorNode(rWrist, 'WRIST-R');
  addSensorNode(rHand, 'RADIAL-R');

  // Vascular tree to arms
  addVascular(heartCenter, lShoulder, 'cardio');
  addVascular(lShoulder, lElbow, 'cardio');
  addVascular(lElbow, lWrist, 'cardio');
  addVascular(heartCenter, rShoulder, 'cardio');
  addVascular(rShoulder, rElbow, 'cardio');
  addVascular(rElbow, rWrist, 'cardio');

  // 8. Pelvis & Hips
  const pelvisCenter = addV(0, 45, 0, 'immune');
  const lHip = addV(-26, 48, 0, 'immune');
  const rHip = addV(26, 48, 0, 'immune');
  const sacrum = addV(0, 40, -12, 'immune');
  const pubis = addV(0, 52, 12, 'immune');
  addEdge(lHip, pubis, 'immune');
  addEdge(rHip, pubis, 'immune');
  addEdge(lHip, sacrum, 'immune');
  addEdge(rHip, sacrum, 'immune');
  addSensorNode(lHip, 'PELVIS-L');
  addSensorNode(rHip, 'PELVIS-R');

  // Aorta bifurcation into iliac arteries
  addVascular(solarPlexus, lHip, 'cardio');
  addVascular(solarPlexus, rHip, 'cardio');

  // 9. Lower Limbs (Thighs, Knees, Calves, Feet)
  const lKnee = addV(-26, 120, 5, 'musculoskeletal');
  const lAnkle = addV(-22, 190, 0, 'musculoskeletal');
  const lHeel = addV(-22, 202, -8, 'musculoskeletal');
  const lToe = addV(-22, 202, 18, 'musculoskeletal');
  addEdge(lHip, lKnee, 'musculoskeletal');
  addEdge(lKnee, lAnkle, 'musculoskeletal');
  addEdge(lAnkle, lHeel, 'musculoskeletal');
  addEdge(lAnkle, lToe, 'musculoskeletal');
  addEdge(lHeel, lToe, 'musculoskeletal');
  addSensorNode(lKnee, 'KNEE-L');
  addSensorNode(lAnkle, 'ANKLE-L');

  const rKnee = addV(26, 120, 5, 'musculoskeletal');
  const rAnkle = addV(22, 190, 0, 'musculoskeletal');
  const rHeel = addV(22, 202, -8, 'musculoskeletal');
  const rToe = addV(22, 202, 18, 'musculoskeletal');
  addEdge(rHip, rKnee, 'musculoskeletal');
  addEdge(rKnee, rAnkle, 'musculoskeletal');
  addEdge(rAnkle, rHeel, 'musculoskeletal');
  addEdge(rAnkle, rToe, 'musculoskeletal');
  addEdge(rHeel, rToe, 'musculoskeletal');
  addSensorNode(rKnee, 'KNEE-R');
  addSensorNode(rAnkle, 'ANKLE-R');

  // Femoral vascular network down legs
  addVascular(lHip, lKnee, 'cardio');
  addVascular(lKnee, lAnkle, 'cardio');
  addVascular(rHip, rKnee, 'cardio');
  addVascular(rKnee, rAnkle, 'cardio');

  // Multi-tier levitating hologram floor rings (matching the image pedestal)
  const holoFloorTiers = [
    { y: 165, r: 100, alpha: 0.65, dash: [4, 4], rotSpeed: 0.8 },
    { y: 178, r: 88, alpha: 0.55, dash: [], rotSpeed: -1.2 },
    { y: 192, r: 76, alpha: 0.45, dash: [2, 6], rotSpeed: 0.6 },
    { y: 205, r: 62, alpha: 0.35, dash: [], rotSpeed: -0.9 },
    { y: 218, r: 110, alpha: 0.75, dash: [], isBase: true } // Base metallic pedestal
  ];

  // Mouse & Touch Drag Listeners
  function attachEvents(canvas) {
    canvas.onmousedown = e => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      lastInteraction = Date.now();
    };

    window.onmousemove = e => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      dragAngleY += dx * 0.015;
      dragAngleX = Math.max(-0.4, Math.min(0.4, dragAngleX + dy * 0.01));
      startX = e.clientX;
      startY = e.clientY;
      lastInteraction = Date.now();
    };

    window.onmouseup = () => { isDragging = false; };

    canvas.ondblclick = () => {
      dragAngleY = 0;
      dragAngleX = 0;
    };

    canvas.ontouchstart = e => {
      if (e.touches && e.touches.length === 1) {
        isDragging = true;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        lastInteraction = Date.now();
      }
    };

    canvas.ontouchmove = e => {
      if (!isDragging || !e.touches || e.touches.length !== 1) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      dragAngleY += dx * 0.015;
      dragAngleX = Math.max(-0.4, Math.min(0.4, dragAngleX + dy * 0.01));
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      lastInteraction = Date.now();
    };

    canvas.ontouchend = () => { isDragging = false; };
  }

  let startTime = Date.now();

  function renderLoop() {
    animId = requestAnimationFrame(renderLoop);
    const canvas = document.querySelector('#body3d');
    if (!canvas || !canvas.getContext) return;

    if (!canvas._hasEvents) {
      attachEvents(canvas);
      canvas._hasEvents = true;
    }

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = rect.width || 340;
    const h = rect.height || 480;

    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2 - 12;
    const now = Date.now();
    const elapsed = (now - startTime) / 1000;

    // Smooth auto-oscillation ("xoay đi xoay lại") left/right ~35°
    if (!isDragging && now - lastInteraction > 1200) {
      angleY = Math.sin(elapsed * 1.1) * 0.65 + dragAngleY;
      angleX = 0.06 + dragAngleX;
    } else {
      angleY = dragAngleY;
      angleX = 0.06 + dragAngleX;
    }

    // =========================================================================
    // LAYER 1: Deep Space Cosmic Void & Stars Backdrop
    // =========================================================================
    ctx.fillStyle = '#070a0f';
    ctx.fillRect(0, 0, w, h);

    // Stars
    stars.forEach(s => {
      const alpha = s.alpha * (0.6 + 0.4 * Math.sin(elapsed * s.twinkleSpeed));
      ctx.fillStyle = `rgba(220, 235, 255, ${alpha})`;
      ctx.beginPath();
      ctx.arc(cx + s.x * (w / 600), cy + s.y * (h / 450), s.r, 0, Math.PI * 2);
      ctx.fill();
    });

    // Cockpit Window Frame Canopy (Panoramic sci-fi bridge struts)
    ctx.save();
    ctx.strokeStyle = 'rgba(38, 48, 60, 0.7)';
    ctx.lineWidth = 1.5;

    // Left canopy window arch
    ctx.beginPath();
    ctx.moveTo(0, 40);
    ctx.lineTo(w * 0.22, 60);
    ctx.lineTo(w * 0.22, h * 0.75);
    ctx.lineTo(0, h * 0.85);
    ctx.stroke();

    // Right canopy window arch
    ctx.beginPath();
    ctx.moveTo(w, 40);
    ctx.lineTo(w * 0.78, 60);
    ctx.lineTo(w * 0.78, h * 0.75);
    ctx.lineTo(w, h * 0.85);
    ctx.stroke();

    // Cockpit Pilot Chairs silhouette (Dark ergonomic flight seats)
    ctx.fillStyle = 'rgba(16, 20, 26, 0.85)';
    // Left chair
    ctx.fillRect(w * 0.18, h * 0.42, w * 0.12, h * 0.28);
    // Right chair
    ctx.fillRect(w * 0.70, h * 0.42, w * 0.12, h * 0.28);
    ctx.restore();

    // Perspective 3D Projection
    const cosY = Math.cos(angleY);
    const sinY = Math.sin(angleY);
    const cosX = Math.cos(angleX);
    const sinX = Math.sin(angleX);

    function project(v) {
      const x1 = v.x * cosY + v.z * sinY;
      const z1 = -v.x * sinY + v.z * cosY;
      const y2 = v.y * cosX - z1 * sinX;
      const z2 = v.y * sinX + z1 * cosX;
      const fov = 350;
      const scale = fov / (fov + z2 + 80);
      return {
        px: cx + x1 * scale,
        py: cy + y2 * scale,
        z: z2,
        scale
      };
    }

    // =========================================================================
    // LAYER 2: Floating Gyroscopic Hologram Floor Rings & Pedestal
    // =========================================================================
    ctx.save();
    holoFloorTiers.forEach(tier => {
      ctx.beginPath();
      const numPts = 36;
      for (let i = 0; i <= numPts; i++) {
        const a = (i / numPts) * Math.PI * 2;
        const pt = project({ x: Math.cos(a) * tier.r, y: tier.y, z: Math.sin(a) * tier.r });
        if (i === 0) ctx.moveTo(pt.px, pt.py);
        else ctx.lineTo(pt.px, pt.py);
      }
      ctx.strokeStyle = tier.isBase ? 'rgba(180, 200, 220, 0.8)' : `rgba(230, 245, 255, ${tier.alpha})`;
      ctx.lineWidth = tier.isBase ? 2.5 : 1.2;
      ctx.setLineDash(tier.dash);
      ctx.stroke();

      // Rotating radial tick marks on rings
      if (!tier.isBase) {
        ctx.setLineDash([]);
        for (let t = 0; t < 12; t++) {
          const a = (t / 12) * Math.PI * 2 + (elapsed * tier.rotSpeed);
          const p1 = project({ x: Math.cos(a) * (tier.r - 4), y: tier.y, z: Math.sin(a) * (tier.r - 4) });
          const p2 = project({ x: Math.cos(a) * (tier.r + 4), y: tier.y, z: Math.sin(a) * (tier.r + 4) });
          ctx.beginPath();
          ctx.moveTo(p1.px, p1.py);
          ctx.lineTo(p2.px, p2.py);
          ctx.strokeStyle = `rgba(230, 245, 255, ${tier.alpha * 0.9})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    });
    ctx.restore();

    // =========================================================================
    // LAYER 3: 3D Hologram Human Skeleton & Vascular Network
    // =========================================================================
    const proj = vertices.map(project);

    // 1. Structural Wireframe Edges (Skull, Spine, Ribs, Bones)
    edges.forEach(([i1, i2, group]) => {
      const p1 = proj[i1];
      const p2 = proj[i2];
      const avgZ = (p1.z + p2.z) / 2;
      const alpha = Math.max(0.25, Math.min(0.95, (avgZ + 70) / 140));

      ctx.beginPath();
      ctx.moveTo(p1.px, p1.py);
      ctx.lineTo(p2.px, p2.py);

      let strokeColor = `rgba(220, 235, 250, ${alpha * 0.75})`;
      let lineWidth = 0.9;

      if (group === activeOrgan) {
        strokeColor = group === 'cardio' ? `rgba(255, 90, 120, ${alpha * 1.5})` :
                      group === 'neuro' ? `rgba(130, 210, 240, ${alpha * 1.5})` :
                      group === 'resp' ? `rgba(120, 220, 160, ${alpha * 1.5})` :
                      `rgba(240, 190, 70, ${alpha * 1.5})`;
        lineWidth = 1.6;
      }

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    });

    // 2. Glowing Vascular / Circulatory Network (Branching vessels)
    ctx.save();
    vascularLines.forEach(([i1, i2, group]) => {
      const p1 = proj[i1];
      const p2 = proj[i2];
      const avgZ = (p1.z + p2.z) / 2;
      const alpha = Math.max(0.3, Math.min(0.95, (avgZ + 60) / 120));

      ctx.beginPath();
      ctx.moveTo(p1.px, p1.py);
      ctx.lineTo(p2.px, p2.py);
      ctx.strokeStyle = `rgba(180, 225, 255, ${alpha * 0.9})`;
      ctx.lineWidth = 1.3;
      ctx.stroke();
    });
    ctx.restore();

    // 3. 3D Anatomical Beating Heart
    const heartProj = proj[heartCenter];
    const heartPulse = (Math.sin(elapsed * 8.0) + 1) / 2;
    const heartRadius = (5.5 + heartPulse * 3.8) * heartProj.scale;

    ctx.save();
    // Outer systolic glow aura
    ctx.beginPath();
    ctx.arc(heartProj.px, heartProj.py, heartRadius * 2.5, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 40, 80, 0.22)';
    ctx.fill();

    // Inner glowing heart mass
    ctx.beginPath();
    ctx.arc(heartProj.px, heartProj.py, heartRadius, 0, Math.PI * 2);
    ctx.fillStyle = '#ff2b56';
    ctx.shadowColor = '#ff2b56';
    ctx.shadowBlur = 12;
    ctx.fill();
    ctx.restore();

    // 4. Bioluminescent Green Sensor Nodes (Matching the reference image!)
    greenSensorNodes.forEach(node => {
      const p = proj[node.idx];
      const nodePulse = (Math.sin(elapsed * 4.5 + node.idx) + 1) / 2;
      const nodeR = (2.2 + nodePulse * 1.2) * p.scale;

      ctx.save();
      // Glowing green halo
      ctx.beginPath();
      ctx.arc(p.px, p.py, nodeR * 3.2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(57, 255, 120, 0.25)';
      ctx.fill();

      // Bright neon green node core
      ctx.beginPath();
      ctx.arc(p.px, p.py, nodeR, 0, Math.PI * 2);
      ctx.fillStyle = '#4ade80';
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.restore();
    });

    // =========================================================================
    // LAYER 4: Futuristic Sci-Fi Cockpit HUD Overlays (Matching reference image)
    // =========================================================================
    ctx.save();
    ctx.font = "9px 'Times New Roman', Times, serif";

    // 1. TOP-LEFT: Circular Biometric Radar Reticle
    const reticleX = 48;
    const reticleY = 48;
    const reticleR = 26;

    // Concentric rings
    ctx.strokeStyle = 'rgba(200, 225, 245, 0.75)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(reticleX, reticleY, reticleR, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = 'rgba(200, 225, 245, 0.35)';
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.arc(reticleX, reticleY, reticleR * 0.65, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Rotating reticle tick
    const rAngle = elapsed * 1.5;
    ctx.beginPath();
    ctx.moveTo(reticleX + Math.cos(rAngle) * (reticleR - 5), reticleY + Math.sin(rAngle) * (reticleR - 5));
    ctx.lineTo(reticleX + Math.cos(rAngle) * (reticleR + 3), reticleY + Math.sin(rAngle) * (reticleR + 3));
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Mini human silhouette inside reticle
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(reticleX, reticleY - 8, 3, 0, Math.PI * 2); // head
    ctx.moveTo(reticleX, reticleY - 5); ctx.lineTo(reticleX, reticleY + 4); // torso
    ctx.moveTo(reticleX - 5, reticleY - 2); ctx.lineTo(reticleX + 5, reticleY - 2); // arms
    ctx.moveTo(reticleX, reticleY + 4); ctx.lineTo(reticleX - 4, reticleY + 12); // left leg
    ctx.moveTo(reticleX, reticleY + 4); ctx.lineTo(reticleX + 4, reticleY + 12); // right leg
    ctx.stroke();

    // Text readouts next to reticle
    ctx.fillStyle = '#ffffff';
    ctx.fillText('30.3', reticleX + 34, reticleY - 10);
    ctx.fillStyle = 'rgba(180, 200, 220, 0.8)';
    ctx.fillText('97.1', reticleX + 34, reticleY + 4);
    ctx.fillText('SYSTEM HUD', reticleX - 24, reticleY + reticleR + 14);

    // 2. MID-LEFT: Vertical Altitude / Pressure Bar Gauge
    const barX = 18;
    const barYTop = 130;
    const barH = 100;
    ctx.strokeStyle = 'rgba(180, 200, 220, 0.5)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(barX, barYTop);
    ctx.lineTo(barX, barYTop + barH);
    ctx.stroke();

    const barMarks = ['250K', '200K', '150M', '100M'];
    barMarks.forEach((m, idx) => {
      const my = barYTop + (idx / 3) * barH;
      ctx.beginPath();
      ctx.moveTo(barX - 4, my);
      ctx.lineTo(barX + 4, my);
      ctx.stroke();
      ctx.fillStyle = 'rgba(180, 200, 220, 0.7)';
      ctx.fillText(m, barX + 8, my + 3);
    });

    // Moving level indicator on bar
    const barLevel = barYTop + ((Math.sin(elapsed * 0.8) + 1) / 2) * barH;
    ctx.fillStyle = '#4ade80';
    ctx.fillRect(barX - 2, barLevel - 2, 5, 5);

    // 3. BOTTOM-LEFT: Diagnostics Matrix Icons Grid
    const diagX = 14;
    const diagY = 275;
    ctx.strokeStyle = 'rgba(180, 200, 220, 0.4)';
    ctx.lineWidth = 0.8;
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        ctx.strokeRect(diagX + c * 13, diagY + r * 13, 11, 11);
      }
    }
    ctx.fillStyle = '#ffffff';
    ctx.fillText('DIAGNOSTICS', diagX, diagY + 48);
    ctx.fillStyle = 'rgba(180, 200, 220, 0.8)';
    ctx.fillText('HEART: 80 BPM', diagX, diagY + 59);
    ctx.fillText('NOMINAL', diagX, diagY + 70);

    // 4. TOP-RIGHT: Diagnostics Card & Live Mini Sparkline
    const trX = w - 95;
    const trY = 22;
    ctx.fillStyle = '#ffffff';
    ctx.fillText('DIAGNOSTICS', trX, trY);

    ctx.fillStyle = 'rgba(180, 200, 220, 0.85)';
    ctx.fillText('✚ OVER 10.7 MGN', trX, trY + 14);
    ctx.fillText('♡ NEURAL 25 LBGH', trX, trY + 26);
    ctx.fillText('⚕ VITAL 65 KRN', trX, trY + 38);
    ctx.fillText('✚ WEIGHT 76.2 KG', trX, trY + 50);

    // Mini sparkline graph
    ctx.strokeStyle = '#4ade80';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < 40; i++) {
      const gx = trX + (i / 40) * 80;
      const gy = (trY + 68) + Math.sin(elapsed * 4 + i * 0.4) * 5;
      if (i === 0) ctx.moveTo(gx, gy);
      else ctx.lineTo(gx, gy);
    }
    ctx.stroke();

    // 5. BOTTOM-RIGHT: Biometric Waveform Card
    const brX = w - 105;
    const brY = h - 68;
    ctx.strokeStyle = 'rgba(180, 200, 220, 0.45)';
    ctx.strokeRect(brX - 6, brY - 14, 100, 68);

    ctx.fillStyle = '#ffffff';
    ctx.fillText('BIOMETRIC', brX, brY);

    // Mini ECG wave
    ctx.strokeStyle = '#ff2b56';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    for (let i = 0; i < 35; i++) {
      const wx = brX + (i / 35) * 85;
      let wy = brY + 14;
      const phase = (i + Math.floor(elapsed * 18)) % 25;
      if (phase === 8) wy -= 12;
      else if (phase === 10) wy += 6;
      if (i === 0) ctx.moveTo(wx, wy);
      else ctx.lineTo(wx, wy);
    }
    ctx.stroke();

    ctx.fillStyle = 'rgba(180, 200, 220, 0.8)';
    ctx.fillText('RED-400 // MSGIT', brX, brY + 34);
    ctx.fillText('09:41:22 UTC', brX, brY + 45);

    ctx.restore();
  }

  // Start animation loop
  if (typeof requestAnimationFrame !== 'undefined') {
    requestAnimationFrame(renderLoop);
  }

  return {
    setOrgan(organ) {
      activeOrgan = organ;
    },
    getOrgan() {
      return activeOrgan;
    }
  };
})();
