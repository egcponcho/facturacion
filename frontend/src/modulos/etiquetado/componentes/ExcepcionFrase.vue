<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import CampoFecha from '@/componentes/CampoFecha.vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import { fmtNum } from '@/nucleo/utils'
import EditorCondiciones from '@/modulos/etiquetado/componentes/EditorCondiciones.vue'
import SalidaRegla from '@/modulos/etiquetado/componentes/SalidaRegla.vue'
import SelectorDiseno from '@/modulos/etiquetado/componentes/SelectorDiseno.vue'
import { CONTEXTOS } from '@/modulos/etiquetado/etiquetas.js'

// Agregar o cambiar una excepción, escrita como frase:
// «Si [el país destino es] [Panamá] usar [diseño] (o no lleva) desde … hasta … porque …».
// El orden lo da la clase de excepción (centro, país, sociedad, proveedor,
// condiciones); dentro de la misma clase, la prioridad. «Aplicar también a»
// copia la excepción en otras filas de la misma columna.
const props = defineProps({
  modelValue: { type: Object, required: true },
  tipo: { type: Object, required: true }, // el tipo de etiqueta (id, sujeto, cantidad, alcance_efectivo)
  campos: { type: Array, default: () => [] }, // campos para las condiciones (Avanzado)
  operadores: { type: Array, default: () => [] }, // operadores simples del servidor
  otras: { type: Array, default: () => [] }, // otras filas de la columna: { nivel, destino_id, nombre }
  coinciden: { type: Number, default: null }, // líneas de OC abiertas que la cumplen hoy (simulación)
  conflicto: { type: String, default: '' },
})
const emit = defineEmits(['aceptar', 'cancelar'])
const x = props.modelValue
const CON_VALORES = ['PAIS_DESTINO', 'CENTRO_DESTINO', 'SOCIEDAD', 'PROVEEDOR']
const clases = computed(() => Object.entries(CONTEXTOS()).filter(([c]) => c !== 'OC'))
const opciones = ref([])
watch(() => x.contexto_tipo, async (c, antes) => {
  if (antes && c !== antes) x.contexto_valores = []
  opciones.value = []
  if (CON_VALORES.includes(c)) {
    opciones.value = await api.get('/etiquetas/usos/valores', { contexto: c }).catch(() => [])
  }
}, { immediate: true })
const listo = computed(() => (x.plantilla_id || x.accion === 'NO_LLEVA') && (x.motivo || '').trim()
  && (CON_VALORES.includes(x.contexto_tipo) ? x.contexto_valores.length > 0
    : x.contexto_tipo === 'CONDICION' ? x.condiciones.some((c) => c.campo) || x.vigente_desde || x.vigente_hasta : false))
// Al aceptar, la frase se muestra con los nombres (Panamá, el diseño), no con los códigos
const selector = ref(null)
function aceptar() {
  x.contexto_nombres = x.contexto_valores.map((v) => opciones.value.find((o) => String(o.valor) === String(v))?.texto || v)
  if (x.accion !== 'NO_LLEVA' && selector.value?.elegido) x.plantilla = selector.value.elegido.nombre
  emit('aceptar')
}
function alternarOtra(o) {
  const clave = `${o.nivel}:${o.destino_id ?? 0}`
  x.aplicar = x.aplicar.includes(clave) ? x.aplicar.filter((k) => k !== clave) : [...x.aplicar, clave]
}
</script>

<template>
  <div class="frase" :class="{ conflicto }">
    <div class="frase-linea">
      <span class="frase-palabra">{{ t('If') }}</span>
      <Seleccion v-model="x.contexto_tipo" :aria-label="t('What is looked at')">
        <option v-for="[c, txt] in clases" :key="c" :value="c">{{ txt }}</option>
      </Seleccion>
      <SelectBusqueda v-if="CON_VALORES.includes(x.contexto_tipo)" v-model="x.contexto_valores" multiple :opciones="opciones"
                      :etiqueta="t('Values')" :prefijo="false" :placeholder="t('Choose one or more…')" class="frase-valores" />
    </div>
    <EditorCondiciones v-if="x.contexto_tipo === 'CONDICION'" :model-value="x.condiciones" :campos="campos" :operadores="operadores" />
    <SalidaRegla :model-value="x" :tipo="tipo" prioridad>
      <div class="frase-linea">
        <span class="frase-palabra">{{ t('use') }}</span>
        <SelectorDiseno ref="selector" v-model="x.plantilla_id" :tipo-id="tipo.id" :miniatura="false" class="frase-diseno" />
      </div>
    </SalidaRegla>
    <div class="frase-linea">
      <label class="frase-fecha"><span>{{ t('from') }}</span><CampoFecha v-model="x.vigente_desde" :aria-label="t('From')" /></label>
      <label class="frase-fecha"><span>{{ t('until') }}</span><CampoFecha v-model="x.vigente_hasta" :aria-label="t('Until')" /></label>
      <label class="frase-motivo"><span class="req">{{ t('because') }}</span>
        <input v-model="x.motivo" maxlength="300" required :placeholder="t('E.g. customs requirement')" /></label>
    </div>
    <div v-if="!x.id && otras.length" class="frase-linea frase-otras">
      <span class="ayuda">{{ t('Apply also to:') }}</span>
      <label v-for="o in otras" :key="`${o.nivel}:${o.destino_id}`" class="check">
        <input type="checkbox" :checked="x.aplicar.includes(`${o.nivel}:${o.destino_id ?? 0}`)" @change="alternarOtra(o)" /> {{ tx(o.nombre) }}</label>
    </div>
    <div class="frase-pie">
      <span v-if="conflicto" class="error-txt"><Icono nombre="alerta" :tam="14" /> {{ conflicto }}</span>
      <span v-else-if="coinciden != null && coinciden > 0" class="ok-txt"><Icono nombre="check" :tam="14" /> {{ t('{0} open PO lines match today', [fmtNum(coinciden)]) }}</span>
      <span v-else-if="coinciden === 0" class="aviso-txt"><Icono nombre="info" :tam="14" /> {{ t('No open PO line matches today; is it right?') }}</span>
      <button type="button" class="btn btn-chico separar" @click="emit('cancelar')">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-chico btn-primario" :disabled="!listo || !!conflicto" @click="aceptar">{{ x.id ? t('Done') : t('Add') }}</button>
    </div>
  </div>
</template>

<style scoped>
.frase { border: 1px solid var(--acento); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; background: var(--superficie); }
.frase.conflicto { border-color: var(--error); }
.frase-linea { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.frase-palabra { font-weight: 600; min-width: 34px; }
.frase-valores { flex: 1 1 220px; min-width: 0; }
.frase-diseno { flex: 1 1 260px; min-width: 0; }
.frase-fecha, .frase-motivo { display: flex; gap: 6px; align-items: center; }
.frase-motivo { flex: 1 1 240px; }
.frase-motivo input { flex: 1; min-width: 0; }
.frase-otras { font-size: 0.86rem; }
.frase-pie { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 0.86rem; }
.ok-txt { color: var(--ok); }
.aviso-txt { color: var(--aviso); }
.error-txt { color: var(--error); }
</style>
