<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import CargaArchivo from '@/componentes/CargaArchivo.vue'
import Icono from '@/componentes/Icono.vue'
import Paginacion from '@/componentes/Paginacion.vue'
import ThOrden from '@/componentes/ThOrden.vue'
import PerfilesImportacion from '@/modulos/compras/componentes/PerfilesImportacion.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { puede } from '@/stores/sesion'
import { useTabla } from '@/composables/useTabla'
import { avisar, errorApi } from '@/stores/ui'
import { filasDefecto } from '@/stores/preferencias'

const archivo = ref(null)
const previa = ref(null)
const filtro = ref('')
const ocupado = ref(false)
// Perfil de importación (cómo leer el archivo del ERP); de entrada, el predeterminado
const perfiles = ref([])
const perfilId = ref('')
const verPerfiles = ref(false)
async function cargarPerfiles() {
  try {
    perfiles.value = (await api.get('/ordenes/importar/perfiles')).perfiles.filter((p) => p.activo)
    if (!perfiles.value.some((p) => String(p.id) === String(perfilId.value))) perfilId.value = perfiles.value.find((p) => p.predeterminado)?.id || ''
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargarPerfiles)

const ESTADOS = {
  nuevo: [t('New'), 'ok', t('Will be created')],
  cambio: [t('Changed'), 'info', t('Will be updated')],
  sin_cambio: [t('Unchanged'), 'neutro', t('Left as they are')],
  conflicto: [t('Conflicts'), 'aviso', t('Kept as alerts')],
  error: [t('With errors'), 'error', t('Not applied')],
}
const filasFiltradas = computed(() => (previa.value?.filas || []).filter((f) => !filtro.value || f.estado === filtro.value))
const tabla = useTabla(filasFiltradas, { porPagina: filasDefecto(), orden: 'fila:asc' })
const aplicables = computed(() => (previa.value?.resumen.nuevo || 0) + (previa.value?.resumen.cambio || 0))
watch(archivo, () => (previa.value = null))
watch(filtro, () => (tabla.estado.pagina = 1))

async function revisar() {
  if (!archivo.value) return
  const datos = new FormData()
  datos.append('archivo', archivo.value)
  if (perfilId.value) datos.append('perfil_id', perfilId.value)
  ocupado.value = true
  try {
    previa.value = await api.post('/ordenes/importar/previa', datos)
    filtro.value = ''
  } catch (e) {
    errorApi(e)
    if (e.detalle?.encontradas) avisar(t('Columns found: {0}', [e.detalle.encontradas.join(', ')]), 'error', null, 12000)
  } finally {
    ocupado.value = false
  }
}

async function aplicar() {
  ocupado.value = true
  try {
    const r = await api.post(`/ordenes/importar/${previa.value.importacion_id}/aplicar`)
    avisar(t('Import applied: {0} order lines created or updated.', [r.aplicadas]) +
      (r.resumen.conflicto ? t(' {0} conflicts were kept as alerts on the home page.', [r.resumen.conflicto]) : ''))
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
      <router-link to="/ordenes" class="volver"><Icono nombre="atras" :tam="15" />{{ t('Purchase orders') }}</router-link>
      <h1>{{ t('Load purchase orders') }}</h1>
      <p>{{ t('Upload a file exported from your ERP. It is checked against the master data; nothing is saved until you confirm.') }}</p>
    </div>
    <router-link v-if="puede('oc.editar')" to="/ordenes/nueva" class="btn"><Icono nombre="mas" />{{ t('New PO') }}</router-link>
    <button type="button" class="btn" :title="t('Excel template with the dates in the format of your profile')" @click="api.descargar('/ordenes/plantilla', 'purchase_orders_template.xlsx')"><Icono nombre="descargar" />{{ t('Sample template') }}</button>
  </div>

  <div class="dos-columnas" style="grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr)">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('1. Choose the file') }}</h2><p>{{ t('One row per PO line.') }}</p></div></div>
      <div class="fila-flex" style="margin-bottom: 10px">
        <label class="campo" style="flex: 1"><span>{{ t('Import profile') }}</span>
          <Seleccion v-model="perfilId" class="entrada" @change="previa = null"><option value="">{{ t('Standard column names') }}</option><option v-for="p in perfiles" :key="p.id" :value="p.id">{{ tx(p.nombre) }}</option></Seleccion></label>
        <button type="button" class="btn" style="align-self: flex-end" @click="verPerfiles = true"><Icono nombre="engrane" :tam="15" />{{ t('Profiles') }}</button>
      </div>
      <CargaArchivo v-model="archivo" :texto="t('Drag the PO file here or choose it')" :ayuda="t('Excel (.xlsx) or CSV, exported from your ERP')" />
      <div class="fila-flex mt">
        <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="revisar"><Icono nombre="lupa" :tam="16" />{{ tx(ocupado ? t('Checking…') : t('Check file')) }}</button>
        <span class="ayuda">{{ t('Codes (PO, line, SKU) are read as text so leading zeros are kept.') }}</span>
      </div>
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('What is checked') }}</h2></div></div>
      <ul class="lista-mensajes ayuda">
        <li>{{ t('PO number and line in your own format (letters and numbers).') }}</li>
        <li><b>{{ t('Item data comes from the item master') }}</b>{{ t(', not from the file: style, color, size, description, brand, group, UoM, HS code and country of origin. The SKU must exist and belong to the PO\'s supplier.') }}</li>
        <li><b>{{ t('PO line data comes from the file') }}</b>{{ t(': line, warehouse, quantity, price, dates, and the purchase packing:') }} <b>casepack</b> {{ t('(exact quantity per carton) and') }} <b>{{ t('inner pack') }}</b> {{ t('(units per inner pack). The casepack must be a multiple of the inner pack, and the quantity a whole number of inner packs. A prepack is already a defined carton and takes neither.') }}</li>
        <li>{{ t('Company, plant and warehouse must match each other, and the supplier must work with the company.') }}</li>
        <li>{{ t('Destination plant, port and countries registered in Master data.') }}</li>
        <li>{{ t('Required: supplier, PO number, line, item and quantity. Company, currency and price are optional when loading and required to invoice.') }}</li>
        <li>{{ t('Commercial release pending leaves the PO not released; released or blank releases it (released with changes if it was already released and changed).') }}</li>
      </ul>
    </section>
  </div>

  <template v-if="previa">
    <h2 class="mt">{{ t('2. Review the result') }}</h2>
    <p class="ayuda mb-3">{{ t('{0} · {1} rows. Click a group to filter.', [previa.archivo, previa.resumen.total]) }}</p>
    <div class="etapas">
      <button v-for="(info, clave) in ESTADOS" :key="clave" type="button" class="etapa" :aria-pressed="filtro === clave" @click="filtro = filtro === clave ? '' : clave">
        <span class="fila-flex"><span class="estado" :class="`estado-${info[1]}`"><span class="estado-marca"></span>{{ tx(info[0]) }}</span></span>
        <b>{{ tx(previa.resumen[clave]) }}</b>
        <span>{{ tx(info[2]) }}</span>
      </button>
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead>
          <tr>
            <ThOrden campo="fila" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">{{ t('Row') }}</ThOrden>
            <ThOrden campo="clave" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">{{ t('PO line') }}</ThOrden>
            <ThOrden campo="estado" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">{{ t('Result') }}</ThOrden>
            <th>{{ t('Detail') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in tabla.filas.value" :key="f.fila">
            <td class="num">{{ tx(f.fila) }}</td>
            <td class="codigo">{{ tx(f.clave) }}</td>
            <td><span class="estado" :class="`estado-${ESTADOS[f.estado][1]}`"><span class="estado-marca"></span>{{ tx(ESTADOS[f.estado][0]) }}</span></td>
            <td class="envolver">
              <div v-for="m in f.mensajes" :key="m">{{ tx(m) }}</div>
              <div v-for="(c, campo) in f.cambios" :key="campo" class="ayuda">{{ tx(campo.replaceAll('_', ' ')) }}: {{ tx(valorTxt(c.antes)) }} → {{ tx(valorTxt(c.despues)) }}</div>
            </td>
          </tr>
          <tr v-if="!tabla.total.value"><td colspan="4" class="vacio">{{ t('No rows in this group.') }}</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
                @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />
    <div class="fila-flex mt">
      <span class="ayuda">{{ t('Conflicts (for example, lowering the quantity below what is already invoiced) are not applied: they are kept as alerts.') }}</span>
      <button class="btn btn-primario separar" :disabled="ocupado || !aplicables" @click="aplicar"><Icono nombre="check" />{{ t('Apply {0} changes', [aplicables]) }}</button>
    </div>
  </template>
  <PerfilesImportacion v-if="verPerfiles" @cerrar="verPerfiles = false" @cambio="cargarPerfiles" />
</template>
