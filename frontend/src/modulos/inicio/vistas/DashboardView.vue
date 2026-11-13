<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { actual, t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Avance from '@/componentes/Avance.vue'
import BarraFlujo from '@/modulos/inicio/componentes/BarraFlujo.vue'
import BloqueEnvios from '@/modulos/inicio/componentes/BloqueEnvios.vue'
import BloqueProveedores from '@/modulos/inicio/componentes/BloqueProveedores.vue'
import GraficoComprasRecepcion from '@/modulos/inicio/componentes/GraficoComprasRecepcion.vue'
import Icono from '@/componentes/Icono.vue'
import IndicadorInicio from '@/modulos/inicio/componentes/IndicadorInicio.vue'
import MiBandeja from '@/modulos/inicio/componentes/MiBandeja.vue'
import PersonalizarPanel from '@/modulos/inicio/componentes/PersonalizarPanel.vue'
import TableroEsqueleto from '@/modulos/inicio/componentes/TableroEsqueleto.vue'
import { esInterno, nombreProveedor, puede, sesion, ve, vePanel } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFecha, fmtFechaHora, fmtNum } from '@/nucleo/utils'

// Inicio (diseño v3): primero «Mi bandeja» (lo que hay que hacer hoy), a su lado
// cuatro indicadores elegidos y debajo una sola gráfica, comprado contra
// recibido. Lo demás (embarques en curso, cumplimiento por proveedor, cadena de
// suministro…) vive en el tablero ejecutivo y cada persona lo trae a su Inicio
// en «Personalizar panel». Nada se repite: lo que ya está en un indicador no
// vuelve a aparecer como tarjeta.
const d = ref(null)
const kpis = ref(null)
const cargando = ref(true)
const personalizando = ref(false)
const grafico = ref(null)

async function cargar() {
  try {
    d.value = await api.get('/dashboard', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
// Los cuatro indicadores (tableros/inicio); sin ninguno que el rol vea, el bloque no aparece
async function cargarIndicadores() {
  try {
    kpis.value = await api.get('/tableros/inicio')
  } catch {
    kpis.value = null
  }
}

// ---- Bloques: los que la persona eligió, dentro de lo que su rol muestra ----
const BLOQUES = computed(() => [
  { clave: 'bandeja', titulo: t('My inbox'), texto: t('What you have to do today, with its button.'), icono: 'bandeja', ve: vePanel('atencion') || vePanel('tareas') },
  { clave: 'indicadores', titulo: t('Indicators'), texto: t('Your four indicators with their trend.'), icono: 'grafica', ve: vePanel('indicadores') },
  { clave: 'grafico', titulo: t('Purchased vs. received'), texto: t('Monthly value bought and received at the warehouse.'), icono: 'grafica',
    ve: vePanel('periodo') && puede('oc.ver') && ve('precios') },
  { clave: 'envios', titulo: t('Shipments in progress'), texto: t('Planned and in-transit shipments with their route.'), icono: 'camion', ve: vePanel('envios') },
  { clave: 'proveedores', titulo: t('By supplier'), texto: t('Balance and documents of each supplier.'), icono: 'usuarios', ve: vePanel('proveedores') && esInterno() },
  { clave: 'flujo', titulo: t('Supply chain'), texto: t('Where the goods are, from PO to load unit.'), icono: 'ruta', ve: vePanel('periodo') },
  { clave: 'contenedores', titulo: t('Load units being planned'), texto: t('Fill rate by volume.'), icono: 'contenedor', ve: vePanel('contenedores') && esInterno() },
  { clave: 'alertas', titulo: t('Alerts'), texto: t('Receipt differences and conflicts when loading POs.'), icono: 'alerta', ve: vePanel('alertas') && esInterno() },
].filter((b) => b.ve))
const DE_FABRICA = ['bandeja', 'indicadores', 'grafico']
const elegidos = computed(() => {
  const propios = sesion.usuario?.preferencias?.inicio_bloques
  return Array.isArray(propios) ? propios : DE_FABRICA
})
const mostrar = (clave) => elegidos.value.includes(clave) && BLOQUES.value.some((b) => b.clave === clave)
// Lo que aún se puede agregar (para la invitación al pie)
const porAgregar = computed(() => BLOQUES.value.filter((b) => !elegidos.value.includes(b.clave)))

// ---- Mi bandeja: atención + tareas + alertas, lo urgente primero ----
const MODULO_DE = { '/productos': t('Products'), '/seguimiento': t('Tracking'), '/transporte': t('Transport'), '/facturas': t('Dispatch'),
  '/ordenes': t('Purchasing'), '/': t('Receipt') }
const moduloDe = (ruta) => MODULO_DE[Object.keys(MODULO_DE).find((p) => p !== '/' && ruta.startsWith(p)) || (ruta === '/' ? '/' : '')] || ''
const bandeja = computed(() => {
  if (!d.value) return []
  const items = []
  for (const a of d.value.atencion) {
    items.push({ clave: `a-${a.clave}`, titulo: `${tx(a.titulo)}: ${fmtNum(a.valor)}`, detalle: a.detalle, modulo: moduloDe(a.ruta),
      a: { path: a.ruta, query: a.query, hash: a.hash || '' }, accion: t('Review'), urgente: a.tono === 'error' })
  }
  // Lo que antes iba en la franja de indicadores y pide acción (OC que llegan tarde, PL sin contenedor)
  for (const k of d.value.kpis.filter((x) => x.tono === 'alerta' && x.valor && ['riesgo', 'listas'].includes(x.clave))) {
    items.push({ clave: `k-${k.clave}`, titulo: `${tx(k.titulo)}: ${fmtNum(k.valor)}`, detalle: k.detalle, modulo: moduloDe(k.ruta),
      a: { path: k.ruta, query: k.query }, accion: t('Review'), urgente: k.clave === 'riesgo' })
  }
  d.value.tareas.forEach((x, i) => items.push({ clave: `t-${i}`, titulo: x.titulo, detalle: x.detalle, modulo: moduloDe(x.ruta),
    a: x.ruta, accion: x.accion, urgente: x.prioridad <= 0 }))
  return [...items.filter((x) => x.urgente), ...items.filter((x) => !x.urgente)]
})
const urgentes = computed(() => bandeja.value.filter((x) => x.urgente).length)

const saludo = computed(() => {
  const h = new Date().getHours()
  const nombre = sesion.usuario?.nombre || ''
  return `${h < 12 ? t('Good morning') : h < 19 ? t('Good afternoon') : t('Good evening')}${nombre ? `, ${nombre}` : ''}`
})
const hoy = new Intl.DateTimeFormat(actual.locale, { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())
const resumen = computed(() => [
  hoy,
  bandeja.value.length ? t('{0} tasks · urgent: {1}', [bandeja.value.length, urgentes.value]) : t('Nothing pending'),
  esInterno() && sesion.proveedorId ? t('Showing only {0}.', [nombreProveedor(sesion.proveedorId)]) : '',
].filter(Boolean).join(' · '))

// ---- Indicadores ----
const defKpi = (clave) => kpis.value?.catalogo.find((c) => c.clave === clave) || {}

// ---- Bloques del tablero ejecutivo traídos al Inicio ----
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

function recargarTodo() {
  personalizando.value = false
  cargarIndicadores()
  grafico.value?.cargar()
}

onMounted(() => { cargar(); cargarIndicadores() })
watch(() => sesion.proveedorId, cargar)
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => cargar(), ['/dashboard'])
</script>

<template>
  <header class="pagina-cabeza tablero-cabeza">
    <div>
      <h1>{{ tx(saludo) }}</h1>
      <p>{{ tx(resumen) }}</p>
    </div>
    <div class="acciones">
      <button type="button" class="btn" @click="personalizando = true"><Icono nombre="columnas" />{{ t('Customize panel') }}</button>
    </div>
  </header>

  <TableroEsqueleto v-if="cargando && !d" />
  <template v-if="d">
    <!-- 1. Lo de hoy: la bandeja y, al lado, los cuatro indicadores -->
    <div v-if="mostrar('bandeja') || mostrar('indicadores')" class="inicio-arriba" :class="{ solo: !mostrar('bandeja') || !mostrar('indicadores') || !kpis }">
      <MiBandeja v-if="mostrar('bandeja')" :items="bandeja" />
      <div v-if="mostrar('indicadores') && kpis?.indicadores.length" class="inicio-kpis">
        <IndicadorInicio v-for="i in kpis.indicadores" :key="i.clave" :i="i" :def="defKpi(i.clave)" :moneda-base="kpis.moneda_base || ''" />
      </div>
    </div>

    <!-- 2. Una sola gráfica -->
    <GraficoComprasRecepcion v-if="mostrar('grafico')" ref="grafico" class="inicio-bloque" />

    <!-- 3. Bloques del tablero ejecutivo que la persona agregó -->
    <div v-if="mostrar('envios') || mostrar('contenedores') || mostrar('alertas')" class="tablero inicio-bloque">
      <div class="col">
      <BloqueEnvios v-if="mostrar('envios')" :envios="d.envios" />
      </div>
      <div class="col">
      <section v-if="mostrar('contenedores') && d.contenedores.length" class="panel">
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

      <section v-if="mostrar('alertas') && esInterno() && d.alertas.length" id="alertas" class="panel">
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

    <section v-if="mostrar('flujo')" class="panel inicio-bloque">
      <div class="panel-cabeza"><div><h2>{{ t('Supply chain') }}</h2><p>{{ t('From PO to load unit, by unit of measure.') }}</p></div></div>
      <BarraFlujo :flujo="d.flujo" />
    </section>

    <BloqueProveedores v-if="mostrar('proveedores') && d.proveedores.length" class="inicio-bloque" :proveedores="d.proveedores" />

    <!-- Invitación a agregar bloques (diseño v3: «Agrega lo que necesitas ver») -->
    <div v-if="porAgregar.length" class="agregar-bloque inicio-bloque">
      <span class="ico" aria-hidden="true"><Icono nombre="mas" :tam="18" /></span>
      <div><b>{{ t('Add what you need to see') }}</b>
        <p class="ayuda">{{ tx(porAgregar.map((b) => tx(b.titulo)).join(', ')) }}.</p></div>
      <button type="button" class="btn separar-izq" @click="personalizando = true">{{ t('Customize panel') }}</button>
    </div>
  </template>

  <PersonalizarPanel v-if="personalizando" :bloques="BLOQUES" :elegidos="elegidos" :catalogo="kpis?.catalogo || []" :indicadores="kpis?.elegidos || []"
                     @cerrar="personalizando = false" @guardado="recargarTodo" />
</template>

<style scoped>
.inicio-arriba { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(260px, 1fr); gap: 16px; align-items: start; }
.inicio-arriba.solo { grid-template-columns: minmax(0, 1fr); }
.inicio-arriba.solo .inicio-kpis { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.inicio-kpis { display: grid; gap: 12px; }
.inicio-kpis .panel + .panel { margin-top: 0; }
.inicio-bloque { margin-top: 16px; }
.agregar-bloque { border: 1.5px dashed var(--borde-hover); border-radius: var(--radio-panel); padding: 16px 18px; display: flex; align-items: center; gap: 14px; color: var(--tinta-2); }
.agregar-bloque b { color: var(--tinta); font-weight: 600; }
.agregar-bloque .ayuda { margin: 2px 0 0; }
.agregar-bloque .ico { width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); flex: none; }
.separar-izq { margin-inline-start: auto; }
@media (max-width: 1100px) {
  .inicio-arriba { grid-template-columns: minmax(0, 1fr); }
  .inicio-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
  .inicio-kpis { grid-template-columns: minmax(0, 1fr); }
  .agregar-bloque { flex-wrap: wrap; }
  .agregar-bloque .btn { width: 100%; justify-content: center; }
}
</style>
