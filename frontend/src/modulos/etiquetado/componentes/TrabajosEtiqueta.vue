<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { fmtNum } from '@/nucleo/utils'
import { errorApi } from '@/stores/ui'
import { ORIGENES } from '@/modulos/etiquetado/etiquetas.js'

// Trabajos de etiquetado: los borradores para retomar donde quedaron, los que
// se están generando y los generados (completos o parciales) con su historial.
const lista = ref({ total: 0, items: [] })
const cargando = ref(false)
const estado = ref('BORRADOR,VALIDADO,EN_PROCESO,PARCIAL,ERROR')
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
onMounted(cargar)
watch(estado, cargar)
const origenTxt = (o) => ORIGENES().find((x) => x[0] === o)?.[1] || o
const columnas = computed(() => [
  { clave: 'nombre', texto: t('Job'), fija: true, prioridad: 1 },
  { clave: 'origen', texto: t('Origin'), prioridad: 2, textoValor: (v) => tx(origenTxt(v)) },
  { clave: 'estado', texto: t('Status'), prioridad: 1 },
  { clave: 'total', texto: t('Labels'), prioridad: 2 },
  { clave: 'creado_por', texto: t('By'), prioridad: 3 },
  { clave: 'actualizado_en', texto: t('Updated'), prioridad: 2, textoValor: (v) => (v ? new Date(v).toLocaleString() : '') },
])
// Datos de otros usuarios: se vuelven a pedir solo cuando cambian (nucleo/cambios.js)
alCambiar(() => cargar(), ['/etiquetas/trabajos'])
</script>

<template>
  <TablaDatos tabla="etiquetas_trabajos" :columnas="columnas" :filas="lista.items" :cargando="cargando" :etiqueta="t('Labeling jobs')"
>
    <template #filtros>
      <Seleccion v-model="estado" :aria-label="t('Status')">
        <option value="BORRADOR,VALIDADO,EN_PROCESO,PARCIAL,ERROR">{{ t('To continue') }}</option>
        <option value="GENERADO">{{ t('Generated') }}</option>
        <option value="">{{ t('All') }}</option>
      </Seleccion>
      <router-link class="btn btn-primario separar" to="/etiquetas/trabajos/nuevo"><Icono nombre="mas" />{{ t('New labeling job') }}</router-link>
    </template>
    <template #celda-nombre="{ fila: x }"><router-link :to="`/etiquetas/trabajos/${x.id}`" class="enlace">{{ x.nombre }}</router-link></template>
    <template #celda-estado="{ fila: x }">
      <EstadoBadge :estado="x.estado" tipo="trabajo" />
      <span v-if="x.estado === 'EN_PROCESO'" class="ayuda"> {{ fmtNum(x.progreso) }}/{{ fmtNum(x.total) }}</span>
      <span v-if="x.conteo?.ERROR" class="etiqueta error">{{ t('{0} with errors', [x.conteo.ERROR]) }}</span>
    </template>
    <template #celda-total="{ fila: x }">{{ fmtNum(x.total) }}</template>
    <template #vacio>{{ t('No labeling jobs here. Start one from a PO, a packing list, items or here.') }}</template>
  </TablaDatos>
</template>
