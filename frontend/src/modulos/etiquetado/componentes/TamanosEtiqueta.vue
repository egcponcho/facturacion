<script setup>
import { t } from '@/i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { catalogos, olvidarCatalogos } from '@/modulos/etiquetado/etiquetas.js'

// Los tamaños que se ofrecen al crear un diseño (cualquier otro se puede
// escribir a mano). Sin tamaños propios, los de fábrica.
const tamanos = ref([])
const edicion = ref(null)
async function cargar() {
  try {
    tamanos.value = (await catalogos()).tamanos
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
function editar() {
  edicion.value = tamanos.value.map((x) => ({ ...x }))
}
async function guardar(lista) {
  try {
    await api.put('/etiquetas/tamanos', { tamanos: lista.map((x) => ({ nombre: x.nombre, ancho: Number(x.ancho), alto: Number(x.alto) })) })
    olvidarCatalogos()
    await cargar()
    edicion.value = null
    avisar(t('Label sizes saved.'))
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section class="panel tm">
    <div class="tm-cabeza">
      <h3>{{ t('Label sizes') }}</h3>
      <button v-if="puede('etiquetas.configurar') && !edicion" type="button" class="btn btn-chico" @click="editar"><Icono nombre="editar" :tam="14" />{{ t('Change') }}</button>
    </div>
    <p class="ayuda">{{ t('Offered when creating a design; any other size can be written by hand.') }}</p>
    <!-- Se cambian aquí mismo, sin ventana -->
    <form v-if="edicion" class="tm-form" @submit.prevent="guardar(edicion)">
      <button type="button" class="btn btn-chico tm-agregar" :disabled="edicion.length >= 40" @click="edicion.unshift({ nombre: '', ancho: 100, alto: 50 })">
        <Icono nombre="mas" :tam="14" />{{ t('Add size') }}</button>
      <div v-for="(x, i) in edicion" :key="i" class="tm-fila">
        <input v-model="x.nombre" required maxlength="40" :aria-label="t('Name')" :placeholder="t('Name')" />
        <input v-model="x.ancho" type="number" min="5" max="1000" step="0.1" required :aria-label="t('Width (mm)')" />
        <span>×</span>
        <input v-model="x.alto" type="number" min="5" max="1000" step="0.1" required :aria-label="t('Height (mm)')" />
        <span class="ayuda">mm</span>
        <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="edicion.splice(i, 1)"><Icono nombre="basura" :tam="14" /></button>
      </div>
      <div class="tm-pie">
        <button type="button" class="btn" @click="guardar([])">{{ t('Back to the factory sizes') }}</button>
        <span class="separar" />
        <button type="button" class="btn" @click="edicion = null">{{ t('Cancel') }}</button>
        <button type="submit" class="btn btn-primario">{{ t('Save') }}</button>
      </div>
    </form>
    <ul v-else class="tm-lista">
      <li v-for="(x, i) in tamanos" :key="i" class="etiqueta ms-0">{{ x.nombre }} · {{ fmtNum(x.ancho, 1) }} × {{ fmtNum(x.alto, 1) }} mm</li>
    </ul>
  </section>

</template>

<style scoped>
.tm { margin-top: 16px; }
.tm-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.tm-cabeza h3 { margin: 0; font-size: 0.95rem; }
.tm-lista { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.tm-form { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; max-width: 640px; }
.tm-pie { display: flex; gap: 8px; margin-top: 6px; }
.tm-pie .separar { flex: 1; }
.tm-fila { display: grid; grid-template-columns: minmax(0, 1fr) 90px auto 90px auto auto; gap: 6px; align-items: center; }
.tm-agregar { align-self: flex-start; }
</style>
