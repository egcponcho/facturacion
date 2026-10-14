<script setup>
import { t } from '@/i18n/index.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { usarEditor } from './estado.js'
import ElementoSvg from './ElementoSvg.vue'

// El lienzo: la etiqueta a escala (1 unidad del SVG = 1 mm) con reglas,
// cuadrícula, área segura y los elementos. Se arrastra para mover, desde las
// asas para cambiar el tamaño o girar, y en el fondo para elegir con un marco.
// Al mover, el elemento se pega a los bordes y centros de la etiqueta y de los
// otros elementos (guías) o a la cuadrícula; Alt lo desactiva.
const props = defineProps({ fuentes: { type: Number, default: 0 } })
const emit = defineEmits(['zoom'])
const ed = usarEditor()
const est = ed.estado
const PX_MM = 96 / 25.4

const marco = ref(null)
const svg = ref(null)
const s = computed(() => est.zoom * PX_MM) // píxeles de pantalla por mm
const pad = computed(() => 26 / s.value)
const d = computed(() => est.diseno)
const vb = computed(() => `${-pad.value} ${-pad.value} ${d.value.ancho + 2 * pad.value} ${d.value.alto + 2 * pad.value}`)
const tamPx = computed(() => ({ width: `${(d.value.ancho + 2 * pad.value) * s.value}px`, height: `${(d.value.alto + 2 * pad.value) * s.value}px` }))
const px = (n) => n / s.value // n píxeles de pantalla en mm
const valores = computed(() => ({ ...ed.ejemplosTodos.value, ...(est.previa?.datos === 'reales' ? est.previa.valores : {}) }))

// ---- Reglas -----------------------------------------------------------------------------
const FACTOR = { mm: 1, cm: 10, in: 25.4 }
const PASOS = { mm: [1, 2, 5, 10, 20, 50, 100], cm: [0.1, 0.2, 0.5, 1, 2, 5, 10], in: [0.0625, 0.125, 0.25, 0.5, 1, 2, 5] }
const regla = computed(() => {
  const u = d.value.unidad || 'mm'
  const f = FACTOR[u]
  const menor = PASOS[u].find((p) => p * f * s.value >= 6) || PASOS[u].at(-1)
  const mayor = PASOS[u].find((p) => p * f * s.value >= 46) || PASOS[u].at(-1)
  const marcas = (largo) => {
    const r = []
    for (let i = 0; i * menor * f <= largo + 1e-6; i++) {
      const v = i * menor
      const esMayor = Math.abs(v / mayor - Math.round(v / mayor)) < 1e-6
      r.push({ mm: v * f, mayor: esMayor, texto: esMayor ? String(Math.round(v * 1000) / 1000) : null })
    }
    return r
  }
  return { x: marcas(d.value.ancho), y: marcas(d.value.alto), u }
})

// ---- Cuadrícula -------------------------------------------------------------------------
const cuadricula = computed(() => {
  const c = d.value.cuadricula || {}
  if (!c.visible) return null
  let paso = c.paso || 1
  while (paso * s.value < 5) paso *= 2 // no más de una línea cada 5 px
  return paso
})

// ---- Coordenadas ------------------------------------------------------------------------
function aMm(ev) {
  const p = svg.value.createSVGPoint()
  p.x = ev.clientX
  p.y = ev.clientY
  return p.matrixTransform(svg.value.getScreenCTM().inverse())
}
const rad = (g) => (g * Math.PI) / 180
const rotar = (x, y, g) => ({ x: x * Math.cos(rad(g)) - y * Math.sin(rad(g)), y: x * Math.sin(rad(g)) + y * Math.cos(rad(g)) })
const redondear = (v) => Math.round(v * 1000) / 1000

// ---- Arrastres --------------------------------------------------------------------------
let gesto = null
const marcoSel = ref(null)
const espacio = ref(false)

function alPresionarElemento(ev, e) {
  if (ev.button !== 0 || espacio.value) return
  ev.stopPropagation()
  const sumar = ev.shiftKey || ev.metaKey || ev.ctrlKey
  if (!est.seleccion.includes(e.id) || sumar) ed.seleccionar(e.id, sumar)
  if (!est.editable || sumar) return
  const lista = ed.seleccionados.value.filter((x) => !x.bloqueado)
  if (!lista.length) return
  const p = aMm(ev)
  gesto = { tipo: 'mover', p0: p, ancla: e, inicio: lista.map((x) => ({ e: x, x: x.x, y: x.y })), movido: false }
  svg.value.setPointerCapture(ev.pointerId)
}

function alPresionarAsa(ev, e, hx, hy) {
  ev.stopPropagation()
  if (!est.editable || e.bloqueado) return
  const c = { x: e.x + e.w / 2, y: e.y + e.h / 2 }
  const local = { x: (-hx * e.w) / 2, y: (-hy * e.h) / 2 }
  const r = rotar(local.x, local.y, e.rot || 0)
  gesto = { tipo: 'tamano', e, hx, hy, fijo: { x: c.x + r.x, y: c.y + r.y }, w0: e.w, h0: e.h }
  svg.value.setPointerCapture(ev.pointerId)
}
function alPresionarExtremo(ev, e, cual) {
  ev.stopPropagation()
  if (!est.editable || e.bloqueado) return
  gesto = { tipo: 'extremo', e, cual, fin: { x: e.x + e.w, y: e.y + e.h }, ini: { x: e.x, y: e.y } }
  svg.value.setPointerCapture(ev.pointerId)
}
function alPresionarGiro(ev, e) {
  ev.stopPropagation()
  if (!est.editable || e.bloqueado) return
  gesto = { tipo: 'giro', e, c: { x: e.x + e.w / 2, y: e.y + e.h / 2 } }
  svg.value.setPointerCapture(ev.pointerId)
}
function alPresionarFondo(ev) {
  if (ev.button === 1 || espacio.value) {
    gesto = { tipo: 'pan', x: ev.clientX, y: ev.clientY, sl: marco.value.scrollLeft, st: marco.value.scrollTop }
    svg.value.setPointerCapture(ev.pointerId)
    ev.preventDefault()
    return
  }
  if (ev.button !== 0) return
  editando.value = null
  const p = aMm(ev)
  gesto = { tipo: 'marco', p0: p, sumar: ev.shiftKey, previa: [...est.seleccion] }
  if (!ev.shiftKey) ed.seleccionar(null)
  marcoSel.value = { x: p.x, y: p.y, w: 0, h: 0 }
  svg.value.setPointerCapture(ev.pointerId)
}

// Guías: candidatos de la etiqueta y de los demás elementos visibles
function guiar(caja, quietos, libre) {
  const W = d.value.ancho
  const H = d.value.alto
  const m = d.value.margen || 0
  const cx = [0, W / 2, W, m, W - m]
  const cy = [0, H / 2, H, m, H - m]
  for (const o of quietos) {
    cx.push(o.x, o.x + o.w / 2, o.x + o.w)
    cy.push(o.y, o.y + o.h / 2, o.y + o.h)
  }
  const umbral = px(6)
  const mejor = (bordes, candidatos) => {
    let r = null
    for (const b of bordes) for (const c of candidatos) {
      const delta = c - b
      if (Math.abs(delta) <= umbral && (!r || Math.abs(delta) < Math.abs(r.delta))) r = { delta, v: c }
    }
    return r
  }
  if (libre) return { dx: 0, dy: 0, guias: [] }
  const gx = mejor([caja.x1, (caja.x1 + caja.x2) / 2, caja.x2], cx)
  const gy = mejor([caja.y1, (caja.y1 + caja.y2) / 2, caja.y2], cy)
  return { dx: gx?.delta ?? null, dy: gy?.delta ?? null, guias: [gx && { eje: 'x', v: gx.v }, gy && { eje: 'y', v: gy.v }].filter(Boolean) }
}

function alMover(ev) {
  if (!gesto) return
  if (gesto.tipo === 'pan') {
    marco.value.scrollLeft = gesto.sl - (ev.clientX - gesto.x)
    marco.value.scrollTop = gesto.st - (ev.clientY - gesto.y)
    return
  }
  const p = aMm(ev)
  if (gesto.tipo === 'marco') {
    const x = Math.min(p.x, gesto.p0.x)
    const y = Math.min(p.y, gesto.p0.y)
    marcoSel.value = { x, y, w: Math.abs(p.x - gesto.p0.x), h: Math.abs(p.y - gesto.p0.y) }
    const dentro = ed.elementos.value.filter((e) => e.visible !== false && e.x < x + marcoSel.value.w && e.x + e.w > x
      && e.y < y + marcoSel.value.h && e.y + Math.max(e.h, 0.01) > y).map((e) => e.id)
    est.seleccion = [...new Set([...(gesto.sumar ? gesto.previa : []), ...dentro])]
    return
  }
  if (gesto.tipo === 'mover') {
    let dx = p.x - gesto.p0.x
    let dy = p.y - gesto.p0.y
    if (!gesto.movido && Math.hypot(dx, dy) < px(3)) return
    gesto.movido = true
    if (ev.shiftKey) {
      if (Math.abs(dx) > Math.abs(dy)) dy = 0
      else dx = 0
    }
    const ids = new Set(gesto.inicio.map((i) => i.e.id))
    const caja = {
      x1: Math.min(...gesto.inicio.map((i) => i.x)) + dx, x2: Math.max(...gesto.inicio.map((i) => i.x + i.e.w)) + dx,
      y1: Math.min(...gesto.inicio.map((i) => i.y)) + dy, y2: Math.max(...gesto.inicio.map((i) => i.y + i.e.h)) + dy,
    }
    const g = guiar(caja, ed.elementos.value.filter((e) => !ids.has(e.id) && e.visible !== false), ev.altKey)
    const ancla = gesto.inicio.find((i) => i.e.id === gesto.ancla.id) || gesto.inicio[0]
    if (g.dx != null) dx += g.dx
    else if (!ev.altKey) dx = ed.ajustar(ancla.x + dx) - ancla.x
    if (g.dy != null) dy += g.dy
    else if (!ev.altKey) dy = ed.ajustar(ancla.y + dy) - ancla.y
    est.guias = g.guias
    for (const i of gesto.inicio) {
      i.e.x = redondear(i.x + dx)
      i.e.y = redondear(i.y + dy)
    }
    return
  }
  const e = gesto.e
  if (gesto.tipo === 'giro') {
    let g = (Math.atan2(p.y - gesto.c.y, p.x - gesto.c.x) * 180) / Math.PI + 90
    if (g > 180) g -= 360
    g = ev.shiftKey ? Math.round(g / 15) * 15 : Math.round(g)
    if (!ev.shiftKey && [0, 90, -90, 180].some((r) => Math.abs(g - r) <= 3)) g = [0, 90, -90, 180].find((r) => Math.abs(g - r) <= 3)
    e.rot = g === -180 ? 180 : g
    return
  }
  if (gesto.tipo === 'extremo') {
    let q = { x: ev.altKey ? p.x : ed.ajustar(p.x), y: ev.altKey ? p.y : ed.ajustar(p.y) }
    const otro = gesto.cual === 'fin' ? gesto.ini : gesto.fin
    if (ev.shiftKey || Math.abs(q.y - otro.y) <= px(4)) q = { ...q, y: otro.y }
    else if (Math.abs(q.x - otro.x) <= px(4)) q = { ...q, x: otro.x }
    if (gesto.cual === 'fin') {
      e.w = redondear(Math.max(q.x - gesto.ini.x, 0))
      e.h = redondear(Math.max(q.y - gesto.ini.y, 0))
    } else {
      e.x = redondear(Math.min(q.x, gesto.fin.x))
      e.y = redondear(Math.min(q.y, gesto.fin.y))
      e.w = redondear(gesto.fin.x - e.x)
      e.h = redondear(gesto.fin.y - e.y)
    }
    return
  }
  // Cambio de tamaño en el marco del elemento (girado o no) con la esquina opuesta fija
  const { hx, hy, fijo } = gesto
  const a = e.rot || 0
  const l = rotar(p.x - fijo.x, p.y - fijo.y, -a)
  const minimo = 0.5
  let w = hx ? Math.max(hx * l.x, minimo) : e.w
  let h = hy ? Math.max(hy * l.y, minimo) : e.h
  if (!a && !ev.altKey) {
    if (hx) w = Math.max(Math.abs(ed.ajustar(fijo.x + hx * w) - fijo.x), minimo)
    if (hy) h = Math.max(Math.abs(ed.ajustar(fijo.y + hy * h) - fijo.y), minimo)
  }
  if (ev.shiftKey && hx && hy) {
    const k = Math.max(w / gesto.w0, h / gesto.h0)
    w = gesto.w0 * k
    h = gesto.h0 * k
  }
  const c = rotar((hx * w) / 2, (hy * h) / 2, a)
  e.w = redondear(w)
  e.h = redondear(h)
  e.x = redondear(fijo.x + c.x - w / 2)
  e.y = redondear(fijo.y + c.y - h / 2)
}
function alSoltar() {
  if (gesto?.tipo === 'marco') marcoSel.value = null
  gesto = null
  est.guias = []
}

// ---- Edición de texto en el lienzo (doble clic) ------------------------------------------
const editando = ref(null)
const areaTexto = ref(null)
async function alDobleClic(e) {
  if (!est.editable || e.bloqueado || e.tipo !== 'texto' || e.rot) return
  editando.value = e.id
  await nextTick()
  areaTexto.value?.[0]?.focus()
  areaTexto.value?.[0]?.select()
}
const elementoEditado = computed(() => (editando.value ? ed.porId(editando.value) : null))
watch(() => est.seleccion.join(), () => {
  if (editando.value && !est.seleccion.includes(editando.value)) editando.value = null
})

// ---- Soltar campos y elementos desde la biblioteca -----------------------------------------
function alSoltarAqui(ev) {
  const dato = ev.dataTransfer.getData('application/x-etiqueta')
  if (!dato || !est.editable) return
  ev.preventDefault()
  const { tipo, extra } = JSON.parse(dato)
  ed.agregar(tipo, extra, aMm(ev))
}
function alArrastrarEncima(ev) {
  if (est.editable && ev.dataTransfer.types.includes('application/x-etiqueta')) {
    ev.preventDefault()
    ev.dataTransfer.dropEffect = 'copy'
  }
}

// ---- Zoom -------------------------------------------------------------------------------
function ajustarZoom() {
  if (!marco.value || !d.value) return
  // Las reglas ocupan 26 px a cada lado (pad) y se deja un respiro de 24 px
  const ancho = marco.value.clientWidth - 2 * 26 - 24
  const alto = marco.value.clientHeight - 2 * 26 - 24
  const z = Math.min(ancho / (d.value.ancho * PX_MM), alto / (d.value.alto * PX_MM))
  emit('zoom', Math.max(0.1, Math.min(Math.round(z * 100) / 100, 8)))
}
// Otra medida (o pasar a vertical): la etiqueta vuelve a caber entera
watch(() => d.value && `${d.value.ancho}x${d.value.alto}`, (nueva, vieja) => {
  if (vieja && nueva !== vieja) nextTick(ajustarZoom)
})
function alRueda(ev) {
  if (!ev.ctrlKey && !ev.metaKey) return
  ev.preventDefault()
  const antes = est.zoom
  const z = Math.max(0.1, Math.min(antes * (ev.deltaY < 0 ? 1.1 : 1 / 1.1), 8))
  const r = marco.value.getBoundingClientRect()
  const ox = ev.clientX - r.left + marco.value.scrollLeft
  const oy = ev.clientY - r.top + marco.value.scrollTop
  emit('zoom', Math.round(z * 100) / 100)
  nextTick(() => {
    marco.value.scrollLeft = (ox * z) / antes - (ev.clientX - r.left)
    marco.value.scrollTop = (oy * z) / antes - (ev.clientY - r.top)
  })
}
const teclaEspacio = (ev) => {
  const escribiendo = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
  if (ev.code === 'Space' && !escribiendo) {
    espacio.value = ev.type === 'keydown'
    if (ev.type === 'keydown') ev.preventDefault()
  }
}
let observador
onMounted(() => {
  window.addEventListener('keydown', teclaEspacio)
  window.addEventListener('keyup', teclaEspacio)
  observador = new ResizeObserver(() => {
    if (!observado) {
      observado = true
      ajustarZoom()
    }
  })
  observador.observe(marco.value)
})
let observado = false
onBeforeUnmount(() => {
  window.removeEventListener('keydown', teclaEspacio)
  window.removeEventListener('keyup', teclaEspacio)
  observador?.disconnect()
})
defineExpose({ ajustarZoom, centro: () => ({ x: d.value.ancho / 2, y: d.value.alto / 2 }) })

// ---- Selección y asas ---------------------------------------------------------------------
const visibles = computed(() => ed.elementos.value.filter((e) => e.visible !== false || est.seleccion.includes(e.id)))
const giro = (e) => (e.rot ? `rotate(${e.rot} ${e.x + e.w / 2} ${e.y + e.h / 2})` : null)
const golpe = (e) => {
  const m = px(4)
  return e.tipo === 'linea'
    ? { x: e.x - m, y: e.y - m, width: e.w + 2 * m, height: e.h + 2 * m }
    : { x: e.x, y: e.y, width: Math.max(e.w, px(6)), height: Math.max(e.h, px(6)) }
}
const ASAS = [[-1, -1], [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0]]
const CURSORES = { '-1,-1': 'nwse', '1,1': 'nwse', '1,-1': 'nesw', '-1,1': 'nesw', '0,-1': 'ns', '0,1': 'ns', '-1,0': 'ew', '1,0': 'ew' }
const asa = computed(() => px(8))
const problemas = ed.problemasDe
const cajaGrupo = computed(() => (ed.seleccionados.value.length > 1 ? ed.caja(ed.seleccionados.value) : null))
const dibujoServidor = computed(() => (!est.disenador && est.previa?.svg ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(est.previa.svg)}` : null))
const cursor = computed(() => (espacio.value ? 'grab' : 'default'))
</script>

<template>
  <div ref="marco" class="lienzo-marco" :style="{ cursor }" @wheel="alRueda" @dragover="alArrastrarEncima" @drop="alSoltarAqui">
    <div class="lienzo-hoja">
      <svg ref="svg" class="lienzo" :viewBox="vb" :style="tamPx" role="application" :aria-label="t('Label canvas')"
           @pointerdown="alPresionarFondo" @pointermove="alMover" @pointerup="alSoltar" @pointercancel="alSoltar">
        <!-- Reglas -->
        <g class="regla" :font-size="px(9.5)">
          <rect :x="-pad" :y="-pad" :width="d.ancho + 2 * pad" :height="px(18)" class="regla-fondo" />
          <rect :x="-pad" :y="-pad" :width="px(18)" :height="d.alto + 2 * pad" class="regla-fondo" />
          <g v-for="m in regla.x" :key="`x${m.mm}`">
            <line :x1="m.mm" :x2="m.mm" :y1="-pad + px(m.mayor ? 6 : 13)" :y2="-pad + px(18)" class="regla-marca" />
            <text v-if="m.texto" :x="m.mm + px(2)" :y="-pad + px(10)">{{ m.texto }}</text>
          </g>
          <g v-for="m in regla.y" :key="`y${m.mm}`">
            <line :y1="m.mm" :y2="m.mm" :x1="-pad + px(m.mayor ? 6 : 13)" :x2="-pad + px(18)" class="regla-marca" />
            <text v-if="m.texto" :x="-pad + px(2)" :y="m.mm - px(2)">{{ m.texto }}</text>
          </g>
          <text :x="-pad + px(2)" :y="-pad + px(10)" class="regla-unidad">{{ regla.u }}</text>
        </g>
        <!-- Etiqueta -->
        <defs>
          <pattern v-if="cuadricula" id="cuadricula-etq" :width="cuadricula" :height="cuadricula" patternUnits="userSpaceOnUse">
            <path :d="`M ${cuadricula} 0 L 0 0 0 ${cuadricula}`" fill="none" class="cuadricula" :stroke-width="px(1)" />
          </pattern>
          <clipPath id="recorte-etq"><rect :width="d.ancho" :height="d.alto" :rx="d.borde?.radio || 0" /></clipPath>
        </defs>
        <rect :width="d.ancho" :height="d.alto" :rx="d.borde?.radio || 0" :fill="d.fondo" class="papel" />
        <rect v-if="cuadricula" :width="d.ancho" :height="d.alto" fill="url(#cuadricula-etq)" pointer-events="none" />
        <!-- Quien no diseña ve el dibujo exacto del servidor (no puede pedir códigos sueltos) -->
        <image v-if="dibujoServidor" :href="dibujoServidor" :width="d.ancho" :height="d.alto" preserveAspectRatio="none" pointer-events="none" />
        <g v-else clip-path="url(#recorte-etq)">
          <ElementoSvg v-for="e in visibles" :key="e.id" :e="e" :valores="valores" :tipos="est.tipos" :version="props.fuentes"
                       :class="{ oculto: e.visible === false }" />
        </g>
        <!-- Lo que sale de la etiqueta se ve atenuado para ubicarlo -->
        <g opacity="0.25" pointer-events="none">
          <ElementoSvg v-for="e in visibles.filter((x) => x.x < 0 || x.y < 0 || x.x + x.w > d.ancho || x.y + x.h > d.alto)" :key="`f${e.id}`" :e="e"
                       :valores="valores" :tipos="est.tipos" :version="props.fuentes" />
        </g>
        <rect v-if="d.borde" :x="d.borde.grosor / 2" :y="d.borde.grosor / 2" :width="d.ancho - d.borde.grosor" :height="d.alto - d.borde.grosor"
              :rx="d.borde.radio || 0" fill="none" :stroke="d.borde.color" :stroke-width="d.borde.grosor" pointer-events="none" />
        <rect v-if="d.margen" :x="d.margen" :y="d.margen" :width="d.ancho - 2 * d.margen" :height="d.alto - 2 * d.margen" class="area-segura"
              :stroke-width="px(1)" :stroke-dasharray="`${px(4)} ${px(3)}`" pointer-events="none" />

        <!-- Zonas para tocar cada elemento (el de encima gana) -->
        <g>
          <rect v-for="e in visibles" :key="`h${e.id}`" v-bind="golpe(e)" :transform="giro(e)" class="golpe"
                :class="{ bloqueado: e.bloqueado, movible: est.editable && !e.bloqueado }"
                @pointerdown="alPresionarElemento($event, e)" @dblclick="alDobleClic(e)">
            <title>{{ e.nombre || e.campo || e.tipo }}</title>
          </rect>
        </g>
        <!-- Problemas que encontró el servidor -->
        <g pointer-events="none">
          <rect v-for="e in visibles.filter((x) => problemas[x.id])" :key="`p${e.id}`" :x="e.x - px(2)" :y="e.y - px(2)" :width="e.w + px(4)"
                :height="e.h + px(4)" :transform="giro(e)" fill="none" :class="`marca-${problemas[e.id]}`" :stroke-width="px(1.5)"
                :stroke-dasharray="`${px(3)} ${px(2)}`" />
        </g>
        <!-- Selección -->
        <g v-for="e in ed.seleccionados.value" :key="`s${e.id}`" :transform="giro(e)">
          <rect :x="e.x" :y="e.y" :width="e.w" :height="Math.max(e.h, 0)" fill="none" class="sel" :stroke-width="px(1.5)" pointer-events="none" />
          <template v-if="ed.seleccionados.value.length === 1 && est.editable && !e.bloqueado">
            <template v-if="e.tipo === 'linea' && !e.rot">
              <circle :cx="e.x" :cy="e.y" :r="asa / 2" class="asa" :stroke-width="px(1.5)" style="cursor: move" @pointerdown="alPresionarExtremo($event, e, 'ini')" />
              <circle :cx="e.x + e.w" :cy="e.y + e.h" :r="asa / 2" class="asa" :stroke-width="px(1.5)" style="cursor: move"
                      @pointerdown="alPresionarExtremo($event, e, 'fin')" />
            </template>
            <template v-else-if="e.tipo !== 'linea'">
              <rect v-for="[hx, hy] in ASAS" :key="`${hx},${hy}`" :x="e.x + ((hx + 1) / 2) * e.w - asa / 2" :y="e.y + ((hy + 1) / 2) * e.h - asa / 2"
                    :width="asa" :height="asa" class="asa" :stroke-width="px(1.5)" :style="{ cursor: `${CURSORES[`${hx},${hy}`]}-resize` }"
                    @pointerdown="alPresionarAsa($event, e, hx, hy)" />
            </template>
            <line :x1="e.x + e.w / 2" :x2="e.x + e.w / 2" :y1="e.y" :y2="e.y - px(20)" class="sel" :stroke-width="px(1.5)" pointer-events="none" />
            <circle :cx="e.x + e.w / 2" :cy="e.y - px(24)" :r="asa / 2" class="asa giro" :stroke-width="px(1.5)" @pointerdown="alPresionarGiro($event, e)">
              <title>{{ t('Rotate (Shift: steps of 15°)') }}</title>
            </circle>
          </template>
        </g>
        <rect v-if="cajaGrupo" :x="cajaGrupo.x1 - px(4)" :y="cajaGrupo.y1 - px(4)" :width="cajaGrupo.x2 - cajaGrupo.x1 + px(8)"
              :height="cajaGrupo.y2 - cajaGrupo.y1 + px(8)" fill="none" class="sel" :stroke-width="px(1)" :stroke-dasharray="`${px(4)} ${px(3)}`" pointer-events="none" />
        <!-- Guías y marco de selección -->
        <g pointer-events="none">
          <line v-for="(g, i) in est.guias" :key="`g${i}`" v-bind="g.eje === 'x' ? { x1: g.v, x2: g.v, y1: -pad, y2: d.alto + pad } : { y1: g.v, y2: g.v, x1: -pad, x2: d.ancho + pad }"
                class="guia" :stroke-width="px(1)" />
          <rect v-if="marcoSel" :x="marcoSel.x" :y="marcoSel.y" :width="marcoSel.w" :height="marcoSel.h" class="marco-sel" :stroke-width="px(1)" />
        </g>
        <!-- Texto editado sobre el lienzo -->
        <foreignObject v-if="elementoEditado" :x="elementoEditado.x" :y="elementoEditado.y" :width="Math.max(elementoEditado.w, px(80))"
                       :height="Math.max(elementoEditado.h, px(40))">
          <textarea ref="areaTexto" v-model="elementoEditado.contenido" class="texto-en-lienzo" :style="{ fontSize: `${px(13)}px`, borderWidth: `${px(1.5)}px`, padding: `${px(2)}px ${px(4)}px`, borderRadius: `${px(3)}px` }" :aria-label="t('Text')"
                    @keydown.esc.stop="editando = null" @keydown.stop @pointerdown.stop />
        </foreignObject>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.lienzo-marco { position: relative; overflow: auto; background: var(--superficie-2); background-image: radial-gradient(var(--linea) 1px, transparent 1px);
  background-size: 16px 16px; min-height: 0; height: 100%; touch-action: none; }
.lienzo-hoja { display: flex; align-items: center; justify-content: center; min-width: 100%; min-height: 100%; width: max-content; padding: 24px; box-sizing: border-box; }
.lienzo { display: block; user-select: none; overflow: visible; }
.papel { filter: drop-shadow(0 1px 1.5px rgba(16, 24, 40, 0.18)); }
.regla-fondo { fill: var(--superficie); }
.regla text { fill: var(--tinta-3); font-family: system-ui, sans-serif; }
.regla-unidad { font-weight: 600; }
.regla-marca { stroke: var(--borde-hover); stroke-width: 0.15; vector-effect: non-scaling-stroke; }
.cuadricula { stroke: rgba(51, 85, 224, 0.12); }
.area-segura { fill: none; stroke: rgba(51, 85, 224, 0.55); }
.golpe { fill: transparent; }
.golpe.movible { cursor: move; }
.golpe.bloqueado { cursor: not-allowed; }
.sel { stroke: var(--acento); }
.asa { fill: #fff; stroke: var(--acento); }
.asa.giro { cursor: grab; }
.guia { stroke: #e0337a; }
.marco-sel { fill: rgba(51, 85, 224, 0.08); stroke: var(--acento); }
.marca-error { stroke: var(--error); }
.marca-advertencia { stroke: #d48a00; }
.oculto { opacity: 0.3; }
.texto-en-lienzo { width: 100%; height: 100%; box-sizing: border-box; resize: none; border: solid var(--acento);
  font-family: system-ui, sans-serif; background: #fff; color: #000; outline: none; }
</style>
