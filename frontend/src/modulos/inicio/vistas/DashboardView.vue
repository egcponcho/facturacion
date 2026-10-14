<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { datosModo } from '@/composables/useRutas'
import { actual, t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import BarraFlujo from '@/modulos/inicio/componentes/BarraFlujo.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import FiltroPeriodo, { periodoInicial } from '@/componentes/FiltroPeriodo.vue'
import GraficoColumnas from '@/componentes/GraficoColumnas.vue'
import Icono from '@/componentes/Icono.vue'
import TableroEsqueleto from '@/modulos/inicio/componentes/TableroEsqueleto.vue'
import Kpi from '@/componentes/Kpi.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { elegirProveedor, esInterno, nombreProveedor, sesion, ve, vePanel } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { avanceViaje, fmtFecha, fmtFechaHora, fmtMoneda, fmtNum, plural } from '@/nucleo/utils'

const router = useRouter()
const d = ref(null)
const cargando = ref(true)
// Periodo de las gráficas y del resumen: por defecto, el mes en curso
const periodo = ref(periodoInicial())
const marcas = ref([])

const ICONOS_TAREA = { clasificar: 'etiqueta', empacar: 'caja', pl: 'caja', datos: 'editar', correccion: 'alerta', finalizar: 'check', antiguo: 'reloj', embarcar: 'barco', liberacion: 'candado' }

async function cargar() {
  try {
    d.value = await api.get('/dashboard', { proveedor_id: sesion.proveedorId, desde: periodo.value.desde, hasta: periodo.value.hasta, marcas: marcas.value.join(',') })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

const saludo = computed(() => {
  const h = new Date().getHours()
  const nombre = sesion.usuario?.nombre || ''
  return `${h < 12 ? t('Good morning') : h < 19 ? t('Good afternoon') : t('Good evening')}${nombre ? `, ${nombre}` : ''}`
})
const hoy = new Intl.DateTimeFormat(actual.locale, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())

const serie = computed(() => (d.value?.periodo?.facturado.serie || []).map((x) => ({ etiqueta: x.etiqueta, valor: x.importe, detalle: plural(x.facturas, t('invoice'), t('invoices')) })))
const totalPeriodo = computed(() => serie.value.reduce((a, m) => a + m.valor, 0))
const GRANO = { dia: t('per day'), semana: t('per week'), mes: t('per month') }
// Cada cifra del período abre su lista con el mismo período
function rutaPeriodo(clave) {
  const { desde, hasta } = periodo.value
  if (clave === 'facturado') return { path: '/facturas', query: { estado: 'FINALIZADA', desde, hasta } }
  if (clave === 'pls') return { path: '/seguimiento', query: { vista: 'documentos', estado_pl: 'FINALIZADO' } }
  return { path: '/transporte', query: { estado: 'RECIBIDO,ENTREGADO,ARRIBADO', arribo_desde: desde, arribo_hasta: hasta } }
}

const montosTxt = (m) => (m === null || m === undefined ? '—' : m.length ? m.map((x) => fmtMoneda(x.valor, x.moneda)).join(' · ') : '—')

// Avance del viaje entre salida (ETD) y llegada (ETA)
const viaje = avanceViaje
function diasPara(fecha) {
  if (!fecha) return ''
  const dias = Math.round((new Date(fecha).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dias === 0) return t('today')
  return dias > 0 ? t('in {0}', [plural(dias, t('day'), t('days'))]) : t('{0} ago', [plural(-dias, t('day'), t('days'))])
}
function abrirEnvio(e) {
  router.push(esInterno() ? `/transporte/embarques/${e.id}` : `/facturas/${e.factura_ids[0]}?tab=pl`)
}

const TIPO_ALERTA = { recepcion_diferencia: t('Receipt'), conflicto_oc: t('PO import') }
async function resolver(a) {
  try {
    await api.post(`/alertas/${a.id}/resolver`)
    avisar(t('Alert marked as resolved.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

// «Por proveedor» en la tabla común (modo local): un clic en la fila filtra todo el sistema
const columnasProveedores = [
  { clave: 'nombre', texto: t('Supplier'), fija: true, prioridad: 1 },
  // Un monto por moneda (nunca sumados); para ordenar y filtrar, el de la moneda principal
  { clave: 'por_facturar', texto: t('To invoice'), num: true, prioridad: 2, valor: (p) => (p.por_facturar ? p.por_facturar[0]?.valor ?? 0 : null),
    textoValor: (v, p) => montosTxt(p?.por_facturar) },
  { clave: 'en_proceso', texto: t('In process'), num: true, prioridad: 2 },
  { clave: 'pl_abiertos', texto: t('Open PLs'), num: true, prioridad: 2 },
  { clave: 'listas', texto: t('Ready'), num: true, prioridad: 3 },
  { clave: 'en_camino', texto: t('On the way'), num: true, prioridad: 3 },
]

onMounted(cargar)
watch(() => sesion.proveedorId, cargar)
watch(periodo, cargar, { deep: true })
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => cargar(), ['/dashboard'])
</script>

<template>
  <header class="pagina-cabeza tablero-cabeza">
    <div>
      <div class="eyebrow">{{ tx(hoy) }}</div>
      <h1>{{ tx(saludo) }}</h1>
      <p>{{ tx(esInterno() ? (sesion.proveedorId ? t('Showing only {0}.', [nombreProveedor(sesion.proveedorId)]) : t('Summary of all suppliers.')) : t('This is what needs your attention today.')) }}</p>
    </div>
    <div class="acciones">
      <router-link v-if="esInterno()" class="btn" to="/transporte"><Icono nombre="barco" />{{ t('Shipments') }}</router-link>
      <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />{{ t('Invoice from POs') }}</router-link>
    </div>
  </header>

  <TableroEsqueleto v-if="cargando && !d" />
  <template v-if="d">
    <!-- 1. Indicadores operativos: una franja; el primero es la cifra principal -->
    <section v-if="vePanel('indicadores')" class="kpis kpis-heroe" :aria-label="t('Indicators')">
      <Kpi v-for="k in d.kpis" :key="k.clave" :titulo="tx(k.titulo)" :valor="k.valor" :formato="k.formato" :moneda="k.moneda"
           :otras="k.otras || []" :detalle="tx(k.detalle)" :tono="k.tono" @abrir="router.push({ path: k.ruta, query: k.query })" />
    </section>

    <!-- 2. Trabajo del día: lo que necesita atención y los próximos pasos | embarques -->
    <div class="tablero">
      <div class="col">
        <section v-if="vePanel('atencion')" class="panel" :aria-label="t('Needs your attention')">
          <div class="panel-cabeza">
            <div><h2>{{ t('Needs your attention') }}</h2><p>{{ t('What blocks the next step comes first.') }}</p></div>
            <span v-if="d.atencion.length" class="etiqueta">{{ tx(d.atencion.length) }}</span>
          </div>
          <ul v-if="d.atencion.length" class="lista-accion">
            <li v-for="a in d.atencion" :key="a.clave">
              <router-link class="lista-accion-fila" :to="{ path: a.ruta, query: a.query, hash: a.hash || '' }">
                <span class="cifra-tono" :class="`tono-${a.tono}`">{{ fmtNum(a.valor) }}</span>
                <span class="lista-accion-texto"><b>{{ tx(a.titulo) }}</b><small>{{ tx(a.detalle) }}</small></span>
                <Icono nombre="derecha" :tam="16" class="lista-accion-ir" />
              </router-link>
            </li>
          </ul>
          <div v-else class="todo-listo">
            <span class="icono-ok"><Icono nombre="check" :tam="20" /></span>
            <div><b>{{ t('Nothing needs your attention') }}</b><p class="ayuda">{{ t('No blocked products, XF dates or arrivals this week. Documents in progress are counted above.') }}</p></div>
          </div>
        </section>

        <section v-if="vePanel('tareas')" class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Next steps') }}</h2><p>{{ t('Ordered by what unblocks the most work.') }}</p></div>
            <span v-if="d.tareas.length" class="etiqueta">{{ tx(d.tareas_total > d.tareas.length ? t('{0} of {1}', [d.tareas.length, d.tareas_total]) : d.tareas.length) }}</span>
          </div>
          <ul v-if="d.tareas.length" class="lista-accion">
            <li v-for="(txt, i) in d.tareas" :key="i">
              <router-link class="lista-accion-fila" :to="txt.ruta">
                <span class="tarea-icono" :class="txt.tipo"><Icono :nombre="ICONOS_TAREA[txt.tipo] || 'flecha'" :tam="16" /></span>
                <span class="lista-accion-texto"><b>{{ tx(txt.titulo) }}</b><small>{{ tx(txt.detalle) }}</small></span>
                <span class="lista-accion-boton">{{ tx(txt.accion) }}<Icono nombre="derecha" :tam="14" /></span>
              </router-link>
            </li>
          </ul>
          <div v-else class="todo-listo">
            <span class="icono-ok"><Icono nombre="check" :tam="20" /></span>
            <div><b>{{ t('All up to date') }}</b><p class="ayuda">{{ t('No pending invoices or packing lists. When you have POs with a balance, start from “Invoice from POs”.') }}</p></div>
          </div>
        </section>
      </div>

      <div class="col">
        <section v-if="vePanel('envios')" class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Shipments') }}</h2><p>{{ tx(esInterno() ? t('Planned and in-transit shipments.') : t('Shipments carrying your goods.')) }}</p></div>
            <router-link v-if="esInterno()" class="btn btn-chico btn-fantasma" to="/transporte">{{ t('See all') }}<Icono nombre="derecha" :tam="14" /></router-link>
          </div>
          <ul v-if="d.envios.length" class="envios">
            <li v-for="e in d.envios" :key="e.id">
              <button type="button" class="envio" @click="abrirEnvio(e)">
                <span class="envio-cabeza">
                  <span class="envio-modo"><Icono :nombre="datosModo(e.tipo_transporte).icono" :tam="16" /></span>
                  <b class="envio-codigo">{{ tx(e.codigo) }}</b>
                  <EstadoBadge :estado="e.estado" tipo="embarque" />
                  <span class="ayuda separar">{{ plural(e.cajas, t('carton'), t('cartons')) }}</span>
                </span>
                <span class="ruta">
                  <span><b>{{ tx(e.origen || t('Origin')) }}</b><small>{{ tx(e.etd ? fmtFecha(e.etd) : t('No ETD')) }}</small></span>
                  <span class="ruta-riel" aria-hidden="true">
                    <span class="ruta-avance" :style="{ width: `${viaje(e)}%` }"></span>
                    <span v-if="e.estado !== 'PLANIFICADO'" class="ruta-punto" :style="{ left: `${viaje(e)}%` }"></span>
                  </span>
                  <span class="texto-derecha"><b>{{ tx(e.destino || t('Destination')) }}</b><small>{{ tx(e.eta ? fmtFecha(e.eta) : t('No ETA')) }}</small></span>
                </span>
                <span class="ayuda envio-pie">
                  <template v-if="e.eta && e.estado !== 'ARRIBADO'">{{ t('Arrives {0}.', [diasPara(e.eta)]) }} </template>
                  {{ tx(e.facturas.slice(0, 2).join(', ')) }}<template v-if="e.facturas.length > 2">&nbsp;{{ t('and {0} more', [e.facturas.length - 2]) }}</template>
                </span>
              </button>
            </li>
          </ul>
          <p v-else class="ayuda">{{ t('No shipments in progress.') }}</p>
        </section>

        <section v-if="vePanel('contenedores') && d.contenedores.length" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Load units being planned') }}</h2><p>{{ t('Fill rate by volume.') }}</p></div></div>
          <ul class="lista-accion">
            <li v-for="u in d.contenedores" :key="u.id">
              <router-link class="lista-accion-fila" :to="`/transporte/embarques/${u.embarque_id}?unidad=${u.id}`">
                <span class="lista-accion-texto"><b>{{ tx(u.nombre) }} <span class="etiqueta">{{ tx(u.tipo) }}</span></b>
                  <small>{{ tx(u.embarque) }}{{ tx(u.etd ? t(' · departs {0}', [fmtFecha(u.etd)]) : '') }} · {{ fmtNum(u.cbm, 1) }} m³</small></span>
                <span class="lista-accion-medidor" :title="t('Volume {0}% · weight {1}%', [fmtNum(u.pct_cbm ?? 0), fmtNum(u.pct_kg ?? 0)])"><Avance v-if="u.capacidad_cbm || u.capacidad_kg" :porcentaje="u.pct || 0" /></span>
              </router-link>
            </li>
          </ul>
        </section>

        <section v-if="vePanel('alertas') && esInterno() && d.alertas.length" id="alertas" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Alerts') }}</h2><p>{{ t('Receipt differences to claim and conflicts found when loading purchase orders.') }}</p></div></div>
          <ul class="linea-tiempo">
            <li v-for="a in d.alertas" :key="a.id">
              <span class="ayuda">{{ fmtFechaHora(a.creada_en) }}<br /><span class="etiqueta" :class="a.tipo === 'recepcion_diferencia' ? 'error' : 'aviso'">{{ tx(TIPO_ALERTA[a.tipo] || a.tipo) }}</span></span>
              <span class="fila-flex">
                {{ tx(a.mensaje) }}
                <span class="separar"></span>
                <router-link v-if="a.enlace" :to="a.enlace" class="btn btn-chico">{{ t('See') }}</router-link>
                <button class="btn btn-chico" @click="resolver(a)">{{ t('Mark resolved') }}</button>
              </span>
            </li>
          </ul>
        </section>
      </div>
    </div>

    <!-- 3. Desempeño del periodo: filtros arriba, indicadores, gráfica y dónde está la mercancía -->
    <section v-if="vePanel('periodo')" class="panel desempeno" :aria-label="t('Period')">
      <div class="panel-cabeza">
        <div><h2>{{ t('Performance') }}</h2><p>{{ t('{0} – {1}', [fmtFecha(d.periodo.desde), fmtFecha(d.periodo.hasta)]) }}</p></div>
        <div class="fila-flex gap-2">
          <FiltroMulti v-if="d.periodo.marcas.length > 1" v-model="marcas" :etiqueta="t('Brand')" :opciones="d.periodo.marcas.map((m) => ({ valor: m, texto: m }))" @change="cargar" />
          <FiltroPeriodo v-model="periodo" />
        </div>
      </div>
      <div class="kpis kpis-planos">
        <Kpi v-for="k in d.periodo.resumen" :key="k.clave" :titulo="tx(k.titulo)" :valor="k.valor" :formato="k.formato" :moneda="k.moneda"
             :otras="k.otras || []" :detalle="tx(k.detalle)" @abrir="router.push(rutaPeriodo(k.clave))" />
      </div>
      <div class="desempeno-cuerpo">
        <div v-if="ve('precios')">
          <h3 class="subtitulo">{{ t('Invoiced value') }} <span class="ayuda">{{ tx(GRANO[d.periodo.facturado.grano]) }} · {{ tx(d.periodo.facturado.moneda) }}</span></h3>
          <GraficoColumnas v-if="totalPeriodo" :datos="serie" :titulo="t('Invoiced value')" :formato="(v) => fmtMoneda(v, d.periodo.facturado.moneda)" />
          <p v-else-if="!d.periodo.facturado.otras.length" class="vacio">{{ t('No finalized invoices in this period. Try a longer period (quarter or year).') }}</p>
          <p v-if="d.periodo.facturado.otras.length" class="ayuda">{{ t('Also invoiced in other currencies (not in the chart): {0}', [d.periodo.facturado.otras.map((o) => fmtMoneda(o.valor, o.moneda)).join(' · ')]) }}</p>
        </div>
        <div>
          <h3 class="subtitulo">{{ t('Where the goods are') }} <span class="ayuda">{{ t('From PO to load unit, by unit of measure.') }}</span></h3>
          <BarraFlujo :flujo="d.flujo" />
        </div>
      </div>
    </section>

    <!-- 4. Por proveedor (equipo interno) -->
    <section v-if="vePanel('proveedores') && d.proveedores.length" class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('By supplier') }}</h2><p>{{ t('Click one to filter the whole system.') }}</p></div></div>
      <TablaDatos tabla="inicio_proveedores" :columnas="columnasProveedores" :filas="d.proveedores" :vistas-guardadas="false" fila-clicable
                  orden-inicial="nombre:asc" :etiqueta="t('By supplier')" @fila="(p) => elegirProveedor(p.id)">
        <template #celda-nombre="{ fila: p }"><span class="principal-celda">{{ tx(p.nombre) }}</span></template>
        <template #celda-por_facturar="{ fila: p }">{{ tx(montosTxt(p.por_facturar)) }}</template>
        <template #celda-en_proceso="{ fila: p }"><span :title="t('Invoices in draft or correction')">{{ tx(p.en_proceso || '—') }}</span></template>
        <template #celda-pl_abiertos="{ fila: p }"><span :class="{ 'etiqueta aviso': p.pl_abiertos }">{{ tx(p.pl_abiertos || '—') }}</span></template>
        <template #celda-listas="{ fila: p }"><span :class="{ 'etiqueta ok': p.listas }" :title="t('Invoices ready to ship')">{{ tx(p.listas || '—') }}</span></template>
        <template #celda-en_camino="{ fila: p }"><span :title="t('Packing lists in transit or arrived')">{{ tx(p.en_camino || '—') }}</span></template>
      </TablaDatos>
    </section>
  </template>
</template>
