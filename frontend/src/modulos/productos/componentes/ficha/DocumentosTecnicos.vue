<script setup>
import { opcionesLista, valores } from '@/nucleo/listas.js'
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtFecha } from '@/nucleo/utils'
import { avisar, errorApi } from '@/stores/ui'

// Fichas técnicas del producto (SDS, TDS, COA): evidencia técnica de la empresa.
// Sus datos (CAS, composición, estado físico, densidad, pH…) completan los
// hechos vacíos de la ficha; nunca son fuente arancelaria (no dan códigos, DAI,
// impuestos ni regulaciones).
const props = defineProps({
  producto: { type: Object, required: true },
  campos: { type: Array, default: () => [] }, // campos de la ficha (para elegir el dato técnico)
  editable: Boolean,
})
const emit = defineEmits(['cambio'])

// Tipos de documento técnico de la empresa (Datos maestros → Listas de valores)
const TIPOS = computed(() => opcionesLista('tipo_documento'))
const nuevo = reactive({ tipo: valores('tipo_documento')[0]?.codigo || '', emisor: '', fecha: '', archivo: null, filas: [{ k: '', v: '' }] })
const ocupado = ref(false)
const opcionesCampo = computed(() => props.campos.filter((c) => c.tipo_dato !== 'composition' && c.tipo_dato !== 'country'))
const etiqueta = (k) => props.campos.find((c) => c.codigo === k)?.etiqueta || k

async function subir() {
  if (!nuevo.archivo) return
  const datos = new FormData()
  datos.append('archivo', nuevo.archivo)
  datos.append('tipo', nuevo.tipo)
  if (nuevo.emisor) datos.append('emisor', nuevo.emisor)
  if (nuevo.fecha) datos.append('fecha', nuevo.fecha)
  const valores = Object.fromEntries(nuevo.filas.filter((f) => f.k && String(f.v).trim()).map((f) => [f.k, f.v]))
  datos.append('datos', JSON.stringify(valores))
  ocupado.value = true
  try {
    await api.post(`/productos/${props.producto.id}/documentos`, datos)
    avisar(t('Document attached. Its technical data fill the empty facts of the sheet.'))
    Object.assign(nuevo, { emisor: '', fecha: '', archivo: null, filas: [{ k: '', v: '' }] })
    emit('cambio')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function quitar(d) {
  if (!window.confirm(t('Remove {0}?', [d.nombre]))) return
  try {
    await api.del(`/productos/${props.producto.id}/documentos/${d.id}`)
    emit('cambio')
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div class="panel mt-chico">
    <p class="nota info"><Icono nombre="info" /><span>{{ t('SDS, TDS and COA are technical evidence of the product: their data (CAS, composition, physical state, density, pH…) fill the empty facts of the sheet. They are never a tariff source: codes, duties, taxes and regulations only come from official sources.') }}</span></p>
    <div class="tabla-marco">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Document') }}</th><th>{{ t('Issued by') }}</th><th>{{ t('Technical data') }}</th><th></th></tr></thead>
        <tbody>
          <tr v-for="d in producto.documentos || []" :key="d.id">
            <td><span class="etiqueta acento">{{ d.tipo }}</span> <a :href="`/api/productos/documentos/${d.id}`" target="_blank" rel="noopener">{{ tx(d.nombre) }}</a>
              <span v-if="d.fecha_documento" class="sub">{{ fmtFecha(d.fecha_documento) }}</span></td>
            <td>{{ tx(d.emisor || '—') }}</td>
            <td><span v-for="(v, k) in d.datos" :key="k" class="etiqueta">{{ tx(etiqueta(k)) }}: {{ tx(String(v)) }}</span><span v-if="!Object.keys(d.datos || {}).length" class="apagado">—</span></td>
            <td class="num"><button v-if="editable" class="btn-icono" :aria-label="t('Remove {0}', [d.nombre])" @click="quitar(d)"><Icono nombre="basura" :tam="16" /></button></td>
          </tr>
          <tr v-if="!(producto.documentos || []).length"><td colspan="4" class="vacio">{{ t('No technical documents attached.') }}</td></tr>
        </tbody>
      </table>
    </div>
    <template v-if="editable">
      <h3 class="mt">{{ t('Attach a document') }}</h3>
      <div class="rejilla-campos">
        <label class="campo"><span class="req">{{ t('Kind') }}</span>
          <Seleccion v-model="nuevo.tipo" class="entrada"><option v-for="[k, txt] in TIPOS" :key="k" :value="k">{{ txt }}</option></Seleccion></label>
        <label class="campo"><span>{{ t('Issued by') }}</span><input v-model="nuevo.emisor" class="entrada" maxlength="200" :placeholder="t('Supplier or laboratory')" /></label>
        <label class="campo"><span>{{ t('Document date') }}</span><input v-model="nuevo.fecha" type="date" class="entrada" /></label>
        <label class="campo"><span class="req">{{ t('File (PDF or image)') }}</span>
          <input type="file" accept="application/pdf,image/png,image/jpeg" class="entrada" @change="nuevo.archivo = $event.target.files?.[0] || null" /></label>
      </div>
      <p class="ayuda">{{ t('Technical data read from the document (optional):') }}</p>
      <div v-for="(f, i) in nuevo.filas" :key="i" class="fila-flex dato-doc">
        <Seleccion v-model="f.k" class="entrada" :aria-label="t('Attribute')"><option value="">{{ t('Attribute…') }}</option>
          <option v-for="c in opcionesCampo" :key="c.codigo" :value="c.codigo">{{ tx(c.etiqueta) }}</option></Seleccion>
        <input v-model="f.v" class="entrada" maxlength="300" :aria-label="t('Value')" :placeholder="t('Value')" />
        <button v-if="nuevo.filas.length > 1" type="button" class="btn-icono" :aria-label="t('Remove')" @click="nuevo.filas.splice(i, 1)"><Icono nombre="cerrar" :tam="14" /></button>
      </div>
      <div class="fila-flex mt-chico">
        <button type="button" class="btn btn-chico" @click="nuevo.filas.push({ k: '', v: '' })"><Icono nombre="mas" :tam="14" />{{ t('Add data') }}</button>
        <button type="button" class="btn btn-primario" :disabled="ocupado || !nuevo.archivo" @click="subir"><Icono nombre="importar" />{{ t('Attach') }}</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dato-doc { gap: 8px; margin-bottom: 6px; }
.dato-doc .entrada { max-width: 320px; }
td .etiqueta { margin: 2px 4px 2px 0; }
</style>
