<script setup>
import { t, tx } from '../../i18n/index.js'
import { onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import Icono from '../Icono.vue'
import Interruptor from '../Interruptor.vue'
import { puede } from '../../stores/sesion'
import { avisar, errorApi } from '../../stores/ui'

// Clases de material que reconoce la composición. Las de base vienen con el
// motor; una familia nueva agrega las suyas (cerámica, vidrio templado…) con
// sus palabras y la palabra con que va en la descripción aduanera. Una
// derivación «clase» de un atributo las lleva a sus opciones.
const edita = puede('aranceles.editar')
const clases = ref([])
const nueva = reactive({ codigo: '', nombre: '', palabras: '', texto_aduana: '' })

async function cargar() {
  try {
    clases.value = await api.get('/aranceles/materiales')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
async function guardar(c, k, v) {
  try {
    const r = await api.patch(`/aranceles/materiales/${c.id}`, { [k]: v })
    Object.assign(c, r)
  } catch (e) {
    errorApi(e)
    cargar()
  }
}
async function agregar() {
  try {
    await api.post('/aranceles/materiales', { ...nueva })
    Object.assign(nueva, { codigo: '', nombre: '', palabras: '', texto_aduana: '' })
    avisar(t('Material class added.'))
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section class="panel">
    <h3><Icono nombre="capas" :tam="16" />{{ t('Material classes') }}</h3>
    <p class="ayuda">{{ t('The composition recognizes these classes of material. Add a class for a new family (e.g. ceramic: ceramica porcelain gres) or more words for an existing one; separate the words with spaces, and use ? for an optional letter (porcelanas?).') }}</p>
    <div class="tabla-marco">
      <table class="tabla">
        <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Name') }}</th><th>{{ t('Extra words') }}</th><th>{{ t('In the customs description') }}</th><th>{{ t('Active') }}</th></tr></thead>
        <tbody>
          <tr v-for="c in clases" :key="c.id" :class="{ apagada: !c.activo }">
            <td class="codigo">{{ tx(c.codigo) }}<br /><small class="ayuda">{{ tx(c.origen === 'MOTOR' ? t('Included') : t('Created by users')) }}</small></td>
            <td><input class="celda" :value="c.nombre" :disabled="!edita" :aria-label="t('Name')" maxlength="80" @change="guardar(c, 'nombre', $event.target.value)" /></td>
            <td><input class="celda" :value="c.palabras" :disabled="!edita" :aria-label="t('Extra words')" maxlength="1000"
                       :placeholder="c.origen === 'MOTOR' ? t('Base words included; add more') : ''" @change="guardar(c, 'palabras', $event.target.value)" /></td>
            <td><input class="celda" :value="c.texto_aduana" :disabled="!edita" :aria-label="t('In the customs description')" maxlength="60" @change="guardar(c, 'texto_aduana', $event.target.value)" /></td>
            <td><Interruptor :model-value="c.activo" :deshabilitado="!edita || c.origen === 'MOTOR'" :etiqueta="t('Active')" @update:model-value="guardar(c, 'activo', $event)" /></td>
          </tr>
          <tr v-if="edita" class="nueva">
            <td><input v-model="nueva.codigo" class="celda" :placeholder="t('Code')" :aria-label="t('Code')" maxlength="30" /></td>
            <td><input v-model="nueva.nombre" class="celda" :placeholder="t('Name')" :aria-label="t('Name')" maxlength="80" /></td>
            <td><input v-model="nueva.palabras" class="celda" :placeholder="t('e.g. ceramica ceramic porcelanas? gres')" :aria-label="t('Extra words')" maxlength="1000" /></td>
            <td><input v-model="nueva.texto_aduana" class="celda" :placeholder="t('e.g. CERÁMICA')" :aria-label="t('In the customs description')" maxlength="60" /></td>
            <td><button class="btn btn-chico" :disabled="!nueva.nombre || !nueva.palabras" @click="agregar"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
h3 { margin: 0 0 6px; font-size: 1rem; display: flex; gap: 6px; align-items: center; }
.celda { width: 100%; min-width: 90px; }
.celda::placeholder { color: var(--tinta-3); }
tr.apagada td { opacity: 0.55; }
</style>
