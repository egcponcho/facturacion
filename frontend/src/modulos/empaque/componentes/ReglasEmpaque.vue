<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import EditorCondiciones from '@/modulos/etiquetado/componentes/EditorCondiciones.vue'
import { buscarArticulos, buscarOrdenes, buscarProductos } from '@/modulos/etiquetado/componentes/buscadores.js'
import { OPERADORES, SIN_VALOR } from '@/modulos/etiquetado/etiquetas.js'
import { confirmar } from '@/stores/confirmar'
import { avisar, errorApi } from '@/stores/ui'

// Reglas de empaque en una lista. Cada una se lee como frase: «Para [destino]
// si [condiciones] → usar [receta]». Gana la más específica (artículo,
// producto, grupo de producto más profundo, toda la empresa); con condiciones gana sobre
// sin condiciones; si aun así empatan, la de arriba. El orden se cambia
// arrastrando o con las flechas (también con teclado).
const props = defineProps({ editable: { type: Boolean, default: true } })
const reglas = ref([])
const recetas = ref([])
const catalogo = ref({ campos: [], operadores: [], grupos: [] })
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    const [r, c, x] = await Promise.all([api.get('/reglas-empaque'), api.get('/reglas-empaque/campos'), api.get('/recetas-empaque')])
    reglas.value = r
    catalogo.value = c
    recetas.value = x
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)

const DESTINOS = computed(() => [['EMPRESA', t('Whole company')], ['GRUPO', t('Product group')], ['PRODUCTO', t('Product')], ['ARTICULO', t('Item')]])
const destinoTxt = (r) => (r.destino === 'EMPRESA' ? t('Whole company') : tx(r.destino_nombre))
// «Proveedor es igual a VANS · Marca está en TNF, VANS»: con los nombres traducidos
function condicionesTxt(r) {
  const ops = OPERADORES()
  const nombre = (c) => tx(catalogo.value.campos.find((f) => f.clave === c)?.etiqueta || c)
  return (r.condiciones || []).map((c) => [nombre(c.campo), ops[c.op] || c.op,
    SIN_VALOR.includes(c.op) ? '' : Array.isArray(c.valor) ? c.valor.join(', ') : c.valor].filter((x) => x !== '').join(' ')).join(' · ')
}

// ---- Orden ----------------------------------------------------------------
const arrastrando = ref(null)
async function guardarOrden(lista) {
  try {
    reglas.value = await api.put('/reglas-empaque/orden', { ids: lista.map((r) => r.id) })
  } catch (e) {
    errorApi(e)
    cargar()
  }
}
function mover(i, paso) {
  const j = i + paso
  if (j < 0 || j >= reglas.value.length) return
  const lista = [...reglas.value]
  ;[lista[i], lista[j]] = [lista[j], lista[i]]
  reglas.value = lista
  guardarOrden(lista)
}
function soltar(j) {
  const i = arrastrando.value
  arrastrando.value = null
  if (i == null || i === j) return
  const lista = [...reglas.value]
  lista.splice(j, 0, lista.splice(i, 1)[0])
  reglas.value = lista
  guardarOrden(lista)
}

// ---- Editor ---------------------------------------------------------------
const edicion = ref(null)
const vacia = () => ({ id: null, version: null, destino: 'EMPRESA', grupo_id: '', producto_id: '', articulo_id: '', receta_id: '',
  condiciones: [], motivo: '', vigente_desde: '', vigente_hasta: '', activa: true, aplicar: true })
function abrir(r = null) {
  edicion.value = reactive(r
    ? { ...vacia(), ...r, grupo_id: r.grupo_id || '', producto_id: r.producto_id || '', articulo_id: r.articulo_id || '',
        condiciones: (r.condiciones || []).map((c) => ({ ...c, valor: Array.isArray(c.valor) ? c.valor.join(', ') : c.valor })),
        vigente_desde: r.vigente_desde || '', vigente_hasta: r.vigente_hasta || '', aplicar: true }
    : vacia())
  impacto.value = null
  prueba.value = null
}
function cuerpo(e = edicion.value) {
  const id = (v) => (v === '' || v == null ? null : Number(v))
  return {
    ...(e.id ? { id: e.id } : {}), receta_id: id(e.receta_id), destino: e.destino,
    grupo_id: e.destino === 'GRUPO' ? id(e.grupo_id) : null, producto_id: e.destino === 'PRODUCTO' ? id(e.producto_id) : null,
    articulo_id: e.destino === 'ARTICULO' ? id(e.articulo_id) : null,
    condiciones: e.condiciones.filter((c) => c.campo).map((c) => ({ campo: c.campo, op: c.op, valor: c.valor === '' ? null : c.valor })),
    motivo: e.motivo || null, vigente_desde: e.vigente_desde || null, vigente_hasta: e.vigente_hasta || null, activa: e.activa,
  }
}
const completa = computed(() => {
  const e = edicion.value
  if (!e || !e.receta_id) return false
  return e.destino === 'EMPRESA' || !!e[{ GRUPO: 'grupo_id', PRODUCTO: 'producto_id', ARTICULO: 'articulo_id' }[e.destino]]
})

// Efecto antes de guardar: cuántas posiciones abiertas cambiarían de receta
const impacto = ref(null)
let espera = null
watch(() => edicion.value && JSON.stringify(cuerpo()), () => {
  clearTimeout(espera)
  if (!completa.value) {
    impacto.value = null
    return
  }
  espera = setTimeout(async () => {
    try {
      impacto.value = await api.post('/reglas-empaque/impacto', { regla: cuerpo() })
    } catch {
      impacto.value = null
    }
  }, 500)
})

// Probar con una OC
const prueba = ref(null)
const ocPrueba = ref('')
watch(ocPrueba, probar)
async function probar() {
  if (!ocPrueba.value || !completa.value) {
    prueba.value = null
    return
  }
  try {
    prueba.value = await api.post('/reglas-empaque/probar', { oc_id: Number(ocPrueba.value), regla: cuerpo() })
  } catch (e) {
    errorApi(e)
  }
}

const guardandoRegla = ref(false)
async function guardar() {
  const e = edicion.value
  guardandoRegla.value = true
  try {
    const datos = { ...cuerpo(), aplicar: e.aplicar }
    delete datos.id
    const r = e.id ? await api.patch(`/reglas-empaque/${e.id}`, { ...datos, version: e.version }) : await api.post('/reglas-empaque', datos)
    avisar(r.aplicadas ? t('Rule saved; {0} open PO lines took its recipe.', [r.aplicadas]) : t('Rule saved.'))
    edicion.value = null
    cargar()
  } catch (err) {
    errorApi(err)
  } finally {
    guardandoRegla.value = false
  }
}
async function quitar(r) {
  let n = 0
  try {
    n = (await api.post('/reglas-empaque/impacto', { quitar: r.id })).cambian
  } catch { /* se pregunta igual */ }
  const ok = await confirmar(n
    ? t('Remove the rule? {0} open PO lines that follow the rules would change recipe (they change only if you apply it).', [n])
    : t('Remove the rule? It stays in the history.'), { titulo: t('Remove rule'), boton: t('Remove'), peligro: true })
  if (!ok) return
  try {
    await api.del(`/reglas-empaque/${r.id}${n ? '?aplicar=true' : ''}`)
    avisar(t('Rule removed.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const recetaTxt = (id) => recetas.value.find((x) => x.id === Number(id))
</script>

<template>
  <div class="reglas">
    <p class="ayuda mt-0">{{ t('The most specific rule wins: item, then product, then the deepest product group (its category, then its family and the families above), then the whole company. With conditions wins over without. If they still tie, the one higher in the list. A recipe chosen by hand in a PO line, or the casepack of the PO, wins over the rules.') }}</p>
    <div class="fila-flex">
      <button v-if="props.editable" type="button" class="btn btn-primario" @click="abrir()"><Icono nombre="mas" />{{ t('New rule') }}</button>
    </div>
    <p v-if="!cargando && !reglas.length" class="nota">{{ t('There are no packing rules yet. Without rules, each PO line keeps the casepack that comes with it or the recipe chosen by hand.') }}</p>
    <ol class="lista" :aria-label="t('Packing rules')">
      <li v-for="(r, i) in reglas" :key="r.id" class="regla" :class="{ apagada: !r.activa, sobre: arrastrando != null && arrastrando !== i }"
          :draggable="props.editable" @dragstart="arrastrando = i" @dragover.prevent @drop="soltar(i)">
        <span v-if="props.editable" class="asa" :title="t('Drag to reorder')"><Icono nombre="mover" :tam="15" /></span>
        <span class="num">{{ i + 1 }}</span>
        <div class="frase">
          <div>
            <b>{{ destinoTxt(r) }}</b>
            <template v-if="r.condiciones?.length">{{ ' ' }}{{ t('if') }}{{ ' ' }}<span class="cond">{{ condicionesTxt(r) }}</span></template>
            <Icono nombre="derecha" :tam="14" /> <b>{{ tx(r.receta) }}</b> <span class="ayuda">{{ tx(r.receta_resumen) }}</span>
          </div>
          <div class="ayuda">
            <span v-if="r.motivo">{{ tx(r.motivo) }}</span>
            <span v-if="r.vigente_desde || r.vigente_hasta"> · {{ r.vigente_desde || '…' }} → {{ r.vigente_hasta || '…' }}</span>
            <span v-if="!r.activa" class="etiqueta ms-0">{{ t('Inactive') }}</span>
          </div>
        </div>
        <div v-if="props.editable" class="acciones">
          <button type="button" class="btn-icono" :disabled="i === 0" :aria-label="t('Move rule {0} up', [i + 1])" @click="mover(i, -1)"><Icono nombre="arriba" :tam="14" /></button>
          <button type="button" class="btn-icono" :disabled="i === reglas.length - 1" :aria-label="t('Move rule {0} down', [i + 1])" @click="mover(i, 1)"><Icono nombre="abajo" :tam="14" /></button>
          <button type="button" class="btn-icono" :aria-label="t('Edit rule {0}', [i + 1])" @click="abrir(r)"><Icono nombre="editar" :tam="14" /></button>
          <button type="button" class="btn-icono" :aria-label="t('Remove rule {0}', [i + 1])" @click="quitar(r)"><Icono nombre="basura" :tam="14" /></button>
        </div>
      </li>
    </ol>
  </div>

  <PanelLateral v-if="edicion" :titulo="edicion.id ? t('Edit packing rule') : t('New packing rule')" ancho="680px" @cerrar="edicion = null">
    <form id="form-regla-empaque" class="formulario" @submit.prevent="guardar">
      <div class="paso">
        <span class="palabra">{{ t('For') }}</span>
        <Segmentos v-model="edicion.destino" :opciones="DESTINOS" :etiqueta="t('Applies to')" />
      </div>
      <label v-if="edicion.destino === 'GRUPO'" class="campo"><span class="req">{{ t('Product group (and everything inside it)') }}</span>
        <Seleccion v-model="edicion.grupo_id" required><option value="">{{ t('Choose…') }}</option>
          <option v-for="g in catalogo.grupos" :key="g.id" :value="g.id">{{ tx(g.nombre) }}{{ g.clase === 'CATEGORIA' ? ` (${t('category')})` : '' }}</option></Seleccion></label>
      <label v-if="edicion.destino === 'PRODUCTO'" class="campo"><span class="req">{{ t('Product (all its variants)') }}</span>
        <SelectBusqueda v-model="edicion.producto_id" :buscar="buscarProductos" :etiqueta="t('Product')" :prefijo="false" requerido /></label>
      <label v-if="edicion.destino === 'ARTICULO'" class="campo"><span class="req">{{ t('Item') }}</span>
        <SelectBusqueda v-model="edicion.articulo_id" :buscar="buscarArticulos" :etiqueta="t('Item')" :prefijo="false" requerido /></label>
      <EditorCondiciones v-model="edicion.condiciones" :campos="catalogo.campos" :operadores="catalogo.operadores"
                         :titulo="t('If (optional; all must be met)')" />
      <label class="campo"><span class="req">{{ t('Use the recipe') }}</span>
        <Seleccion v-model="edicion.receta_id" required><option value="">{{ t('Choose…') }}</option>
          <option v-for="x in recetas" :key="x.id" :value="x.id">{{ tx(x.nombre) }} · {{ tx(x.resumen) }}</option></Seleccion></label>
      <p v-if="recetaTxt(edicion.receta_id)" class="ayuda mt-0">{{ tx(recetaTxt(edicion.receta_id).resumen) }}</p>
      <label class="campo"><span>{{ t('Because') }}</span><input v-model="edicion.motivo" maxlength="300" :placeholder="t('Reason, for whoever reads it later')" /></label>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Valid from') }}</span><CampoFecha v-model="edicion.vigente_desde" /></label>
        <label class="campo"><span>{{ t('Valid until') }}</span><CampoFecha v-model="edicion.vigente_hasta" /></label>
      </div>
      <label class="check"><input v-model="edicion.activa" type="checkbox" /> {{ t('Active') }}</label>

      <section v-if="impacto" class="impacto" aria-live="polite">
        <p v-if="impacto.cambian" class="nota aviso"><Icono nombre="info" />{{ t('{0} open PO lines that follow the rules would change recipe.', [fmtNum(impacto.cambian)]) }}</p>
        <p v-else class="ayuda">{{ t('No open PO line that follows the rules changes recipe.') }}</p>
        <ul v-if="impacto.ejemplos.length" class="ejemplos">
          <li v-for="x in impacto.ejemplos" :key="`${x.oc}-${x.posicion}`">{{ t('PO {0} line {1} ({2}): {3} → {4}', [x.oc, x.posicion, x.articulo, tx(x.antes || t('none')), tx(x.despues || t('none'))]) }}</li>
        </ul>
        <label v-if="impacto.cambian" class="check"><input v-model="edicion.aplicar" type="checkbox" /> {{ t('Apply it to those lines when saving') }}</label>
      </section>

      <details class="probar">
        <summary>{{ t('Test with a PO') }}</summary>
        <label class="campo"><span>{{ t('Purchase order') }}</span>
          <SelectBusqueda v-model="ocPrueba" :buscar="buscarOrdenes" :etiqueta="t('Purchase order')" :prefijo="false" :vacio="t('None')" /></label>
        <div v-if="prueba" class="tabla-scroll">
          <table class="tabla">
            <thead><tr><th>{{ t('Line') }}</th><th>{{ t('Item') }}</th><th>{{ t('Today') }}</th><th>{{ t('With the rules') }}</th></tr></thead>
            <tbody>
              <tr v-for="f in prueba.posiciones" :key="f.posicion_id">
                <td>{{ f.posicion }}</td><td>{{ f.articulo }}</td>
                <td>{{ tx(f.actual.receta || '—') }}</td>
                <td><b>{{ tx(f.reglas.receta || t('No rule')) }}</b> <span v-if="f.reglas.destino" class="ayuda">{{ tx(f.reglas.destino) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </form>
    <template #pie>
      <button class="btn separar" type="button" @click="edicion = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-regla-empaque" :disabled="!completa || guardandoRegla">{{ t('Save rule') }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.reglas { display: flex; flex-direction: column; gap: 10px; }
.lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.regla { display: flex; align-items: center; gap: 8px; border: 1px solid var(--linea); border-radius: 8px; padding: 8px 10px; background: var(--superficie); }
.regla.apagada { opacity: 0.6; }
.regla.sobre { border-style: dashed; }
.asa { cursor: grab; color: var(--tinta-3); }
.num { font-variant-numeric: tabular-nums; color: var(--tinta-3); min-width: 1.5em; }
.frase { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.cond { background: var(--acento-claro); border-radius: 6px; padding: 0 6px; }
.acciones { display: flex; gap: 2px; }
.formulario { display: flex; flex-direction: column; gap: 12px; }
.paso { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.palabra { font-weight: 650; }
.impacto { border-top: 1px solid var(--linea); padding-top: 8px; }
.ejemplos { margin: 4px 0; padding-inline-start: 18px; font-size: var(--t-sm); }
.probar summary { cursor: pointer; font-weight: 600; }
.tabla-scroll { overflow-x: auto; }
@media (max-width: 600px) { .regla { flex-wrap: wrap; } }
</style>
