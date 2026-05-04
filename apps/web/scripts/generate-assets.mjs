// Genera assets visuales para producción a partir de los originales en public/.
//
// Outputs:
//   - apps/web/public/favicon.ico        32×32 ICO (PNG embebido, formato moderno post-Vista)
//   - apps/web/app/icon.png              192×192 PNG (Next.js App Router file convention)
//   - apps/web/app/apple-icon.png        180×180 PNG (Next.js App Router file convention)
//   - apps/web/public/og-image.jpg       1200×630 JPG con hero + overlay + logo + claim
//
// Uso: node scripts/generate-assets.mjs   (o:  npm run generate-assets)

import sharp from "sharp";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const PUBLIC_DIR = path.join(ROOT, "public");
const APP_DIR = path.join(ROOT, "app");

const LOGO = path.join(PUBLIC_DIR, "logo-demin.jpg");
const HERO = path.join(PUBLIC_DIR, "obras", "hero-boveda-ladrillo.jpg");
const BG_GREY = "#3D3F40"; // mismo gris sólido de fondo del logo original

async function fileSizeKB(p) {
  const s = await fs.stat(p);
  return (s.size / 1024).toFixed(1) + " KB";
}

// Empaqueta un PNG dentro de un contenedor ICO mínimo. Los navegadores modernos
// (post-Vista) soportan ICO con payload PNG, así no dependemos de png-to-ico.
function pngBufferToIco(pngBuffer, size) {
  const header = Buffer.alloc(6 + 16);
  // ICONDIR (6 bytes)
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type 1 = icon
  header.writeUInt16LE(1, 4); // image count = 1
  // ICONDIRENTRY (16 bytes)
  header.writeUInt8(size >= 256 ? 0 : size, 6); // width (0 == 256)
  header.writeUInt8(size >= 256 ? 0 : size, 7); // height
  header.writeUInt8(0, 8); // palette colors (0 = no palette)
  header.writeUInt8(0, 9); // reserved
  header.writeUInt16LE(1, 10); // color planes
  header.writeUInt16LE(32, 12); // bits per pixel
  header.writeUInt32LE(pngBuffer.length, 14); // payload size
  header.writeUInt32LE(22, 18); // payload offset
  return Buffer.concat([header, pngBuffer]);
}

// ──────────────────────────────────────────────────────────────────────────────
// TAREA 1 — FAVICON
// El logo original (866×866) tiene: símbolo cuadrado en y≈240–390, wordmark
// "DEMIN GROUP" empezando en y≈440. Estrategia:
//   1) extract() ajustado al símbolo (sin tocar el wordmark)
//   2) extend() con el mismo gris para añadir aire alrededor y dejar un cuadrado
//   3) resize() a los tres tamaños finales
// ──────────────────────────────────────────────────────────────────────────────
async function generateFavicons() {
  // Recorte conservador centrado en el símbolo. 160×160 captura el marco cuadrado
  // y su interior con un mínimo margen orgánico; 40px de extend en cada lado da
  // 240×240 finales con aire visual generoso.
  const SYMBOL = { left: 353, top: 235, width: 160, height: 160 };
  const PAD = 40;

  const symbolSquare = await sharp(LOGO)
    .extract(SYMBOL)
    .extend({
      top: PAD,
      bottom: PAD,
      left: PAD,
      right: PAD,
      background: BG_GREY,
    })
    .toBuffer();

  // app/icon.png — 192×192 (Next sirve esto como <link rel="icon">)
  const iconPng = path.join(APP_DIR, "icon.png");
  await sharp(symbolSquare).resize(192, 192).png().toFile(iconPng);

  // app/apple-icon.png — 180×180 (Next sirve esto como <link rel="apple-touch-icon">)
  const appleIconPng = path.join(APP_DIR, "apple-icon.png");
  await sharp(symbolSquare).resize(180, 180).png().toFile(appleIconPng);

  // public/favicon.ico — 32×32 PNG envuelto en contenedor ICO
  const favicon32Png = await sharp(symbolSquare).resize(32, 32).png().toBuffer();
  const icoBuffer = pngBufferToIco(favicon32Png, 32);
  const faviconIco = path.join(PUBLIC_DIR, "favicon.ico");
  await fs.writeFile(faviconIco, icoBuffer);

  // Borrar el favicon.ico por defecto que Next.js scaffold deja en app/, para
  // que la URL /favicon.ico sirva el nuestro desde public/ sin colisión.
  const defaultAppFavicon = path.join(APP_DIR, "favicon.ico");
  try {
    await fs.unlink(defaultAppFavicon);
  } catch (e) {
    if (e.code !== "ENOENT") throw e;
  }

  return [iconPng, appleIconPng, faviconIco];
}

// ──────────────────────────────────────────────────────────────────────────────
// TAREA 2 — OG IMAGE (1200×630)
// Composición de capas:
//   1) hero-boveda-ladrillo.jpg redimensionado en cover a 1200×630
//   2) overlay rectangular negro al 55% de opacidad
//   3) logo cuadrado 200×200 en esquina superior izquierda con margen 60px
//   4) claim "La fase cero de tu reforma" en blanco, ~80px, centrado
// ──────────────────────────────────────────────────────────────────────────────
async function generateOgImage() {
  const W = 1200;
  const H = 630;

  // 1) Base: hero recortado en cover
  const base = await sharp(HERO)
    .resize(W, H, { fit: "cover", position: "center" })
    .toBuffer();

  // 2) Overlay negro 55%. Generado como SVG → sharp lo rasteriza con alpha.
  const overlaySvg = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
       <rect width="${W}" height="${H}" fill="black" fill-opacity="0.55"/>
     </svg>`
  );

  // 3) Logo 200×200 (el original es 866×866 cuadrado, así que mantiene ratio)
  const logo200 = await sharp(LOGO).resize(200, 200, { fit: "cover" }).toBuffer();

  // 4) Texto como SVG. Usamos sans-serif del sistema (Arial/Helvetica), peso bold.
  //    Posicionado con baseline en y=440 → centro vertical-bajo del lienzo.
  const claim = "La fase cero de tu reforma";
  const textSvg = Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
       <style>
         .claim {
           font-family: 'Arial', 'Helvetica', sans-serif;
           font-size: 80px;
           font-weight: 700;
           fill: #ffffff;
           letter-spacing: -1px;
         }
       </style>
       <text x="50%" y="440" text-anchor="middle" class="claim">${claim}</text>
     </svg>`
  );

  const ogPath = path.join(PUBLIC_DIR, "og-image.jpg");
  await sharp(base)
    .composite([
      { input: overlaySvg, top: 0, left: 0 },
      { input: logo200, top: 60, left: 60 },
      { input: textSvg, top: 0, left: 0 },
    ])
    .jpeg({ quality: 85, mozjpeg: true })
    .toFile(ogPath);

  return [ogPath];
}

// ──────────────────────────────────────────────────────────────────────────────
// MAIN
// ──────────────────────────────────────────────────────────────────────────────
async function main() {
  const t0 = Date.now();
  const favicons = await generateFavicons();
  const og = await generateOgImage();
  const all = [...favicons, ...og];

  console.log("\nGenerated assets:");
  for (const p of all) {
    const rel = path.relative(ROOT, p).replace(/\\/g, "/");
    console.log(`  apps/web/${rel}  —  ${await fileSizeKB(p)}`);
  }
  console.log(`\nDone in ${Date.now() - t0} ms`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
