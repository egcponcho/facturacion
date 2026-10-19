<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoVacio from '@/componentes/EstadoVacio.vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import CabezaEtiquetado from '@/modulos/etiquetado/componentes/CabezaEtiquetado.vue'
import PrimerUsoEtiquetado from '@/modulos/etiquetado/componentes/PrimerUsoEtiquetado.vue'
import { ORIGENES } from '@/modulos/etiquetado/etiquetas.js'

// Imprimir: la tarea de todos los días. Los trabajos recientes (borradores
// para retomar, los que se están generando y los generados) y un solo botón
// para empezar uno nuevo. Si la empresa aún no tiene tipos de etiqueta, el
// asistente de primer uso en lugar de una tabla vacía.
const router = useRouter()
const lista = ref({ total: 0, items: [] })
const cargando = ref(false)
const estado = ref('BORRADOR,VALIDADO,EN_PROCESO,PARCIAL,ERROR')
const sinTipos = ref(false)
const primerUso = ref(false)

async function cargar() {
  cargando.value = true
  try {
    lista.value = await api.get('/etiquetas/trabajos', { estado: estado.value || undefined, size: 200 })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
async function revisarTipos() {
  try {
    sinTipos.value = !(await api.get('/etiquetas/tipos')).length
  } catch {
    sinTipos.value = false
  }
}
onMounted(() => {
  cargar()
  revisarTipos()
})
watch(estado, cargar)
alCambiar(() => cargar(), ['/etiquetas/trabajos'])
alCambiar(() => revisarTipos(), ['/etiquetas/tipos'])

const origenTxt = (o) => ORIGENES().find((x) => x[0] === o)?.[1] || o
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Job'), fija: true, prioridad: 1 },
  { clave: 'origen', texto: t('Origin'), prioridad: 2, textoValor: (v) => origenTxt(v) },
  { clave: 'estado', texto: t('Status'), prioridad: 1 },
  { clave: 'total', texto: t('Labels'), prioridad: 2 },
  { clave: 'creado_por', texto: t('By'), prioridad: 3 },
  { clave: 'actualizado_en', texto: t('Updated'), prioridad: 2, textoValor: (v) => (v ? new Date(v).toLocaleString() : '') },
])
function listo() {
  primerUso.value = false
  sinTipos.value = false
  router.push({ path: '/etiquetas/configuracion', query: { vista: 'matriz' } })
}
</script>

<template>
  <CabezaEtiquetado :titulo="t('Labels')" :texto="t('Print the labels of a PO, a packing list or some items; set up once which design goes on what.')">
    <router-link v-if="puede('etiquetas.generar') && !sinTipos" class="btn btn-primario" to="/etiquetas/trabajos/nuevo"><Icono nombre="mas" />{{ t('New job') }}</router-link>
  </CabezaEtiquetado>

  <EstadoVacio v-if="sinTipos" icono="etiqueta" :titulo="t('Your company has no label types yet')"
               :texto="t('Tell us which labels you print (hang tag, price sticker, carton label…) and how you group your items; it takes a minute.')">
    <button v-if="puede('etiquetas.configurar')" type="button" class="btn btn-primario" @click="primerUso = true"><Icono nombre="varita" />{{ t('Set up my labels') }}</button>
    <p v-else class="ayuda">{{ t('Ask someone who can configure labeling to set them up.') }}</p>
  </EstadoVacio>

  <TablaDatos v-else tabla="etiquetas_trabajos" :columnas="columnas" :filas="lista.items" :cargando="cargando" :etiqueta="t('Labeling jobs')">
    <template #filtros>
      <Seleccion v-model="estado" :aria-label="t('Status')">
        <option value="BORRADOR,VALIDADO,EN_PROCESO,PARCIAL,ERROR">{{ t('To continue') }}</option>
        <option value="GENERADO">{{ t('Generated') }}</option>
        <option value="">{{ t('All') }}</option>
      </Seleccion>
    </template>
    <template #celda-nombre="{ fila: x }"><router-link :to="`/etiquetas/trabajos/${x.id}`" class="enlace">{{ x.nombre }}</router-link></template>
    <template #celda-estado="{ fila: x }">
      <EstadoBadge :estado="x.estado" tipo="trabajo" />
      <span v-if="x.estado === 'EN_PROCESO'" class="ayuda"> {{ fmtNum(x.progreso) }}/{{ fmtNum(x.total) }}</span>
      <span v-if="x.conteo?.ERROR" class="etiqueta error">{{ t('{0} with errors', [x.conteo.ERROR]) }}</span>
    </template>
    <template #celda-total="{ fila: x }">{{ fmtNum(x.total) }}</template>
    <template #vacio>{{ t('No labeling jobs here. Start one from a PO, a packing list, a product or with “New job”.') }}</template>
  </TablaDatos>

  <PrimerUsoEtiquetado v-if="primerUso" @cerrar="primerUso = false" @listo="listo" />
</template>
