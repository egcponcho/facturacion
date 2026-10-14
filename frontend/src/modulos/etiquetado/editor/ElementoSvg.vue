<script setup>
import { computed, ref, watch } from 'vue'
import { usarEditor } from './estado.js'
import { PT_MM, TRAZOS, anchoTexto, cumple, formatear, maquetar, sustituir, valorCodigo as valorDeCodigo } from '@/modulos/etiquetado/etiquetas.js'

// Un elemento del diseño dibujado en el lienzo del editor (en mm), con los
// valores de ejemplo de cada campo. Textos, formas e imágenes se dibujan igual
// que en el servidor; los códigos de barras y QR los dibuja el servidor (los
// mismos que se imprimen) y, mientras llegan o si el valor no es válido, se
// muestra una representación.
const props = defineProps({
  e: { type: Object, required: true },
  valores: { type: Object, default: () => ({}) },
  tipos: { type: Object, default: () => ({}) },
  version: { type: Number, default: 0 }, // cambia al cargar las fuentes: vuelve a medir
})

const giro = computed(() => (props.e.rot ? `rotate(${props.e.rot} ${props.e.x + props.e.w / 2} ${props.e.y + props.e.h / 2})` : null))
const aplica = computed(() => cumple(props.e.condicion, props.valores))

// ---- Texto y campo ----------------------------------------------------------------------
const texto = computed(() => {
  const e = props.e
  if (e.tipo === 'texto') return sustituir(e.contenido, props.valores, props.tipos)
  if (e.tipo !== 'campo') return ''
  let v = formatear(props.valores[e.campo], e.formato, props.tipos[e.campo])
  if (v == null) v = e.si_vacio === 'alternativo' ? e.alternativo || '' : ''
  return v ? `${e.prefijo || ''}${v}${e.sufijo || ''}` : ''
})
const marcador = computed(() => (props.e.tipo === 'campo' ? `{{${props.e.campo}}}` : props.e.contenido || ''))
const estilo = computed(() => ({ fuente: 'sans', tam: 10, interlineado: 1.15, espaciado: 0, relleno: 0, alin: 'izq', valign: 'arriba', ajuste: 'reducir', tam_min: 6, color: '#000000', ...(props.e.estilo || {}) }))
const maqueta = computed(() => {
  void props.version
  const est = estilo.value
  const vacioTxt = !texto.value
  let txt = vacioTxt ? marcador.value : texto.value
  if (est.mayusculas) txt = txt.toUpperCase()
  const m = maquetar(txt, est, props.e.w, props.e.h)
  const rel = est.relleno || 0
  const ancho = Math.max(props.e.w - 2 * rel, 0.1)
  const alto = Math.max(props.e.h - 2 * rel, 0.1)
  const total = (m.lineas.length - 1) * m.interlinea + m.tam * PT_MM
  const y0 = props.e.y + rel + { arriba: 0, medio: (alto - total) / 2, abajo: alto - total }[est.valign]
  const lineas = m.lineas.map((l, i) => {
    const w = anchoTexto(l, est, m.tam)
    return { l, w, x: props.e.x + rel + { izq: 0, centro: (ancho - w) / 2, der: ancho - w }[est.alin], y: y0 + i * m.interlinea + m.tam * PT_MM * 0.8 }
  })
  return { ...m, lineas, vacio: vacioTxt }
})
const decoracion = computed(() => [estilo.value.subrayado && 'underline', estilo.value.tachado && 'line-through'].filter(Boolean).join(' ') || null)

// ---- Imagen -----------------------------------------------------------------------------
const imagen = computed(() => {
  const e = props.e
  if (e.tipo !== 'imagen') return null
  if (e.fuente_imagen === 'adjunto' && e.adjunto_id) return `/api/etiquetas/imagenes/${e.adjunto_id}`
  if (e.fuente_imagen === 'datos' && e.datos) return e.datos
  const v = e.fuente_imagen === 'campo' ? props.valores[e.campo] : null
  return typeof v === 'string' && (v.startsWith('data:image/') || v.startsWith('/')) ? v : null
})
const encaje = computed(() => ({ contener: 'xMidYMid meet', cubrir: 'xMidYMid slice', estirar: 'none' })[props.e.encaje || 'contener'])

// ---- Código: representación con barras deterministas o módulos de QR -------------------------
const valorCodigo = computed(() => (props.e.tipo === 'codigo' ? valorDeCodigo(props.e, props.valores, props.tipos) : ''))
function semilla(s) {
  let h = 2166136261
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return () => ((h = Math.imul(h ^ (h >>> 13), 1274126177)) >>> 0) / 4294967296
}
const codigo = computed(() => {
  const e = props.e
  if (e.tipo !== 'codigo') return null
  const m = e.margen || 0
  const w = Math.max(e.w - 2 * m, 0.5)
  const h = Math.max(e.h - 2 * m, 0.5)
  const azar = semilla(`${e.simbologia}${valorCodigo.value}`)
  if (e.simbologia === 'qr') {
    const n = 25
    const lado = Math.min(w, h)
    const mod = lado / n
    const x0 = e.x + m + (w - lado) / 2
    const y0 = e.y + m + (h - lado) / 2
    const ojo = (i, j) => [[0, 0], [n - 7, 0], [0, n - 7]].some(([a, b]) => i >= a && i < a + 7 && j >= b && j < b + 7)
    const rects = []
    for (const [a, b] of [[0, 0], [n - 7, 0], [0, n - 7]]) {
      rects.push({ x: x0 + a * mod, y: y0 + b * mod, w: 7 * mod, h: 7 * mod, hueco: true })
      rects.push({ x: x0 + (a + 2) * mod, y: y0 + (b + 2) * mod, w: 3 * mod, h: 3 * mod })
    }
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (!ojo(i, j) && azar() > 0.52) rects.push({ x: x0 + i * mod, y: y0 + j * mod, w: mod, h: mod })
    return { rects, mod, texto: null }
  }
  const tamTexto = e.legible ? Math.max(Math.min(h * 0.22 / PT_MM, 10), 4) : 0
  const altoBarras = e.legible ? h - tamTexto * PT_MM * 1.25 : h
  const rects = []
  const modulos = 95
  const mod = w / modulos
  let i = 0
  while (i < modulos) {
    const ancho = 1 + Math.floor(azar() * 3)
    if (i === 0 || i >= modulos - 3 || azar() > 0.45) rects.push({ x: e.x + m + i * mod, y: e.y + m, w: Math.min(ancho, modulos - i) * mod, h: altoBarras })
    i += ancho + 1 + Math.floor(azar() * 2)
  }
  return { rects, mod, texto: e.legible ? { tam: tamTexto * PT_MM, x: e.x + e.w / 2, y: e.y + m + h - tamTexto * PT_MM * 0.2 } : null }
})
// El código real del servidor, pedido al dejar de cambiar el valor o las medidas
const ed = usarEditor()
const claveCodigo = computed(() => {
  const e = props.e
  if (e.tipo !== 'codigo' || !ed?.estado.disenador) return null
  return JSON.stringify([e.simbologia, valorCodigo.value, e.w, e.h, e.margen, e.legible, e.correccion, e.color, e.relleno || ed.estado.diseno?.fondo])
})
const codigoReal = ref(null)
let esperaCodigo
watch(claveCodigo, (k) => {
  clearTimeout(esperaCodigo)
  if (!k) return
  esperaCodigo = setTimeout(() => ed.codigoServidor(k, props.e, valorCodigo.value), 350)
}, { immediate: true })
watch(() => (claveCodigo.value ? ed.codigos[claveCodigo.value] : undefined), (v) => {
  if (v !== null && v !== undefined) codigoReal.value = v
}, { immediate: true })
// ---- Tabla: encabezado, filas de la lista (ejemplo o reales) y total; el servidor decide si caben ------
const tabla = computed(() => {
  const e = props.e
  if (e.tipo !== 'tabla' || !e.columnas?.length) return null
  const filas = Array.isArray(props.valores[e.coleccion]) ? props.valores[e.coleccion]
    : [Object.fromEntries(e.columnas.map((c) => [c.campo, `‹${c.campo}›`]))]
  const fijas = (e.encabezado ? 1 : 0) + (e.totales?.length ? 1 : 0)
  const cabe = Math.max(Math.floor(e.h / e.alto_fila + 1e-6) - fijas, 0)
  const pesos = e.columnas.reduce((s, c) => s + (c.ancho || 1), 0)
  let x = e.x
  const xs = e.columnas.map((c) => {
    const w = (e.w * (c.ancho || 1)) / pesos
    const r = { x, w, alin: c.alin || 'izq' }
    x += w
    return r
  })
  const tam = (e.estilo?.tam || 7) * PT_MM
  const celda = (texto, i, fila) => ({ texto: String(texto ?? ''), x: xs[i].alin === 'der' ? xs[i].x + xs[i].w - 0.6 : xs[i].alin === 'centro' ? xs[i].x + xs[i].w / 2 : xs[i].x + 0.6,
    ancla: xs[i].alin === 'der' ? 'end' : xs[i].alin === 'centro' ? 'middle' : 'start', y: e.y + fila * e.alto_fila + (e.alto_fila + tam * 0.7) / 2 })
  const lineas = []
  let fila = 0
  if (e.encabezado) lineas.push(...e.columnas.map((c, i) => ({ ...celda(c.titulo || c.campo, i, fila++ * 0 + 0), negrita: true })))
  if (e.encabezado) fila = 1
  const visibles = filas.slice(0, cabe)
  for (const f of visibles) {
    lineas.push(...e.columnas.map((c, i) => celda(formatear(f[c.campo], c.formato, props.tipos[`${e.coleccion}.${c.campo}`]) ?? '', i, fila)))
    fila++
  }
  if (e.totales?.length) {
    lineas.push(...e.columnas.map((c, i) => ({ ...celda(e.totales.includes(c.campo) ? (Array.isArray(props.valores[e.coleccion])
      ? formatear(filas.reduce((s, x) => s + (Number(x[c.campo]) || 0), 0), c.formato, 'numero') : 'Σ') : '', i, fila), negrita: true })))
    fila++
  }
  return { lineas, alto: fila * e.alto_fila, xs, tam, desborda: filas.length > cabe }
})
const trazo = (e) => (TRAZOS[e.trazo] ? TRAZOS[e.trazo](e.grosor || 0.3) : null)
</script>

<template>
  <g :transform="giro" :opacity="aplica ? 1 : 0.35" :data-elemento="e.id">
    <template v-if="e.tipo === 'texto' || e.tipo === 'campo'">
      <rect v-if="estilo.fondo" :x="e.x" :y="e.y" :width="e.w" :height="e.h" :fill="estilo.fondo" />
      <text v-for="(l, i) in maqueta.lineas" :key="i" :x="l.x" :y="l.y" :font-size="maqueta.tam * PT_MM"
            :font-family="`Etiqueta-${estilo.fuente}`" :font-weight="estilo.negrita ? 700 : 400" :font-style="estilo.cursiva ? 'italic' : 'normal'"
            :letter-spacing="estilo.espaciado ? estilo.espaciado * PT_MM : null" :text-decoration="decoracion"
            :fill="maqueta.vacio ? '#9aa4b2' : estilo.color" xml:space="preserve">{{ l.l }}</text>
    </template>
    <template v-else-if="e.tipo === 'imagen'">
      <image v-if="imagen" :href="imagen" :x="e.x" :y="e.y" :width="e.w" :height="e.h" :preserveAspectRatio="encaje" />
      <g v-else>
        <rect :x="e.x" :y="e.y" :width="e.w" :height="e.h" fill="#eef2f7" stroke="#9aa4b2" stroke-width="0.25" stroke-dasharray="1 0.8" />
        <path :d="`M${e.x + e.w * 0.2} ${e.y + e.h * 0.75} L${e.x + e.w * 0.42} ${e.y + e.h * 0.45} L${e.x + e.w * 0.58} ${e.y + e.h * 0.62} L${e.x + e.w * 0.68} ${e.y + e.h * 0.52} L${e.x + e.w * 0.8} ${e.y + e.h * 0.75} Z`"
              fill="#c3cbd6" />
      </g>
    </template>
    <image v-else-if="e.tipo === 'codigo' && codigoReal" :href="codigoReal" :x="e.x" :y="e.y" :width="e.w" :height="e.h" preserveAspectRatio="none" />
    <template v-else-if="e.tipo === 'codigo' && codigo">
      <rect v-if="e.relleno" :x="e.x" :y="e.y" :width="e.w" :height="e.h" :fill="e.relleno" />
      <template v-for="(r, i) in codigo.rects" :key="i">
        <rect v-if="r.hueco" :x="r.x + codigo.mod / 2" :y="r.y + codigo.mod / 2" :width="r.w - codigo.mod" :height="r.h - codigo.mod" fill="none"
              :stroke="e.color" :stroke-width="codigo.mod" />
        <rect v-else :x="r.x" :y="r.y" :width="r.w" :height="r.h" :fill="e.color" />
      </template>
      <text v-if="codigo.texto" :x="codigo.texto.x" :y="codigo.texto.y" :font-size="codigo.texto.tam" text-anchor="middle" font-family="Etiqueta-mono"
            :fill="e.color">{{ valorCodigo }}</text>
    </template>
    <rect v-else-if="e.tipo === 'rect'" :x="e.x" :y="e.y" :width="e.w" :height="e.h" :rx="e.radio || null" :fill="e.relleno || 'none'"
          :stroke="e.borde && e.grosor ? e.borde : null" :stroke-width="e.borde ? e.grosor : null" :stroke-dasharray="trazo(e)" />
    <ellipse v-else-if="e.tipo === 'elipse'" :cx="e.x + e.w / 2" :cy="e.y + e.h / 2" :rx="e.w / 2" :ry="e.h / 2" :fill="e.relleno || 'none'"
             :stroke="e.borde && e.grosor ? e.borde : null" :stroke-width="e.borde ? e.grosor : null" :stroke-dasharray="trazo(e)" />
    <g v-else-if="e.tipo === 'tabla' && tabla">
      <rect v-if="e.cuadricula" :x="e.x" :y="e.y" :width="e.w" :height="tabla.alto" fill="none" :stroke="e.color" :stroke-width="e.grosor" />
      <template v-if="e.cuadricula">
        <line v-for="k in Math.max(Math.round(tabla.alto / e.alto_fila) - 1, 0)" :key="`h${k}`" :x1="e.x" :x2="e.x + e.w" :y1="e.y + k * e.alto_fila" :y2="e.y + k * e.alto_fila"
              :stroke="e.color" :stroke-width="e.grosor" />
        <line v-for="(c, k) in tabla.xs.slice(1)" :key="`v${k}`" :x1="c.x" :x2="c.x" :y1="e.y" :y2="e.y + tabla.alto" :stroke="e.color" :stroke-width="e.grosor" />
      </template>
      <text v-for="(l, k) in tabla.lineas" :key="k" :x="l.x" :y="l.y" :font-size="tabla.tam" :text-anchor="l.ancla" font-family="Etiqueta-sans"
            :font-weight="l.negrita ? 700 : 400" :fill="e.estilo?.color || '#000000'">{{ l.texto }}</text>
      <rect v-if="tabla.desborda" :x="e.x" :y="e.y" :width="e.w" :height="e.h" fill="none" stroke="#d32f2f" stroke-width="0.4" stroke-dasharray="1 0.8" />
    </g>
    <line v-else-if="e.tipo === 'linea'" :x1="e.x" :y1="e.y" :x2="e.x + e.w" :y2="e.y + e.h" :stroke="e.color" :stroke-width="e.grosor"
          :stroke-dasharray="trazo(e)" />
  </g>
</template>
