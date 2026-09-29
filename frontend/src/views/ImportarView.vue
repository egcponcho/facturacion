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
  nuevo: ['Nuevas', 'ok', 'Se crean'],
  cambio: ['Con cambios', 'info', 'Se actualizan'],
  sin_cambio: ['Sin cambios', 'neutro', 'No se tocan'],
  conflicto: ['Conflictos', 'aviso', 'Quedan como alerta'],
  error: ['Con errores', 'error', 'No se aplican'],
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
      (r.resumen.conflicto ? ` ${r.resumen.conflicto} conflictos quedaron como alertas en el inicio.` : ''))
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
      <router-link to="/ordenes" class="volver"><Icono nombre="atras" :tam="15" />Órdenes de compra</router-link>
      <h1>Importar órdenes de compra</h1>
      <p>Sube el Excel o CSV exportado de SAP. Cada fila se valida contra los datos maestros (artículos, sociedades, centros, destinos y puertos); nada se guarda hasta que confirmes.</p>
    </div>
    <a class="btn" href="/plantilla_oc.csv" download><Icono nombre="descargar" />Formato de ejemplo</a>
  </div>

  <div class="dos-columnas" style="grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr)">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>1. Elige el archivo</h2><p>Una fila por posición de OC.</p></div></div>
      <CargaArchivo v-model="archivo" texto="Arrastra aquí el archivo de OCs o elígelo" ayuda="Excel (.xlsx) o CSV, exportado de SAP" />
      <div class="fila-flex mt">
        <button class="btn btn-primario" :disabled="!archivo || ocupado" @click="revisar"><Icono nombre="lupa" :tam="16" />{{ ocupado ? 'Revisando…' : 'Revisar archivo' }}</button>
        <span class="ayuda">Los códigos (OC, posición, SKU) se leen como texto para no perder ceros iniciales.</span>
      </div>
    </section>
    <section class="panel">
      <div class="panel-cabeza"><div><h2>Qué se valida</h2></div></div>
      <ul class="lista-mensajes ayuda">
        <li>OC con formato 44 + 8 dígitos y posiciones de 10 en 10.</li>
        <li>El SKU debe existir en el maestro de artículos; de ahí salen estilo, color, talla, marca, grupo y casepack (el casepack de la OC manda si viene).</li>
        <li>Sociedad, centro y almacén deben corresponder entre sí.</li>
        <li>País de destino (4 dígitos), puerto y países registrados en Mantenimiento.</li>
        <li>Liberación comercial P deja la OC en 304; C o vacío la libera (300, o 301 si ya estaba liberada y cambió).</li>
      </ul>
    </section>
  </div>

  <template v-if="previa">
    <h2 class="mt">2. Revisa el resultado</h2>
    <p class="ayuda" style="margin-bottom: 12px">{{ previa.archivo }} · {{ previa.resumen.total }} filas. Haz clic en un grupo para filtrar.</p>
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
            <ThOrden campo="fila" :orden="tabla.estado.orden" num @ordenar="tabla.ordenar">Fila</ThOrden>
            <ThOrden campo="clave" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Posición</ThOrden>
            <ThOrden campo="estado" :orden="tabla.estado.orden" @ordenar="tabla.ordenar">Resultado</ThOrden>
            <th>Detalle</th>
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
          <tr v-if="!tabla.total.value"><td colspan="4" class="vacio">No hay filas en este grupo.</td></tr>
        </tbody>
      </table>
    </div>
    <Paginacion :page="tabla.estado.pagina" :size="tabla.estado.porPagina" :total="tabla.total.value"
                @cambiar="(p) => (tabla.estado.pagina = p)" @tamano="(t) => (tabla.estado.porPagina = t)" />
    <div class="fila-flex mt">
      <span class="ayuda">Los conflictos (por ejemplo, bajar la cantidad por debajo de lo ya facturado) no se aplican: quedan como alertas.</span>
      <button class="btn btn-primario separar" :disabled="ocupado || !aplicables" @click="aplicar"><Icono nombre="check" />Aplicar {{ aplicables }} cambios</button>
    </div>
  </template>
</template>
