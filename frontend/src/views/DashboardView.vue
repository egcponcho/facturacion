<script setup>
import { actual, t, tx } from '../i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraFlujo from '../components/BarraFlujo.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import FiltroMulti from '../components/FiltroMulti.vue'
import FiltroPeriodo, { periodoInicial } from '../components/FiltroPeriodo.vue'
import GraficoColumnas from '../components/GraficoColumnas.vue'
import Icono from '../components/Icono.vue'
import TableroEsqueleto from '../components/TableroEsqueleto.vue'
import Kpi from '../components/Kpi.vue'
import { elegirProveedor, esInterno, nombreProveedor, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFecha, fmtFechaHora, fmtMoneda, fmtNum, plural } from '../utils'

const router = useRouter()
const d = ref(null)
const cargando = ref(true)
// Periodo de las gráficas y del resumen: por defecto, el mes en curso
const periodo = ref(periodoInicial())
const marcas = ref([])
// El resumen estadístico queda plegado: primero lo que pide atención (se recuerda)
const resumenAbierto = ref((() => { try { return localStorage.getItem('home-resumen') === '1' } catch { return false } })())
watch(resumenAbierto, (v) => { try { localStorage.setItem('home-resumen', v ? '1' : '0') } catch { /* sin almacenamiento */ } })

const ICONOS_KPI = { por_facturar: 'moneda', en_proceso: 'factura', pl_abiertos: 'caja', listas: 'check', tentativas: 'reloj', en_camino: 'barco', riesgo: 'alerta' }
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
const ICONOS_PERIODO = { facturado: 'moneda', pls: 'caja', llegadas: 'barco', clasificados: 'etiqueta' }
const RUTAS_PERIODO = { facturado: '/facturas', pls: '/facturas', llegadas: '/seguimiento', clasificados: '/productos' }

// Avance del viaje entre salida (ETD) y llegada (ETA)
function viaje(e) {
  if (e.estado === 'ARRIBADO') return 100
  if (e.estado !== 'EN_TRANSITO' || !e.etd || !e.eta) return e.estado === 'PLANIFICADO' ? 0 : 50
  const ini = new Date(e.etd).getTime()
  const fin = new Date(e.eta).getTime()
  return Math.max(4, Math.min(96, ((Date.now() - ini) * 100) / Math.max(1, fin - ini)))
}
function diasPara(fecha) {
  if (!fecha) return ''
  const dias = Math.round((new Date(fecha).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dias === 0) return 'today'
  return dias > 0 ? t('in {0}', [plural(dias, t('day'), t('days'))]) : t('{0} ago', [plural(-dias, t('day'), t('days'))])
}
function abrirEnvio(e) {
  router.push(esInterno() ? `/transporte/embarques/${e.id}` : `/facturas/${e.factura_ids[0]}?tab=pl`)
}

async function resolver(a) {
  try {
    await api.post(`/alertas/${a.id}/resolver`)
    avisar(t('Alert marked as resolved.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

onMounted(cargar)
watch(() => sesion.proveedorId, cargar)
watch(periodo, cargar, { deep: true })
</script>

<template>
  <div class="saludo">
    <div>
      <div class="eyebrow">{{ tx(hoy) }}</div>
      <h1>{{ tx(saludo) }}</h1>
      <p v-if="esInterno()">{{ tx(sesion.proveedorId ? t('Showing only {0}.', [nombreProveedor(sesion.proveedorId)]) : t('Summary of all suppliers.')) }}</p>
      <p v-else>{{ t('This is what needs your attention today.') }}</p>
    </div>
    <div class="fila-flex">
      <router-link v-if="esInterno()" class="btn" to="/transporte"><Icono nombre="barco" />{{ t('Shipments') }}</router-link>
      <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />{{ t('Invoice from POs') }}</router-link>
    </div>
  </div>

  <TableroEsqueleto v-if="cargando && !d" />
  <template v-if="d">
    <section class="panel atencion" :aria-label="t('Needs your attention')">
      <div class="panel-cabeza">
        <div><h2>{{ t('Needs your attention') }}</h2><p>{{ t('What blocks the next step comes first. Open any item to see the records already filtered.') }}</p></div>
      </div>
      <ul v-if="d.atencion.length" class="atencion-lista">
        <li v-for="a in d.atencion" :key="a.clave">
          <router-link class="atencion-item" :class="`tono-${a.tono}`" :to="{ path: a.ruta, query: a.query }">
            <span class="atencion-valor">{{ fmtNum(a.valor) }}</span>
            <span class="atencion-texto"><b>{{ tx(a.titulo) }}</b><small>{{ tx(a.detalle) }}</small></span>
            <Icono nombre="derecha" :tam="16" class="atencion-ir" />
          </router-link>
        </li>
      </ul>
      <div v-else class="todo-listo">
        <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
        <div><b>{{ t('Nothing needs your attention') }}</b><p class="ayuda">{{ t('No blocked products, documents to finish, XF dates or arrivals this week.') }}</p></div>
      </div>
    </section>

    <div class="tablero">
      <div class="col">
        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Next steps') }}</h2><p>{{ t('Ordered by what unblocks the most work.') }}</p></div>
            <span v-if="d.tareas.length" class="etiqueta acento">{{ tx(d.tareas.length) }}</span>
          </div>
          <ul v-if="d.tareas.length" class="tareas">
            <li v-for="(txt, i) in d.tareas" :key="i" class="tarea">
              <span class="tarea-icono" :class="txt.tipo"><Icono :nombre="ICONOS_TAREA[txt.tipo] || 'flecha'" :tam="17" /></span>
              <div>
                <div class="tarea-titulo">{{ tx(txt.titulo) }}</div>
                <div class="tarea-detalle">{{ tx(txt.detalle) }}</div>
              </div>
              <router-link class="btn btn-chico" :to="txt.ruta">{{ tx(txt.accion) }}<Icono nombre="derecha" :tam="14" /></router-link>
            </li>
          </ul>
          <div v-else class="todo-listo">
            <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
            <div>
              <b>{{ t('All up to date') }}</b>
              <p class="ayuda">{{ t('No pending invoices or packing lists. When you have POs with a balance, start from “Invoice from POs”.') }}</p>
            </div>
          </div>
        </section>

      </div>
      <div class="col">
        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Shipments') }}</h2><p>{{ tx(esInterno() ? t('Planned and in-transit shipments.') : t('Shipments carrying your goods.')) }}</p></div>
            <router-link v-if="esInterno()" class="btn btn-chico btn-fantasma" to="/transporte">{{ t('See all') }}<Icono nombre="derecha" :tam="14" /></router-link>
          </div>
          <ul v-if="d.envios.length" class="envios">
            <li v-for="e in d.envios" :key="e.id" class="envio">
              <div class="envio-cabeza">
                <Icono :nombre="e.tipo_transporte === 'AEREO' ? 'avion' : e.tipo_transporte === 'TERRESTRE' ? 'camion' : 'barco'" />
                <button class="btn-texto envio-codigo" style="padding: 0; text-decoration: none; color: inherit" @click="abrirEnvio(e)">{{ tx(e.codigo) }}</button>
                <EstadoBadge :estado="e.estado" />
                <span class="ayuda separar">{{ plural(e.packing_lists, 'PL', t('PLs')) }} · {{ plural(e.cajas, t('carton'), t('cartons')) }}</span>
              </div>
              <div class="ruta">
                <span><b>{{ tx(e.origen || t('Origin')) }}</b><br />{{ tx(e.etd ? t('ETD {0}', [fmtFecha(e.etd)]) : t('No ETD')) }}</span>
                <div class="ruta-riel" aria-hidden="true">
                  <div class="ruta-avance" :style="{ width: `${viaje(e)}%` }"></div>
                  <div v-if="e.estado !== 'PLANIFICADO'" class="ruta-punto" :style="{ left: `${viaje(e)}%` }"></div>
                </div>
                <span class="texto-derecha"><b>{{ tx(e.destino || t('Destination')) }}</b><br />{{ tx(e.eta ? t('ETA {0}', [fmtFecha(e.eta)]) : t('No ETA')) }}</span>
              </div>
              <div class="ayuda">
                <template v-if="e.eta && e.estado !== 'ARRIBADO'">{{ t('Arrives {0}.', [diasPara(e.eta)]) }} </template>
                <template v-if="e.tentativos">{{ t('{0} to confirm.', [plural(e.tentativos, t('tentative PL'), t('tentative PLs'))]) }} </template>
                {{ tx(e.facturas.slice(0, 3).join(', ')) }}<template v-if="e.facturas.length > 3"> {{ t('and {0} more', [e.facturas.length - 3]) }}</template>
              </div>
            </li>
          </ul>
          <p v-else class="ayuda">{{ t('No shipments in progress.') }}</p>
        </section>

        <section v-if="esInterno()" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Import alerts') }}</h2><p>{{ t('Conflicts found when loading purchase orders.') }}</p></div></div>
          <p v-if="!d.alertas.length" class="ayuda">{{ t('No open conflicts.') }}</p>
          <ul v-else class="linea-tiempo">
            <li v-for="a in d.alertas" :key="a.id">
              <span class="ayuda">{{ fmtFechaHora(a.creada_en) }}</span>
              <span class="fila-flex">{{ tx(a.mensaje) }}<button class="btn btn-chico separar" @click="resolver(a)">{{ t('Mark resolved') }}</button></span>
            </li>
          </ul>
        </section>
      </div>
    </div>

    <h2 class="titulo-seccion">{{ t('Overview') }}</h2>
    <section class="kpis" :aria-label="t('Indicators')">
      <Kpi v-for="k in d.kpis" :key="k.clave" :titulo="tx(k.titulo)" :valor="k.valor" :formato="k.formato" :moneda="k.moneda"
           :detalle="tx(k.detalle)" :tono="k.tono" :icono="ICONOS_KPI[k.clave]" @abrir="router.push({ path: k.ruta, query: k.query })" />
    </section>


    <details class="resumen-plegable" :open="resumenAbierto" @toggle="resumenAbierto = $event.target.open">
      <summary>{{ t('Period summary and charts') }}<span class="ayuda">{{ t('Invoiced, packed, arrivals and classification in the selected period.') }}</span></summary>
    <section class="panel periodo-panel" :aria-label="t('Period')">
      <div class="panel-cabeza">
        <div><h2>{{ t('In the period') }}</h2><p>{{ t('What happened in the selected period; the chart below uses it too.') }}</p></div>
        <div class="fila-flex" style="gap: 8px">
          <FiltroMulti v-if="d.periodo.marcas.length > 1" v-model="marcas" :etiqueta="t('Brand')" :opciones="d.periodo.marcas.map((m) => ({ valor: m, texto: m }))" @change="cargar" />
          <FiltroPeriodo v-model="periodo" />
        </div>
      </div>
      <div class="kpis kpis-periodo">
        <Kpi v-for="k in d.periodo.resumen" :key="k.clave" :titulo="tx(k.titulo)" :valor="k.valor" :formato="k.formato" :moneda="k.moneda"
             :detalle="tx(k.detalle)" :icono="ICONOS_PERIODO[k.clave]" @abrir="router.push(RUTAS_PERIODO[k.clave])" />
      </div>
    </section>

      <div class="tablero">
        <div class="col">
        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Invoiced') }}</h2><p>{{ t('Finalized invoices {0}, {1} – {2} ({3}{4}).', [GRANO[d.periodo.facturado.grano], fmtFecha(d.periodo.desde), fmtFecha(d.periodo.hasta), d.moneda, marcas.length ? ` · ${marcas.join(', ')}` : '']) }}</p></div>
            <b>{{ fmtMoneda(totalPeriodo, d.moneda) }}</b>
          </div>
          <GraficoColumnas v-if="totalPeriodo" :datos="serie" :titulo="t('Invoiced value')" :formato="(v) => fmtMoneda(v, d.moneda)" />
          <p v-else class="ayuda">{{ t('No finalized invoices in this period. Try a longer period (quarter or year).') }}</p>
        </section>

        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>{{ t('Where the goods are') }}</h2><p>{{ t('From PO to load unit, by unit of measure.') }}</p></div>
          </div>
          <BarraFlujo :flujo="d.flujo" />
        </section>

        </div>
        <div class="col">
        <section v-if="d.proveedores.length" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('By supplier') }}</h2><p>{{ t('Click one to filter the whole system.') }}</p></div></div>
          <div class="tabla-marco" style="box-shadow: none">
            <table class="tabla" v-tarjetas>
              <thead>
                <tr>
                  <th>{{ t('Supplier') }}</th>
                  <th class="num">{{ t('To invoice') }}</th>
                  <th class="num" :title="t('Invoices in draft or correction')">{{ t('In process') }}</th>
                  <th class="num">{{ t('Open PLs') }}</th>
                  <th class="num" :title="t('Invoices ready to ship')">{{ t('Ready') }}</th>
                  <th class="num" :title="t('Packing lists in transit or arrived')">{{ t('On the way') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in d.proveedores" :key="p.id" class="clicable" @click="elegirProveedor(p.id)">
                  <td class="principal-celda">{{ tx(p.nombre) }}</td>
                  <td class="num">{{ fmtMoneda(p.por_facturar, d.moneda) }}</td>
                  <td class="num">{{ tx(p.en_proceso || '—') }}</td>
                  <td class="num"><span :class="{ 'etiqueta aviso': p.pl_abiertos }">{{ tx(p.pl_abiertos || '—') }}</span></td>
                  <td class="num"><span :class="{ 'etiqueta ok': p.listas }">{{ tx(p.listas || '—') }}</span></td>
                  <td class="num">{{ tx(p.en_camino || '—') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section v-if="d.contenedores.length" class="panel">
          <div class="panel-cabeza"><div><h2>{{ t('Load units being planned') }}</h2><p>{{ t('Fill rate by volume.') }}</p></div></div>
          <div class="contenedores">
            <router-link v-for="u in d.contenedores" :key="u.id" class="contenedor-mini" :to="`/transporte/embarques/${u.embarque_id}?unidad=${u.id}`">
              <span class="fila-flex"><span class="nombre">{{ tx(u.nombre) }}</span><span class="etiqueta">{{ tx(u.tipo) }}</span></span>
              <span class="ayuda">{{ tx(u.embarque) }}{{ tx(u.etd ? t(' · departs {0}', [fmtFecha(u.etd)]) : '') }}</span>
              <Avance v-if="u.capacidad_cbm" :porcentaje="u.pct_cbm || 0" />
              <span class="ayuda">{{ fmtNum(u.cbm, 1) }} m³ · {{ plural(u.packing_lists, 'PL', t('PLs')) }}<template v-if="u.tentativas"> {{ t('· {0} tentative', [u.tentativas]) }}</template></span>
            </router-link>
          </div>
        </section>

        </div>
      </div>
    </details>
  </template>
</template>
