<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Seleccion from '@/componentes/Seleccion.vue'

// Los datos de una familia de etiquetado (en la página, sin ventana): código,
// nombre, de qué familia es subfamilia, descripción, si está activa y sus
// campos habituales u obligatorios. v-model: el borrador del formulario; quien
// lo usa decide qué hacer al guardar (crear, cambiar o seguir un asistente).
const modelo = defineModel({ type: Object, required: true })
const props = defineProps({ familias: { type: Array, default: () => [] }, conCampos: { type: Boolean, default: true } })
const campos = ref([])
onMounted(() => api.get('/etiquetas/campos', { sujeto: 'ARTICULO' })
  .then((r) => (campos.value = r.campos.filter((c) => ['articulo', 'producto'].includes(c.grupo)))).catch(() => {}))
const marcado = (clave) => (modelo.value.campos || []).find((c) => c.campo === clave)
function alternarCampo(clave, tipo, si) {
  const lista = [...(modelo.value.campos || [])]
  const actual = lista.find((c) => c.campo === clave)
  if (tipo === 'habitual') {
    if (si && !actual) lista.push({ campo: clave, obligatorio: false })
    modelo.value.campos = si ? lista : lista.filter((c) => c.campo !== clave)
    return
  }
  if (si && actual) actual.obligatorio = true
  else if (si) lista.push({ campo: clave, obligatorio: true })
  else if (actual) actual.obligatorio = false
  modelo.value.campos = lista
}
// No puede ser subfamilia de sí misma ni de las que están debajo de ella
const madres = computed(() => props.familias.filter((x) => x.id !== modelo.value.id && !(modelo.value.id && (x.ruta || '').split(' / ').includes(modelo.value.nombre))))
const nombreCampo = (clave) => campos.value.find((c) => c.clave === clave)?.etiqueta || clave
</script>

<template>
  <div class="ff">
    <div class="rejilla-campos">
      <label class="campo"><span class="req">{{ t('Code') }}</span><input v-model="modelo.codigo" required maxlength="20" :placeholder="t('E.g. FOOTWEAR')" /></label>
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="modelo.nombre" required maxlength="100" :placeholder="t('E.g. Footwear')" /></label>
    </div>
    <label class="campo"><span>{{ t('Subfamily of') }}</span>
      <Seleccion v-model="modelo.padre_id"><option :value="null">{{ t('None (main family)') }}</option>
        <option v-for="x in madres" :key="x.id" :value="x.id">{{ tx(x.ruta || x.nombre) }}</option></Seleccion>
      <small class="ayuda">{{ t('A subfamily inherits the required fields and the designs of the families that contain it.') }}</small></label>
    <label class="campo"><span>{{ t('Description') }}</span><textarea v-model="modelo.descripcion" maxlength="300" rows="2"></textarea></label>
    <label class="check"><input v-model="modelo.activa" type="checkbox" /> {{ t('Active') }}</label>
    <div v-if="props.conCampos" class="campo">
      <span>{{ t('Fields of this family') }}</span>
      <p class="ayuda">{{ t('Usual: suggested when designing. Required: a warning when an item of the family lacks it.') }}</p>
      <div class="ff-campos">
        <table class="tabla">
          <thead><tr><th>{{ t('Field') }}</th><th class="centro">{{ t('Usual') }}</th><th class="centro">{{ t('Required') }}</th></tr></thead>
          <tbody>
            <tr v-for="c in campos" :key="c.clave">
              <td>{{ tx(c.etiqueta) }}</td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)" :aria-label="t('Usual')" @change="alternarCampo(c.clave, 'habitual', $event.target.checked)" /></td>
              <td class="centro"><input type="checkbox" :checked="!!marcado(c.clave)?.obligatorio" :aria-label="t('Required')" @change="alternarCampo(c.clave, 'obligatorio', $event.target.checked)" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="modelo.heredados?.length" class="ayuda">{{ t('Inherited fields: {0}', [modelo.heredados.map((c) => tx(nombreCampo(c.campo)) + (c.obligatorio ? ' *' : '')).join(', ')]) }}</p>
    </div>
  </div>
</template>

<style scoped>
.ff { display: flex; flex-direction: column; gap: 14px; }
.ff-campos { max-height: 340px; overflow: auto; border: 1px solid var(--linea); border-radius: 8px; }
.ff-campos .tabla { font-size: 0.84rem; }
.ff-campos thead th { position: sticky; top: 0; background: var(--superficie-2); }
.centro { text-align: center; }
</style>
