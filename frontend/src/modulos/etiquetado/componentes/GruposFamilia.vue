<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import { fmtNum } from '@/nucleo/utils'
import { avisar, errorApi } from '@/stores/ui'

// Qué artículos son de una familia: grupos de artículos completos (todos sus
// artículos la heredan) y artículos específicos (su familia propia manda
// sobre la del grupo). Los grupos se agregan varios a la vez.
const props = defineProps({ familia: { type: Object, required: true }, editable: Boolean })
const emit = defineEmits(['cambio'])
const todos = ref([])
const cargando = ref(false)

async function cargar() {
  cargando.value = true
  try {
    todos.value = await api.get('/etiquetas/grupos-articulos')
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
const propios = computed(() => todos.value.filter((g) => g.familia_id === props.familia.id))
const articulosPorGrupo = computed(() => propios.value.reduce((s, g) => s + g.articulos - g.con_familia_propia, 0))

async function asignar(ids, familiaId) {
  try {
    const r = await api.post('/etiquetas/grupos-articulos/familia', { familia_id: familiaId, grupo_ids: ids })
    avisar(familiaId ? t('{0} groups added to {1}.', [r.cambiados, props.familia.nombre]) + (r.movidos ? ` ${t('{0} of them left another family.', [r.movidos])}` : '')
      : t('{0} groups removed from the family.', [r.cambiados]))
    await cargar()
    emit('cambio')
  } catch (e) {
    errorApi(e)
  }
}

// Agregar varios grupos a la vez
const modal = ref(false)
const q = ref('')
const soloSin = ref(true)
const elegidos = ref([])
const normal = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const disponibles = computed(() => todos.value.filter((g) => g.familia_id !== props.familia.id && (!soloSin.value || !g.familia_id)
  && (!q.value || normal(`${g.codigo} ${g.nombre} ${g.categoria}`).includes(normal(q.value)))))
const todosVisibles = computed({
  get: () => disponibles.value.length > 0 && disponibles.value.every((g) => elegidos.value.includes(g.id)),
  set: (v) => {
    const ids = disponibles.value.map((g) => g.id)
    elegidos.value = v ? [...new Set([...elegidos.value, ...ids])] : elegidos.value.filter((id) => !ids.includes(id))
  },
})
const deOtra = computed(() => todos.value.filter((g) => elegidos.value.includes(g.id) && g.familia_id && g.familia_id !== props.familia.id))
const articulosElegidos = computed(() => todos.value.filter((g) => elegidos.value.includes(g.id)).reduce((s, g) => s + g.articulos, 0))
function abrir() {
  elegidos.value = []
  q.value = ''
  modal.value = true
}
async function agregar() {
  await asignar(elegidos.value, props.familia.id)
  modal.value = false
}
</script>

<template>
  <div class="grupos-familia">
    <div class="gf-cifras">
      <div><strong>{{ fmtNum(familia.articulos || 0) }}</strong><span>{{ t('items in the family') }}</span></div>
      <div><strong>{{ fmtNum(propios.length) }}</strong><span>{{ t('item groups') }}</span></div>
      <div><strong>{{ fmtNum(familia.articulos_propios || 0) }}</strong><span>{{ t('specific items') }}</span></div>
    </div>

    <div class="gf-cabeza">
      <h4>{{ t('Item groups') }}</h4>
      <button v-if="editable" type="button" class="btn btn-chico" @click="abrir"><Icono nombre="mas" :tam="14" />{{ t('Add groups') }}</button>
    </div>
    <p class="ayuda">{{ t('Every item of these groups belongs to the family ({0} items), except the items that have their own family.', [fmtNum(articulosPorGrupo)]) }}</p>
    <ul v-if="propios.length" class="gf-lista">
      <li v-for="g in propios" :key="g.id">
        <span><strong>{{ g.codigo }}</strong> {{ tx(g.nombre) }} <span class="apagado">· {{ t('{0} items', [fmtNum(g.articulos)]) }}</span></span>
        <button v-if="editable" type="button" class="btn-icono" :aria-label="t('Remove')" :title="t('Remove from the family')" @click="asignar([g.id], null)"><Icono nombre="cerrar" :tam="14" /></button>
      </li>
    </ul>
    <p v-else-if="!cargando" class="apagado">{{ t('No groups yet.') }}</p>

    <div class="gf-cabeza mt">
      <h4>{{ t('Specific items') }}</h4>
      <router-link :to="{ path: '/etiquetas', query: { vista: 'articulos', familia: familia.id } }" class="btn btn-chico">{{ t('See and add items') }}</router-link>
    </div>
    <p class="ayuda">{{ t('An item assigned directly keeps this family even if its group has another one.') }}</p>

    <Modal v-if="modal" :titulo="t('Add item groups to {0}', [familia.nombre])" ancho="640px" @cerrar="modal = false">
      <div class="gf-buscar">
        <label class="buscador"><Icono nombre="buscar" :tam="15" /><input v-model="q" type="search" :placeholder="t('Search group or category')" :aria-label="t('Search')" /></label>
        <label class="check"><input v-model="soloSin" type="checkbox" /> {{ t('Only groups without a family') }}</label>
      </div>
      <div class="gf-tabla">
        <table class="tabla">
          <thead><tr>
            <th class="col-check"><input v-model="todosVisibles" type="checkbox" :aria-label="t('All the groups shown')" /></th>
            <th>{{ t('Group') }}</th><th>{{ t('Category') }}</th><th class="num">{{ t('Items') }}</th><th>{{ t('Current family') }}</th>
          </tr></thead>
          <tbody>
            <tr v-for="g in disponibles" :key="g.id" @click="elegidos.includes(g.id) ? (elegidos = elegidos.filter((x) => x !== g.id)) : elegidos.push(g.id)">
              <td class="col-check"><input v-model="elegidos" type="checkbox" :value="g.id" :aria-label="g.nombre" @click.stop /></td>
              <td><strong>{{ g.codigo }}</strong> {{ tx(g.nombre) }}</td>
              <td>{{ g.categoria }}</td>
              <td class="num">{{ fmtNum(g.articulos) }}</td>
              <td><span v-if="g.familia" class="etiqueta aviso ms-0">{{ tx(g.familia) }}</span><span v-else class="apagado">—</span></td>
            </tr>
            <tr v-if="!disponibles.length"><td colspan="5" class="apagado">{{ t('No groups match.') }}</td></tr>
          </tbody>
        </table>
      </div>
      <p v-if="deOtra.length" class="nota aviso mt-chico"><Icono nombre="alerta" :tam="16" />{{ t('{0} of the chosen groups belong to another family: they move to this one.', [deOtra.length]) }}</p>
      <template #pie>
        <span class="ayuda separar">{{ t('{0} groups · {1} items', [elegidos.length, fmtNum(articulosElegidos)]) }}</span>
        <button type="button" class="btn" @click="modal = false">{{ t('Cancel') }}</button>
        <button type="button" class="btn btn-primario" :disabled="!elegidos.length" @click="agregar">{{ t('Add {0} groups', [elegidos.length]) }}</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.grupos-familia { display: flex; flex-direction: column; gap: 6px; }
.gf-cifras { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 6px; }
.gf-cifras > div { border: 1px solid var(--linea); border-radius: 10px; padding: 8px 10px; display: flex; flex-direction: column; }
.gf-cifras strong { font-size: 1.2rem; }
.gf-cifras span { font-size: 0.74rem; color: var(--tinta-3); }
.gf-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.gf-cabeza h4 { margin: 0; font-size: 0.86rem; }
.gf-lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow: auto; }
.gf-lista li { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--linea); border-radius: 8px; font-size: 0.84rem; }
.gf-buscar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.gf-buscar .buscador { flex: 1; min-width: 220px; }
.gf-tabla { max-height: 380px; overflow: auto; border: 1px solid var(--linea); border-radius: 8px; }
.gf-tabla tbody tr { cursor: pointer; }
.col-check { width: 34px; }
.ayuda { margin: 0; font-size: 0.78rem; }
</style>
