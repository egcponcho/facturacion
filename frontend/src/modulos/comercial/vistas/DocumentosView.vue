<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import NavComercial from '@/modulos/comercial/componentes/NavComercial.vue'
import { estadosCobro, estadosDocumento } from '@/nucleo/estados.js'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { fmtFecha, fmtMoneda } from '@/nucleo/utils'

const ESTADOS_COBRO = estadosCobro()
const ESTADOS_DOCUMENTO = estadosDocumento()

// Documentos comerciales: ventas (emitidos) y compras (recibidos, incluidas las
// facturas de proveedor finalizadas), con su saldo y su estado de cobro
const route = useRoute()
const router = useRouter()
const tabla = ref(null)
const filtros = reactive({ direccion: route.query.direccion || 'EMITIDO', q: route.query.q || '', cobro: route.query.cobro || '' })
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)

const DIRECCIONES = [['EMITIDO', t('Sales')], ['RECIBIDO', t('Purchases')], ['', t('All')]]
const COBROS = [['', t('Any balance')], ...ESTADOS_COBRO]
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Document'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'tipo', texto: t('Type'), prioridad: 2 },
  { clave: 'tercero', texto: filtros.direccion === 'RECIBIDO' ? t('Supplier') : filtros.direccion === 'EMITIDO' ? t('Customer') : t('Business partner'), prioridad: 1 },
  { clave: 'fecha', texto: t('Date'), prioridad: 2, textoValor: (v) => fmtFecha(v) },
  { clave: 'vencimiento', texto: t('Due date'), prioridad: 3, filtro: false },
  { clave: 'sociedad', texto: t('Company'), prioridad: 3, inicial: false },
  { clave: 'moneda', texto: t('Currency'), prioridad: 3, inicial: false },
  { clave: 'total', texto: t('Total'), num: true, prioridad: 1, filtro: false },
  { clave: 'saldo', texto: t('Balance'), num: true, prioridad: 2, ordenable: false, filtro: false },
  { clave: 'estado', texto: t('Status'), prioridad: 2, opciones: ESTADOS_DOCUMENTO },
  { clave: 'estado_cobro', texto: t('Payment status'), prioridad: 2, ordenable: false, filtro: false },
])
const externosApi = () => ({ direccion: filtros.direccion || undefined, q: filtros.q || undefined, cobro: filtros.cobro || undefined })
const valores = (columna, buscar, otros) => api.get('/documentos/valores', { columna, buscar, f: JSON.stringify(otros), ...externosApi() })

let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/documentos', { ...externosApi(), orden: c.orden, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
    router.replace({ query: { ...(filtros.direccion !== 'EMITIDO' && { direccion: filtros.direccion }), ...(filtros.q && { q: filtros.q }),
      ...(filtros.cobro && { cobro: filtros.cobro }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Billing and payments') }}</h1>
      <p>{{ t('Invoices, credit and debit notes you issue and receive, with their balance. Supplier invoices appear here once finalized.') }}</p>
    </div>
    <div class="acciones">
      <router-link v-if="puede('comercial.editar')" class="btn btn-primario" to="/comercial/documentos/nuevo"><Icono nombre="mas" />{{ t('New document') }}</router-link>
    </div>
  </div>
  <NavComercial />

  <TablaDatos ref="tabla" tabla="documentos_comerciales" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total"
              :cargando="cargando" fila-clicable :etiqueta="t('Documents')" :valores="valores" :externos="{ direccion: filtros.direccion, q: filtros.q, cobro: filtros.cobro }"
              @consulta="consultar" @fila="(d) => router.push(`/comercial/documentos/${d.id}`)">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search number or business partner')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <div class="segmentos" role="group" :aria-label="t('Direction')">
        <button v-for="[v, txt] in DIRECCIONES" :key="v" class="segmento" type="button" :aria-pressed="filtros.direccion === v" @click="filtros.direccion = v; recargar()">{{ tx(txt) }}</button>
      </div>
      <div class="segmentos" role="group" :aria-label="t('Payment status')">
        <button v-for="[v, txt] in COBROS" :key="v" class="segmento" type="button" :aria-pressed="filtros.cobro === v" @click="filtros.cobro = v; recargar()">{{ tx(txt) }}</button>
      </div>
    </template>
    <template #celda-nombre="{ fila: d }">
      <router-link :to="`/comercial/documentos/${d.id}`" class="enlace-doc" @click.stop><strong class="codigo">{{ tx(d.estado === 'BORRADOR' && !d.numero && !d.referencia_externa ? t('Draft') : d.nombre) }}</strong></router-link>
      <span class="sub">{{ tx(d.tipo_nombre) }}</span>
    </template>
    <template #celda-tipo="{ fila: d }">{{ tx(d.tipo_nombre) }}</template>
    <template #celda-fecha="{ fila: d }">{{ fmtFecha(d.fecha) }}</template>
    <template #celda-vencimiento="{ fila: d }">{{ fmtFecha(d.fecha_vencimiento) }}</template>
    <template #celda-total="{ fila: d }"><span class="fuerte">{{ fmtMoneda(d.signo < 0 ? -d.total : d.total, d.moneda) }}</span></template>
    <template #celda-saldo="{ fila: d }">{{ d.estado === 'EMITIDO' ? fmtMoneda(d.saldo, d.moneda) : '—' }}</template>
    <template #celda-estado="{ fila: d }"><EstadoBadge :estado="d.estado" tipo="documento" /></template>
    <template #celda-estado_cobro="{ fila: d }"><EstadoBadge v-if="d.estado_cobro" :estado="d.estado_cobro" tipo="cobro" /><span v-else class="apagado">—</span></template>
    <template #acciones><Icono nombre="derecha" :tam="16" /></template>
    <template #vacio>
      <div v-if="filtros.q || filtros.cobro" class="vacio">{{ t('No documents match these filters.') }}</div>
      <EstadoVacio v-else icono="factura" :titulo="t('There are no documents yet.')"
                   :texto="t('Issue invoices to your customers, register what your suppliers bill you and keep track of what is pending.')">
        <router-link v-if="puede('comercial.editar')" class="btn btn-primario" to="/comercial/documentos/nuevo"><Icono nombre="mas" />{{ t('New document') }}</router-link>
      </EstadoVacio>
    </template>
  </TablaDatos>
</template>
