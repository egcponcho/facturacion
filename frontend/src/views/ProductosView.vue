<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CargaArticulos from '../components/CargaArticulos.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import FiltroMulti from '../components/FiltroMulti.vue'
import EstadoVacio from '../components/EstadoVacio.vue'
import Icono from '../components/Icono.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { cargarContexto, clasificarVarios } from '../clasificacion/useClasificacion'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, puede, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { useSeleccion } from '../utils'
import { filasDefecto } from '../stores/preferencias'

// Un producto es un estilo-color de un proveedor: su ficha técnica y su
// clasificación arancelaria valen para todas sus tallas (SKU) y prepacks.
const route = useRoute()
const router = useRouter()
const interno = esInterno()
// Quien aprueba empieza por lo que espera revisión; quien llena la ficha, por lo que falta completar
const revisa = puede('producto.clasificar')
const filtros = reactive({
  estado: route.query.estado ?? (revisa ? 'revision' : 'borradores'),
  q: route.query.q || '',
  marcas: [],
  tipos: [],
  orden: '',
  page: 1,
  size: filasDefecto(),
})
const datos = ref({ items: [], total: 0, kpis: {} })
const opciones = ref({ marcas: [] })
const cargando = ref(false)
const ocupado = ref(false)
const sel = useSeleccion()
const cargaAbierta = ref(false)

// Bandeja de trabajo: pocas vistas, en el orden en que trabaja cada quien
const VISTAS = computed(() => {
  const k = datos.value.kpis || {}
  // Lo que deja facturas sin poder finalizarse va primero (solo cuando hay)
  const bloquean = k.bloquean || filtros.estado === 'bloquean' ? [['bloquean', t('Blocking invoices'), k.bloquean]] : []
  if (revisa) {
    return [
      ...bloquean,
      ['revision', t('To review'), k.revision],
      ...(k.baja_confianza != null ? [['baja_confianza', t('Low confidence'), k.baja_confianza]] : []),
      ['borradores', t('Drafts'), k.borradores],
      ['observado', t('Returned'), k.observado],
      ['aprobados', t('Approved'), k.aprobados],
      ['', t('All'), k.total],
    ]
  }
  return [
    ...bloquean,
    ['borradores', t('To complete'), k.borradores],
    ['observado', interno ? t('Returned') : t('Returned to you'), k.observado],
    ['revision', t('Sent to review'), k.revision],
    ['aprobados', t('Approved'), k.aprobados],
    ['', t('All'), k.total],
  ]
})

// El siguiente paso de cada producto para quien mira la lista
function siguiente(p) {
  if (['aprobado', 'corregido'].includes(p.estado)) return null
  const llena = puede('producto.ficha')
  if (p.estado === 'revision') return revisa ? { texto: t('Review and approve'), accion: true } : { texto: t('Waiting for customs review') }
  if (p.estado === 'observado') return llena ? { texto: t('Fix what customs noted'), accion: true } : { texto: t('Returned: waiting for the fix') }
  if (!p.ficha_completa) {
    if (!llena) return { texto: t('Waiting for the technical sheet') }
    return { texto: p.faltan.length ? t('Complete: {0}', [p.faltan[0]]) : t('Complete the technical sheet'), accion: true }
  }
  if (llena && (!revisa || flujo.value.revision_obligatoria)) return { texto: t('Send to review'), accion: true }
  return revisa ? { texto: t('Ready to approve'), accion: true } : { texto: t('Waiting for customs review') }
}

const consulta = () => ({ estado: filtros.estado, q: filtros.q, orden: filtros.orden, marca_id: filtros.marcas.join(','), tipo: filtros.tipos.join(',') })

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get('/productos', { ...consulta(), page: filtros.page, size: filtros.size, proveedor_id: sesion.proveedorId })
    sel.podar(datos.value.items.map((p) => p.id))
    router.replace({ query: { estado: filtros.estado, ...(filtros.q && { q: filtros.q }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
function recargar() {
  filtros.page = 1
  cargar()
}
function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  recargar()
}

const ids = computed(() => datos.value.items.map((p) => p.id))
const elegidos = computed(() => datos.value.items.filter((p) => sel.tiene(p.id)))
// Flujo de clasificación configurado por el administrador
const flujo = computed(() => sesion.usuario?.flujo || {})
const porAprobar = computed(() => elegidos.value.filter((p) => (flujo.value.revision_obligatoria ? ['revision'] : ['sugerida', 'revision']).includes(p.estado) && p.ficha_completa))
const envia = computed(() => puede('producto.ficha') && (!puede('producto.clasificar') || !!flujo.value.revision_obligatoria))
const porEnviar = computed(() => elegidos.value.filter((p) => ['sugerida', 'observado', 'borrador'].includes(p.estado)))

async function enviar() {
  ocupado.value = true
  try {
    const r = await api.post('/productos/enviar', { ids: porEnviar.value.map((p) => p.id) })
    if (r.errores.length) avisar(t('{0} sent to review; {1} need attention.', [r.enviados, r.errores.length]), 'error', r.errores.map((e) => e.mensaje))
    else avisar(t('{0} {1} sent to review.', [r.enviados, r.enviados === 1 ? 'sheet' : 'sheets']))
    sel.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function clasificar() {
  ocupado.value = true
  try {
    const r = await clasificarVarios(elegidos.value.filter((p) => !['aprobado', 'corregido'].includes(p.estado)).map((p) => p.id))
    avisar(t('Products classified: {0}.', [r.clasificados]))
    sel.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function aprobar() {
  ocupado.value = true
  try {
    const r = await api.post('/productos/aprobar', { ids: porAprobar.value.map((p) => p.id) })
    if (r.errores.length) avisar(t('{0} approved; {1} need attention.', [r.aprobados, r.errores.length]), 'error', r.errores.map((e) => e.mensaje))
    else avisar(t('Products approved: {0}.', [r.aprobados]))
    sel.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function exportar(formato) {
  try {
    await api.descargar('/productos/exportar', t('products.{0}', [formato]), { ...consulta(), formato, proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}

const codigoDe = (p) => p.codigo || p.sugerido
const descCorta = (d) => (d && d.length > 60 ? `${d.slice(0, 58)}…` : d || '')
// Categorías para el filtro: las de la configuración
const categorias = ref([])
cargarContexto().then((c) => (categorias.value = (c.categorias || []).filter((x) => x.activo !== false).map((x) => ({ valor: x.codigo, texto: x.nombre_corto || x.nombre })))).catch(() => {})

onMounted(async () => {
  cargar()
  try {
    opciones.value = await api.get('/productos/opciones')
  } catch {
    /* los filtros extra son opcionales */
  }
})
watch(() => sesion.proveedorId, recargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <div v-if="puede('aranceles.ver') || puede('clasificacion.ver')" class="pestanas-pildora sub-mod">
        <span class="pildora" aria-current="page" aria-pressed="true">{{ t('Products') }}</span>
        <router-link v-if="puede('clasificacion.ver')" to="/familias" class="pildora">{{ t('Product families') }}</router-link>
        <router-link v-if="puede('aranceles.ver')" to="/aranceles" class="pildora">{{ t('Tariff schedule') }}</router-link>
      </div>
      <h1>{{ t('Products') }}</h1>
      <p v-if="interno">{{ t('Technical sheets and tariff classification. Approved HS codes flow to purchase orders and invoices for each destination country.') }}</p>
      <p v-else>{{ t('Complete the technical sheet of each product. Customs uses it to classify it; the approved code appears on your orders and invoices.') }}</p>
    </div>
    <div class="acciones">
      <button class="btn btn-fantasma" @click="exportar('xlsx')"><Icono nombre="descargar" />{{ t('Excel') }}</button>
      <button class="btn btn-fantasma" @click="exportar('pdf')"><Icono nombre="descargar" />PDF</button>
      <button v-if="puede('catalogos.crear')" class="btn" @click="cargaAbierta = true"><Icono nombre="importar" />{{ t('Upload items and sheets') }}</button>
    </div>
  </div>

  <div class="filtros" v-filtros>
    <div class="segmentos" role="group" :aria-label="t('View')">
      <button v-for="[v, txt, n] in VISTAS" :key="v" class="segmento" type="button" :aria-pressed="filtros.estado === v"
              @click="filtros.estado = v; recargar()">{{ tx(txt) }}<span v-if="n !== undefined" class="cuenta">{{ tx(n) }}</span></button>
    </div>
  </div>
  <div class="filtros" v-filtros>
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" :placeholder="t('Generic, style, color, name, item code, UPC or HS code')" :aria-label="t('Search')" @input="buscar" />
    </label>
    <FiltroMulti v-if="opciones.marcas.length > 1 || filtros.marcas.length" v-model="filtros.marcas" :etiqueta="t('Brand')" :opciones="opciones.marcas.map((m) => ({ valor: String(m.id), texto: m.nombre }))" @change="recargar" />
    <FiltroMulti v-model="filtros.tipos" :etiqueta="t('Category')" :opciones="categorias" @change="recargar" />
    <span class="ayuda separar">{{ t('{0} products', [datos.total]) }}</span>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla" v-tarjetas>
      <thead>
        <tr>
          <th class="check"><input type="checkbox" :aria-label="t('Select all')" :checked="sel.todos(ids)" @change="sel.alternarTodos(ids)" /></th>
          <ThOrden campo="estilo" :orden="filtros.orden" @ordenar="ordenar">{{ t('Product') }}</ThOrden>
          <th v-if="!sesion.proveedorId && interno">{{ t('Supplier') }}</th>
          <ThOrden campo="codigo" :orden="filtros.orden" @ordenar="ordenar">{{ t('HS code') }}</ThOrden>
          <th>{{ t('Countries') }}</th>
          <ThOrden campo="estado" :orden="filtros.orden" @ordenar="ordenar">{{ t('Status') }}</ThOrden>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in datos.items" :key="p.id" class="clicable" @click="router.push(`/productos/${p.id}`)">
          <td class="check" @click.stop><input type="checkbox" :aria-label="t('Select {0}', [p.estilo])" :checked="sel.tiene(p.id)" @change="sel.alternar(p.id)" /></td>
          <td>
            <div class="producto-celda">
              <span class="miniatura">
                <img v-if="p.foto_id" :src="`/api/productos/fotos/${p.foto_id}`" alt="" loading="lazy" />
                <Icono v-else nombre="caja" :tam="18" />
              </span>
              <span>
                <router-link :to="`/productos/${p.id}`" class="fuerte" @click.stop><span v-if="p.codigo_generico" class="codigo-sac">{{ tx(p.codigo_generico) }}</span> {{ tx(p.estilo) }} · {{ tx(p.color) }}</router-link>
                <span class="sub">{{ tx(p.descripcion_comercial || '—') }} · {{ tx(p.rango_tallas || t('no sizes')) }}<template v-if="p.tipo"> · {{ tx(p.tipo_txt || p.tipo) }}</template></span>
              </span>
            </div>
          </td>
          <td v-if="!sesion.proveedorId && interno">{{ tx(p.proveedor) }}</td>
          <td>
            <template v-if="codigoDe(p)">
              <span class="codigo-sac" :class="{ tentativo: !p.codigo }">{{ tx(codigoDe(p)) }}</span>
              <span class="sub" :title="tx(p.codigo_desc || '')">{{ tx(p.codigo ? descCorta(p.codigo_desc) : t('Suggested, not approved')) }}</span>
            </template>
            <span v-else class="apagado">{{ t('Not classified') }}</span>
          </td>
          <td>
            <span v-if="p.paises_ok === p.paises_total" class="etiqueta ok"><Icono nombre="check" :tam="12" />{{ tx(p.paises_ok) }}/{{ tx(p.paises_total) }}</span>
            <span v-else-if="p.paises_ok" class="etiqueta aviso">{{ tx(p.paises_ok) }}/{{ tx(p.paises_total) }}</span>
            <span v-else class="apagado">—</span>
          </td>
          <td>
            <EstadoBadge :estado="p.estado" />
            <span v-if="siguiente(p)" class="sub recortar siguiente" :class="{ accion: siguiente(p).accion }" :title="tx(p.faltan.join(', '))">
              <Icono v-if="siguiente(p).accion" nombre="derecha" :tam="12" />{{ tx(siguiente(p).texto) }}</span>
          </td>
          <td class="num"><Icono nombre="derecha" :tam="16" /></td>
        </tr>
        <tr v-if="!datos.items.length && !cargando">
          <td v-if="!datos.kpis?.total && !filtros.q" colspan="7">
            <EstadoVacio icono="etiqueta" :titulo="t('There are no products yet.')"
                         :texto="t('A product is a style and color of a supplier: its technical sheet and its HS code apply to all its sizes. Products are created with the items of the purchase orders or from Master data.')">
              <router-link v-if="puede('catalogos.ver')" class="btn" to="/mantenimiento"><Icono nombre="base" />{{ t('Master data') }}</router-link>
              <router-link v-if="puede('oc.importar')" class="btn btn-primario" to="/importar"><Icono nombre="importar" />{{ t('Import purchase orders') }}</router-link>
            </EstadoVacio>
          </td>
          <td v-else colspan="7" class="vacio">
            <template v-if="['pendientes', 'sugerida', 'revision', 'borradores', 'baja_confianza', 'bloquean'].includes(filtros.estado)"><Icono nombre="check" /> {{ t('Nothing pending here.') }}</template>
            <template v-else>{{ t('No products match these filters.') }}</template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total" @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />

  <CargaArticulos v-if="cargaAbierta" @cerrar="cargaAbierta = false" @listo="cargar" />
  <BarraSeleccion :cantidad="sel.ids.size" singular="product" plural="products" @limpiar="sel.limpiar()">
    <template #resumen>
      <template v-if="interno && porAprobar.length">{{ t('{0} ready to approve', [porAprobar.length]) }}</template>
    </template>
    <button v-if="puede('producto.ficha')" class="btn" :disabled="ocupado" :title="t('Run the classification engine on the saved technical sheets')" @click="clasificar"><Icono nombre="varita" />{{ t('Classify') }}</button>
    <button v-if="puede('producto.clasificar') && flujo.aprobacion_lote !== false" class="btn btn-primario" :disabled="ocupado || !porAprobar.length"
            :title="t('Approve the suggested code of the complete sheets')" @click="aprobar"><Icono nombre="check" />{{ t('Approve {0}', [porAprobar.length || '']) }}</button>
    <button v-if="envia" class="btn btn-primario" :disabled="ocupado || !porEnviar.length"
            :title="t('Send the complete drafts to review')" @click="enviar"><Icono nombre="enviar" />{{ t('Send to review {0}', [porEnviar.length || '']) }}</button>
  </BarraSeleccion>
</template>

<style scoped>
.producto-celda { display: flex; align-items: center; gap: 10px; }
.miniatura { width: 38px; height: 38px; border-radius: 8px; background: var(--superficie-2); border: 1px solid var(--linea); display: grid; place-items: center; color: var(--tinta-3); overflow: hidden; flex: none; }
.sub-mod { margin-bottom: 10px; }
.siguiente :deep(svg) { vertical-align: -2px; margin-inline-end: 3px; }
.siguiente.accion { color: var(--acento-texto); font-weight: 600; }
.sub-mod .pildora { text-decoration: none; }
.recortar { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.miniatura img { width: 100%; height: 100%; object-fit: cover; }
</style>
