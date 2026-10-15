<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import { puede } from '@/stores/sesion'
import CabezaEtiquetado from '@/modulos/etiquetado/componentes/CabezaEtiquetado.vue'
import CamposEtiqueta from '@/modulos/etiquetado/componentes/CamposEtiqueta.vue'
import NombresCampos from '@/modulos/etiquetado/componentes/NombresCampos.vue'
import FamiliasYArticulos from '@/modulos/etiquetado/componentes/FamiliasYArticulos.vue'
import HistorialEtiquetas from '@/modulos/etiquetado/componentes/HistorialEtiquetas.vue'
import MatrizEtiquetado from '@/modulos/etiquetado/componentes/MatrizEtiquetado.vue'
import PrimerUsoEtiquetado from '@/modulos/etiquetado/componentes/PrimerUsoEtiquetado.vue'
import TamanosEtiqueta from '@/modulos/etiquetado/componentes/TamanosEtiqueta.vue'
import TiposEtiqueta from '@/modulos/etiquetado/componentes/TiposEtiqueta.vue'

// Configuración del etiquetado (de vez en cuando, un responsable): qué diseño
// lleva cada cosa (la matriz, pantalla principal), los tipos de etiqueta, las
// familias con sus productos y artículos, los campos lógicos y el historial.
// La vista viaja en la dirección (?vista=).
const route = useRoute()
const router = useRouter()
const VISTAS = () => [
  ['matriz', t('Which design goes on what'), 'ruta'],
  ['tipos', t('Label types'), 'etiqueta'],
  ['familias', t('Families and items'), 'capas'],
  ['campos', t('Fields'), 'filtro'],
  ['historial', t('History'), 'historial'],
]
const vista = computed(() => (VISTAS().some((v) => v[0] === route.query.vista) ? route.query.vista : 'matriz'))
const ir = (v, extra = {}) => router.replace({ query: { vista: v === 'matriz' ? undefined : v, ...extra } })

const sinTipos = ref(false)
const primerUso = ref(false)
async function revisarTipos() {
  try {
    sinTipos.value = !(await api.get('/etiquetas/tipos', { todos: true })).length
  } catch {
    sinTipos.value = false
  }
}
onMounted(revisarTipos)
alCambiar(() => revisarTipos(), ['/etiquetas/tipos'])
function listo() {
  primerUso.value = false
  sinTipos.value = false
  ir('matriz')
}
</script>

<template>
  <CabezaEtiquetado :titulo="t('Labeling setup')" :texto="t('Which design goes on each family and label type, with its exceptions; label types, families and fields.')" />
  <nav class="pestanas pestanas-sub" role="tablist" :aria-label="t('Labeling setup')">
    <button v-for="[clave, texto, icono] in VISTAS()" :key="clave" type="button" class="pestana" role="tab" :aria-selected="vista === clave"
            @click="ir(clave)"><Icono :nombre="icono" :tam="15" />{{ texto }}</button>
  </nav>

  <EstadoVacio v-if="sinTipos && ['matriz', 'tipos'].includes(vista) && !primerUso" icono="etiqueta" :titulo="t('Your company has no label types yet')"
               :texto="t('Tell us which labels you print (hang tag, price sticker, carton label…) and how you group your items; it takes a minute.')">
    <button v-if="puede('etiquetas.configurar')" type="button" class="btn btn-primario" @click="primerUso = true"><Icono nombre="varita" />{{ t('Set up my labels') }}</button>
    <button v-if="puede('etiquetas.configurar') && vista === 'matriz'" type="button" class="btn" @click="ir('tipos'); sinTipos = false">{{ t('Create them one by one') }}</button>
  </EstadoVacio>
  <MatrizEtiquetado v-else-if="vista === 'matriz'" @familias="(f) => ir('familias', { familia: f })" />
  <template v-else-if="vista === 'tipos'">
    <TiposEtiqueta @cambio="revisarTipos" />
    <TamanosEtiqueta />
  </template>
  <FamiliasYArticulos v-else-if="vista === 'familias'" :key="String(route.query.familia || '')" />
  <template v-else-if="vista === 'campos'">
    <NombresCampos />
    <CamposEtiqueta />
  </template>
  <HistorialEtiquetas v-else />

  <PrimerUsoEtiquetado v-if="primerUso" @cerrar="primerUso = false" @listo="listo" />
</template>

<style scoped>
.pestanas-sub { margin-top: 0; }
</style>
