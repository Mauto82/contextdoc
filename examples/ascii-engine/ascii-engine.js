// ASCII 3D engine, from the ψ lab of the MAuToBlog theme, after the "Projection" engine (Mauto82/SPLIT_CORE):
// points in a [-1,1]³ world, an orbiting camera, perspective projection, a z-buffer per character cell
// and a ramp of characters for brightness (lit surfaces) or depth (curves).
const RAMP = ' .:-=+*#%@';
const LEVELS = RAMP.length - 1;

const normalize = (x, y, z) => {
  const l = Math.hypot(x, y, z) || 1;
  return [x / l, y / l, z / l];
};

// light in view space: from the front, top left (the camera looks towards +z)
const [LX, LY, LZ] = normalize(-0.6, 0.45, -0.65);

export class AsciiEngine {
  constructor(screen) {
    this.screen = screen;
    this.yaw = 0.6;
    this.pitch = 0.42;
    this.distance = 4.5;
    this.resize();
  }

  // grid size from the <pre>'s box and the size of one character
  resize() {
    const probe = document.createElement('span');
    probe.textContent = 'M'.repeat(40);
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre';
    this.screen.appendChild(probe);
    const charW = probe.getBoundingClientRect().width / 40;
    probe.remove();
    const cs = getComputedStyle(this.screen);
    const charH = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
    const width = this.screen.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const height = this.screen.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    this.cols = Math.max(20, Math.floor(width / charW));
    this.rows = Math.max(10, Math.floor(height / charH));
    // a cell is taller than wide: horizontal distances take more columns than rows
    this.aspect = charH / charW;
    this.focal = this.distance * Math.min(0.5 * this.rows, 0.45 * this.cols / this.aspect);
    const cells = this.cols * this.rows;
    this.depth = new Float32Array(cells);
    this.level = new Uint8Array(cells);
  }

  begin() {
    this.depth.fill(Infinity);
    this.level.fill(0);
    this.cy = Math.cos(this.yaw);
    this.sy = Math.sin(this.yaw);
    this.cp = Math.cos(this.pitch);
    this.sp = Math.sin(this.pitch);
  }

  // camera rotation: yaw around the vertical axis, then pitch (camera above: the far side rises)
  rotate(x, y, z) {
    const x1 = x * this.cy + z * this.sy;
    const z1 = -x * this.sy + z * this.cy;
    return [x1, y * this.cp + z1 * this.sp, -y * this.sp + z1 * this.cp];
  }

  // a point with brightness b in [0,1]
  plot(x, y, z, b) {
    const [x1, y1, z1] = this.rotate(x, y, z);
    this.put(x1, y1, z1 + this.distance, b);
  }

  put(vx, vy, zc, b) {
    if (zc < 0.2) return;
    const inv = this.focal / zc;
    const col = Math.round(this.cols / 2 + vx * inv * this.aspect);
    const row = Math.round(this.rows / 2 - vy * inv);
    if (col < 0 || col >= this.cols || row < 0 || row >= this.rows) return;
    const i = row * this.cols + col;
    if (zc >= this.depth[i]) return;
    this.depth[i] = zc;
    this.level[i] = 1 + Math.round(Math.min(1, Math.max(0, b)) * (LEVELS - 1));
  }

  // a point lit by its normal (two-sided: a normal facing away is flipped)
  lit(x, y, z, nx, ny, nz) {
    const [x1, y1, z1] = this.rotate(x, y, z);
    let [mx, my, mz] = this.rotate(nx, ny, nz);
    if (mz > 0) { mx = -mx; my = -my; mz = -mz; }
    const lum = (mx * LX + my * LY + mz * LZ) / (Math.hypot(mx, my, mz) || 1);
    this.put(x1, y1, z1 + this.distance, 0.1 + 0.9 * Math.max(0, lum));
  }

  // a point whose brightness says how near it is (curves, trails), scaled by k
  dot(x, y, z, k = 1) {
    const [x1, y1, z1] = this.rotate(x, y, z);
    const near = 1 - (z1 + 1.3) / 2.6;
    this.put(x1, y1, z1 + this.distance, (0.25 + 0.75 * near) * k);
  }

  // height field y = h[i][j] over x, z in [-1,1], h a Float32Array of (n+1)² values
  surface(n, h) {
    const step = 2 / n;
    const w = n + 1;
    for (let i = 0; i <= n; i++) {
      const x = -1 + i * step;
      for (let j = 0; j <= n; j++) {
        const z = -1 + j * step;
        const k = i * w + j;
        const dx = (h[Math.min(i + 1, n) * w + j] - h[Math.max(i - 1, 0) * w + j]) / (2 * step);
        const dz = (h[i * w + Math.min(j + 1, n)] - h[i * w + Math.max(j - 1, 0)]) / (2 * step);
        this.lit(x, h[k], z, -dx, 1, -dz);
      }
    }
  }

  end() {
    const lines = new Array(this.rows);
    const row = new Array(this.cols);
    for (let r = 0; r < this.rows; r++) {
      const base = r * this.cols;
      for (let c = 0; c < this.cols; c++) row[c] = RAMP[this.level[base + c]];
      lines[r] = row.join('');
    }
    this.screen.textContent = lines.join('\n');
  }
}
