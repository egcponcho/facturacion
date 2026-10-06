// Casos de paridad de la detección por texto: lo que la ficha deducía con
// motor.js (detectarFicha + detectarNac, como FichaTecnica) para un corpus de
// nombres de estilo, usos, tallas y composiciones.
// Uso: node scripts/paridad-deteccion.mjs
import { writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

const nombres = new Set(["Men's Antora rain jacket", "Men's Vectiv trail running shoe", 'Borealis backpack 28 L', 'Glacier half-zip fleece', 'Old Skool',
  "W Nuptse down vest", 'Kids Sk8-Hi', 'Baby onesie cotton', 'Mens leather belt', 'Unisex canvas tote', 'Steel toe work boot', 'Womens slide sandal',
  'Hi-vis safety vest', 'Wool blazer', 'Full zip hoodie', 'Bandana', 'Polo shirt', 'Leather gloves', 'Insulated water bottle stainless', 'Rain boots kids',
  'Trucker cap', 'Straw hat', 'Yoga mat', 'Crash pad', 'Headlamp', 'Shoe box corrugated', 'Paper shopping bag', 'Wooden hanger', 'Woven label',
  'Mannequin', 'Liquid chalk', 'Skateboard deck', 'Smart watch gps', 'Watch strap silicone', 'Scrunchie', 'Faux fur throw', 'Hammock', 'Zipper pulls',
  'Keychain metal', 'Sticker pack', 'Dog leash', 'Sleeping bag', 'Self-inflating sleeping pad', 'Pillow', 'Beach towel terry', 'Camp chair padded',
  'Trekking poles', 'Shoe cleaner kit', 'Insoles', 'Laces', 'Trail gaiters', 'Sunglasses', 'Umbrella compact', 'Bracelet leather', 'Tent footprint',
  'Pajama set', 'Boxer briefs', 'Sports bra', 'Board shorts', 'Bib overall', 'Ski suit', 'Wallet', 'Rolling luggage', 'Duffel bag', 'Crossbody bag'])
for (const v of Object.values(M.TIPO_ALIAS)) v.split(/\s+(?=[a-z])/).forEach((w) => w.length > 3 && nombres.add(w))
const USOS = ['', 'for hiking', 'bag worn on the waist to carry climbing chalk', 'school uniform', 'work and industrial use']
const TALLAS = ['', 'S to XL', '0-3 meses', '2T to 5T']
const COMPS = [{}, { exterior: '100% cotton' }, { corte: '100% leather', suela: '100% rubber' }, { material: '100% stainless steel' }]
let i = 0
const casos = []
for (const estilo of nombres) {
  const uso = USOS[i % USOS.length], tallas = TALLAS[(i >> 1) % TALLAS.length], comp = COMPS[(i >> 2) % COMPS.length]
  i++
  const f = { estilo, descArchivo: '', uso, tallas, comp, marca: '' }
  const d = M.detectarFicha({ ...f }, [])
  const tmp = M.detectarNac({ ...f, tipo: d.tipo, estiloCalz: d.estiloCalz, ...Object.fromEntries(M.NAC_IDS.map((k) => [k, undefined])) }, true)
  const out = { ...d }
  for (const k of M.NAC_IDS) if (tmp[k] !== undefined) out[k] = tmp[k]
  if (out.edadNac === undefined && d.edad === 'bebe') out.edadNac = 'bebe'
  delete out.edad; delete out._palabra; delete out.upperMixto
  casos.push({ estilo, uso, tallas, comp, detectado: out })
}
writeFileSync(new URL('../../backend/tests/paridad/deteccion.json', import.meta.url), JSON.stringify({ casos }, null, 0) + '\n')
console.log(casos.length, 'casos de detección')
