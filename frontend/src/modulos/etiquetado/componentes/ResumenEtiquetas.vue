<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import SelectorDiseno from '@/modulos/etiquetado/componentes/SelectorDiseno.vue'

// Antes de imprimir desde una OC o una lista de empaque: cuántas etiquetas de
// cada tipo salen, con qué diseños y qué falta. Es solo para ver (panel); el
// diseño especial de una OC se crea en una ventana, y «Imprimir» abre el
// asistente directo en «Revisar».
const props = defineProps({
  origen: { type: String, required: true }, // OC · PACKING
  id: { type: Number, required: true },
  numero: { type: String, default: '' },
})
const emit = defineEmits(['cerrar'])
const router = useRouter()
const datos = ref(null)
const abiertos = ref({})
async function cargar() {
  try {
    datos.value = await api.get('/etiquetas/resumen', { origen: props.origen, id: props.id })
  } catch (e) {
    errorApi(e)
    emit('cerrar')
  }
}
onMounted(cargar)
const titulo = computed(() => (props.origen === 'OC' ? t('Labels of PO {0}', [props.numero]) : t('Labels of packing list {0}', [props.numero])))
const reales = computed(() => datos.value?.etiquetas_reales !== false)
const conEtiquetas = computed(() => (datos.value?.tipos || []).filter((x) => x.etiquetas > 0))
const sinDiseno = (x) => x.problemas.filter((p) => p.codigo === 'sin_plantilla' && p.nivel === 'error').length
function imprimir() {
  const query = props.origen === 'OC' ? { origen: 'OC', oc: props.id } : { origen: 'PACKING', pl: props.id }
  router.push({ path: '/etiquetas/trabajos/nuevo', query: { ...query, tipos: conEtiquetas.value.map((x) => x.tipo.id).join(',') || undefined, ...(!reales.value && { prueba: '1' }) } })
}

// Diseño especial para esta OC: el único lugar donde se crean excepciones de una OC
const especial = ref(null)
const familias = ref([])
async function abrirEspecial() {
  if (!familias.value.length) familias.value = await api.get('/etiquetas/familias', { activas: true }).catch(() => [])
  especial.value = { tipo_etiqueta_id: datos.value.tipos[0]?.tipo.id || '', plantilla_id: '', familia_id: '', motivo: '' }
}
const tipoEspecial = computed(() => datos.value?.tipos.find((x) => x.tipo.id === Number(especial.value?.tipo_etiqueta_id))?.tipo)
async function guardarEspecial() {
  const e = especial.value
  try {
    await api.post('/etiquetas/usos', { tipo_etiqueta_id: Number(e.tipo_etiqueta_id), plantilla_id: Number(e.plantilla_id), contexto_tipo: 'OC', oc_id: props.id,
      nivel: e.familia_id ? 'FAMILIA' : 'GENERAL', destino_id: e.familia_id ? Number(e.familia_id) : null, motivo: e.motivo })
    avisar(t('Special design saved for this PO.'))
    especial.value = null
    cargar()
  } catch (err) {
    errorApi(err)
  }
}
</script>

<template>
  <PanelLateral :titulo="titulo" ancho="560px" @cerrar="emit('cerrar')">
    <div v-if="!datos" class="vacio">{{ t('Loading…') }}</div>
    <!-- Diseño especial: dentro del mismo panel, sin otra ventana encima -->
    <template v-else-if="especial">
      <button type="button" class="btn btn-chico btn-texto re-volver" @click="especial = null"><Icono nombre="atras" :tam="14" />{{ t('Back to the summary') }}</button>
      <h3 class="re-titulo">{{ t('Special design for PO {0}', [numero]) }}</h3>
      <form id="form-especial" class="re-form" @submit.prevent="guardarEspecial">
        <label class="campo"><span class="req">{{ t('Label type') }}</span>
          <Seleccion v-model="especial.tipo_etiqueta_id"><option v-for="x in datos.tipos" :key="x.tipo.id" :value="x.tipo.id">{{ tx(x.tipo.nombre) }}</option></Seleccion></label>
        <SelectorDiseno v-if="tipoEspecial" :key="tipoEspecial.id" v-model="especial.plantilla_id" :tipo-id="tipoEspecial.id" />
        <label v-if="tipoEspecial?.sujeto === 'ARTICULO'" class="campo"><span>{{ t('Only for the family') }}</span>
          <Seleccion v-model="especial.familia_id"><option value="">{{ t('Every item of the PO') }}</option>
            <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.ruta || f.nombre) }}</option></Seleccion></label>
        <label class="campo"><span class="req">{{ t('Reason') }}</span><input v-model="especial.motivo" required maxlength="300" :placeholder="t('E.g. the customer asks for its own carton label')" /></label>
      </form>
    </template>
    <template v-else>
      <p v-if="!reales" class="nota aviso"><Icono nombre="alerta" :tam="16" />{{ t('The packing list is a draft; real labels are enabled when it is confirmed. Until then only test labels.') }}</p>
      <ul class="re-tipos">
        <li v-for="x in datos.tipos" :key="x.tipo.id" :class="{ apagado: !x.etiquetas }">
          <button type="button" class="re-fila" :aria-expanded="!!abiertos[x.tipo.id]" :disabled="!x.disenos.length && !x.problemas.length"
                  @click="abiertos = { ...abiertos, [x.tipo.id]: !abiertos[x.tipo.id] }">
            <strong>{{ tx(x.tipo.nombre) }}</strong>
            <span>{{ t('{0} labels', [fmtNum(x.etiquetas)]) }} · {{ t('{0} designs', [x.disenos.length]) }}</span>
            <Icono :nombre="abiertos[x.tipo.id] ? 'arriba' : 'abajo'" :tam="14" />
          </button>
          <div v-if="abiertos[x.tipo.id]" class="re-detalle">
            <p v-for="d in x.disenos" :key="d.plantilla_id">{{ tx(d.plantilla) }} · {{ t('{0} labels', [fmtNum(d.etiquetas)]) }}
              <span v-if="!d.aprobada" class="etiqueta aviso ms-0">{{ t('Not approved yet') }}</span></p>
          </div>
          <p v-if="sinDiseno(x)" class="re-problema"><Icono nombre="alerta" :tam="14" />{{ t('{0} records without a design of this type', [sinDiseno(x)]) }}
            <router-link v-if="puede('etiquetas.configurar')" to="/etiquetas/configuracion" class="btn btn-chico">{{ t('Resolve') }}</router-link></p>
        </li>
      </ul>
      <ul v-if="datos.problemas.length" class="re-generales">
        <li v-for="(p, i) in datos.problemas" :key="i" :class="p.nivel"><Icono :nombre="p.nivel === 'error' ? 'alerta' : 'info'" :tam="14" /> {{ tx(p.mensaje) }}</li>
      </ul>
      <p class="ayuda">{{ t('Total: {0} labels. Already generated: {1}.', [fmtNum(datos.total), fmtNum(datos.ya_generadas)]) }}</p>
    </template>
    <template v-if="especial" #pie>
      <button type="button" class="btn separar" @click="especial = null">{{ t('Cancel') }}</button>
      <button type="submit" class="btn btn-primario" form="form-especial" :disabled="!especial.plantilla_id">{{ t('Save') }}</button>
    </template>
    <template v-else #pie>
      <button v-if="origen === 'OC' && puede('etiquetas.configurar') && datos?.tipos.length" type="button" class="btn separar" @click="abrirEspecial">{{ t('Special design for this PO…') }}</button>
      <button v-if="puede('etiquetas.generar')" type="button" class="btn btn-primario" :disabled="!datos || !conEtiquetas.length" @click="imprimir">
        <Icono nombre="etiqueta" :tam="16" />{{ reales ? t('Print labels') : t('Print test') }}</button>
    </template>
  </PanelLateral>

</template>

<style scoped>
.re-tipos, .re-generales { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.re-tipos > li { border: 1px solid var(--linea); border-radius: 10px; padding: 4px 6px; }
.re-tipos > li.apagado { opacity: 0.6; }
.re-fila { width: 100%; display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center; text-align: start; background: none; border: 0;
  font: inherit; color: inherit; padding: 6px; cursor: pointer; min-height: 40px; }
.re-fila:disabled { cursor: default; }
.re-detalle { padding: 0 6px 6px; font-size: 0.86rem; }
.re-detalle p { margin: 2px 0; }
.re-problema { color: var(--aviso); display: flex; gap: 6px; align-items: center; margin: 0 6px 6px; font-size: 0.86rem; flex-wrap: wrap; }
.re-generales li { display: flex; gap: 6px; align-items: baseline; font-size: 0.86rem; }
.re-generales .error { color: var(--error); }
.re-generales .advertencia { color: var(--aviso); }
.re-form { display: flex; flex-direction: column; gap: 14px; }
.re-volver { align-self: flex-start; margin-bottom: 4px; }
.re-titulo { margin: 0 0 12px; font-size: 1rem; }
</style>
