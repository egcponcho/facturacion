<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import CargaArticulos from '@/modulos/maestros/componentes/CargaArticulos.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { cargarContexto, clasificarVarios } from '@/modulos/clasificacion/useClasificacion'
import { fmtCode } from '@/modulos/clasificacion/formato.js'
import { estado as leerEstado } from '@/nucleo/estados.js'
import { comercioExterior, esInterno, puede, sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import Segmentos from '@/componentes/Segmentos.vue'

// Catálogo de productos: cada producto con sus variantes (SKU), packs y kits.
// Con el complemento de comercio exterior es además la bandeja de las fichas
// técnicas y su clasificación arancelaria (por estado); sin él, una lista simple.
const route = useRoute()
const router = useRouter()
const interno = esInterno()
const comex = comercioExterior()
// Quien aprueba empieza por lo que espera revisión; quien llena la ficha, por lo que falta completar
const revisa = puede('producto.clasificar')
// Filtros de la pantalla: búsqueda y bandeja (vista de estado); el resto (familia,
// cada atributo del producto, categoría, código, estado, proveedor…) va en el filtro de su columna
const filtros = reactive({
  estado: route.query.estado ?? (!comex ? '' : revisa ? 'revision' : 'borradores'),
  q: route.query.q || '',
})
const datos = ref({ items: [], total: 0, kpis: {} })
// Sin pestaña pedida en la dirección, se abre la primera que tenga productos
// (y no una vacía con «Nada pendiente aquí»)
let elegirInicial = route.query.estado === undefined && comex
const opciones = ref({ marcas: [], paises: [], atributos: [] })
const cargando = ref(false)
const ocupado = ref(false)
const seleccion = ref([])
const cargaAbierta = ref(false)
const tabla = ref(null)

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

// Categorías (para el nombre en el filtro de su columna): las de la configuración
const categorias = ref([])
if (comex) cargarContexto().then((c) => (categorias.value = (c.categorias || []).map((x) => [x.codigo, x.nombre_corto || x.nombre]))).catch(() => {})
const nombresMarca = computed(() => Object.fromEntries((opciones.value.marcas || []).map((m) => [m.codigo, m.nombre])))
const nombresPais = computed(() => Object.fromEntries((opciones.value.paises || []).map((x) => [x.codigo, x.nombre])))
const ESTADOS_PRODUCTO = ['borrador', 'sugerida', 'observado', 'revision', 'aprobado', 'corregido']
  .map((c) => [c, c === 'corregido' ? t('Corrected') : leerEstado(c, 'producto')[0]])
// Columnas (TablaDatos en modo servidor): cada una filtra por sus valores únicos
// (los da el servidor); la de países se calcula al vuelo y no se filtra
const columnas = computed(() => [
  { clave: 'producto', texto: t('Product'), fija: true, prioridad: 1 },
  { clave: 'generico', texto: t('Product code'), inicial: false, prioridad: 3 },
  ...(!sesion.proveedorId && interno ? [{ clave: 'proveedor', texto: t('Supplier'), prioridad: 2 }] : []),
  { clave: 'familia', texto: t('Family'), prioridad: 2 },
  // Una columna por atributo del producto (marca, modelo, material…): los que defina la empresa
  ...(opciones.value.atributos || []).map((a, i) => ({ clave: `atr.${a.codigo}`, texto: a.nombre, prioridad: i < 2 ? 2 : 3,
    inicial: i < 2, ordenable: false, valor: (p) => p.atributos?.[a.codigo],
    textoValor: (v) => (a.catalogo === 'marcas' ? nombresMarca.value[v] || v : v) })),
  // La ficha técnica y la clasificación, solo con el complemento de comercio exterior
  ...(comex ? [
    { clave: 'tipo', texto: t('Category'), prioridad: 3, opciones: categorias.value },
    { clave: 'codigo', texto: t('HS code'), prioridad: 2, textoValor: (v) => fmtCode(v) },
    { clave: 'origen', texto: t('Origin'), inicial: false, prioridad: 3, opciones: Object.entries(nombresPais.value) },
    { clave: 'paises', texto: t('Countries'), ordenable: false, filtro: false, prioridad: 3 },
    { clave: 'estado', texto: t('Status'), prioridad: 1, opciones: ESTADOS_PRODUCTO },
  ] : []),
])

// Filtros de la pantalla que viajan con la lista, los valores de cada columna y la exportación
// Desde el resumen: ?familia=<id> muestra solo esa familia (y sus subfamilias)
const familia = ref(route.query.familia ? String(route.query.familia) : '')
const nombreFamilia = ref('')
if (familia.value) api.get('/grupos-producto').then((l) => (nombreFamilia.value = (l || []).find((x) => String(x.id) === familia.value)?.nombre || '')).catch(() => {})
function quitarFamilia() {
  familia.value = ''
  router.replace({ query: { ...route.query, familia: undefined } })
  recargar()
}
const pantalla = () => ({ estado: filtros.estado, q: filtros.q, proveedor_id: sesion.proveedorId || undefined,
  familia: familia.value || undefined })
const filtrosColumna = (c) => (c && Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined)
const valores = (columna, buscar, otros) => api.get('/productos/valores', { columna, buscar, f: JSON.stringify(otros), ...pantalla() })

let ultima = null
let turno = 0
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  const n = ++turno
  let otra = false
  cargando.value = true
  try {
    const r = await api.get('/productos', { ...pantalla(), orden: c.orden, page: c.page, size: c.size, f: filtrosColumna(c) })
    if (n !== turno) return // llegó una consulta más nueva
    datos.value = r
    const ids = new Set(r.items.map((p) => p.id))
    seleccion.value = seleccion.value.filter((id) => ids.has(id))
    if (elegirInicial) {
      elegirInicial = false
      if (!r.total) {
        const conDatos = VISTAS.value.find(([v, , k]) => v && k)
        filtros.estado = conDatos ? conDatos[0] : ''
        otra = true
      }
    }
    if (!otra) router.replace({ query: { estado: filtros.estado, ...(filtros.q && { q: filtros.q }) } })
  } catch (e) {
    errorApi(e)
  } finally {
    if (n === turno) cargando.value = false
  }
  if (otra) consultar()
}
// La búsqueda, la vista, la marca o el proveedor elegido vuelven a la primera página
function recargar() {
  if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}
function elegirVista(v) {
  filtros.estado = v
  elegirInicial = false
  recargar()
}

// Vistas guardadas: también la bandeja y la búsqueda
const externos = computed(() => ({ estado: filtros.estado, q: filtros.q }))
function aplicarVista(q) {
  filtros.estado = q.estado || ''
  filtros.q = q.q || ''
  elegirInicial = false
  recargar()
}

const elegidos = computed(() => datos.value.items.filter((p) => seleccion.value.includes(p.id)))
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
    seleccion.value = []
    await consultar()
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
    seleccion.value = []
    await consultar()
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
    seleccion.value = []
    await consultar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

// La exportación lleva los mismos filtros y el mismo orden que la tabla
async function exportar(formato) {
  try {
    await api.descargar('/productos/exportar', t('products.{0}', [formato]), { ...pantalla(), orden: ultima?.orden, f: filtrosColumna(ultima), formato })
  } catch (e) {
    errorApi(e)
  }
}

const codigoDe = (p) => p.codigo || p.sugerido
const descCorta = (d) => (d && d.length > 60 ? `${d.slice(0, 58)}…` : d || '')

onMounted(async () => {
  try {
    opciones.value = await api.get('/productos/opciones')
  } catch {
    /* los filtros extra son opcionales */
  }
})
watch(() => sesion.proveedorId, recargar)
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => consultar(), ['/productos'])
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Products') }}</h1>
      <p v-if="!comex">{{ t('Every product with its variants, packs and kits.') }}</p>
      <p v-else-if="interno">{{ t('Products, technical sheets and tariff classification. Approved HS codes flow to purchase orders and invoices for each destination country.') }}</p>
      <p v-else>{{ t('Complete the technical sheet of each product. Customs uses it to classify it; the approved code appears on your orders and invoices.') }}</p>
    </div>
    <div class="acciones">
      <button class="btn btn-fantasma" @click="exportar('xlsx')"><Icono nombre="descargar" />{{ t('Excel') }}</button>
      <button class="btn btn-fantasma" @click="exportar('pdf')"><Icono nombre="descargar" />PDF</button>
      <button v-if="puede('catalogos.crear')" class="btn" @click="cargaAbierta = true"><Icono nombre="importar" />{{ t('Upload products') }}</button>
    </div>
  </div>

  <TablaDatos ref="tabla" tabla="productos" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :valores="valores" :externos="externos"
              seleccionable v-model:seleccion="seleccion" fila-clicable :etiqueta="t('Products')"
              @consulta="consultar" @fila="(p) => router.push(`/productos/${p.id}`)" @vista="aplicarVista">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="comex ? t('Product code, name, item code, barcode or HS code') : t('Product code, name, item code or barcode')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <Segmentos v-if="comex" :model-value="filtros.estado" :opciones="VISTAS" :etiqueta="t('View')" @change="elegirVista" />
      <button v-if="familia" type="button" class="chip-filtro" :aria-label="t('Remove filter {0}', [tx(nombreFamilia || familia)])" @click="quitarFamilia">
        {{ t('Family: {0}', [tx(nombreFamilia || familia)]) }}<Icono nombre="cerrar" :tam="13" /></button>
    </template>

    <template #celda-producto="{ fila: p }">
      <div class="producto-celda">
        <span class="miniatura">
          <img v-if="p.foto_id" :src="`/api/productos/fotos/${p.foto_id}`" alt="" loading="lazy" />
          <Icono v-else nombre="caja" :tam="18" />
        </span>
        <span>
          <router-link :to="`/productos/${p.id}`" class="enlace-doc" @click.stop><strong><span v-if="p.codigo_generico" class="codigo">{{ tx(p.codigo_generico) }}</span> {{ tx(p.nombre || '—') }}</strong></router-link>
          <span class="sub">{{ [p.descripcion_comercial, p.resumen_variantes || t('no variants')].filter(Boolean).map(tx).join(' · ') }}</span>
        </span>
      </div>
    </template>
    <template #celda-familia="{ fila: p }"><template v-if="p.familia">{{ tx(p.familia) }}</template><span v-else class="apagado">—</span></template>
    <template v-for="a in opciones.atributos" :key="a.codigo" #[`celda-atr.${a.codigo}`]="{ fila: p }">
      <template v-if="p.atributos?.[a.codigo]">{{ tx(a.catalogo === 'marcas' ? p.marca_nombre || p.atributos[a.codigo] : p.atributos[a.codigo]) }}</template>
      <span v-else class="apagado">—</span></template>
    <template #celda-generico="{ fila: p }"><span class="codigo">{{ tx(p.codigo_generico || '—') }}</span></template>
    <template #celda-tipo="{ fila: p }">
      <template v-if="p.tipo">{{ tx(p.tipo_txt || p.tipo) }}</template>
      <span v-else class="apagado">—</span>
    </template>
    <template #celda-codigo="{ fila: p }">
      <template v-if="codigoDe(p)">
        <span class="codigo-sac" :class="{ tentativo: !p.codigo }">{{ tx(codigoDe(p)) }}</span>
        <span class="sub" :title="tx(p.codigo_desc || '')">{{ tx(p.codigo ? descCorta(p.codigo_desc) : t('Suggested, not approved')) }}</span>
      </template>
      <span v-else class="apagado">{{ t('Not classified') }}</span>
    </template>
    <template #celda-origen="{ fila: p }">
      <template v-if="p.pais_origen">{{ tx(nombresPais[p.pais_origen] || p.pais_origen) }}</template>
      <span v-else class="apagado">—</span>
    </template>
    <template #celda-paises="{ fila: p }">
      <span v-if="p.paises_ok === p.paises_total" class="etiqueta ok ms-0"><Icono nombre="check" :tam="12" />{{ tx(p.paises_ok) }}/{{ tx(p.paises_total) }}</span>
      <span v-else-if="p.paises_ok" class="etiqueta aviso ms-0">{{ tx(p.paises_ok) }}/{{ tx(p.paises_total) }}</span>
      <span v-else class="apagado">—</span>
    </template>
    <template #celda-estado="{ fila: p }">
      <EstadoBadge :estado="p.estado" tipo="producto" />
      <span v-if="siguiente(p)" class="sub recortar siguiente" :class="{ accion: siguiente(p).accion }" :title="tx(p.faltan.join(', '))">
        <Icono v-if="siguiente(p).accion" nombre="derecha" :tam="12" />{{ tx(siguiente(p).texto) }}</span>
    </template>
    <template #acciones><Icono nombre="derecha" :tam="16" /></template>
    <template #vacio>
      <EstadoVacio v-if="!datos.kpis?.total && !filtros.q" icono="etiqueta" :titulo="t('There are no products yet.')"
                   :texto="t('A product has a code, a name and a unit, and its variants differ by the attributes of its family. Create one with New product, upload them in bulk or import them with the purchase orders.')">
        <router-link v-if="puede('catalogos.ver')" class="btn" to="/mantenimiento"><Icono nombre="base" />{{ t('Master data') }}</router-link>
        <router-link v-if="puede('oc.importar')" class="btn btn-primario" to="/importar"><Icono nombre="importar" />{{ t('Import purchase orders') }}</router-link>
      </EstadoVacio>
      <template v-else-if="['pendientes', 'sugerida', 'revision', 'borradores', 'baja_confianza', 'bloquean'].includes(filtros.estado)"><Icono nombre="check" /> {{ t('Nothing pending here.') }}</template>
      <template v-else>{{ t('No products match these filters.') }}</template>
    </template>
  </TablaDatos>

  <CargaArticulos v-if="cargaAbierta" @cerrar="cargaAbierta = false" @listo="consultar()" />
  <BarraSeleccion :cantidad="seleccion.length" singular="product" plural="products" @limpiar="seleccion = []">
    <template #resumen>
      <template v-if="interno && porAprobar.length">{{ t('{0} ready to approve', [porAprobar.length]) }}</template>
    </template>
    <button v-if="comex && puede('producto.ficha')" class="btn" :disabled="ocupado" :title="t('Run the classification engine on the saved technical sheets')" @click="clasificar"><Icono nombre="varita" />{{ t('Classify') }}</button>
    <button v-if="comex && puede('producto.clasificar') && flujo.aprobacion_lote !== false" class="btn btn-primario" :disabled="ocupado || !porAprobar.length"
            :title="t('Approve the suggested code of the complete sheets')" @click="aprobar"><Icono nombre="check" />{{ t('Approve {0}', [porAprobar.length || '']) }}</button>
    <button v-if="comex && envia" class="btn btn-primario" :disabled="ocupado || !porEnviar.length"
            :title="t('Send the complete drafts to review')" @click="enviar"><Icono nombre="enviar" />{{ t('Send to review {0}', [porEnviar.length || '']) }}</button>
  </BarraSeleccion>
</template>

<style scoped>
.producto-celda { display: flex; align-items: center; gap: 10px; }
.miniatura { width: 38px; height: 38px; border-radius: 8px; background: var(--superficie-2); border: 1px solid var(--linea); display: grid; place-items: center; color: var(--tinta-3); overflow: hidden; flex: none; }
.td-compacta .miniatura { width: 26px; height: 26px; border-radius: 6px; }
.td-amplia .miniatura { width: 48px; height: 48px; }
.sub-mod { margin-bottom: 10px; }
.siguiente :deep(svg) { vertical-align: -2px; margin-inline-end: 3px; }
.siguiente.accion { color: var(--acento-texto); font-weight: 600; }
.sub-mod .pildora { text-decoration: none; }
.recortar { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.miniatura img { width: 100%; height: 100%; object-fit: cover; }
.chip-filtro { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--acento-medio); background: var(--acento-claro); color: var(--acento-texto);
  border-radius: 20px; padding: 4px 10px; font: inherit; font-size: var(--t-sm); font-weight: 600; cursor: pointer; }
.chip-filtro:hover { border-color: var(--acento); }
</style>
