<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtNum, porUnidadTxt } from '../utils'
import EstadoBadge from './EstadoBadge.vue'
import ExplosionPrepack from './ExplosionPrepack.vue'
import GraficoColumnas from './GraficoColumnas.vue'
import Icono from './Icono.vue'
import Kpi from './Kpi.vue'
import Paginacion from './Paginacion.vue'
import ThOrden from './ThOrden.vue'

// Tablero de embarques: un renglón por embarque y su documento de transporte
// (BL, AWB o carta de porte). Se abre en sus unidades de carga y cada unidad
// en lo que lleva por orden de compra.
const props = defineProps({ filtros: { type: Object, required: true } })
const emit = defineEmits(['opciones', 'filtrar'])
const datos = ref({ items: [], total: 0, kpis: {}, por_estado: [], llegadas: [] })
const cargando = ref(true)
const tabla = reactive({ orden: '', page: 1, size: 25 })
const abiertos = reactive({})
const explosiones = reactive({})
const explosion = ref(null)
const RIESGOS = { ATRASO: ['Llega tarde', 'error'], JUSTO: ['Justo', 'aviso'], A_TIEMPO: ['A tiempo', 'ok'] }
const MODOS = {
  MARITIMO: { nombre: 'Marítimo', icono: 'barco', unidad: 'Contenedor', doc: 'BL' },
  AEREO: { nombre: 'Aéreo', icono: 'avion', unidad: 'Guía', doc: 'AWB' },
  TERRESTRE: { nombre: 'Terrestre', icono: 'camion', unidad: 'Camión', doc: 'Carta de porte' },
}

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/seguimiento/embarques', {
      ...props.filtros, ...tabla, proveedor_id: sesion.proveedorId || undefined,
    })
    emit('opciones', datos.value.opciones)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function alternar(e) {
  abiertos[e.embarque_id] = !abiertos[e.embarque_id]
}
async function alternarUnidad(u) {
  if (explosiones[u.unidad_id]) {
    delete explosiones[u.unidad_id]
    return
  }
  try {
    explosiones[u.unidad_id] = await api.get(`/seguimiento/unidades/${u.unidad_id}/explosion`,
      { ...props.filtros, proveedor_id: sesion.proveedorId || undefined })
  } catch (e) {
    errorApi(e)
  }
}
function ordenar(campo) {
  tabla.orden = siguienteOrden(tabla.orden, campo)
  tabla.page = 1
  cargar()
}
const llegadas = computed(() => datos.value.llegadas.map((s, i) => ({
  etiqueta: i === 0 ? 'Esta sem.' : fmtFecha(s.desde).slice(0, 5),
  valor: s.embarques,
  detalle: `${fmtFecha(s.desde)} – ${fmtFecha(s.hasta)}`,
})))
const estados = computed(() => datos.value.por_estado.map((e) => ({ etiqueta: e.nombre, valor: e.total })))
const porModo = computed(() => Object.entries(datos.value.kpis.por_modo || {}).filter(([, n]) => n)
  .map(([m, n]) => `${fmtNum(n)} ${MODOS[m].nombre.toLowerCase()}`).join(' · ') || 'sin embarques')

watch(() => [props.filtros, sesion.proveedorId], () => {
  tabla.page = 1
  for (const k of Object.keys(explosiones)) delete explosiones[k]
  cargar()
}, { deep: true })
onMounted(cargar)
</script>

<template>
  <section class="kpis" style="margin-bottom: 16px">
    <Kpi titulo="Embarques" :valor="datos.kpis.embarques" icono="ruta" :detalle="porModo" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Unidades de carga" :valor="datos.kpis.unidades" icono="contenedor" detalle="contenedores, guías y camiones" @abrir="emit('filtrar', {})" />
    <Kpi titulo="En tránsito" :valor="datos.kpis.en_camino" icono="barco" detalle="ya salieron" @abrir="emit('filtrar', { estado: 'EN_TRANSITO' })" />
    <Kpi titulo="Llegan en 7 días" :valor="datos.kpis.llegan_7_dias" icono="reloj" detalle="por ETA" @abrir="emit('filtrar', {})" />
    <Kpi titulo="Llegan tarde a tienda" :valor="datos.kpis.atrasados" icono="alerta" :tono="datos.kpis.atrasados ? 'alerta' : 'exito'"
         detalle="ETA después de la fecha en tienda" @abrir="emit('filtrar', { riesgo: 'ATRASO' })" />
  </section>

  <div class="dos-columnas" style="margin-bottom: 16px">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Llegadas por semana</h2><p>Embarques que aún no arriban, por semana de su ETA.</p></div></div>
      <GraficoColumnas :datos="llegadas" titulo="Embarques por semana de llegada" />
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Embarques por estado</h2><p>Según los filtros; usa el filtro de estado para ver solo uno.</p></div></div>
      <GraficoColumnas :datos="estados" titulo="Embarques por estado" />
    </section>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <th><span class="oculto-visual">Abrir</span></th>
          <ThOrden campo="embarque" :orden="tabla.orden" @ordenar="ordenar">Embarque</ThOrden>
          <ThOrden campo="documento" :orden="tabla.orden" @ordenar="ordenar">Documento de transporte</ThOrden>
          <ThOrden campo="estado" :orden="tabla.orden" @ordenar="ordenar">Estado</ThOrden>
          <th>Ruta</th>
          <ThOrden campo="etd" :orden="tabla.orden" @ordenar="ordenar">Salida</ThOrden>
          <ThOrden campo="eta" :orden="tabla.orden" @ordenar="ordenar">Llegada</ThOrden>
          <ThOrden campo="holgura" :orden="tabla.orden" @ordenar="ordenar">Vs. tienda</ThOrden>
          <ThOrden campo="unidades" :orden="tabla.orden" num @ordenar="ordenar">Unidades</ThOrden>
          <ThOrden campo="ocs" :orden="tabla.orden" num @ordenar="ordenar">OCs</ThOrden>
          <th class="num">Contenido</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="11" class="vacio">Cargando…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="11" class="vacio">No hay embarques con mercancía para esos filtros.</td></tr>
        <template v-for="e in datos.items" :key="e.embarque_id">
          <tr class="clicable" @click="alternar(e)">
            <td>
              <button type="button" class="btn-icono" :aria-expanded="!!abiertos[e.embarque_id]" :aria-label="`Ver las unidades de ${e.embarque}`">
                <Icono :nombre="abiertos[e.embarque_id] ? 'abajo' : 'derecha'" :tam="16" />
              </button>
            </td>
            <td>
              <router-link v-if="esInterno()" :to="`/transporte/embarques/${e.embarque_id}`" class="codigo fuerte" @click.stop>{{ e.embarque }}</router-link>
              <b v-else class="codigo">{{ e.embarque }}</b>
              <span class="sub"><Icono :nombre="MODOS[e.modo]?.icono || 'ruta'" :tam="12" /> {{ MODOS[e.modo]?.nombre || e.modo }}<template v-if="e.modalidad"> · {{ e.modalidad }}</template></span>
            </td>
            <td>
              <span class="codigo">{{ e.documento || 'Pendiente' }}</span>
              <span class="sub">{{ MODOS[e.modo]?.doc }}<template v-if="e.transportista"> · {{ e.transportista }}</template></span>
            </td>
            <td><EstadoBadge :estado="e.estado" /></td>
            <td>{{ e.puerto_origen || '—' }} <Icono nombre="flecha" :tam="12" /> {{ e.puerto_destino || '—' }}<span v-if="e.centro" class="sub">centro {{ e.centro }}</span></td>
            <td>{{ fmtFecha(e.etd) }}</td>
            <td>{{ fmtFecha(e.eta) }}<span class="sub">{{ e.arribado ? 'arribó' : e.dias_eta === null ? '' : e.dias_eta >= 0 ? `en ${e.dias_eta} d` : `ETA vencida ${-e.dias_eta} d` }}</span></td>
            <td>
              <span v-if="e.riesgo" class="etiqueta" :class="RIESGOS[e.riesgo][1]" style="margin-left: 0">{{ RIESGOS[e.riesgo][0] }}</span>
              <span v-if="e.holgura !== null" class="sub">{{ e.holgura < 0 ? `${-e.holgura} d tarde` : `${e.holgura} d de margen` }}</span>
            </td>
            <td class="num">{{ e.unidades }}</td>
            <td class="num">{{ e.ocs }}</td>
            <td class="num">{{ porUnidadTxt(e.por_unidad, null) }}<span class="sub">{{ e.marcas.join(' · ') }}</span></td>
          </tr>
          <tr v-if="abiertos[e.embarque_id]" class="fila-hija">
            <td colspan="11">
              <div class="subtabla">
                <div v-for="u in e.detalle_unidades" :key="u.unidad_id" class="explosion-oc">
                  <button type="button" class="explosion-oc-cabeza enlace-bloque" :aria-expanded="!!explosiones[u.unidad_id]" @click="alternarUnidad(u)">
                    <Icono :nombre="explosiones[u.unidad_id] ? 'abajo' : 'derecha'" :tam="14" />
                    <b class="codigo">{{ MODOS[e.modo]?.unidad }} {{ u.contenedor }}</b>
                    <span class="etiqueta" style="margin-left: 0">{{ u.tipo_nombre }}</span>
                    <span v-if="u.modalidad" class="etiqueta acento">{{ u.modalidad }}</span>
                    <span class="ayuda">{{ u.sello ? `sello ${u.sello}` : 'sin sello' }} · {{ u.ocs }} OC · {{ u.facturas.join(', ') || 'sin factura' }}</span>
                    <span v-if="u.riesgo" class="etiqueta" :class="RIESGOS[u.riesgo][1]">{{ RIESGOS[u.riesgo][0] }}</span>
                    <span class="separar fuerte">{{ porUnidadTxt(u.por_unidad, null) }}</span>
                  </button>
                  <template v-if="explosiones[u.unidad_id]">
                    <div v-for="o in explosiones[u.unidad_id].ocs" :key="o.oc_id" class="explosion-sub">
                      <div class="explosion-oc-cabeza">
                        <b class="codigo">OC {{ o.oc }}</b>
                        <span class="ayuda">{{ o.proveedor }} · {{ o.sociedad }}/{{ o.centro }} · destino {{ o.centro_destino || '—' }} · en tienda {{ fmtFecha(o.fecha_tienda) }}</span>
                        <span v-if="o.riesgo" class="etiqueta" :class="RIESGOS[o.riesgo][1]">{{ RIESGOS[o.riesgo][0] }}</span>
                        <span class="separar fuerte">{{ porUnidadTxt(o.por_unidad, null) }}</span>
                      </div>
                      <div class="tabla-marco" style="box-shadow: none">
                        <table class="tabla">
                          <thead><tr><th>Pos.</th><th>SKU</th><th>Marca · grupo</th><th>Estilo · color</th><th>Talla</th><th>Almacén</th><th>UM</th><th class="num">Cantidad</th><th>Factura / PL</th></tr></thead>
                          <tbody>
                            <tr v-for="(l, i) in o.lineas" :key="i">
                              <td class="codigo">{{ l.posicion }}</td>
                              <td class="codigo">{{ l.sku }}</td>
                              <td>{{ l.marca }}<span class="sub">{{ l.grupo }}</span></td>
                              <td>{{ l.estilo }} · {{ l.color }}</td>
                              <td>
                                <b>{{ l.talla }}</b>
                                <button v-if="l.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" title="Ver la explosión del prepack"
                                        @click="explosion = { sku: l.sku, cajas: l.cantidad }">Prepack <Icono nombre="lupa" :tam="12" /></button>
                              </td>
                              <td>{{ l.almacen || '—' }}</td>
                              <td><span class="etiqueta" style="margin-left: 0">{{ l.unidad }}</span></td>
                              <td class="num">{{ fmtNum(l.cantidad) }}</td>
                              <td>
                                <router-link v-if="l.factura_id" :to="`/facturas/${l.factura_id}`">{{ l.factura }}</router-link>
                                <router-link v-if="l.pl_id" :to="`/packing-lists/${l.pl_id}`" class="sub">PL {{ l.pl }}</router-link>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
  <Paginacion :page="tabla.page" :size="tabla.size" :total="datos.total" @cambiar="(p) => { tabla.page = p; cargar() }" @tamano="(t) => (tabla.size = t)" />
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
