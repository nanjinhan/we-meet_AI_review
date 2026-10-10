// T-F6 PWA 아이콘 생성 — 외부 이미지 에셋/캔버스 의존성 없이 PNG를 바이트 단위로 직접 작성한다.
// 디자인: 앱 primary 바이올렛(#7c5cfc) 배경 + 흰색 말풍선(리뷰) 심볼. 실제 로고가 생기면 교체할 자리표시자.
import { createWriteStream, mkdirSync } from "node:fs";
import { deflateSync } from "node:zlib";
import path from "node:path";

const PRIMARY = [0x7c, 0x5c, 0xfc]; // --primary
const WHITE = [0xff, 0xff, 0xff];

function crc32(buf) {
  let c;
  const table = crc32.table ?? (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c;
    }
    return t;
  })());
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, "ascii");
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

/** 심볼: 모서리가 둥근 사각 말풍선(채팅/리뷰) — 중심에 흰 점 3개(로딩/대화 느낌). */
function pixelIsSymbol(x, y, size) {
  const cx = size / 2;
  const cy = size * 0.46;
  const w = size * 0.56;
  const h = size * 0.4;
  const r = size * 0.1;
  const left = cx - w / 2;
  const right = cx + w / 2;
  const top = cy - h / 2;
  const bottom = cy + h / 2;

  // 꼬리(말풍선 하단 삼각형)
  const tailTop = bottom - size * 0.02;
  const tailBottomY = bottom + size * 0.12;
  const tailLeftX = cx - size * 0.05;
  const tailRightX = cx + size * 0.14;
  if (y >= tailTop && y <= tailBottomY && x >= tailLeftX && x <= tailRightX) {
    const t = (y - tailTop) / (tailBottomY - tailTop);
    const lx = tailLeftX + (tailRightX - tailLeftX) * 0.1 * t;
    const rx = tailRightX - (tailRightX - tailLeftX) * 0.75 * t;
    if (x >= lx && x <= rx) return true;
  }

  // 둥근 사각형 본체
  if (x < left || x > right || y < top || y > bottom) return false;
  const inCornerBox =
    (x < left + r && y < top + r) ||
    (x > right - r && y < top + r) ||
    (x < left + r && y > bottom - r) ||
    (x > right - r && y > bottom - r);
  if (!inCornerBox) return true;
  const cornerCx = x < left + r ? left + r : right - r;
  const cornerCy = y < top + r ? top + r : bottom - r;
  return (x - cornerCx) ** 2 + (y - cornerCy) ** 2 <= r * r;
}

/** 본체 안의 세 점(말줄임 "..." 느낌)은 배경색으로 뚫는다. */
function pixelIsDot(x, y, size) {
  const cy = size * 0.46;
  const r = size * 0.035;
  const spacing = size * 0.13;
  const cx = size / 2;
  for (const dx of [-spacing, 0, spacing]) {
    if ((x - (cx + dx)) ** 2 + (y - cy) ** 2 <= r * r) return true;
  }
  return false;
}

function buildPng(size, { maskable = false } = {}) {
  const rowBytes = size * 3;
  const raw = Buffer.alloc((rowBytes + 1) * size);
  // maskable 아이콘은 safe-zone(약 80%)을 고려해 심볼을 약간 축소해 중앙에 둔다.
  const scale = maskable ? 0.8 : 1;
  const offset = (size * (1 - scale)) / 2;

  for (let y = 0; y < size; y++) {
    raw[y * (rowBytes + 1)] = 0; // filter: none
    for (let x = 0; x < size; x++) {
      const sx = (x - offset) / scale;
      const sy = (y - offset) / scale;
      let rgb = PRIMARY;
      if (sx >= 0 && sy >= 0 && sx < size && sy < size) {
        if (pixelIsSymbol(sx, sy, size) && !pixelIsDot(sx, sy, size)) rgb = WHITE;
      }
      const off = y * (rowBytes + 1) + 1 + x * 3;
      raw[off] = rgb[0];
      raw[off + 1] = rgb[1];
      raw[off + 2] = rgb[2];
    }
  }

  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // color type: RGB
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const idat = deflateSync(raw);
  return Buffer.concat([sig, chunk("IHDR", ihdr), chunk("IDAT", idat), chunk("IEND", Buffer.alloc(0))]);
}

const outDir = path.join(import.meta.dirname, "..", "public", "icons");
mkdirSync(outDir, { recursive: true });

const targets = [
  ["icon-192.png", 192, {}],
  ["icon-512.png", 512, {}],
  ["maskable-512.png", 512, { maskable: true }],
  ["apple-touch-icon.png", 180, {}],
];

for (const [name, size, opts] of targets) {
  const buf = buildPng(size, opts);
  createWriteStream(path.join(outDir, name)).end(buf);
  console.log(`wrote ${name} (${buf.length} bytes)`);
}
