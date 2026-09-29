<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraFlujo from '../components/BarraFlujo.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import GraficoColumnas from '../components/GraficoColumnas.vue'
import Icono from '../components/Icono.vue'
import Kpi from '../components/Kpi.vue'
import { elegirProveedor, esInterno, nombreProveedor, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFecha, fmtFechaHora, fmtMoneda, fmtNum, plural } from '../utils'

const router = useRouter()
const d = ref(null)
const cargando = ref(true)

const ICONOS_KPI = { por_facturar: 'moneda', en_proceso: 'factura', pl_abiertos: 'caja', listas: 'check', tentativas: 'reloj', en_camino: 'barco' }
const ICONOS_TAREA = { empacar: 'caja', pl: 'caja', datos: 'editar', correccion: 'alerta', finalizar: 'check', antiguo: 'reloj', embarcar: 'barco' }
const MES = new Intl.DateTimeFormat('es', { month: 'short' })

async function cargar() {
  try {
    d.value = await api.get('/dashboard', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

const saludo = computed(() => {
  const h = new Date().getHours()
  const nombre = sesion.usuario?.nombre || ''
  return `${h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'}${nombre ? `, ${nombre}` : ''}`
})
const hoy = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())

const meses = computed(() => (d.value?.facturado_mes || []).map((m) => {
  const [a, mm] = m.mes.split('-')
  return { etiqueta: MES.format(new Date(Number(a), Number(mm) - 1, 1)).replace('.', ''), valor: m.importe, detalle: plural(m.facturas, 'factura', 'facturas') }
}))
const totalSeisMeses = computed(() => meses.value.reduce((a, m) => a + m.valor, 0))

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
  if (dias === 0) return 'hoy'
  return dias > 0 ? `en ${plural(dias, 'día', 'días')}` : `hace ${plural(-dias, 'día', 'días')}`
}
function abrirEnvio(e) {
  router.push(esInterno() ? `/transporte/embarques/${e.id}` : `/facturas/${e.factura_ids[0]}?tab=pl`)
}

async function resolver(a) {
  try {
    await api.post(`/alertas/${a.id}/resolver`)
    avisar('Alerta marcada como resuelta.')
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

onMounted(cargar)
watch(() => sesion.proveedorId, cargar)
</script>

<template>
  <div class="saludo">
    <div>
      <div class="eyebrow">{{ hoy }}</div>
      <h1>{{ saludo }}</h1>
      <p v-if="esInterno()">{{ sesion.proveedorId ? `Viendo solo ${nombreProveedor(sesion.proveedorId)}.` : 'Resumen de todos los proveedores.' }}</p>
      <p v-else>Esto es lo que necesita tu atención hoy.</p>
    </div>
    <div class="fila-flex">
      <router-link v-if="esInterno()" class="btn" to="/transporte"><Icono nombre="barco" />Embarques</router-link>
      <router-link class="btn btn-primario" to="/ordenes"><Icono nombre="mas" />Facturar desde OCs</router-link>
    </div>
  </div>

  <p v-if="cargando" class="ayuda">Cargando el tablero…</p>
  <template v-if="d">
    <section class="kpis" aria-label="Indicadores">
      <Kpi v-for="k in d.kpis" :key="k.clave" :titulo="k.titulo" :valor="k.valor" :formato="k.formato" :moneda="k.moneda"
           :detalle="k.detalle" :tono="k.tono" :icono="ICONOS_KPI[k.clave]" @abrir="router.push({ path: k.ruta, query: k.query })" />
    </section>

    <div class="tablero">
      <div class="col">
        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>Próximos pasos</h2><p>Ordenados por lo que destraba más trabajo.</p></div>
            <span v-if="d.tareas.length" class="etiqueta acento">{{ d.tareas.length }}</span>
          </div>
          <ul v-if="d.tareas.length" class="tareas">
            <li v-for="(t, i) in d.tareas" :key="i" class="tarea">
              <span class="tarea-icono" :class="t.tipo"><Icono :nombre="ICONOS_TAREA[t.tipo] || 'flecha'" :tam="17" /></span>
              <div>
                <div class="tarea-titulo">{{ t.titulo }}</div>
                <div class="tarea-detalle">{{ t.detalle }}</div>
              </div>
              <router-link class="btn btn-chico" :to="t.ruta">{{ t.accion }}<Icono nombre="derecha" :tam="14" /></router-link>
            </li>
          </ul>
          <div v-else class="todo-listo">
            <span class="icono-ok"><Icono nombre="check" :tam="22" /></span>
            <div>
              <b>Todo al día</b>
              <p class="ayuda">No hay facturas ni packing lists pendientes. Cuando tengas OCs con saldo, empieza desde “Facturar desde OCs”.</p>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>Dónde está la mercancía</h2><p>De la OC al contenedor, por unidad de medida.</p></div>
          </div>
          <BarraFlujo :flujo="d.flujo" />
        </section>

        <section v-if="d.proveedores.length" class="panel">
          <div class="panel-cabeza"><div><h2>Por proveedor</h2><p>Haz clic en uno para filtrar todo el sistema.</p></div></div>
          <div class="tabla-marco" style="box-shadow: none">
            <table class="tabla">
              <thead>
                <tr>
                  <th>Proveedor</th>
                  <th class="num">Por facturar</th>
                  <th class="num" title="Facturas en borrador o corrección">En proceso</th>
                  <th class="num">PL abiertos</th>
                  <th class="num" title="Facturas listas para embarcar">Listas</th>
                  <th class="num" title="Packing lists en tránsito o arribados">En camino</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in d.proveedores" :key="p.id" class="clicable" @click="elegirProveedor(p.id)">
                  <td class="principal-celda">{{ p.nombre }}</td>
                  <td class="num">{{ fmtMoneda(p.por_facturar, d.moneda) }}</td>
                  <td class="num">{{ p.en_proceso || '—' }}</td>
                  <td class="num"><span :class="{ 'etiqueta aviso': p.pl_abiertos }">{{ p.pl_abiertos || '—' }}</span></td>
                  <td class="num"><span :class="{ 'etiqueta ok': p.listas }">{{ p.listas || '—' }}</span></td>
                  <td class="num">{{ p.en_camino || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div class="col">
        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>Facturado por mes</h2><p>Facturas finalizadas, últimos 6 meses ({{ d.moneda }}).</p></div>
            <b>{{ fmtMoneda(totalSeisMeses, d.moneda) }}</b>
          </div>
          <GraficoColumnas v-if="totalSeisMeses" :datos="meses" titulo="Valor facturado por mes" :formato="(v) => fmtMoneda(v, d.moneda)" />
          <p v-else class="ayuda">Aún no hay facturas finalizadas en este periodo.</p>
        </section>

        <section class="panel">
          <div class="panel-cabeza">
            <div><h2>Envíos</h2><p>{{ esInterno() ? 'Embarques planificados y en camino.' : 'Embarques con tu mercancía.' }}</p></div>
            <router-link v-if="esInterno()" class="btn btn-chico btn-fantasma" to="/transporte">Ver todos<Icono nombre="derecha" :tam="14" /></router-link>
          </div>
          <ul v-if="d.envios.length" class="envios">
            <li v-for="e in d.envios" :key="e.id" class="envio">
              <div class="envio-cabeza">
                <Icono :nombre="e.tipo_transporte === 'AEREO' ? 'avion' : e.tipo_transporte === 'TERRESTRE' ? 'camion' : 'barco'" />
                <button class="btn-texto envio-codigo" style="padding: 0; text-decoration: none; color: inherit" @click="abrirEnvio(e)">{{ e.codigo }}</button>
                <EstadoBadge :estado="e.estado" />
                <span class="ayuda separar">{{ plural(e.packing_lists, 'PL', 'PL') }} · {{ plural(e.cajas, 'caja', 'cajas') }}</span>
              </div>
              <div class="ruta">
                <span><b>{{ e.origen || 'Origen' }}</b><br />{{ e.etd ? `ETD ${fmtFecha(e.etd)}` : 'Sin ETD' }}</span>
                <div class="ruta-riel" aria-hidden="true">
                  <div class="ruta-avance" :style="{ width: `${viaje(e)}%` }"></div>
                  <div v-if="e.estado !== 'PLANIFICADO'" class="ruta-punto" :style="{ left: `${viaje(e)}%` }"></div>
                </div>
                <span class="texto-derecha"><b>{{ e.destino || 'Destino' }}</b><br />{{ e.eta ? `ETA ${fmtFecha(e.eta)}` : 'Sin ETA' }}</span>
              </div>
              <div class="ayuda">
                <template v-if="e.eta && e.estado !== 'ARRIBADO'">Llega {{ diasPara(e.eta) }}. </template>
                <template v-if="e.tentativos">{{ plural(e.tentativos, 'PL tentativo', 'PL tentativos') }} por confirmar. </template>
                {{ e.facturas.slice(0, 3).join(', ') }}<template v-if="e.facturas.length > 3"> y {{ e.facturas.length - 3 }} más</template>
              </div>
            </li>
          </ul>
          <p v-else class="ayuda">No hay embarques en curso.</p>
        </section>

        <section v-if="d.contenedores.length" class="panel">
          <div class="panel-cabeza"><div><h2>Contenedores en planificación</h2><p>Ocupación por volumen.</p></div></div>
          <div class="contenedores">
            <router-link v-for="u in d.contenedores" :key="u.id" class="contenedor-mini" :to="`/transporte/embarques/${u.embarque_id}?unidad=${u.id}`">
              <span class="fila-flex"><span class="nombre">{{ u.nombre }}</span><span class="etiqueta">{{ u.tipo }}</span></span>
              <span class="ayuda">{{ u.embarque }}{{ u.etd ? ` · sale ${fmtFecha(u.etd)}` : '' }}</span>
              <Avance v-if="u.capacidad_cbm" :porcentaje="u.pct_cbm || 0" />
              <span class="ayuda">{{ fmtNum(u.cbm, 1) }} m³ · {{ plural(u.packing_lists, 'PL', 'PL') }}<template v-if="u.tentativas"> · {{ u.tentativas }} tentativos</template></span>
            </router-link>
          </div>
        </section>

        <section v-if="esInterno()" class="panel">
          <div class="panel-cabeza"><div><h2>Alertas de importación</h2><p>Conflictos al cargar OCs desde SAP.</p></div></div>
          <p v-if="!d.alertas.length" class="ayuda">No hay conflictos abiertos.</p>
          <ul v-else class="linea-tiempo">
            <li v-for="a in d.alertas" :key="a.id">
              <span class="ayuda">{{ fmtFechaHora(a.creada_en) }}</span>
              <span class="fila-flex">{{ a.mensaje }}<button class="btn btn-chico separar" @click="resolver(a)">Marcar resuelta</button></span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </template>
</template>
