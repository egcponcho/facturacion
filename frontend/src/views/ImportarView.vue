<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { avisar, errorApi } from '../stores/ui'

const archivo = ref(null)
const previa = ref(null)
const filtro = ref('')
const ocupado = ref(false)

const ESTADOS = {
  nuevo: ['Nuevas', 'ok'],
  cambio: ['Con cambios', 'aviso'],
  sin_cambio: ['Sin cambios', ''],
  conflicto: ['Conflictos', 'error'],
  error: ['Con errores', 'error'],
}
const filas = computed(() => (previa.value?.filas || []).filter((f) => !filtro.value || f.estado === filtro.value))
const aplicables = computed(() => (previa.value?.resumen.nuevo || 0) + (previa.value?.resumen.cambio || 0))

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
    if (e.detalle?.encontradas) avisar(`Columnas encontradas: ${e.detalle.encontradas.join(', ')}`, 'error', null, 12000)
  } finally {
    ocupado.value = false
  }
}

async function aplicar() {
  ocupado.value = true
  try {
    const r = await api.post(`/ordenes/importar/${previa.value.importacion_id}/aplicar`)
    avisar(`Importación aplicada: ${r.aplicadas} posiciones creadas o actualizadas.` +
      (r.resumen.conflicto ? ` ${r.resumen.conflicto} conflictos quedaron como alertas en Pendientes.` : ''))
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
      <h1>Importar órdenes de compra</h1>
      <p>Sube el Excel o CSV exportado de SAP. Primero verás qué se crea, qué cambia y qué no se puede aplicar; nada se guarda hasta que confirmes.</p>
    </div>
    <a class="btn" href="/plantilla_oc.csv" download>Descargar formato de ejemplo</a>
  </div>

  <section class="panel">
    <div class="fila-flex">
      <input type="file" accept=".xlsx,.xlsm,.csv" aria-label="Archivo de OCs" @change="archivo = $event.target.files[0]; previa = null" />
      <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="revisar">Revisar archivo</button>
    </div>
    <p class="ayuda mt">Los códigos SAP, UPC, OC y posición se leen como texto para conservar ceros iniciales. Si en Excel ya se perdieron, formatea esas columnas como texto antes de exportar.</p>
  </section>

  <template v-if="previa">
    <div class="tarjetas mt">
      <button v-for="(info, clave) in ESTADOS" :key="clave" type="button" class="tarjeta"
        :class="[filtro === clave ? 'tono-normal' : '', info[1] === 'error' && previa.resumen[clave] ? 'tono-alerta' : '']"
        @click="filtro = filtro === clave ? '' : clave">
        <span class="valor">{{ previa.resumen[clave] }}</span>
        <span class="titulo">{{ info[0] }}</span>
      </button>
    </div>
    <div class="tabla-marco mt">
      <table class="tabla">
        <thead><tr><th class="num">Fila</th><th>Posición</th><th>Resultado</th><th>Detalle</th></tr></thead>
        <tbody>
          <tr v-for="f in filas.slice(0, 500)" :key="f.fila">
            <td class="num">{{ f.fila }}</td>
            <td class="codigo">{{ f.clave }}</td>
            <td><span class="etiqueta" :class="ESTADOS[f.estado][1]">{{ ESTADOS[f.estado][0] }}</span></td>
            <td>
              <div v-for="m in f.mensajes" :key="m">{{ m }}</div>
              <div v-for="(c, campo) in f.cambios" :key="campo" class="ayuda">{{ campo.replaceAll('_', ' ') }}: {{ valorTxt(c.antes) }} a {{ valorTxt(c.despues) }}</div>
            </td>
          </tr>
          <tr v-if="!filas.length"><td colspan="4" class="vacio">No hay filas en este grupo.</td></tr>
        </tbody>
      </table>
    </div>
    <div class="fila-flex mt">
      <span class="ayuda">Los conflictos (por ejemplo, bajar la cantidad por debajo de lo ya facturado) no se aplican: quedan como alertas.</span>
      <button class="btn btn-primario separar" :disabled="ocupado || !aplicables" @click="aplicar">Aplicar {{ aplicables }} cambios</button>
    </div>
  </template>
</template>
