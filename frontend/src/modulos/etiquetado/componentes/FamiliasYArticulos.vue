<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import Icono from '@/componentes/Icono.vue'
import MenuAcciones from '@/componentes/MenuAcciones.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtNum, textoVariante } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import CategoriasFamilia from '@/modulos/etiquetado/componentes/CategoriasFamilia.vue'
import CeldaEtiquetado from '@/modulos/etiquetado/componentes/CeldaEtiquetado.vue'
import FormFamilia from '@/modulos/etiquetado/componentes/FormFamilia.vue'
import { textoDonde, textoSalida } from '@/modulos/etiquetado/etiquetas.js'

// Familias de etiquetado y qué es de cada una. A la izquierda el árbol (solo
// nombres y cuántos artículos tienen); a la derecha la ficha de la elegida
// (sus etiquetas, sus campos y sus acciones juntas) y lo que pertenece a ella:
// productos (la familia se pone al producto y la heredan sus tallas), artículos
// con familia propia o grupos de artículos completos. Para agregar no hay que ir
// al final: «Agregar a esta familia» está arriba y lo elegido se pone desde la
// barra flotante. Editar y crear se hace en la misma página, sin ventanas.
const route = useRoute()
const router = useRouter()
const editable = computed(() => puede('etiquetas.familias'))
const familias = ref([])
const elegida = ref(route.query.familia ? String(route.query.familia) : '') // '' todas · 'sin' · id
const que = ref('productos')
const cargandoFamilias = ref(false)

async function cargarFamilias() {
  cargandoFamilias.value = true
  try {
    familias.value = await api.get('/etiquetas/familias')
  } catch (e) {
    errorApi(e)
  } finally {
    cargandoFamilias.value = false
  }
}
onMounted(cargarFamilias)
alCambiar(() => cargarFamilias(), ['/etiquetas/familias'])
const arbol = computed(() => {
  const hijos = {}
  for (const f of familias.value) (hijos[f.padre_id || 0] ||= []).push(f)
  const res = []
  const poner = (padre, nivel) => (hijos[padre] || []).sort((a, b) => a.orden - b.orden).forEach((f) => {
    res.push({ ...f, nivel })
    poner(f.id, nivel + 1)
  })
  poner(0, 0)
  return res
})
const familiaElegida = computed(() => familias.value.find((f) => String(f.id) === elegida.value) || null)
const tituloDerecha = computed(() => (elegida.value === 'sin' ? t('Without family') : familiaElegida.value ? tx(familiaElegida.value.nombre) : t('All')))
const subfamilias = computed(() => (familiaElegida.value ? familias.value.filter((f) => f.padre_id === familiaElegida.value.id) : []))
function elegir(v) {
  elegida.value = v
  modo.value = 'ver'
  celda.value = null
}
watch(elegida, (v) => router.replace({ query: { ...route.query, familia: v || undefined } }))

// ---- Las etiquetas de la familia (de la matriz: propio, heredado o falta) -----------------------------
const matriz = ref(null)
async function cargarMatriz() {
  try {
    matriz.value = await api.get('/etiquetas/matriz', { sujeto: 'ARTICULO' })
  } catch {
    matriz.value = null
  }
}
onMounted(cargarMatriz)
alCambiar(() => cargarMatriz(), ['/etiquetas/usos', '/etiquetas/tipos', '/etiquetas/plantillas', '/etiquetas/familias', '/etiquetas/categorias'])
const filaMatriz = computed(() => (matriz.value?.filas || []).find((f) => f.nivel === 'FAMILIA' && String(f.id) === elegida.value))
const celda = ref(null)
function abrirCelda(tipo) {
  const f = filaMatriz.value
  celda.value = { tipo, nivel: 'FAMILIA', destinoId: f.id, nombre: tx(f.nombre) }
}
// La celda de una categoría de la familia (sus reglas, más específicas que las de la familia)
function abrirCeldaCategoria(c) {
  celda.value = c
}
// Las categorías de la familia elegida (para ponerlas a mano en productos)
const categorias = ref([])
const categoriaDestino = ref('')
async function asignarCategoria(categoria) {
  try {
    const r = await api.post('/etiquetas/productos/categoria', { categoria_id: categoria ? Number(categoria) : null, ids: seleccion.value })
    avisar(t('{0} changed.', [fmtNum(r.cambiados)]))
    categoriaDestino.value = ''
    cargarMatriz()
    recargar()
  } catch (e) {
    errorApi(e)
  }
}
function celdaGuardada() {
  celda.value = null
  cargarMatriz()
}

// ---- Productos, artículos o grupos ------------------------------------------------------------------
// ver: lo que es de la familia elegida · agregar: lo que aún no es de ella (sin familia o de otra)
const modo = ref('ver')
const origenAgregar = ref('sin')
const filtroFamilia = computed(() => (modo.value === 'agregar' ? origenAgregar.value : elegida.value) || undefined)
const tabla = ref(null)
const q = ref('')
const datos = ref({ items: [], total: 0 })
const grupos = ref([])
const cargando = ref(false)
const seleccion = ref([])
const destino = ref('')
let ultima = null
async function consultar(c = ultima) {
  if (que.value === 'grupos') return cargarGrupos()
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    const ruta = que.value === 'productos' ? '/etiquetas/productos' : '/etiquetas/articulos'
    const r = await api.get(ruta, { q: q.value || undefined, familia: filtroFamilia.value, page: c.page, size: c.size })
    // Al agregar desde «todas», no se ofrece lo que ya es de esta familia
    datos.value = modo.value === 'agregar' && !origenAgregar.value
      ? { ...r, items: r.items.filter((x) => String(x.familia_id || '') !== elegida.value) } : r
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function cargarGrupos() {
  cargando.value = true
  try {
    const r = await api.get('/etiquetas/grupos-articulos', { q: q.value || undefined, familia: filtroFamilia.value })
    grupos.value = modo.value === 'agregar' ? r.filter((g) => String(g.familia_id || '') !== elegida.value) : r
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function recargar() {
  seleccion.value = []
  if (que.value === 'grupos') return cargarGrupos()
  await nextTick()
  if (tabla.value && tabla.value.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
watch(q, () => {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
})
watch([elegida, que, modo, origenAgregar], recargar)
onMounted(() => que.value === 'grupos' && cargarGrupos())

const columnas = computed(() => (que.value === 'productos' ? [
  { clave: 'estilo', texto: t('Product'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'nombre', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'grupo', texto: t('Group'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'tallas', texto: t('Sizes'), num: true, prioridad: 3, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
  { clave: 'categoria', texto: t('Labeling category'), prioridad: 2, ordenable: false, filtro: false },
] : que.value === 'articulos' ? [
  { clave: 'sku', texto: t('SKU'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'descripcion', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'variante', texto: t('Variant'), valor: (x) => textoVariante(x), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'grupo', texto: t('Group'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
] : [
  { clave: 'codigo', texto: t('Group'), fija: true, prioridad: 1 },
  { clave: 'nombre', texto: t('Name'), prioridad: 1 },
  { clave: 'categoria', texto: t('Category'), prioridad: 3 },
  { clave: 'articulos', texto: t('Items'), num: true, prioridad: 2 },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1 },
]))
const ORIGEN = () => ({ ARTICULO: t('own'), PRODUCTO: t('by product'), GRUPO: t('by group') })
const QUE_TXT = () => ({ productos: t('products'), articulos: t('items'), grupos: t('groups') })

// Poner en una familia (o quitarla) lo elegido; con artículos, también todos los del filtro
async function asignar(familia, todos = false) {
  const familia_id = familia === 'ninguna' || familia == null ? null : Number(familia)
  try {
    let r
    if (que.value === 'productos') r = await api.post('/etiquetas/productos/familia', { familia_id, ids: seleccion.value })
    else if (que.value === 'grupos') r = await api.post('/etiquetas/grupos-articulos/familia', { familia_id, grupo_ids: seleccion.value })
    else {
      r = await api.post('/etiquetas/articulos/familia', todos ? { familia_id, filtro: { q: q.value || undefined, familia: filtroFamilia.value } }
        : { familia_id, ids: seleccion.value })
    }
    avisar(t('{0} changed.', [fmtNum(r.cambiados ?? seleccion.value.length)]))
    destino.value = ''
    await cargarFamilias()
    cargarMatriz()
    recargar()
  } catch (e) {
    errorApi(e)
  }
}
const otrasFamilias = computed(() => arbol.value.filter((x) => x.activa && String(x.id) !== elegida.value))

// ---- Alta y edición en la página ---------------------------------------------------------------------
const formulario = ref(null)
function editar(f) {
  formulario.value = { ...f, campos: (f.campos || []).map((c) => ({ ...c })) }
  modo.value = 'editar'
  celda.value = null
}
async function guardar() {
  const f = formulario.value
  const cuerpo = { codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion, activa: f.activa, campos: f.campos, padre_id: f.padre_id || null }
  try {
    const r = f.id ? await api.patch(`/etiquetas/familias/${f.id}`, cuerpo) : await api.post('/etiquetas/familias', cuerpo)
    avisar(f.id ? t('Family saved.') : t('Family “{0}” created.', [f.nombre]))
    formulario.value = null
    await cargarFamilias()
    elegida.value = String(r.id)
    modo.value = f.id ? 'ver' : 'agregar' // recién creada: lo siguiente es ponerle productos
  } catch (e) {
    errorApi(e)
  }
}
function cancelar() {
  formulario.value = null
  modo.value = 'ver'
}
async function eliminar(f) {
  if (!(await confirmar(t('The family {0} is deleted (if something uses it, it is deactivated instead).', [f.nombre]), { titulo: t('Delete family'), boton: t('Delete'), peligro: true }))) return
  try {
    await api.del(`/etiquetas/familias/${f.id}`)
    avisar(t('Family deleted.'))
    formulario.value = null
    elegir('')
    cargarFamilias()
  } catch (e) {
    errorApi(e)
  }
}
async function mover(f, delta) {
  const hermanas = arbol.value.filter((x) => (x.padre_id || 0) === (f.padre_id || 0))
  const i = hermanas.findIndex((x) => x.id === f.id)
  const j = i + delta
  if (j < 0 || j >= hermanas.length) return
  const ids = familias.value.slice().sort((a, b) => a.orden - b.orden).map((x) => x.id)
  const a = ids.indexOf(hermanas[i].id)
  const b = ids.indexOf(hermanas[j].id)
  ;[ids[a], ids[b]] = [ids[b], ids[a]]
  try {
    familias.value = await api.put('/etiquetas/familias/orden', { ids })
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="fa">
    <aside class="fa-arbol panel" :aria-label="t('Labeling families')">
      <div class="fa-cabeza">
        <h3>{{ t('Families') }}</h3>
        <button v-if="editable" type="button" class="btn btn-chico btn-primario" @click="router.push('/etiquetas/configuracion/familia/nueva')"><Icono nombre="mas" :tam="14" />{{ t('New family') }}</button>
      </div>
      <ul>
        <li><button type="button" class="fa-item" :aria-pressed="elegida === ''" @click="elegir('')"><span>{{ t('All') }}</span></button></li>
        <li v-for="f in arbol" :key="f.id">
          <button type="button" class="fa-item" :class="{ apagada: !f.activa, sub: f.nivel > 0 }" :style="{ '--nivel': f.nivel }"
                  :aria-pressed="elegida === String(f.id)" @click="elegir(String(f.id))">
            <span class="fa-nombre">{{ tx(f.nombre) }}<small v-if="!f.activa"> · {{ t('inactive') }}</small></span>
            <span class="fa-cuenta">{{ fmtNum(f.articulos || 0) }}</span></button>
        </li>
        <li><button type="button" class="fa-item fa-sin" :aria-pressed="elegida === 'sin'" @click="elegir('sin')"><span>{{ t('Without family') }}</span></button></li>
      </ul>
      <p v-if="!familias.length && !cargandoFamilias" class="ayuda">{{ t('No labeling families yet. Create the ones your operation needs, for example footwear, apparel or chemicals.') }}</p>
    </aside>

    <section class="fa-contenido">
      <!-- Crear o editar una familia (en la página) -->
      <div v-if="modo === 'editar' && formulario" class="panel fa-edicion">
        <header class="fa-edicion-cabeza">
          <button type="button" class="btn btn-icono" :aria-label="t('Back')" @click="cancelar"><Icono nombre="atras" /></button>
          <h3>{{ formulario.id ? t('Edit the family {0}', [tx(formulario.nombre)]) : t('New labeling family') }}</h3>
          <button v-if="formulario.id" type="button" class="btn btn-peligro" @click="eliminar(formulario)"><Icono nombre="basura" :tam="15" />{{ t('Delete') }}</button>
        </header>
        <form id="form-familia" @submit.prevent="guardar">
          <FormFamilia v-model="formulario" :familias="arbol" />
        </form>
        <footer class="fa-edicion-pie">
          <button type="button" class="btn" @click="cancelar">{{ t('Cancel') }}</button>
          <button type="submit" form="form-familia" class="btn btn-primario" :disabled="!formulario.codigo.trim() || !formulario.nombre.trim()">
            {{ formulario.id ? t('Save') : t('Create and add products') }}</button>
        </footer>
      </div>

      <template v-else>
        <!-- Ficha de la familia elegida -->
        <div v-if="familiaElegida" class="panel fa-ficha">
          <div class="fa-ficha-cabeza">
            <div class="fa-ficha-titulo">
              <p v-if="familiaElegida.padre_id" class="fa-ruta">{{ tx(familiaElegida.ruta || '') }}</p>
              <h3>{{ tx(familiaElegida.nombre) }} <span class="etiqueta ms-0">{{ familiaElegida.codigo }}</span>
                <span v-if="!familiaElegida.activa" class="etiqueta aviso ms-0">{{ t('Inactive') }}</span></h3>
              <p class="ayuda">{{ t('{0} items · {1} products · {2} groups', [fmtNum(familiaElegida.articulos || 0), fmtNum(familiaElegida.productos || 0), fmtNum(familiaElegida.grupos || 0)]) }}
                <template v-if="subfamilias.length"> · {{ t('{0} subfamilies', [subfamilias.length]) }}</template></p>
            </div>
            <div v-if="editable" class="fa-ficha-acciones">
              <router-link :to="`/etiquetas/configuracion/familia/${familiaElegida.id}`" class="btn btn-primario"><Icono nombre="varita" :tam="15" />{{ t('Set up step by step') }}</router-link>
              <button type="button" class="btn" @click="editar(familiaElegida)"><Icono nombre="editar" :tam="15" />{{ t('Edit') }}</button>
              <MenuAcciones :etiqueta="t('More options of the family')">
                <button type="button" role="menuitem" @click="router.push({ path: '/etiquetas/configuracion/familia/nueva', query: { padre: familiaElegida.id } })">{{ t('New subfamily') }}</button>
                <button type="button" role="menuitem" @click="mover(familiaElegida, -1)">{{ t('Move up in the list') }}</button>
                <button type="button" role="menuitem" @click="mover(familiaElegida, 1)">{{ t('Move down in the list') }}</button>
                <button type="button" role="menuitem" @click="eliminar(familiaElegida)">{{ t('Delete') }}</button>
              </MenuAcciones>
            </div>
          </div>
          <div v-if="filaMatriz" class="fa-etiquetas">
            <p class="fa-etiquetas-titulo">{{ t('Its labels') }}</p>
            <button v-for="tp in matriz.tipos" :key="tp.id" type="button" class="fa-etiqueta" :class="{ falta: filaMatriz.celdas[tp.id].falta }"
                    :title="t('Change the design of {0} for this family', [tx(tp.nombre)])" @click="abrirCelda(tp)">
              <span class="fa-etiqueta-tipo">{{ tx(tp.nombre) }}</span>
              <span v-if="filaMatriz.celdas[tp.id].normal" class="fa-etiqueta-diseno"><Icono :nombre="filaMatriz.celdas[tp.id].normal.accion === 'NO_LLEVA' ? 'cerrar' : 'etiqueta'" :tam="13" />{{ textoSalida(filaMatriz.celdas[tp.id].normal) }}</span>
              <span v-else-if="filaMatriz.celdas[tp.id].falta" class="fa-etiqueta-diseno aviso"><Icono nombre="alerta" :tam="13" />{{ t('No design (required)') }}</span>
              <span v-else-if="filaMatriz.celdas[tp.id].hereda" class="fa-etiqueta-diseno apagado">↳ {{ textoSalida(filaMatriz.celdas[tp.id].hereda) }}
                <small>({{ textoDonde(filaMatriz.celdas[tp.id].hereda.nivel, filaMatriz.celdas[tp.id].hereda.destino) }})</small></span>
              <span v-else class="fa-etiqueta-diseno apagado">—</span>
              <span v-if="filaMatriz.celdas[tp.id].excepciones" class="fa-etiqueta-extra">{{ t('{0} exceptions', [filaMatriz.celdas[tp.id].excepciones]) }}</span>
            </button>
          </div>
          <p v-if="familiaElegida.campos?.length" class="ayuda fa-campos-txt">{{ t('Fields') }}:
            {{ familiaElegida.campos.map((c) => c.campo + (c.obligatorio ? ' *' : '')).join(' · ') }}</p>
          <CategoriasFamilia v-if="!celda" :familia="familiaElegida" :matriz="matriz" @celda="abrirCeldaCategoria" @cambio="cargarMatriz"
                             @cargadas="categorias = $event" />
        </div>
        <div v-else class="fa-titulo">
          <h3>{{ tituloDerecha }}</h3>
        </div>

        <CeldaEtiquetado v-if="celda" :tipo="celda.tipo" :nivel="celda.nivel" :destino-id="celda.destinoId" :nombre="celda.nombre"
                         @cerrar="celda = null" @guardado="celdaGuardada" />

        <template v-else>
          <!-- Arriba de la tabla: qué se ve, buscar y agregar (nada de ir hasta el final) -->
          <div class="fa-barra">
            <Segmentos v-model="que" :opciones="[['productos', t('Products')], ['articulos', t('Items (sizes)')], ['grupos', t('Item groups')]]" :etiqueta="t('Show')" />
            <label class="buscador fa-buscar"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search')" :aria-label="t('Search')" /></label>
            <span class="crece" />
            <template v-if="familiaElegida && editable">
              <button v-if="modo === 'ver'" type="button" class="btn btn-primario" @click="modo = 'agregar'"><Icono nombre="mas" :tam="15" />{{ t('Add to this family') }}</button>
              <button v-else type="button" class="btn" @click="modo = 'ver'"><Icono nombre="atras" :tam="15" />{{ t('Back to the family') }}</button>
            </template>
          </div>
          <div v-if="modo === 'agregar'" class="nota fa-agregando">
            <Icono nombre="info" :tam="16" />
            <span>{{ t('Choose the {0} to put in «{1}», then use the bar at the bottom.', [QUE_TXT()[que], tituloDerecha]) }}</span>
            <Segmentos v-model="origenAgregar" :opciones="[['sin', t('Without family')], ['', t('All the others')]]" :etiqueta="t('From')" />
          </div>
          <p v-else class="ayuda">{{ que === 'productos' ? t('The family is set on the product; all its sizes inherit it unless a size has its own.')
            : que === 'articulos' ? t('A size with its own family keeps it even if its product or group has another one.')
              : t('Every item of a group belongs to its family, except the products or items that have their own.') }}</p>

          <TablaDatos v-if="que !== 'grupos'" :key="`${que}-${modo}`" ref="tabla" :tabla="`etiquetas_${que}`" modo="servidor" :columnas="columnas" :filas="datos.items"
                      :total="datos.total" :cargando="cargando" :seleccionable="editable" v-model:seleccion="seleccion" :etiqueta="tituloDerecha"
                      :externos="{ q, elegida, modo, origenAgregar }" @consulta="consultar">
            <template #celda-estilo="{ fila: p }"><router-link :to="`/productos/${p.id}?vista=etiquetas`" class="enlace"><strong>{{ p.estilo }}</strong></router-link><span class="sub">{{ p.color }}</span></template>
            <template #celda-sku="{ fila: a }"><strong class="codigo">{{ a.sku }}</strong><span class="sub">{{ a.estilo }}</span></template>
            <template #celda-familia="{ fila: x }">
              <span v-if="x.familia" class="etiqueta ms-0">{{ tx(x.familia) }}</span>
              <span v-if="x.familia && x.familia_origen" class="sub">{{ ORIGEN()[x.familia_origen] }}</span>
              <span v-if="!x.familia" class="etiqueta aviso ms-0">{{ t('Without family') }}</span>
            </template>
            <template #celda-categoria="{ fila: x }">
              <template v-if="x.categoria"><span class="etiqueta ms-0">{{ tx(x.categoria) }}</span>
                <span class="sub">{{ x.categoria_parcial ? t('only some sizes') : x.categoria_origen === 'MANUAL' ? t('set by hand') : t('by its conditions') }}</span></template>
              <template v-else-if="x.categorias?.length"><span v-for="c in x.categorias" :key="c" class="etiqueta ms-0">{{ tx(c) }}</span>
                <span class="sub">{{ t('depends on the size') }}</span></template>
              <span v-else class="apagado">—</span>
            </template>
            <template #vacio>{{ modo === 'agregar' ? t('Nothing to add here: everything already has a family.') : t('Nothing here.') }}</template>
          </TablaDatos>
          <TablaDatos v-else tabla="etiquetas_grupos" :columnas="columnas" :filas="grupos" :cargando="cargando" :seleccionable="editable"
                      v-model:seleccion="seleccion" :etiqueta="t('Item groups')">
            <template #celda-codigo="{ fila: g }"><strong class="codigo">{{ g.codigo }}</strong></template>
            <template #celda-familia="{ fila: g }"><span v-if="g.familia" class="etiqueta ms-0">{{ tx(g.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></template>
            <template #vacio>{{ t('Nothing here.') }}</template>
          </TablaDatos>
          <p v-if="editable && modo === 'agregar' && que === 'articulos' && datos.total > seleccion.length" class="ayuda">
            <button type="button" class="enlace" @click="asignar(elegida, true)">{{ t('Put all {0} of the filter in «{1}»', [fmtNum(datos.total), tituloDerecha]) }}</button></p>
        </template>
      </template>
    </section>
  </div>

  <!-- Lo elegido: acciones en la barra flotante -->
  <BarraSeleccion v-if="editable && modo !== 'editar' && !celda" :cantidad="seleccion.length" :singular="t('record selected')" :plural="t('records selected')" @limpiar="seleccion = []">
    <template v-if="modo === 'agregar' && familiaElegida">
      <button type="button" class="btn" @click="asignar(familiaElegida.id)"><Icono nombre="mas" :tam="15" />{{ t('Put in «{0}»', [tx(familiaElegida.nombre)]) }}</button>
    </template>
    <template v-else>
      <Seleccion v-model="destino" class="fa-destino" :aria-label="t('Labeling family')">
        <option value="">{{ familiaElegida ? t('Move to…') : t('Put in…') }}</option>
        <option v-for="f in otrasFamilias" :key="f.id" :value="f.id">{{ '— '.repeat(f.nivel) }}{{ tx(f.nombre) }}</option>
      </Seleccion>
      <button type="button" class="btn" :disabled="!destino" @click="asignar(destino)"><Icono nombre="check" :tam="15" />{{ t('Apply') }}</button>
      <button v-if="elegida !== 'sin'" type="button" class="btn" @click="asignar('ninguna')"><Icono nombre="cerrar" :tam="15" />{{ t('Remove the family') }}</button>
      <!-- La categoría a mano (solo productos de una familia con categorías) -->
      <template v-if="que === 'productos' && familiaElegida && categorias.length">
        <Seleccion v-model="categoriaDestino" class="fa-destino" :aria-label="t('Labeling category')">
          <option value="">{{ t('Category…') }}</option>
          <option value="auto">{{ t('Recognize by its conditions') }}</option>
          <option v-for="c in categorias.filter((x) => x.activa)" :key="c.id" :value="c.id">{{ tx(c.nombre) }}</option>
        </Seleccion>
        <button type="button" class="btn" :disabled="!categoriaDestino" @click="asignarCategoria(categoriaDestino === 'auto' ? null : categoriaDestino)">
          <Icono nombre="check" :tam="15" />{{ t('Set category') }}</button>
      </template>
    </template>
  </BarraSeleccion>
</template>

<style scoped>
.fa { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 16px; align-items: start; }
.fa-arbol { position: sticky; top: 12px; max-height: calc(100vh - 140px); overflow: auto; padding: 12px; }
.fa-arbol ul { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.fa-cabeza, .fa-titulo { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.fa-cabeza h3, .fa-titulo h3 { margin: 0; font-size: var(--t-base); }
.fa-item { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px; text-align: start; background: none; border: 0;
  border-radius: 8px; padding: 7px 10px; padding-inline-start: calc(10px + var(--nivel, 0) * 16px); font: inherit; font-size: var(--t-sm); color: var(--tinta);
  cursor: pointer; min-height: 36px; position: relative; }
.fa-item.sub::before { content: ''; position: absolute; inset-inline-start: calc(var(--nivel) * 16px - 4px); top: 6px; bottom: 6px; border-inline-start: 1px solid var(--linea); }
.fa-item:hover { background: var(--superficie-2); }
.fa-item[aria-pressed='true'] { background: var(--acento-claro); color: var(--acento-texto); font-weight: 600; }
.fa-item.apagada .fa-nombre { opacity: 0.6; }
.fa-nombre { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fa-nombre small { font-weight: 400; }
.fa-sin { margin-top: 6px; border-top: 1px solid var(--linea-suave); border-radius: 0; }
.fa-cuenta { color: var(--tinta-3); font-size: var(--t-xs); font-weight: 500; flex: none; background: var(--superficie-2); border-radius: 10px; padding: 1px 7px; }
.fa-item[aria-pressed='true'] .fa-cuenta { background: var(--superficie); }
.fa-contenido { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
/* Ficha */
.fa-ficha { display: flex; flex-direction: column; gap: 12px; }
.fa-ficha-cabeza { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: flex-start; }
.fa-ficha-titulo h3 { margin: 0; font-size: var(--t-lg); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.fa-ficha-titulo p { margin: 4px 0 0; }
.fa-ruta { font-size: var(--t-xs); color: var(--tinta-3); margin: 0 0 2px !important; }
.fa-ficha-acciones { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.fa-etiquetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.fa-etiquetas-titulo { grid-column: 1 / -1; margin: 0; font-size: var(--t-xs); text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.fa-etiqueta { display: flex; flex-direction: column; gap: 3px; text-align: start; border: 1px solid var(--linea); border-radius: 10px; padding: 8px 10px;
  background: var(--superficie); font: inherit; color: var(--tinta); cursor: pointer; }
.fa-etiqueta:hover { border-color: var(--acento); background: var(--acento-claro); }
.fa-etiqueta.falta { border-color: var(--aviso); background: var(--aviso-fondo); }
.fa-etiqueta-tipo { font-size: var(--t-xs); color: var(--tinta-3); }
.fa-etiqueta-diseno { display: inline-flex; gap: 5px; align-items: center; font-weight: 600; font-size: var(--t-sm); flex-wrap: wrap; }
.fa-etiqueta-diseno.apagado { font-weight: 400; color: var(--tinta-2); }
.fa-etiqueta-diseno.aviso { color: var(--aviso); }
.fa-etiqueta-diseno small { color: var(--tinta-3); font-weight: 400; }
.fa-etiqueta-extra { font-size: var(--t-xs); color: var(--tinta-2); }
.fa-campos-txt { margin: 0; }
/* Barra de la tabla */
.fa-barra { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.fa-barra .crece { flex: 1; }
.fa-buscar input { min-width: 220px; }
.fa-agregando { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 0; }
.fa-agregando > span { flex: 1; min-width: 220px; }
/* Edición */
.fa-edicion { display: flex; flex-direction: column; gap: 14px; }
.fa-edicion-cabeza { display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--linea); padding-bottom: 12px; }
.fa-edicion-cabeza h3 { flex: 1; margin: 0; font-size: var(--t-md); }
.fa-edicion-pie { display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--linea); padding-top: 12px; }
.fa-destino { min-width: 200px; }
@media (max-width: 860px) { .fa { grid-template-columns: 1fr; } .fa-arbol { position: static; max-height: none; } }
</style>
