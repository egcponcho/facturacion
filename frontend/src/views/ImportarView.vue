<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import CargaArchivo from '../components/CargaArchivo.vue'
import Icono from '../components/Icono.vue'
import Paginacion from '../components/Paginacion.vue'
import ThOrden from '../components/ThOrden.vue'
import { useTabla } from '../composables/useTabla'
import { avisar, errorApi } from '../stores/ui'

const archivo = ref(null)
const previa = ref(null)
const filtro = ref('')
const ocupado = ref(false)

const ESTADOS = {
  nuevo: ['New', 'ok', 'Will be created'],
  cambio: ['Changed', 'info', 'Will be updated'],
  sin_cambio: ['Unchanged', 'neutro', 'Left as they are'],
  conflicto: ['Conflicts', 'aviso', 'Kept as alerts'],
  error: ['With errors', 'error', 'Not applied'],
}
const filasFiltradas = computed(() => (previa.value?.filas || []).filter((f) => !filtro.value || f.estado === filtro.value))
const tabla = useTabla(filasFiltradas, { porPagina: 15, orden: 'fila:asc' })
const aplicables = computed(() => (previa.value?.resumen.nuevo || 0) + (previa.value?.resumen.cambio || 0))
watch(archivo, () => (previa.value = null))
watch(filtro, () => (tabla.estado.pagina = 1))

async function revisar() {
  if (!archivo.value) return
  const datos = new FormData()
  datos.append('archivo', archivo.value)
  ocupado.value = true
  try {
    previa.value = await api.post('/ordenes/importar/previa', datos)
    filtro.value = ''
  } catch (e) {
    errorApi(e)
    if (e.detalle?.encontradas) avisar(`Columns found: ${e.detalle.encontradas.join(', ')}`, 'error', null, 12000)
  } finally {
    ocupado.value = false
  }
}

async function aplicar() {
  ocupado.value = true
  try {
    const r = await api.post(`/ordenes/importar/${previa.value.importacion_id}/aplicar`)
    avisar(`Import applied: ${r.aplicadas} order lines created or updated.` +
      (r.resumen.conflicto ? ` ${r.resumen.conflicto} conflicts were kept as alerts on the home page.` : ''))
    previa.value = null
    archivo.value = null
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

const valorTxt = (v) => (v === null || v === undefined || v === '' ? '—' : v)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <router-link to="/ordenes" class="volver"><Icono nombre="atras" :tam="15" />Purchase orders</router-link>
      <h1>Import purchase orders</h1>
      <p>Upload the Excel or CSV exported from SAP. Each row is checked against the master data (items, companies, plants, destinations and ports); nothing is saved until you confirm.</p>
    </div>
    <a class="btn" href="/plantilla_oc.csv" download><Icono nombre="descargar" />Sample template</a>
  </div>

  <div class="dos-columnas" style="grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr)">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>1. Choose the file</h2><p>One row per PO line.</p></div></div>
      <CargaArchivo v-model="archivo" texto="Drag the PO file here or choose it" ayuda="Excel (.xlsx) or CSV, exported from SAP" />
      <div class="fila-flex mt">
        <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="revisar"><Icono nombre="lupa" :tam="16" />{{ ocupado ? 'Checking…' : 'Check file' }}</button>
        <span class="ayuda">Codes (PO, line, SKU) are read as text so leading zeros are kept.</span>
      </div>
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>What is checked</h2></div></div>
      <ul class="lista-mensajes ayuda">
        <li>PO in the format 44 + 8 digits and lines in steps of 10.</li>
        <li><b>Item data comes from the item master</b>, not from the file: style, color, size, description, brand, group, UoM, HS code and country of origin. The SKU must exist and belong to the PO's supplier.</li>
        <li><b>PO line data comes from the file</b>: line, warehouse, quantity, price, dates, and the purchase packing: <b>casepack</b> (exact quantity per carton) and <b>inner pack</b> (units per inner pack). The casepack must be a multiple of the inner pack, and the quantity a whole number of inner packs. A prepack is already a defined carton and takes neither.</li>
        <li>Company, plant and warehouse must match each other, and the supplier must work with the company.</li>
        <li>Destination plant, port and countries registered in Master data.</li>
        <li>Commercial release P leaves the PO at 304; C or blank releases it (300, or 301 if it was already released and changed).</li>
      </ul>
    </section>
  </div>

  <template v-if="previa">
    <h2 class="mt">2. Review the result</h2>
    <p class="ayuda" style="margin-bottom: 12px">{{ previa.archivo }} · {{ previa.resumen.total }} rows. Click a group to filter.</p>
    <div class="etapas">
      <button v-for="(info, clave) in ESTADOS" :key="clave" type="button" class="etapa" :aria-pressed="filtro === clave" @click="filtro = filtro === clave ? '' : clave">
        <span class="fila-flex"><span class="estado" :class="`estado-${info[1]}`"><span class="estado-marca"></span>{{ info[0] }}</span></span>
        <b>{{ previa.resumen[clave] }}</b>
        <span>{{ info[2] }}</span>
      </button>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla">
        <thead>
          <tr>
            <ThOrden campo="fila" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">Row</ThOrden>
            <ThOrden campo="clave" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">PO line</ThOrden>
            <ThOrden campo="estado" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Result</ThOrden>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in tabla.filas.value" :key="f.fila">
            <td class="num">{{ f.fila }}</td>
            <td class="codigo">{{ f.clave }}</td>
            <td><span class="estado" :class="`estado-${ESTADOS[f.estado][1]}`"><span class="estado-marca"></span>{{ ESTADOS[f.estado][0] }}</span></td>
            <td class="envolver">
              <div v-for="m in f.mensajes" :key="m">{{ m }}</div>
              <div v-for="(c, campo) in f.cambios" :key="campo" class="ayuda">{{ campo.replaceAll('_', ' ') }}: {{ valorTxt(c.antes) }} → {{ valorTxt(c.despues) }}</div>
            </td>
          </tr>
          <tr v-if="!tabla.total.value"><td colspan="4" class="vacio">No rows in this group.</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
                @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />
    <div class="fila-flex mt">
      <span class="ayuda">Conflicts (for example, lowering the quantity below what is already invoiced) are not applied: they are kept as alerts.</span>
      <button class="btn btn-primario separar" :disabled="ocupado || !aplicables" @click="aplicar"><Icono nombre="check" />Apply {{ aplicables }} changes</button>
    </div>
  </template>
</template>
