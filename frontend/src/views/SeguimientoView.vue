<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import EstadoBadge from '../components/EstadoBadge.vue'
import Icono from '../components/Icono.vue'
import ExplosionPrepack from '../components/ExplosionPrepack.vue'
import Paginacion from '../components/Paginacion.vue'
import SeguimientoDocumentos from '../components/SeguimientoDocumentos.vue'
import SelectBusqueda from '../components/SelectBusqueda.vue'
import ThOrden from '../components/ThOrden.vue'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { cantTxt, fmtFecha, fmtNum, porUnidadTxt } from '../utils'

// Dónde está cada SKU: de la OC al contenedor y a la bodega, con la holgura
// frente a la fecha requerida en tienda.
const route = useRoute()
const router = useRouter()
// Dos seguimientos: la mercancía (por SKU, contenedor, estilo…) y los
// documentos (facturas y packing lists)
const vista = ref(route.query.vista === 'documentos' ? 'documentos' : 'mercancia')
watch(vista, (v) => router.replace({ query: v === 'documentos' ? { vista: v } : {} }))
const NOMBRES = {
  marca: 'Marca', grupo: 'Grupo', estilo: 'Estilo', color: 'Color', talla: 'Talla', sku: 'SKU', almacen: 'Almacén',
  contenedor: 'Contenedor', documento: 'BL / AWB', etapa: 'Etapa', riesgo: 'Riesgo', embarque_id: 'Embarque',
  eta_desde: 'ETA desde', eta_hasta: 'ETA hasta', fecha_xf_desde: 'XF desde', fecha_xf_hasta: 'XF hasta',
  fecha_tienda_desde: 'En tienda desde', fecha_tienda_hasta: 'En tienda hasta',
}
const FILTROS = ['q', ...Object.keys(NOMBRES)]
const filtros = reactive({ ...Object.fromEntries(FILTROS.map((k) => [k, ''])), orden: 'holgura:asc', page: 1, size: 25 })
for (const k of FILTROS) if (route.query[k]) filtros[k] = String(route.query[k])
const masFiltros = ref(['talla', 'sku', 'almacen', 'embarque_id', 'riesgo', 'eta_desde', 'eta_hasta', 'fecha_xf_desde',
  'fecha_xf_hasta', 'fecha_tienda_desde', 'fecha_tienda_hasta'].some((k) => filtros[k]))
const datos = ref({ items: [], total: 0, etapas: [], por_marca: [], opciones: {} })
const cargando = ref(true)
const explosion = ref(null)

const COLORES = {
  PEND_LIBERACION: 'var(--aviso)', POR_FACTURAR: 'var(--tinta-3)', FACTURADO: 'var(--info)', EN_PL: '#8b5cf6',
  CONTENEDOR: 'var(--acento)', EN_TRANSITO: '#0ea5e9', ARRIBADO: '#14b8a6', ENTREGADO: 'var(--ok)', RECIBIDO: '#15803d',
}
const TONO_ETAPA = {
  PEND_LIBERACION: 'aviso', POR_FACTURAR: 'neutro', FACTURADO: 'info', EN_PL: 'acento', CONTENEDOR: 'acento',
  EN_TRANSITO: 'info', ARRIBADO: 'info', ENTREGADO: 'ok', RECIBIDO: 'ok',
}
const RIESGOS = { ATRASO: ['Atrasado', 'error'], JUSTO: ['Justo', 'aviso'], A_TIEMPO: ['A tiempo', 'ok'] }
const nombreEtapa = computed(() => Object.fromEntries(datos.value.etapas.map((e) => [e.clave, e.nombre])))

const activos = computed(() => FILTROS.filter((k) => k !== 'q' && filtros[k]).map((k) => {
  let texto = filtros[k]
  if (k === 'etapa') texto = nombreEtapa.value[filtros[k]] || texto
  if (k === 'riesgo') texto = RIESGOS[filtros[k]]?.[0] || texto
  if (k === 'embarque_id') texto = datos.value.opciones.embarques?.find((e) => String(e.id) === String(filtros[k]))?.codigo || texto
  if (k.endsWith('_desde') || k.endsWith('_hasta')) texto = fmtFecha(texto)
  return { k, texto: `${NOMBRES[k]}: ${texto}` }
}))

async function cargar() {
  cargando.value = true
  try {
    const params = { orden: filtros.orden, page: filtros.page, size: filtros.size, proveedor_id: sesion.proveedorId || undefined }
    for (const k of FILTROS) if (filtros[k]) params[k] = filtros[k]
    datos.value = await api.get('/seguimiento', params)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

function aplicar() {
  filtros.page = 1
  const query = {}
  for (const k of FILTROS) if (filtros[k]) query[k] = filtros[k]
  router.replace({ query })
  cargar()
}

function quitar(k) {
  filtros[k] = ''
  aplicar()
}

function limpiar() {
  for (const k of FILTROS) filtros[k] = ''
  aplicar()
}

function alternarEtapa(clave) {
  filtros.etapa = filtros.etapa === clave ? '' : clave
  aplicar()
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(aplicar, 300)
}

function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  filtros.page = 1
  cargar()
}

// Barra apilada por marca: qué parte de lo pedido está en cada etapa
function segmentos(m) {
  return datos.value.etapas
    .map((e) => ({ clave: e.clave, nombre: e.nombre, cantidad: m.etapas[e.clave] || 0 }))
    .filter((s) => s.cantidad > 0)
    .map((s) => ({ ...s, ancho: (s.cantidad * 100) / m.total }))
}

function holguraTxt(f) {
  if (f.holgura === null || f.holgura === undefined) return '—'
  if (f.holgura < 0) return `${-f.holgura} d tarde`
  return `${f.holgura} d de margen`
}

watch(() => sesion.proveedorId, () => { filtros.page = 1; cargar() })
onMounted(cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Seguimiento</h1>
      <p v-if="vista === 'mercancia'">Cada SKU desde la orden de compra hasta la bodega: en qué etapa está, en qué contenedor viaja y si llega a tiempo a tienda.</p>
      <p v-else>Cada factura y packing list: en qué paso va, qué le falta y si ya tiene contenedor.</p>
    </div>
  </div>
  <div class="pestanas-pildora" role="tablist">
    <button class="pildora" role="tab" :aria-selected="vista === 'mercancia'" @click="vista = 'mercancia'"><Icono nombre="ruta" :tam="15" />Mercancía y contenedores</button>
    <button class="pildora" role="tab" :aria-selected="vista === 'documentos'" @click="vista = 'documentos'"><Icono nombre="factura" :tam="15" />Facturación y packing lists</button>
  </div>

  <SeguimientoDocumentos v-if="vista === 'documentos'" />
  <template v-else>

  <div class="etapas" role="group" aria-label="Filtrar por etapa">
    <button v-for="e in datos.etapas" :key="e.clave" type="button" class="etapa" :aria-pressed="filtros.etapa === e.clave" @click="alternarEtapa(e.clave)">
      <span class="etapa-titulo"><i class="punto" :style="{ background: COLORES[e.clave] }"></i>{{ e.nombre }}</span>
      <b>{{ porUnidadTxt(e.por_unidad, null) }}</b>
    </button>
  </div>

  <section v-if="datos.por_marca.length" class="panel">
    <div class="panel-cabeza">
      <div><h2>Avance por marca</h2><p>Distribución de lo pedido por etapa. Pasa el cursor sobre la barra para ver cantidades; clic en la marca para filtrar.</p></div>
    </div>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>Marca</th><th class="num">Total</th><th style="width: 55%">Etapas</th><th class="num">Líneas con atraso</th></tr></thead>
        <tbody>
          <tr v-for="m in datos.por_marca" :key="`${m.marca}-${m.unidad}`">
            <td><button type="button" class="enlace fuerte" @click="filtros.marca = m.marca === 'Sin marca' ? '' : m.marca; aplicar()">{{ m.marca }}</button></td>
            <td class="num">{{ cantTxt(m.total, m.unidad) }}</td>
            <td>
              <div class="apilada" role="img" :aria-label="segmentos(m).map((s) => `${s.nombre}: ${s.cantidad}`).join(', ')">
                <span v-for="s in segmentos(m)" :key="s.clave" :style="{ width: `${s.ancho}%`, background: COLORES[s.clave] }" :title="`${s.nombre}: ${cantTxt(s.cantidad, m.unidad)}`"></span>
              </div>
            </td>
            <td class="num"><span v-if="m.atraso" class="etiqueta error">{{ m.atraso }}</span><span v-else class="ayuda">0</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="leyenda-etapas">
      <span v-for="e in datos.etapas" :key="e.clave"><i class="punto" :style="{ background: COLORES[e.clave] }"></i>{{ e.nombre }}</span>
    </div>
  </section>

  <div class="filtros" style="margin-top: 18px">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="SKU, OC, factura, PL, contenedor o embarque" aria-label="Buscar" @input="buscar" />
    </label>
    <SelectBusqueda v-model="filtros.marca" :opciones="datos.opciones.marcas || []" vacio="Marca: todas" etiqueta="Marca" @change="aplicar" />
    <SelectBusqueda v-model="filtros.grupo" :opciones="datos.opciones.grupos || []" vacio="Grupo: todos" etiqueta="Grupo de artículos" @change="aplicar" />
    <SelectBusqueda v-model="filtros.estilo" :opciones="datos.opciones.estilos || []" vacio="Estilo: todos" etiqueta="Estilo" @change="aplicar" />
    <SelectBusqueda v-model="filtros.color" :opciones="datos.opciones.colores || []" vacio="Color: todos" etiqueta="Color" @change="aplicar" />
    <SelectBusqueda v-model="filtros.contenedor" :opciones="datos.opciones.contenedores || []" vacio="Contenedor: todos" etiqueta="Contenedor" @change="aplicar" />
    <SelectBusqueda v-model="filtros.documento" :opciones="datos.opciones.documentos || []" vacio="BL / AWB: todos" etiqueta="Documento de transporte" @change="aplicar" />
    <button type="button" class="btn btn-fantasma btn-chico" :aria-expanded="masFiltros" @click="masFiltros = !masFiltros">
      <Icono nombre="filtro" :tam="14" />{{ masFiltros ? 'Menos filtros' : 'Más filtros' }}
    </button>
  </div>
  <div v-if="masFiltros" class="filtros filtros-extra">
    <SelectBusqueda v-model="filtros.talla" :opciones="datos.opciones.tallas || []" vacio="Talla: todas" etiqueta="Talla" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sku" :opciones="datos.opciones.skus || []" vacio="SKU: todos" etiqueta="Código de producto" @change="aplicar" />
    <SelectBusqueda v-model="filtros.almacen" :opciones="datos.opciones.almacenes || []" vacio="Almacén: todos" etiqueta="Almacén" @change="aplicar" />
    <SelectBusqueda v-model="filtros.embarque_id" :opciones="(datos.opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    vacio="Embarque: todos" etiqueta="Embarque" @change="aplicar" />
    <select v-model="filtros.riesgo" aria-label="Riesgo" @change="aplicar">
      <option value="">Llegada a tienda: todas</option>
      <option v-for="(r, k) in RIESGOS" :key="k" :value="k">{{ r[0] }}</option>
    </select>
    <label v-for="[k, t] in [['eta', 'ETA'], ['fecha_xf', 'XF'], ['fecha_tienda', 'En tienda']]" :key="k" class="rango-fechas">
      <span>{{ t }}</span>
      <input v-model="filtros[`${k}_desde`]" type="date" :aria-label="`${t} desde`" @change="aplicar" />
      <span>a</span>
      <input v-model="filtros[`${k}_hasta`]" type="date" :aria-label="`${t} hasta`" @change="aplicar" />
    </label>
  </div>
  <div v-if="activos.length" class="chips">
    <span v-for="a in activos" :key="a.k" class="chip">{{ a.texto }}<button type="button" :aria-label="`Quitar ${a.texto}`" @click="quitar(a.k)"><Icono nombre="cerrar" :tam="13" /></button></span>
    <button type="button" class="btn btn-fantasma btn-chico" @click="limpiar">Limpiar filtros</button>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="marca" :orden="filtros.orden" @ordenar="ordenar">Marca</ThOrden>
          <ThOrden campo="estilo" :orden="filtros.orden" @ordenar="ordenar">Estilo · color</ThOrden>
          <ThOrden campo="talla" :orden="filtros.orden" @ordenar="ordenar">Talla</ThOrden>
          <ThOrden campo="oc" :orden="filtros.orden" @ordenar="ordenar">OC / SKU</ThOrden>
          <ThOrden campo="cantidad" :orden="filtros.orden" num @ordenar="ordenar">Cantidad</ThOrden>
          <ThOrden campo="etapa" :orden="filtros.orden" @ordenar="ordenar">Etapa</ThOrden>
          <th>Documentos</th>
          <ThOrden campo="contenedor" :orden="filtros.orden" @ordenar="ordenar">Contenedor</ThOrden>
          <ThOrden campo="fecha_xf" :orden="filtros.orden" @ordenar="ordenar">XF</ThOrden>
          <ThOrden campo="recolectado_en" :orden="filtros.orden" @ordenar="ordenar">Recolección</ThOrden>
          <ThOrden campo="eta" :orden="filtros.orden" @ordenar="ordenar">ETA</ThOrden>
          <ThOrden campo="fecha_tienda" :orden="filtros.orden" @ordenar="ordenar">En tienda</ThOrden>
          <ThOrden campo="holgura" :orden="filtros.orden" @ordenar="ordenar">Holgura</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="13" class="vacio">Cargando…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="13" class="vacio">No hay mercancía con esos filtros.</td></tr>
        <tr v-for="(f, i) in datos.items" :key="i">
          <td class="fuerte">{{ f.marca || '—' }}<span v-if="f.grupo" class="sub">{{ f.grupo }}</span></td>
          <td>{{ f.estilo }}<span class="sub">{{ f.color }}</span></td>
          <td>{{ f.talla || '—' }}</td>
          <td>
            <router-link :to="{ path: '/ordenes', query: { q: f.oc, solo_disponible: '0' } }" class="codigo fuerte">{{ f.oc }}</router-link> <span class="ayuda">/{{ f.posicion }}</span>
            <span class="sub codigo">{{ f.sku }}<template v-if="f.almacen"> · {{ f.almacen }}</template></span>
          </td>
          <td class="num">{{ cantTxt(f.cantidad, f.unidad) }}<button v-if="f.tipo_empaque === 'PREPACK'" type="button" class="etiqueta acento btn-explosion" title="Ver la explosión del prepack"
                  @click="explosion = { sku: f.sku, cajas: f.cantidad }">Prepack <Icono nombre="lupa" :tam="12" /></button></td>
          <td><span class="etiqueta" :class="TONO_ETAPA[f.etapa]" style="margin-left: 0">{{ nombreEtapa[f.etapa] || f.etapa }}</span></td>
          <td>
            <router-link v-if="f.factura_id" :to="`/facturas/${f.factura_id}`">{{ f.factura }}</router-link>
            <span v-else class="ayuda">—</span>
            <router-link v-if="f.pl_id" :to="`/packing-lists/${f.pl_id}`" class="sub">PL {{ f.pl }}</router-link>
          </td>
          <td>
            <template v-if="f.embarque_id">
              <span class="codigo">{{ f.contenedor }}</span><span v-if="f.documento" class="sub codigo">BL {{ f.documento }}</span>
              <span class="sub"><router-link v-if="esInterno()" :to="`/transporte/embarques/${f.embarque_id}`">{{ f.embarque }}</router-link><template v-else>{{ f.embarque }}</template> · <EstadoBadge :estado="f.estado_embarque" /></span>
            </template>
            <span v-else class="ayuda">—</span>
          </td>
          <td>{{ fmtFecha(f.fecha_xf) }}</td>
          <td>
            <template v-if="f.recolectado_en">
              {{ fmtFecha(f.recolectado_en) }}
              <span v-if="f.atraso_recoleccion > 0" class="sub" style="color: var(--error)">{{ f.atraso_recoleccion }} d después del XF</span>
              <span v-else class="sub">a tiempo con el XF</span>
            </template>
            <span v-else-if="f.pl_id" class="ayuda">Pendiente</span>
            <span v-else class="ayuda">—</span>
          </td>
          <td>{{ fmtFecha(f.arribo_real || f.eta) }}<span v-if="f.arribo_real" class="sub">real</span></td>
          <td>{{ fmtFecha(f.fecha_tienda) }}</td>
          <td>
            <span v-if="f.riesgo" class="etiqueta" :class="RIESGOS[f.riesgo][1]" style="margin-left: 0">{{ holguraTxt(f) }}</span>
            <span v-else class="ayuda">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total"
              @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
  <p class="ayuda" style="margin-top: 8px">Total filtrado: {{ fmtNum(datos.total) }} líneas. La holgura compara la llegada (real o ETA) con la fecha requerida en tienda; sin embarque, cuenta los días que faltan desde hoy.</p>
  </template>
  <ExplosionPrepack v-if="explosion" :sku="explosion.sku" :cajas="explosion.cajas" @cerrar="explosion = null" />
</template>
