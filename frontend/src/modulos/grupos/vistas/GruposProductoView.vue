<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { alCambiar } from '@/nucleo/cambios.js'
import { plural } from '@/nucleo/utils'
import EditorCondiciones from '@/modulos/etiquetado/componentes/EditorCondiciones.vue'
import { OPERADORES, SIN_VALOR, condicionesLimpias } from '@/modulos/etiquetado/etiquetas.js'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Grupos de producto: un solo árbol de familias (con subfamilias) y categorías
// (dentro de una familia, reconocidas por condiciones) para toda la empresa.
// Las reglas de etiquetado y de empaque lo recorren de lo más específico a lo
// más general; las pantallas del etiquetado editan estos mismos nodos.
const editable = computed(() => puede('catalogos.editar') || puede('etiquetas.familias'))
const nodos = ref([])
const catalogo = ref({ campos: [], operadores: [] })
const filtro = ref('')
const inactivos = ref(true)
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    nodos.value = await api.get('/grupos-producto', { incluir_inactivos: inactivos.value })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
// Atributos de variante de la empresa: cada familia elige los que distinguen a sus variantes
const atributos = ref([])
onMounted(() => {
  cargar()
  api.get('/grupos-producto/campos').then((c) => (catalogo.value = c)).catch(() => {})
  api.get('/catalogos/atributos_variante', { size: 200 }).then((r) => (atributos.value = (r.items || []).filter((a) => a.activo !== false)))
    .catch(() => {})
})
alCambiar(cargar, ['/grupos-producto'])

const familias = computed(() => nodos.value.filter((g) => g.clase === 'FAMILIA'))
// Con un texto: los nodos que lo tienen y sus antecesores, para no perder dónde están
const visibles = computed(() => {
  const q = filtro.value.trim().toLowerCase()
  if (!q) return nodos.value
  const por = Object.fromEntries(nodos.value.map((g) => [g.id, g]))
  const quedan = new Set()
  for (const g of nodos.value) {
    if (!`${g.codigo} ${g.nombre}`.toLowerCase().includes(q)) continue
    for (let x = g; x && !quedan.has(x.id); x = por[x.padre_id]) quedan.add(x.id)
  }
  return nodos.value.filter((g) => quedan.has(g.id))
})
const nombreCampo = (clave) => tx(catalogo.value.campos.find((f) => f.clave === clave)?.etiqueta || clave)
function condicionesTxt(g) {
  if (!g.condiciones?.length) return t('Only set by hand on the product')
  const ops = OPERADORES()
  return g.condiciones.map((c) => [nombreCampo(c.campo), ops[c.op] || c.op,
    SIN_VALOR.includes(c.op) ? '' : Array.isArray(c.valor) ? c.valor.join(', ') : c.valor].filter((x) => x !== '' && x != null).join(' ')).join(' · ')
}
function usosTxt(g) {
  const partes = []
  if (g.grupos_articulos) partes.push(plural(g.grupos_articulos, t('item group'), t('item groups')))
  if (g.productos) partes.push(plural(g.productos, t('product'), t('products')))
  if (g.articulos) partes.push(plural(g.articulos, t('item of its own'), t('items of their own')))
  if (g.reglas_etiqueta) partes.push(plural(g.reglas_etiqueta, t('label rule'), t('label rules')))
  if (g.reglas_empaque) partes.push(plural(g.reglas_empaque, t('packing rule'), t('packing rules')))
  return partes.join(' · ') || t('Not in use')
}

// ---- Alta y edición ---------------------------------------------------------
const CLASES = computed(() => [['FAMILIA', t('Family')], ['CATEGORIA', t('Category')]])
const edicion = ref(null)
const guardando = ref(false)
function nuevo(clase = 'FAMILIA', padre = null) {
  edicion.value = reactive({ id: null, clase, codigo: '', nombre: '', descripcion: '', padre_id: padre?.id ?? '',
    condiciones: clase === 'CATEGORIA' ? [{ campo: '', op: 'contiene', valor: '' }] : [], ejes_variante: [], activa: true })
}
function editar(g) {
  edicion.value = reactive({ ...g, descripcion: g.descripcion || '', padre_id: g.padre_id ?? '', ejes_variante: [...(g.ejes_variante || [])],
    condiciones: (g.condiciones || []).map((c) => ({ ...c, valor: Array.isArray(c.valor) ? c.valor.join(', ') : c.valor })) })
}
// Una familia no puede quedar dentro de sí misma ni de una de sus subfamilias
const padresPosibles = computed(() => {
  const e = edicion.value
  if (!e) return []
  if (!e.id || e.clase === 'CATEGORIA') return familias.value
  return familias.value.filter((f) => f.id !== e.id && !rutaIds(f).includes(e.id))
})
function rutaIds(g) {
  const por = Object.fromEntries(nodos.value.map((x) => [x.id, x]))
  const ids = []
  for (let x = g; x && !ids.includes(x.id); x = por[x.padre_id]) ids.push(x.id)
  return ids
}
async function guardar() {
  const e = edicion.value
  const cuerpo = { codigo: e.codigo, nombre: e.nombre, descripcion: e.descripcion || null,
    padre_id: e.padre_id === '' ? null : Number(e.padre_id), activa: e.activa,
    ...(e.clase === 'CATEGORIA' ? { condiciones: condicionesLimpias(e.condiciones) } : { ejes_variante: e.ejes_variante }) }
  guardando.value = true
  try {
    if (e.id) await api.patch(`/grupos-producto/${e.id}`, cuerpo)
    else await api.post('/grupos-producto', { ...cuerpo, clase: e.clase })
    avisar(e.id ? t('Group saved.') : t('Group “{0}” created.', [e.nombre]))
    edicion.value = null
    cargar()
  } catch (err) {
    errorApi(err)
  } finally {
    guardando.value = false
  }
}
async function quitar(g) {
  const enUso = g.articulos || g.productos || g.grupos_articulos || g.reglas_etiqueta || g.reglas_empaque
    || nodos.value.some((x) => x.padre_id === g.id)
  try {
    if (enUso) {
      if (!(await confirmar(t('{0} is in use, so it is deactivated instead of deleted. Its rules stop applying and it cannot be assigned again.', [tx(g.nombre)]),
        { titulo: t('Deactivate group'), boton: t('Deactivate'), peligro: true }))) return
      await api.patch(`/grupos-producto/${g.id}`, { activa: false })
      avisar(t('Group deactivated.'))
    } else {
      if (!(await confirmar(t('The group {0} is deleted.', [tx(g.nombre)]), { titulo: t('Delete group'), boton: t('Delete'), peligro: true }))) return
      await api.del(`/grupos-producto/${g.id}`)
      avisar(t('Group deleted.'))
    }
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Product groups') }}</h1>
      <p>{{ t('One tree of families and categories for the whole company. Labeling and packing rules use it, from the most specific group to the most general.') }}</p>
    </div>
    <div v-if="editable" class="acciones-cabeza">
      <button type="button" class="btn btn-primario" @click="nuevo('FAMILIA')"><Icono nombre="mas" />{{ t('New family') }}</button>
    </div>
  </div>

  <section class="panel">
    <div class="fila-flex">
      <input v-model="filtro" type="search" class="buscar" :placeholder="t('Search by code or name')" :aria-label="t('Search by code or name')" />
      <label class="check"><input v-model="inactivos" type="checkbox" @change="cargar" /> {{ t('Show inactive') }}</label>
    </div>
    <p v-if="!cargando && !nodos.length" class="nota">{{ t('There are no product groups yet. Create a family (footwear, apparel…) and assign it to item groups, products or items from Labels → Families.') }}</p>
    <ul class="arbol" :aria-label="t('Product groups')">
      <li v-for="g in visibles" :key="g.id" class="nodo" :class="{ apagado: !g.activa, categoria: g.clase === 'CATEGORIA' }"
          :style="{ '--prof': g.profundidad }">
        <Icono :nombre="g.clase === 'CATEGORIA' ? 'etiqueta' : 'capas'" :tam="16" class="icono-clase" />
        <div class="cuerpo">
          <div class="titulo">
            <b>{{ tx(g.nombre) }}</b> <span class="codigo">{{ g.codigo }}</span>
            <span class="etiqueta ms-0" :class="g.clase === 'CATEGORIA' ? 'info' : ''">{{ g.clase === 'CATEGORIA' ? t('Category') : t('Family') }}</span>
            <span v-if="!g.activa" class="etiqueta ms-0">{{ t('Inactive') }}</span>
          </div>
          <div v-if="g.clase === 'CATEGORIA'" class="ayuda">{{ condicionesTxt(g) }}</div>
          <div class="ayuda">{{ usosTxt(g) }}</div>
        </div>
        <div v-if="editable" class="acciones">
          <template v-if="g.clase === 'FAMILIA' && g.activa">
            <button type="button" class="btn-icono" :title="t('Add a subfamily')" :aria-label="t('Add a subfamily to {0}', [tx(g.nombre)])"
                    @click="nuevo('FAMILIA', g)"><Icono nombre="mas" :tam="14" /></button>
            <button type="button" class="btn-icono" :title="t('Add a category')" :aria-label="t('Add a category to {0}', [tx(g.nombre)])"
                    @click="nuevo('CATEGORIA', g)"><Icono nombre="etiqueta" :tam="14" /></button>
          </template>
          <button type="button" class="btn-icono" :aria-label="t('Edit {0}', [tx(g.nombre)])" @click="editar(g)"><Icono nombre="editar" :tam="14" /></button>
          <button v-if="g.activa" type="button" class="btn-icono" :aria-label="t('Remove {0}', [tx(g.nombre)])" @click="quitar(g)"><Icono nombre="basura" :tam="14" /></button>
        </div>
      </li>
    </ul>
  </section>

  <PanelLateral v-if="edicion" :titulo="edicion.id ? t('Edit {0}', [tx(edicion.nombre)]) : t('New product group')" ancho="620px" @cerrar="edicion = null">
    <form id="form-grupo" class="formulario" @submit.prevent="guardar">
      <Segmentos v-if="!edicion.id" v-model="edicion.clase" :opciones="CLASES" :etiqueta="t('Kind')" />
      <p class="ayuda mt-0">{{ edicion.clase === 'CATEGORIA'
        ? t('A category goes inside a family and is recognized by its conditions on the item data, or set by hand on the product.')
        : t('A family is assigned by hand to item groups, products or items; its subfamilies and categories inherit its rules.') }}</p>
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="edicion.codigo" required maxlength="20" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="edicion.nombre" required maxlength="100" /></label>
      </div>
      <label class="campo"><span :class="{ req: edicion.clase === 'CATEGORIA' }">{{ edicion.clase === 'CATEGORIA' ? t('Inside the family') : t('Inside (optional)') }}</span>
        <Seleccion v-model="edicion.padre_id" :required="edicion.clase === 'CATEGORIA'">
          <option value="">{{ edicion.clase === 'CATEGORIA' ? t('Choose…') : t('Top level') }}</option>
          <option v-for="f in padresPosibles" :key="f.id" :value="f.id">{{ tx(f.ruta) }}</option>
        </Seleccion></label>
      <label class="campo"><span>{{ t('Description') }}</span><input v-model="edicion.descripcion" maxlength="300" /></label>
      <div v-if="edicion.clase === 'FAMILIA'" class="campo"><span>{{ t('Variant attributes of its products') }}</span>
        <div class="fila-flex gap-2 envolver">
          <label v-for="a in atributos" :key="a.codigo" class="check"><input v-model="edicion.ejes_variante" type="checkbox" :value="a.codigo" /> {{ tx(a.nombre) }}</label>
        </div>
        <small class="ayuda">{{ t('What tells the variants of its products apart (e.g. color and size; flavor and presentation; concentration and container). Empty: the ones of the parent family, or all.') }}</small></div>
      <EditorCondiciones v-if="edicion.clase === 'CATEGORIA'" v-model="edicion.condiciones" :campos="catalogo.campos"
                         :operadores="catalogo.operadores" :titulo="t('Recognized when (all must be met; empty: only by hand)')" />
      <label class="check"><input v-model="edicion.activa" type="checkbox" /> {{ t('Active') }}</label>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="edicion = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-grupo" :disabled="guardando">{{ t('Save group') }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.acciones-cabeza { display: flex; gap: 8px; }
.buscar { flex: 1 1 240px; min-width: 0; max-width: 360px; }
.arbol { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.nodo { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; border: 1px solid var(--linea); border-radius: 8px;
  background: var(--superficie); margin-inline-start: calc(min(var(--prof), 6) * 20px); }
.nodo.categoria { border-style: dashed; }
.nodo.apagado { opacity: 0.6; }
.icono-clase { color: var(--tinta-3); margin-top: 2px; flex: none; }
.cuerpo { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.titulo { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.codigo { font-family: var(--mono, monospace); font-size: 0.82rem; color: var(--tinta-3); }
.acciones { display: flex; gap: 2px; flex: none; }
.formulario { display: flex; flex-direction: column; gap: 12px; }
@media (max-width: 600px) {
  .nodo { margin-inline-start: calc(min(var(--prof), 3) * 12px); flex-wrap: wrap; }
}
</style>
