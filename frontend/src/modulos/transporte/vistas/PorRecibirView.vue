<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { errorApi } from '@/stores/ui'
import { fmtCant, fmtFecha } from '@/nucleo/utils'

// Recepción (diseño v3): la bandeja de bodega. «Por recibir» son las unidades
// de carga de los embarques en camino o ya llegados que faltan por contar; las
// que ya llegaron se abren en su recepción y las que vienen en camino se ven con
// su ETA para planear el trabajo. «Recibidas» son las ya contadas, con sus
// diferencias. La vista elegida queda en la dirección (?vista=recibidas).
const route = useRoute()
const router = useRouter()
const vista = ref(route.query.vista === 'recibidas' ? 'recibidas' : 'pendientes')
const filas = ref([])
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    filas.value = await api.get('/recepciones', { vista: vista.value })
  } catch (err) {
    errorApi(err)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
function cambiarVista(v) {
  router.replace({ query: v === 'pendientes' ? {} : { vista: v } })
  cargar()
}
alCambiar(() => cargar(), ['/recepciones', '/transporte'])

const VISTAS = [['pendientes', t('To receive')], ['recibidas', t('Received units')]]
const pendientes = computed(() => vista.value === 'pendientes')
const proveedores = (f) => f.proveedores.join(', ')

// Las columnas cambian con la vista: por recibir importa cuándo llega y qué
// falta; en las recibidas, cuándo se recibió y con cuántas diferencias.
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Load unit'), fija: true, prioridad: 1 },
  { clave: 'embarque', texto: t('Shipment'), prioridad: 2, textoValor: (v) => v?.codigo || '', exporta: (f) => f.embarque.codigo },
  { clave: 'centro', texto: t('Warehouse'), prioridad: 2 },
  { clave: 'proveedores', texto: t('Suppliers'), prioridad: 3, textoValor: (v) => (v || []).join(', '), exporta: proveedores },
  ...(pendientes.value
    ? [
        { clave: 'eta', texto: t('ETA'), prioridad: 2, textoValor: (v, f) => fmtFecha(f?.arribo_real || v) },
        { clave: 'enviado', texto: t('Shipped'), num: true, prioridad: 3 },
        { clave: 'pendiente', texto: t('Pending'), num: true, prioridad: 1 },
      ]
    : [
        { clave: 'recibida_en', texto: t('Received on'), prioridad: 2, textoValor: (v) => fmtFecha(v) },
        { clave: 'recibido', texto: t('Received'), num: true, prioridad: 2 },
        { clave: 'danado', texto: t('Damaged'), num: true, prioridad: 3 },
        { clave: 'diferencias', texto: t('Differences'), num: true, prioridad: 1 },
      ]),
  { clave: 'recepcion_estado', texto: t('Status'), prioridad: 1 },
])
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Receiving') }}</h1>
      <p>{{ t('Load units to count at the warehouse and the ones already received. Units still on the way show their ETA so the work can be planned.') }}</p>
    </div>
  </div>

  <TablaDatos :key="vista" :tabla="`recepcion-${vista}`" :columnas="columnas" :filas="filas" clave-fila="id" :cargando="cargando" :etiqueta="t('Receiving')">
    <template #barra>
      <Segmentos v-model="vista" :opciones="VISTAS" :etiqueta="t('View')" @change="cambiarVista" />
    </template>
    <template #celda-nombre="{ fila: f }">
      <router-link :to="`/transporte/unidades/${f.id}/recepcion`" class="enlace"><b class="codigo">{{ tx(f.nombre) }}</b></router-link>
      <span class="sub">{{ tx(f.tipo || '') }} · {{ t('{0} packing lists', [f.listas]) }}</span>
    </template>
    <template #celda-embarque="{ fila: f }">
      <router-link :to="`/transporte/embarques/${f.embarque.id}`" class="enlace">{{ tx(f.embarque.codigo) }}</router-link>
      <span class="sub"><EstadoBadge :estado="f.embarque.estado" tipo="embarque" /></span>
    </template>
    <template #celda-centro="{ fila: f }">{{ tx(f.centro || '') }}</template>
    <template #celda-proveedores="{ fila: f }">{{ tx(proveedores(f)) }}</template>
    <template #celda-eta="{ fila: f }">
      <template v-if="f.arribo_real">{{ fmtFecha(f.arribo_real) }}<span class="sub">{{ t('Arrived') }}</span></template>
      <template v-else>{{ fmtFecha(f.eta) }}<span class="sub">{{ t('Expected') }}</span></template>
    </template>
    <template #celda-enviado="{ fila: f }">{{ fmtCant(f.enviado) }}</template>
    <template #celda-pendiente="{ fila: f }"><b>{{ fmtCant(f.pendiente) }}</b></template>
    <template #celda-recibida_en="{ fila: f }">{{ fmtFecha(f.recibida_en) }}</template>
    <template #celda-recibido="{ fila: f }">{{ fmtCant(f.recibido) }}</template>
    <template #celda-danado="{ fila: f }"><span :class="{ 'texto-aviso': f.danado > 0 }">{{ fmtCant(f.danado) }}</span></template>
    <template #celda-diferencias="{ fila: f }"><span :class="{ 'texto-aviso': f.diferencias > 0 }">{{ f.diferencias }}</span></template>
    <template #celda-recepcion_estado="{ fila: f }">
      <router-link v-if="pendientes && f.puede_recibir" :to="`/transporte/unidades/${f.id}/recepcion`" class="btn btn-chico">{{ t('Receive') }}</router-link>
      <EstadoBadge v-else :estado="f.recepcion_estado" tipo="recepcion" />
    </template>
    <template #vacio>
      <Icono nombre="bandeja" :tam="28" />
      <p>{{ pendientes ? t('Nothing to receive. Units appear here when their shipment is on the way.') : t('No units received yet.') }}</p>
    </template>
  </TablaDatos>
</template>
