<script setup>
import { ve } from '@/stores/sesion'
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'
import { ACCIONES, fmtFecha, fmtFechaHora, fmtMoneda, fmtNum, plural, porUnidadTxt, unidadTxt } from '@/nucleo/utils'
import Avance from '@/componentes/Avance.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Pasos from '@/componentes/Pasos.vue'
import Requisitos from '@/componentes/Requisitos.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { estado as leerEstado } from '@/nucleo/estados.js'

// Resumen de una factura en el panel lateral: cifras, en qué paso va, cuánto
// está en packing list, empacado y cargado, qué le falta, sus packing lists,
// sus líneas (tabla común, de 10 en 10) y la actividad reciente.
const props = defineProps({ id: { type: Number, required: true } })
const emit = defineEmits(['cerrar'])
const f = ref(null)
const actividad = ref([])
const EN_CAMINO = ['EN_TRANSITO', 'ARRIBADO', 'ENTREGADO', 'RECIBIDO']

watch(() => props.id, async (id) => {
  f.value = null
  try {
    const [d, h] = await Promise.all([api.get(`/facturas/${id}`), api.get(`/facturas/${id}/historial`)])
    f.value = d
    actividad.value = h.slice(0, 6)
  } catch (e) {
    errorApi(e)
    emit('cerrar')
  }
}, { immediate: true })

const faltan = computed(() => (f.value?.pendientes || []).map((p, i) => ({
  clave: String(i), ok: false, titulo: p.mensaje,
  acciones: p.producto_id ? [{ texto: t('Open technical sheet'), to: `/productos/${p.producto_id}` }] : [],
})))

// Totales de mercancía y de bultos (sumando sus packing lists)
const suma = (campo) => Object.values(f.value?.totales.por_unidad || {}).reduce((a, u) => a + (u[campo] || 0), 0)
const pls = computed(() => (f.value?.packing_lists || []).filter((p) => p.estado !== 'CANCELADO'))
const bultos = computed(() => pls.value.reduce((a, p) => ({
  cajas: a.cajas + (p.totales?.cajas || 0), kg: a.kg + (p.totales?.peso_bruto || 0), cbm: a.cbm + (p.totales?.cbm || 0),
}), { cajas: 0, kg: 0, cbm: 0 }))
const cargados = computed(() => pls.value.filter((p) => p.transporte).length)
const enCamino = computed(() => pls.value.filter((p) => EN_CAMINO.includes(p.transporte?.estado)).length)

const pasos = computed(() => {
  const d = f.value
  if (!d) return []
  const borrador = ['BORRADOR', 'EN_CORRECCION'].includes(d.estado)
  const facturado = suma('facturado')
  const plListo = pls.value.length && pls.value.every((p) => p.estado === 'FINALIZADO') && suma('empacado') >= facturado
  const n = pls.value.length
  return [
    { titulo: t('Invoice'), estado: borrador ? (faltan.value.length ? 'alerta' : 'actual') : 'hecho',
      detalle: borrador ? plural(faltan.value.length, t('pending item'), t('pending items')) : fmtFecha(d.finalizado_en) },
    { titulo: t('Packing list'), estado: plListo ? 'hecho' : borrador ? 'pendiente' : 'actual',
      detalle: n ? plural(n, 'PL', t('PLs')) : '' },
    { titulo: t('Load unit'), estado: n && cargados.value === n ? 'hecho' : cargados.value ? 'actual' : 'pendiente',
      detalle: n ? t('{0} of {1}', [cargados.value, n]) : '' },
    { titulo: t('On the way'), estado: n && enCamino.value === n ? 'hecho' : enCamino.value ? 'actual' : 'pendiente',
      detalle: n && enCamino.value ? t('{0} of {1}', [enCamino.value, n]) : '' },
  ]
})

// Packing lists y líneas en la tabla común (modo local, sin vistas guardadas:
// es un resumen dentro del panel)
const columnasPls = [
  { clave: 'numero', texto: 'PL', fija: true, prioridad: 1, valor: (pl) => pl.numero },
  { clave: 'estado', texto: t('Status'), prioridad: 3, inicial: false, textoValor: (v) => tx(leerEstado(v)[0]) },
  { clave: 'cajas', texto: t('Cartons'), num: true, prioridad: 2, valor: (pl) => pl.totales?.cajas || 0 },
  { clave: 'kg', texto: 'kg', num: true, prioridad: 3, valor: (pl) => pl.totales?.peso_bruto || 0, textoValor: (v) => fmtNum(v, 1) },
  { clave: 'cbm', texto: 'm³', num: true, prioridad: 3, valor: (pl) => pl.totales?.cbm || 0, textoValor: (v) => fmtNum(v, 2) },
  { clave: 'unidad', texto: t('Load unit'), prioridad: 2, valor: (pl) => pl.transporte?.unidad || null },
]
const columnasLineas = [
  { clave: 'articulo', texto: t('Item'), fija: true, prioridad: 1, valor: (l) => [l.estilo, l.color, l.talla].filter(Boolean).join(' · ') },
  { clave: 'oc', texto: t('PO'), prioridad: 3, inicial: false, valor: (l) => l.oc_numero },
  { clave: 'partida', texto: t('HS code'), prioridad: 3, inicial: false, valor: (l) => l.partida_arancelaria || null },
  { clave: 'cantidad', texto: t('Qty.'), num: true, prioridad: 1 },
  { clave: 'importe', texto: t('Total'), num: true, grupo: 'precios', prioridad: 2 },
]

const descargar = (formato) => api.descargar(`/facturas/${props.id}/exportar?formato=${formato}`, `invoice.${formato}`).catch(errorApi)
</script>

<template>
  <PanelLateral :titulo="f?.nombre || t('Invoice')" :detalle="`/facturas/${props.id}`" ancho="560px" @cerrar="emit('cerrar')">
    <template #estado>
      <span v-if="f" class="fila-flex pl-subtitulo"><EstadoBadge :estado="f.estado" /><span class="ayuda">{{ tx(f.proveedor) }} · {{ fmtFecha(f.fecha) || '—' }}</span></span>
    </template>
    <p v-if="!f" class="ayuda">{{ t('Loading…') }}</p>
    <template v-else>
      <div class="pl-acciones">
        <button type="button" class="btn btn-chico" @click="descargar('pdf')"><Icono nombre="descargar" :tam="14" />PDF</button>
        <button type="button" class="btn btn-chico" @click="descargar('xlsx')"><Icono nombre="descargar" :tam="14" />{{ t('Excel') }}</button>
      </div>

      <div class="pl-cifras">
        <div v-if="ve('precios')" class="pl-cifra principal"><span>{{ t('Amount') }}</span><b>{{ fmtMoneda(f.totales.importe, f.moneda) }}</b>
          <small>{{ tx(f.incoterm || '—') }} · {{ plural(f.lineas.length, t('line'), t('lines')) }}</small></div>
        <div class="pl-cifra"><span>{{ t('Quantity') }}</span><b>{{ porUnidadTxt(f.totales.por_unidad, 'facturado') }}</b></div>
        <div class="pl-cifra"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(bultos.cajas) }}</b></div>
        <div class="pl-cifra"><span>{{ t('Gross weight') }}</span><b>{{ fmtNum(bultos.kg, 1) }} kg</b></div>
        <div class="pl-cifra"><span>{{ t('Volume') }}</span><b>{{ fmtNum(bultos.cbm, 2) }} m³</b></div>
      </div>

      <Pasos :pasos="pasos" class="pl-pasos" />

      <section class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Progress') }}</h3>
        <div class="pl-avances">
          <span>{{ t('In packing list') }}</span><Avance :valor="suma('en_pl')" :total="suma('facturado')" />
          <span>{{ t('Packed') }}</span><Avance :valor="suma('empacado')" :total="suma('facturado')" />
          <span>{{ t('In a load unit') }}</span><Avance :valor="cargados" :total="pls.length" />
        </div>
      </section>

      <section v-if="faltan.length" class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Missing to finalize ({0})', [faltan.length]) }}</h3>
        <Requisitos :items="faltan.slice(0, 6)" />
        <p v-if="faltan.length > 6" class="ayuda">{{ t('And {0} more.', [faltan.length - 6]) }}</p>
      </section>

      <section class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Packing lists') }}</h3>
        <p v-if="!pls.length" class="ayuda">{{ t('No packing list') }}</p>
        <TablaDatos v-else tabla="factura_resumen_pls" :columnas="columnasPls" :filas="pls" :vistas-guardadas="false" :etiqueta="t('Packing lists')">
          <template #celda-numero="{ fila: pl }"><router-link :to="`/packing-lists/${pl.id}`">{{ tx(pl.numero) }}</router-link><div><EstadoBadge :estado="pl.estado" /></div></template>
          <template #celda-estado="{ fila: pl }"><EstadoBadge :estado="pl.estado" /></template>
          <template #celda-cajas="{ fila: pl }">{{ fmtNum(pl.totales?.cajas || 0) }}</template>
          <template #celda-kg="{ fila: pl }">{{ fmtNum(pl.totales?.peso_bruto || 0, 1) }}</template>
          <template #celda-cbm="{ fila: pl }">{{ fmtNum(pl.totales?.cbm || 0, 2) }}</template>
          <template #celda-unidad="{ fila: pl }">
            <template v-if="pl.transporte">
              <b>{{ tx(pl.transporte.unidad) }}</b>
              <div class="ayuda">{{ tx(pl.transporte.embarque) }}<template v-if="pl.transporte.eta"> · ETA {{ fmtFecha(pl.transporte.arribo_real || pl.transporte.eta) }}</template></div>
            </template>
            <span v-else class="ayuda">{{ t('Not assigned') }}</span>
          </template>
        </TablaDatos>
      </section>

      <section class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Lines') }}</h3>
        <TablaDatos tabla="factura_resumen_lineas" :columnas="columnasLineas" :filas="f.lineas" :vistas-guardadas="false" :etiqueta="t('Lines')">
          <template #celda-articulo="{ fila: l }"><b>{{ tx(l.estilo) }}</b> · {{ tx(l.color) }} · {{ tx(l.talla) }}<div class="ayuda">{{ t('PO') }} {{ tx(l.oc_numero) }} · {{ tx(l.partida_arancelaria || t('No HS code')) }}</div></template>
          <template #celda-oc="{ fila: l }"><span class="codigo">{{ tx(l.oc_numero) }}</span></template>
          <template #celda-partida="{ fila: l }"><span class="codigo-sac">{{ tx(l.partida_arancelaria || '—') }}</span></template>
          <template #celda-cantidad="{ fila: l }">{{ fmtNum(l.cantidad) }} {{ unidadTxt(l.unidad, l.cantidad) }}</template>
          <template #celda-importe="{ fila: l }">{{ fmtMoneda(l.importe, f.moneda) }}</template>
        </TablaDatos>
      </section>

      <section class="pl-seccion pl-partes">
        <div v-if="f.facturar_a"><h3 class="resumen-titulo">{{ t('Bill to') }}</h3><b>{{ tx(f.facturar_a.razon_social || f.facturar_a.nombre) }}</b>
          <div class="ayuda">{{ tx(f.facturar_a.id_fiscal || '') }}</div><div class="ayuda">{{ tx(f.facturar_a.pais || '') }}</div></div>
        <div v-if="f.notify"><h3 class="resumen-titulo">{{ t('Notify') }}</h3><b>{{ tx(f.notify.nombre) }}</b>
          <div class="ayuda">{{ tx(f.notify.puerto_nombre || f.notify.puerto || '') }}</div><div class="ayuda">{{ tx(f.notify.pais || '') }}</div></div>
      </section>

      <section v-if="actividad.length" class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Recent activity') }}</h3>
        <ul class="linea-tiempo">
          <li v-for="h in actividad" :key="h.id">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<template v-if="h.usuario"> · {{ tx(h.usuario) }}</template></span>
            <span>{{ tx(ACCIONES[h.accion] || h.accion) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </PanelLateral>
</template>
