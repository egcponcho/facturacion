<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import GruposFamilia from '@/modulos/etiquetado/componentes/GruposFamilia.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// Familias de etiquetado propias de la empresa: no son las familias de la
// clasificación arancelaria. Cada una dice qué campos suele llevar su
// etiqueta y cuáles son obligatorios antes de generar.
const lista = ref([])
const campos = ref([])
const cargando = ref(false)
const editable = computed(() => puede('etiquetas.familias'))

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/familias')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(() => {
  cargar()
  api.get('/etiquetas/campos', { modalidad: 'ARTICULO' }).then((r) => {
    campos.value = r.campos.filter((c) => ['articulo', 'producto'].includes(c.grupo))
  }).catch(() => {})
})

const columnas = computed(() => [
  { clave: 'orden', texto: '#', num: true, prioridad: 2, filtro: false },
  { clave: 'codigo', texto: t('Code'), fija: true, prioridad: 1 },
  { clave: 'nombre', texto: t('Name'), prioridad: 1 },
  { clave: 'descripcion', texto: t('Description'), prioridad: 3 },
  { clave: 'campos', texto: t('Usual fields'), prioridad: 2, filtro: false, textoValor: (v) => String((v || []).length) },
  { clave: 'grupos', texto: t('Item groups'), num: true, prioridad: 2 },
  { clave: 'articulos', texto: t('Items'), num: true, prioridad: 2 },
  { clave: 'plantillas', texto: t('Designs'), num: true, prioridad: 2 },
  { clave: 'activa', texto: t('Status'), prioridad: 2, opciones: [[true, t('Active')], [false, t('Inactive')]] },
])

const panel = ref(null)
function editar(f) {
  panel.value = f ? { ...f, campos: (f.campos || []).map((c) => ({ ...c })) } : { codigo: '', nombre: '', descripcion: '', activa: true, campos: [] }
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
  const datos = { codigo: f.codigo, nombre: f.nombre, descripcion: f.descripcion, activa: f.activa, campos: f.campos }
  try {
    if (f.id) await api.patch(`/etiquetas/familias/${f.id}`, datos)
    else await api.post('/etiquetas/familias', datos)
    avisar(f.id ? t('Family saved.') : t('Family “{0}” created.', [f.nombre]))
    panel.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
// Al agregar o quitar grupos cambian los conteos de la familia abierta
async function recontar() {
  await cargar()
  const f = lista.value.find((x) => x.id === panel.value?.id)
  if (f) Object.assign(panel.value, { articulos: f.articulos, grupos: f.grupos, articulos_propios: f.articulos_propios })
}
async function mover(f, delta) {
  const ids = lista.value.map((x) => x.id)
  const i = ids.indexOf(f.id)
  const j = i + delta
  if (j < 0 || j >= ids.length) return
  ;[ids[i], ids[j]] = [ids[j], ids[i]]
  try {
    lista.value = await api.put('/etiquetas/familias/orden', { ids })
  } catch (e) {
    errorApi(e)
  }
}
async function alternarActiva(f) {
  try {
    await api.patch(`/etiquetas/familias/${f.id}`, { activa: !f.activa })
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function eliminar(f) {
  try {
    await api.del(`/etiquetas/familias/${f.id}`)
    avisar(t('Family deleted.'))
    panel.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const nombreCampo = (clave) => campos.value.find((c) => c.clave === clave)?.etiqueta || clave
</script>

<template>
  <p class="nota mb-3"><Icono nombre="info" :tam="16" />{{ t('Labeling families group items by the label they need (footwear, apparel, chemicals…). They are independent from the tariff classification families.') }}</p>
  <TablaDatos tabla="familias_etiquetado" :columnas="columnas" :filas="lista" :cargando="cargando" orden-inicial="orden:asc" fila-clicable
              :clase-fila="(x) => ({ apagada: !x.activa })" :etiqueta="t('Labeling families')" @fila="(f) => editable && editar(f)">
    <template #filtros>
      <button v-if="editable" type="button" class="btn btn-primario separar" @click="editar(null)"><Icono nombre="mas" />{{ t('New family') }}</button>
    </template>
    <template #celda-codigo="{ fila: f }"><strong class="codigo">{{ f.codigo }}</strong></template>
    <template #celda-campos="{ fila: f }">
      <span v-if="!f.campos.length" class="apagado">—</span>
      <span v-else :title="f.campos.map((c) => tx(nombreCampo(c.campo)) + (c.obligatorio ? ' *' : '')).join(', ')">
        {{ t('{0} fields', [f.campos.length]) }}<template v-if="f.campos.some((c) => c.obligatorio)"> · {{ t('{0} required', [f.campos.filter((c) => c.obligatorio).length]) }}</template>
      </span>
    </template>
    <template #celda-activa="{ fila: f }"><span class="etiqueta ms-0" :class="f.activa ? 'ok' : ''">{{ f.activa ? t('Active') : t('Inactive') }}</span></template>
    <template #acciones="{ fila: f }">
      <template v-if="editable">
        <button type="button" class="btn-icono" :aria-label="t('Move up')" :title="t('Move up')" @click.stop="mover(f, -1)"><Icono nombre="arriba" :tam="15" /></button>
        <button type="button" class="btn-icono" :aria-label="t('Move down')" :title="t('Move down')" @click.stop="mover(f, 1)"><Icono nombre="abajo" :tam="15" /></button>
        <button type="button" class="btn btn-chico" @click.stop="alternarActiva(f)">{{ f.activa ? t('Deactivate') : t('Activate') }}</button>
      </template>
      <router-link v-if="puede('etiquetas.generar') && f.articulos" :to="{ path: '/etiquetas/masiva', query: { familia: f.id } }" class="btn btn-chico" @click.stop>
        <Icono nombre="descargar" :tam="14" />{{ t('Generate labels') }}</router-link>
    </template>
    <template #vacio>{{ t('No labeling families yet. Create the ones your operation needs, for example footwear, apparel or chemicals.') }}</template>
  </TablaDatos>

  <PanelLateral v-if="panel" :titulo="panel.id ? t('Family {0}', [panel.codigo]) : t('New labeling family')" ancho="560px" @cerrar="panel = null">
    <form id="form-familia" class="formulario-panel" @submit.prevent="guardar">
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="panel.codigo" required maxlength="20" :placeholder="t('E.g. FOOTWEAR')" /></label>
        <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="panel.nombre" required maxlength="100" /></label>
      </div>
      <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="panel.descripcion" maxlength="300" rows="2"></textarea></label>
      <label class="check"><input v-model="panel.activa" type="checkbox" /> {{ t('Active') }}</label>
      <section v-if="panel.id" class="campo">
        <span>{{ t('Which items belong to this family') }}</span>
        <GruposFamilia :familia="panel" :editable="editable" @cambio="recontar" />
      </section>
      <p v-else class="ayuda">{{ t('Save the family to add item groups and items to it.') }}</p>
      <div class="campo">
        <span>{{ t('Fields of this family') }}</span>
        <p class="ayuda">{{ t('Usual: suggested when designing. Required: labels are not generated while the item lacks it.') }}</p>
        <table class="tabla tabla-campos">
          <thead><tr><th>{{ t('Field') }}</th><th>{{ t('Source') }}</th><th class="centro">{{ t('Usual') }}</th><th class="centro">{{ t('Required') }}</th></tr></thead>
          <tbody>
            <tr v-for="c in campos" :key="c.clave">
              <td>{{ tx(c.etiqueta) }}</td>
              <td class="apagado"><code>{{ c.origen }}</code></td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)" :aria-label="t('Usual')" @change="alternarCampo(c.clave, 'habitual', $event.target.checked)" /></td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)?.obligatorio" :aria-label="t('Required')" @change="alternarCampo(c.clave, 'obligatorio', $event.target.checked)" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </form>
    <template #pie>
      <button v-if="panel.id && !panel.articulos && !panel.plantillas && !panel.grupos" class="btn btn-peligro" type="button" @click="eliminar(panel)">{{ t('Delete') }}</button>
      <button class="btn separar" type="button" @click="panel = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" type="submit" form="form-familia">{{ t('Save') }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.formulario-panel { display: flex; flex-direction: column; gap: 14px; }
.tabla-campos { font-size: 0.84rem; }
.tabla-campos code { font-size: 0.74rem; }
.centro { text-align: center; }
:deep(tr.apagada > td) { opacity: 0.6; }
</style>
