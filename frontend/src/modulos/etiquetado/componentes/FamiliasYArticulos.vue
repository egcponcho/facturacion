<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtNum } from '@/nucleo/utils'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Familias de etiquetado y qué es de cada una. A la izquierda el árbol de
// familias; a la derecha lo que pertenece a la elegida: productos (la familia
// se pone al producto y la heredan sus tallas), artículos con familia propia o
// grupos de artículos completos. Se asigna a varios a la vez. Las familias de
// etiquetado no son las de la clasificación arancelaria.
const route = useRoute()
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
// El árbol: cada familia debajo de su madre, en el orden de la empresa
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

// ---- Productos, artículos o grupos de la familia elegida ----------------------------------------
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
    datos.value = await api.get(ruta, { q: q.value || undefined, familia: elegida.value || undefined, page: c.page, size: c.size })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function cargarGrupos() {
  cargando.value = true
  try {
    grupos.value = await api.get('/etiquetas/grupos-articulos', { q: q.value || undefined, familia: elegida.value || undefined })
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
watch([elegida, que], recargar)
onMounted(() => que.value === 'grupos' && cargarGrupos())

const columnas = computed(() => (que.value === 'productos' ? [
  { clave: 'estilo', texto: t('Product'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'nombre', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'grupo', texto: t('Group'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'tallas', texto: t('Sizes'), num: true, prioridad: 3, ordenable: false, filtro: false },
  { clave: 'familia', texto: t('Labeling family'), prioridad: 1, ordenable: false, filtro: false },
] : que.value === 'articulos' ? [
  { clave: 'sku', texto: t('SKU'), fija: true, prioridad: 1, ordenable: false, filtro: false },
  { clave: 'descripcion', texto: t('Description'), prioridad: 2, ordenable: false, filtro: false },
  { clave: 'talla', texto: t('Size'), prioridad: 2, ordenable: false, filtro: false },
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

async function asignar(todos = false) {
  const familia_id = destino.value === 'ninguna' ? null : Number(destino.value)
  try {
    let r
    if (que.value === 'productos') r = await api.post('/etiquetas/productos/familia', { familia_id, ids: seleccion.value })
    else if (que.value === 'grupos') r = await api.post('/etiquetas/grupos-articulos/familia', { familia_id, grupo_ids: seleccion.value })
    else {
      r = await api.post('/etiquetas/articulos/familia', todos ? { familia_id, filtro: { q: q.value || undefined, familia: elegida.value || undefined } }
        : { familia_id, ids: seleccion.value })
    }
    avisar(t('{0} changed.', [fmtNum(r.cambiados ?? seleccion.value.length)]))
    destino.value = ''
    await cargarFamilias()
    recargar()
  } catch (e) {
    errorApi(e)
  }
}

// ---- Alta y edición de familias ---------------------------------------------------------------------
const campos = ref([])
onMounted(() => api.get('/etiquetas/campos', { sujeto: 'ARTICULO' })
  .then((r) => (campos.value = r.campos.filter((c) => ['articulo', 'producto'].includes(c.grupo)))).catch(() => {}))
const panel = ref(null)
function editar(f) {
  panel.value = f ? { ...f, campos: (f.campos || []).map((c) => ({ ...c })) } : { codigo: '', nombre: '', descripcion: '', activa: true, campos: [],
    padre_id: familiaElegida.value?.id || null }
}
const marcado = (clave) => panel.value.campos.find((c) => c.campo === clave)
function alternarCampo(clave, tipo, si) {
  const actual = marcado(clave)
  if (tipo === 'habitual') {
    if (si && !actual) panel.value.campos.push({ campo: clave, obligatorio: false })
    if (!si) panel.value.campos = panel.value.campos.filter((c) => c.campo !== clave)
  } else if (si) {
    if (actual) actual.obligatorio = true
    else panel.value.campos.push({ campo: clave, obligatorio: true })
  } else if (actual) actual.obligatorio = false
}
async function guardar() {
  const f = panel.value
  const cuerpo = { codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion, activa: f.activa, campos: f.campos, padre_id: f.padre_id || null }
  try {
    const r = f.id ? await api.patch(`/etiquetas/familias/${f.id}`, cuerpo) : await api.post('/etiquetas/familias', cuerpo)
    avisar(f.id ? t('Family saved.') : t('Family “{0}” created.', [f.nombre]))
    panel.value = null
    await cargarFamilias()
    elegida.value = String(r.id)
  } catch (e) {
    errorApi(e)
  }
}
async function eliminar(f) {
  if (!(await confirmar(t('The family {0} is deleted (if something uses it, it is deactivated instead).', [f.nombre]), { titulo: t('Delete family'), boton: t('Delete'), peligro: true }))) return
  try {
    await api.del(`/etiquetas/familias/${f.id}`)
    avisar(t('Family deleted.'))
    panel.value = null
    elegida.value = ''
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
const nombreCampo = (clave) => campos.value.find((c) => c.clave === clave)?.etiqueta || clave
</script>

<template>
  <div class="fa">
    <aside class="fa-arbol panel" :aria-label="t('Labeling families')">
      <div class="fa-cabeza">
        <h3>{{ t('Families') }}</h3>
        <button v-if="editable" type="button" class="btn btn-chico" @click="editar(null)"><Icono nombre="mas" :tam="14" />{{ t('New') }}</button>
      </div>
      <ul>
        <li><button type="button" class="fa-item" :aria-pressed="elegida === ''" @click="elegida = ''">{{ t('All') }}</button></li>
        <li v-for="f in arbol" :key="f.id">
          <div class="fa-item-fila" :style="{ paddingInlineStart: `${f.nivel * 14}px` }">
            <button type="button" class="fa-item" :class="{ apagada: !f.activa }" :aria-pressed="elegida === String(f.id)" @click="elegida = String(f.id)">
              <span>{{ tx(f.nombre) }}</span><span class="fa-cuenta">{{ fmtNum(f.articulos || 0) }}</span></button>
            <template v-if="editable && elegida === String(f.id)">
              <button type="button" class="btn-icono" :aria-label="t('Move up')" @click="mover(f, -1)"><Icono nombre="arriba" :tam="13" /></button>
              <button type="button" class="btn-icono" :aria-label="t('Move down')" @click="mover(f, 1)"><Icono nombre="abajo" :tam="13" /></button>
              <button type="button" class="btn-icono" :aria-label="t('Edit')" @click="editar(f)"><Icono nombre="editar" :tam="13" /></button>
            </template>
          </div>
        </li>
        <li><button type="button" class="fa-item fa-sin" :aria-pressed="elegida === 'sin'" @click="elegida = 'sin'">{{ t('Without family') }}</button></li>
      </ul>
      <p v-if="!familias.length && !cargandoFamilias" class="ayuda">{{ t('No labeling families yet. Create the ones your operation needs, for example footwear, apparel or chemicals.') }}</p>
    </aside>

    <section class="fa-contenido">
      <div class="fa-titulo">
        <h3>{{ tituloDerecha }}</h3>
        <span v-if="familiaElegida" class="ayuda">{{ t('{0} items · {1} products · {2} groups', [fmtNum(familiaElegida.articulos || 0), fmtNum(familiaElegida.productos || 0), fmtNum(familiaElegida.grupos || 0)]) }}</span>
      </div>
      <div class="fa-barra">
        <Segmentos v-model="que" :opciones="[['productos', t('Products')], ['articulos', t('Items (sizes)')], ['grupos', t('Item groups')]]" :etiqueta="t('Show')" />
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="q" type="search" :placeholder="t('Search')" :aria-label="t('Search')" /></label>
      </div>
      <p class="ayuda">{{ que === 'productos' ? t('The family is set on the product; all its sizes inherit it unless a size has its own.')
        : que === 'articulos' ? t('A size with its own family keeps it even if its product or group has another one.')
          : t('Every item of a group belongs to its family, except the products or items that have their own.') }}</p>

      <TablaDatos v-if="que !== 'grupos'" :key="que" ref="tabla" :tabla="`etiquetas_${que}`" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total"
                  :cargando="cargando" :seleccionable="editable" v-model:seleccion="seleccion" :etiqueta="tituloDerecha"
                  :externos="{ q, elegida }" @consulta="consultar">
        <template #celda-estilo="{ fila: p }"><router-link :to="`/productos/${p.id}?vista=etiquetas`" class="enlace"><strong>{{ p.estilo }}</strong></router-link><span class="sub">{{ p.color }}</span></template>
        <template #celda-sku="{ fila: a }"><strong class="codigo">{{ a.sku }}</strong><span class="sub">{{ a.estilo }}</span></template>
        <template #celda-familia="{ fila: x }">
          <span v-if="x.familia" class="etiqueta ms-0">{{ tx(x.familia) }}</span>
          <span v-if="x.familia && x.familia_origen" class="sub">{{ ORIGEN()[x.familia_origen] }}</span>
          <span v-if="!x.familia" class="etiqueta aviso ms-0">{{ t('Without family') }}</span>
        </template>
        <template #vacio>{{ t('Nothing here.') }}</template>
      </TablaDatos>
      <TablaDatos v-else tabla="etiquetas_grupos" :columnas="columnas" :filas="grupos" :cargando="cargando" :seleccionable="editable"
                  v-model:seleccion="seleccion" :etiqueta="t('Item groups')">
        <template #celda-codigo="{ fila: g }"><strong class="codigo">{{ g.codigo }}</strong></template>
        <template #celda-familia="{ fila: g }"><span v-if="g.familia" class="etiqueta ms-0">{{ tx(g.familia) }}</span><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span></template>
        <template #vacio>{{ t('Nothing here.') }}</template>
      </TablaDatos>

      <div v-if="editable" class="fa-asignar panel">
        <label class="campo"><span>{{ t('Put in the family') }}</span>
          <Seleccion v-model="destino" :aria-label="t('Labeling family')">
            <option value="">{{ t('Choose…') }}</option>
            <option value="ninguna">{{ t('No family (remove it)') }}</option>
            <option v-for="f in arbol.filter((x) => x.activa)" :key="f.id" :value="f.id">{{ '— '.repeat(f.nivel) }}{{ tx(f.nombre) }}</option>
          </Seleccion></label>
        <button type="button" class="btn btn-primario" :disabled="!destino || !seleccion.length" @click="asignar(false)">{{ t('Apply to the {0} selected', [seleccion.length]) }}</button>
        <button v-if="que === 'articulos'" type="button" class="btn" :disabled="!destino || !datos.total" @click="asignar(true)">{{ t('Apply to all {0} of the filter', [fmtNum(datos.total)]) }}</button>
      </div>
    </section>
  </div>

  <Modal v-if="panel" :titulo="panel.id ? t('Family {0}', [panel.codigo]) : t('New labeling family')" ancho="600px" @cerrar="panel = null">
    <form id="form-familia" class="fa-form" @submit.prevent="guardar">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="panel.codigo" required maxlength="20" :placeholder="t('E.g. FOOTWEAR')" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="panel.nombre" required maxlength="100" /></label>
      </div>
      <label class="campo"><span>{{ t('Subfamily of') }}</span>
        <Seleccion v-model="panel.padre_id"><option :value="null">{{ t('None (main family)') }}</option>
          <option v-for="x in arbol.filter((y) => y.id !== panel.id && !(y.ruta || '').includes(panel.nombre + ' /'))" :key="x.id" :value="x.id">{{ tx(x.ruta || x.nombre) }}</option></Seleccion>
        <small class="ayuda">{{ t('A subfamily inherits the required fields and the designs of the families that contain it.') }}</small></label>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="panel.descripcion" maxlength="300" rows="2"></textarea></label>
      <label class="check"><input v-model="panel.activa" type="checkbox" /> {{ t('Active') }}</label>
      <div class="campo">
        <span>{{ t('Fields of this family') }}</span>
        <p class="ayuda">{{ t('Usual: suggested when designing. Required: a warning when an item of the family lacks it.') }}</p>
        <table class="tabla fa-campos">
          <thead><tr><th>{{ t('Field') }}</th><th class="centro">{{ t('Usual') }}</th><th class="centro">{{ t('Required') }}</th></tr></thead>
          <tbody>
            <tr v-for="c in campos" :key="c.clave">
              <td>{{ tx(c.etiqueta) }}</td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)" :aria-label="t('Usual')" @change="alternarCampo(c.clave, 'habitual', $event.target.checked)" /></td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)?.obligatorio" :aria-label="t('Required')" @change="alternarCampo(c.clave, 'obligatorio', $event.target.checked)" /></td>
            </tr>
          </tbody>
        </table>
        <p v-if="panel.heredados?.length" class="ayuda">{{ t('Inherited fields: {0}', [panel.heredados.map((c) => tx(nombreCampo(c.campo)) + (c.obligatorio ? ' *' : '')).join(', ')]) }}</p>
      </div>
    </form>
    <template #pie>
      <button v-if="panel.id" class="btn btn-peligro" type="button" @click="eliminar(panel)">{{ t('Delete') }}</button>
      <button class="btn separar" type="button" @click="panel = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-familia">{{ t('Save') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.fa { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start; }
.fa-arbol { position: sticky; top: 12px; max-height: calc(100vh - 140px); overflow: auto; }
.fa-arbol ul { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.fa-cabeza, .fa-titulo { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.fa-cabeza h3, .fa-titulo h3 { margin: 0; font-size: 0.95rem; }
.fa-item-fila { display: flex; align-items: center; gap: 2px; }
.fa-item { flex: 1; display: flex; justify-content: space-between; gap: 8px; text-align: start; background: none; border: 0; border-radius: 8px; padding: 7px 10px;
  font: inherit; font-size: 0.88rem; color: var(--tinta); cursor: pointer; min-height: 36px; }
.fa-item:hover { background: var(--superficie-2); }
.fa-item[aria-pressed='true'] { background: var(--acento-claro); color: var(--acento-texto); font-weight: 600; }
.fa-item.apagada { opacity: 0.6; }
.fa-arbol li > .fa-item { width: 100%; }
.fa-sin { margin-top: 6px; border-top: 1px solid var(--linea-suave); border-radius: 0; }
.fa-cuenta { color: var(--tinta-3); font-size: 0.78rem; }
.fa-contenido { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.fa-barra { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.fa-asignar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.fa-asignar .campo { min-width: 240px; }
.fa-form { display: flex; flex-direction: column; gap: 14px; }
.fa-campos { font-size: 0.84rem; }
.centro { text-align: center; }
@media (max-width: 860px) { .fa { grid-template-columns: 1fr; } .fa-arbol { position: static; max-height: none; } }
</style>
