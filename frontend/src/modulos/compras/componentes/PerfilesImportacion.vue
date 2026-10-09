<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { avisar, errorApi } from '@/stores/ui'

// Perfiles de importación: cómo leer el archivo de OCs que exporta el ERP de la
// empresa (nombres de columna, fila de encabezados, formato de fecha y valores
// por defecto). Sin perfil, el sistema reconoce los nombres genéricos.
const emit = defineEmits(['cerrar', 'cambio'])
const datos = ref({ perfiles: [], campos: [], formatos_fecha: [] })
const editando = ref(null)
const ocupado = ref(false)

const vacio = () => ({ id: null, codigo: '', nombre: '', fila_encabezado: 1, formato_fecha: '', predeterminado: false, activo: true, columnas: {}, valores: {} })
async function cargar() {
  try {
    datos.value = await api.get('/ordenes/importar/perfiles')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)

const elegir = (p) => { editando.value = JSON.parse(JSON.stringify(p)) }
const nuevo = () => { editando.value = vacio() }
const camposVisibles = computed(() => datos.value.campos)

async function guardar() {
  const p = editando.value
  const cuerpo = { codigo: p.codigo, nombre: p.nombre, fila_encabezado: Number(p.fila_encabezado) || 1, formato_fecha: p.formato_fecha || null,
                   predeterminado: p.predeterminado, activo: p.activo, columnas: p.columnas, valores: p.valores }
  ocupado.value = true
  try {
    const r = p.id ? await api.patch(`/ordenes/importar/perfiles/${p.id}`, cuerpo) : await api.post('/ordenes/importar/perfiles', cuerpo)
    avisar(t('Import profile saved.'))
    await cargar()
    editando.value = JSON.parse(JSON.stringify(r))
    emit('cambio')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

async function eliminar() {
  ocupado.value = true
  try {
    await api.del(`/ordenes/importar/perfiles/${editando.value.id}`)
    avisar(t('Import profile deleted.'))
    editando.value = null
    await cargar()
    emit('cambio')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <Modal :titulo="t('Import profiles')" ancho="980px" @cerrar="emit('cerrar')">
    <p class="ayuda">{{ t('How to read the PO file your ERP exports: the name of each column, the row with the headers, the date format and default values for what the file does not bring. Without a profile, the standard column names are recognized.') }}</p>
    <div class="perfiles">
      <aside>
        <button v-for="p in datos.perfiles" :key="p.id" type="button" class="perfil" :aria-pressed="editando?.id === p.id" @click="elegir(p)">
          <b>{{ tx(p.nombre) }}</b><span class="ayuda">{{ p.codigo }}<template v-if="p.predeterminado"> · {{ t('Default') }}</template><template v-if="!p.activo"> · {{ t('Inactive') }}</template></span>
        </button>
        <p v-if="!datos.perfiles.length" class="ayuda">{{ t('No profiles yet.') }}</p>
        <button type="button" class="btn btn-chico" @click="nuevo"><Icono nombre="mas" :tam="14" />{{ t('New profile') }}</button>
      </aside>
      <form v-if="editando" class="perfil-form" @submit.prevent="guardar">
        <div class="rejilla-campos">
          <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="editando.codigo" class="entrada" maxlength="20" required /></label>
          <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="editando.nombre" class="entrada" maxlength="80" required /></label>
          <label class="campo"><span>{{ t('Header row') }}</span><input v-model.number="editando.fila_encabezado" class="entrada" type="number" min="1" max="50" /></label>
          <label class="campo"><span>{{ t('Date format of the file') }}</span>
            <Seleccion v-model="editando.formato_fecha" class="entrada"><option value="">{{ t('Recognize it') }}</option><option v-for="f in datos.formatos_fecha" :key="f" :value="f">{{ f }}</option></Seleccion></label>
          <div class="campo"><span>{{ t('Default profile') }}</span><Interruptor v-model="editando.predeterminado" :etiqueta="t('Default profile')" /></div>
          <div class="campo"><span>{{ t('Active') }}</span><Interruptor v-model="editando.activo" :etiqueta="t('Active')" /></div>
        </div>
        <div class="tabla-marco mt">
          <table class="tabla">
            <thead><tr><th>{{ t('Data') }}</th><th>{{ t('Column in your file') }}</th><th>{{ t('Default value') }}</th></tr></thead>
            <tbody>
              <tr v-for="c in camposVisibles" :key="c.campo">
                <td><span :class="{ req: c.requerido }">{{ tx(c.etiqueta) }}</span><span v-if="c.fecha" class="ayuda"> · {{ t('date') }}</span></td>
                <td><input v-model="editando.columnas[c.campo]" class="entrada" maxlength="200" :placeholder="c.reconocidos[0]" :aria-label="t('Column in your file')" /></td>
                <td><input v-if="c.admite_defecto" v-model="editando.valores[c.campo]" class="entrada" maxlength="100" :aria-label="t('Default value')" /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="ayuda">{{ t('Several names for one column go separated by commas. Empty = the standard names.') }}</p>
        <div class="fila-flex mt">
          <button v-if="editando.id" type="button" class="btn btn-fantasma btn-peligro" :disabled="ocupado" @click="eliminar"><Icono nombre="basura" :tam="15" />{{ t('Delete') }}</button>
          <button class="btn btn-primario separar" type="submit" :disabled="ocupado"><Icono nombre="check" :tam="16" />{{ t('Save profile') }}</button>
        </div>
      </form>
      <p v-else class="ayuda">{{ t('Choose a profile or create one.') }}</p>
    </div>
  </Modal>
</template>

<style scoped>
.perfiles { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 18px; margin-top: 12px; align-items: start; }
aside { display: flex; flex-direction: column; gap: 6px; }
.perfil { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 10px; border: 1px solid var(--linea); border-radius: 8px; background: var(--superficie); text-align: left; cursor: pointer; }
.perfil[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-claro); }
.tabla-marco { max-height: 46vh; overflow: auto; }
@media (max-width: 760px) { .perfiles { grid-template-columns: 1fr; } }
</style>
