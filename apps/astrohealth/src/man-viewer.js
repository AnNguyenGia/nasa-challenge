import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// BlendSwap "Man" is an illustrative body mesh, not an anatomical data source.
// The GLB is generated from the credited Blender source in dist/assets.
let activeViewer = null;

const markerPositions = {
  neuro: [0, 1.43, 0.26],
  resp: [-0.25, 0.70, 0.32],
  cardio: [0.22, 0.56, 0.34],
  immune: [0, -0.10, 0.26],
  musculoskeletal: [-0.24, -1.02, 0.20],
};

function showFallback(host, message) {
  const status = host.querySelector('#model-loading');
  const image = host.querySelector('.model-fallback');
  host.classList.add('model-unavailable');
  if (status) status.textContent = message;
  if (image) image.hidden = false;
}

function mount(host) {
  activeViewer?.dispose();
  activeViewer = null;
  if (!host) return;

  const canvas = host.querySelector('#man-model-canvas');
  const status = host.querySelector('#model-loading');
  if (!canvas) return;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' });
  } catch (error) {
    console.error('3D renderer unavailable', error);
    showFallback(host, 'Không thể mở WebGL; đang dùng ảnh cơ thể dự phòng.');
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 100);
  const root = new THREE.Group();
  scene.add(root);

  const markers = [...host.querySelectorAll('.body-hotspot')];
  const temp = new THREE.Vector3();
  let disposed = false;
  let frame = 0;
  let yaw = 0;
  let pitch = 0;
  let distance = 7.8;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let model = null;
  const addedEdges = [];

  function resize() {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    const compact = height < 450;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.position.set(0, 0, Math.max(distance, compact ? 9.2 : 7.8, 1.1 / camera.aspect));
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    root.position.y = compact ? 0.4 : 0;
  }

  function placeMarkers() {
    root.updateMatrixWorld(true);
    for (const marker of markers) {
      const position = markerPositions[marker.dataset.organ];
      if (!position) continue;
      temp.set(...position).applyMatrix4(root.matrixWorld).project(camera);
      marker.style.left = `${(temp.x + 1) * 50}%`;
      marker.style.top = `${(1 - temp.y) * 50}%`;
      marker.style.opacity = temp.z > 1 || Math.abs(temp.x) > 1 || Math.abs(temp.y) > 1 ? '0.3' : '1';
    }
  }

  function animate() {
    if (disposed) return;
    frame = requestAnimationFrame(animate);
    if (!host.isConnected || document.hidden) return;
    root.rotation.set(pitch, yaw, 0);
    placeMarkers();
    renderer.render(scene, camera);
  }

  function onPointerDown(event) {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event) {
    if (!dragging) return;
    yaw += (event.clientX - lastX) * 0.008;
    pitch = THREE.MathUtils.clamp(pitch + (event.clientY - lastY) * 0.005, -0.32, 0.32);
    lastX = event.clientX;
    lastY = event.clientY;
  }
  function onPointerUp() { dragging = false; }
  function reset() { yaw = 0; pitch = 0; }

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('dblclick', reset);
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();
  animate();

  const viewer = {
    reset,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('dblclick', reset);
      for (const edge of addedEdges) {
        edge.geometry.dispose();
        edge.material.dispose();
      }
      model?.traverse(object => {
        if (object.isMesh) {
          object.geometry.dispose();
          object.material.dispose();
        }
      });
      renderer.dispose();
    },
  };
  activeViewer = viewer;

  new GLTFLoader().load('assets/man.glb', gltf => {
    if (disposed) return;
    model = gltf.scene;
    let meshes = 0;
    model.traverse(object => {
      if (!object.isMesh) return;
      meshes++;
      object.material = new THREE.MeshBasicMaterial({
        color: 0x91a4ae, transparent: true, opacity: 0.18,
        side: THREE.DoubleSide, depthWrite: false,
      });
      const edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(object.geometry, 0),
        new THREE.LineBasicMaterial({ color: 0xdbe2e5, transparent: true, opacity: 0.68, depthWrite: false }),
      );
      object.add(edge);
      addedEdges.push(edge);
    });
    if (!meshes) {
      showFallback(host, 'Tệp 3D không có lưới cơ thể; đang dùng ảnh dự phòng.');
      return;
    }
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const scale = 3.6 / Math.max(size.y, 0.001);
    model.scale.setScalar(scale);
    model.position.copy(center).multiplyScalar(-scale);
    root.add(model);
    const normalizedWidth = size.x * scale;
    distance = Math.max(7.8, normalizedWidth / (2 * Math.tan(THREE.MathUtils.degToRad(17.5)) * Math.max(camera.aspect, 0.2)) * 1.12);
    resize();
    if (status) status.hidden = true;
    const fallback = host.querySelector('.model-fallback');
    if (fallback) fallback.hidden = true;
    host.classList.remove('model-unavailable');
    host.classList.add('model-ready');
  }, undefined, error => {
    if (disposed) return;
    console.error('Unable to load local Man model', error);
    showFallback(host, 'Không nạp được tệp 3D cục bộ; đang dùng ảnh dự phòng.');
  });
}

window.ManViewer = {
  mount,
  reset() { activeViewer?.reset(); },
};
