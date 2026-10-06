// Casos de paridad de la lectura de composiciones: ejecuta motor.js sobre un
// corpus (composiciones del seed y casos difíciles: errores de dedo, números
// sin %, etiquetas, sinónimos) y guarda lo que devuelve para que
// backend/tests/test_composicion.py compare con app/services/composicion.py.
// Uso: node scripts/paridad-composicion.mjs
import { writeFileSync } from 'node:fs'
import * as M from '../src/clasificacion/motor.js'

const CORPUS = [
  '100% nylon', '100% polyester', '80% textile, 20% synthetic', '100% rubber', '65% canvas, 35% suede', '100% canvas', '100% cotton',
  '60% cotton 40% polyester', '50% polyester 50% viscose', '100% leather', '100% polyurethane', '100% paper', '100% wood', '100% steel', '100% cork',
  'shell: 100% nylon; lining: 100% polyester; fill: 90% down 10% feather', 'Exterior: 100% poliéster, forro: 100% algodón',
  '60 cotton 40 polyester', '60/40 cotton polyester', 'cotton 60% polyester 40%', '95% algodon 5% elastano', '70% poliestr 30% algodn',
  'synthetic leather', 'faux suede upper with mesh', 'leather and textile', 'PU leather 70%, mesh 30%', 'full grain leather', 'EVA', 'phylon / rubber',
  'gum rubber outsole', 'vaqueta', 'nobuk', 'microfiber', 'neoprene 100%', '100% neopreno', 'stainless steel 18/8', 'aluminum', 'tritan plastic', 'BPA free plastic',
  'corrugated cardboard', 'kraft paper', 'card stock', 'straw', 'paja toquilla', 'zinc alloy', 'brass', 'silicone', 'wood and metal', 'glass',
  '100% acrylic', 'merino wool 100%', '100% silk', '55% linen 45% cotton', '100% lyocell', 'rayon 100', 'polyamide 80% elastane 20%',
  '40% wool 30% cotton 30% polyester', '50% cotton 50% polyester', '33% cotton 33% wool 34% acrylic', '100 % algodón orgánico', 'recycled polyester',
  'body: 100% cotton; rib: 95% cotton 5% spandex', 'upper: 100% leather; sole: rubber', '100% xyzfabric', '50% cotton 50% unknown', 'cotton',
  '100% pes', 'co 100%', 'tela', 'textil', 'nylon webbing', 'leather strap with metal buckle', 'cuero sintético', 'piel', 'gamuza sintética',
  '70% cotton 30% polyester 5% elastane', '120% cotton', '100% cottn', '100% polyestre', '100% leathr', 'canvas 60 suede 40', '', '   ',
  'PVC', 'TPU film', 'rubber sole', 'leatherette', 'bonded leather', 'denim', 'mezclilla 100%', 'fleece', 'polar', 'terry 100% cotton',
]
const MAPAS = [
  ['exterior', { cuero: 'cuero', textil: 'textil', plastico: 'plastico', otro: 'otro' }, {}],
  ['material', { cuero: 'cuero', textil: 'textil', plastico: 'plastico', otro: 'otro', metal: 'otro' }, { metal: true }],
  ['exterior', { paja: true, textil: 'textil', cuero: 'otro', plastico: 'otro', otro: 'otro' }, { paja: true }],
  ['material', { metal: true, cuero: 'cuero', textil: 'textil', plastico: 'plastico' }, { metal: true }],
]
M.setSinonimos([{ palabra: 'toquilla', equivale: 'straw' }])
const casos = CORPUS.map((txt) => {
  const pr = M.prepMat(txt)
  const pc = M.parseComp(txt)
  const mat = (modo) => { const p = M.parseMat(txt, modo); return p && { pesos: p.pesos, pred: p.pred, mixto: !!p.mixto, grupos: p.grupos || null } }
  const cm = M.claseMat({ comp: { x: txt } }, 'x')
  return {
    txt,
    prep: { s: pr.s, cambios: pr.cambios, desconocidas: pr.desconocidas, ambiguas: pr.ambiguas },
    comp: pc && { pesos: pc.pesos, pred: pc.pred, segmento: pc.segmento, uso_segmento: pc.usoSegmento },
    corte: mat('corte'), suela: mat('suela'),
    clase: cm && { pred: cm.pred, corrugado: cm.corrugado, aluminio: cm.aluminio },
    clase_texto: M.claseTexto(txt) && M.claseTexto(txt).clase,
    filas: M.filasDesdeTexto(txt),
    derivados: MAPAS.map(([parte, mapa]) => {
      const s = { comp: { [parte]: txt } }
      // matDerivado no está exportado: se reproduce con los atributos que lo usan
      return M.ATTRS.filter((a) => a.deComp === parte && a.fijo).map((a) => [a.id, a.fijo({ ...s, tipo: tipoDe(a.id) }) ?? null])
    }).flat(),
  }
})
function tipoDe(id) {
  return { materialCinturon: 'cinturon', exterior: 'mochila', materialGorra: 'gorra', materialLlavero: 'llavero', upper: 'calzado', sole: 'calzado',
    materialBotella: 'botella', materialAvio: 'avios', materialMueble: 'exhibidor', materialBisu: 'bisuteria', materialBolsa: 'bolsa_compra',
    materialCaja: 'caja', materialGancho: 'gancho', materialEtiqueta: 'etiqueta' }[id] || ''
}
const ruta = new URL('../../backend/tests/paridad/composicion.json', import.meta.url)
writeFileSync(ruta, JSON.stringify({ sinonimos: [{ palabra: 'toquilla', equivale: 'straw' }], casos }, null, 1) + '\n')
console.log(casos.length, 'casos →', String(ruta))
