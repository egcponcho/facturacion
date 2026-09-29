<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { siguienteOrden } from '../composables/useTabla'
import { esInterno, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'
import { fmtFecha, fmtMoneda, fmtNum } from '../utils'
import Avance from './Avance.vue'
import EstadoBadge from './EstadoBadge.vue'
import Icono from './Icono.vue'
import Paginacion from './Paginacion.vue'
import SelectBusqueda from './SelectBusqueda.vue'
import ThOrden from './ThOrden.vue'

// Seguimiento de facturación y empaque: una fila por packing list (o por
// factura sin PL), con el paso en que va y lo que le falta.
const filtros = reactive({
  q: '', etapa: '', estado_factura: '', estado_pl: '', sociedad: '', centro: '', embarque_id: '', proveedor: '',
  con_pendientes: false, orden: 'dias:desc', page: 1, size: 25,
})
const datos = ref({ items: [], total: 0, etapas: [], opciones: {} })
const cargando = ref(true)

const TONO = {
  FACTURA_ABIERTA: 'aviso', EMPACANDO: 'aviso', POR_FINALIZAR_PL: 'info', POR_FINALIZAR_FACTURA: 'info',
  LISTO_EMBARQUE: 'ok', TENTATIVO: 'aviso', EN_CONTENEDOR: 'acento', EN_CAMINO: 'info', RECIBIDO: 'ok',
}
const nombreEtapa = computed(() => Object.fromEntries(datos.value.etapas.map((e) => [e.clave, e.nombre])))

async function cargar() {
  cargando.value = true
  try {
    const params = { proveedor_id: sesion.proveedorId || undefined }
    for (const [k, v] of Object.entries(filtros)) if (v !== '' && v !== false) params[k] = v
    datos.value = await api.get('/seguimiento/documentos', params)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function aplicar() {
  filtros.page = 1
  cargar()
}
function ordenar(campo) {
  filtros.orden = siguienteOrden(filtros.orden, campo)
  aplicar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(aplicar, 300)
}
watch(() => sesion.proveedorId, aplicar)
onMounted(cargar)
</script>

<template>
  <div class="etapas" role="group" aria-label="Filtrar por paso">
    <button v-for="e in datos.etapas" :key="e.clave" type="button" class="etapa" :aria-pressed="filtros.etapa === e.clave"
            @click="filtros.etapa = filtros.etapa === e.clave ? '' : e.clave; aplicar()">
      <span class="etapa-titulo">{{ e.nombre }}</span>
      <b>{{ fmtNum(e.total) }}</b>
    </button>
  </div>

  <div class="filtros">
    <label class="buscador">
      <Icono nombre="buscar" :tam="16" />
      <input v-model="filtros.q" type="search" placeholder="Factura, PL, OC o contenedor" aria-label="Buscar" @input="buscar" />
    </label>
    <SelectBusqueda v-if="esInterno()" v-model="filtros.proveedor" :opciones="datos.opciones.proveedores || []" vacio="Proveedor: todos" etiqueta="Proveedor" @change="aplicar" />
    <SelectBusqueda v-model="filtros.sociedad" :opciones="datos.opciones.sociedades || []" vacio="Facturar a: todas" etiqueta="Sociedad" @change="aplicar" />
    <SelectBusqueda v-model="filtros.centro" :opciones="datos.opciones.centros || []" vacio="Centro: todos" etiqueta="Centro" @change="aplicar" />
    <select v-model="filtros.estado_factura" aria-label="Estado de la factura" @change="aplicar">
      <option value="">Factura: todas</option><option value="BORRADOR">Borrador</option>
      <option value="EN_CORRECCION">En corrección</option><option value="FINALIZADA">Finalizada</option>
    </select>
    <select v-model="filtros.estado_pl" aria-label="Estado del packing list" @change="aplicar">
      <option value="">Packing list: todos</option><option value="BORRADOR">Borrador</option>
      <option value="EN_CORRECCION">En corrección</option><option value="FINALIZADO">Finalizado</option>
    </select>
    <SelectBusqueda v-model="filtros.embarque_id" :opciones="(datos.opciones.embarques || []).map((e) => ({ valor: String(e.id), texto: e.codigo }))"
                    vacio="Embarque: todos" etiqueta="Embarque" @change="aplicar" />
    <label class="check"><input v-model="filtros.con_pendientes" type="checkbox" @change="aplicar" /> Solo con datos pendientes</label>
  </div>

  <div class="tabla-marco tabla-fija">
    <table class="tabla">
      <thead>
        <tr>
          <ThOrden campo="factura" :orden="filtros.orden" @ordenar="ordenar">Factura</ThOrden>
          <ThOrden v-if="!sesion.proveedorId" campo="proveedor" :orden="filtros.orden" @ordenar="ordenar">Proveedor</ThOrden>
          <ThOrden campo="centro" :orden="filtros.orden" @ordenar="ordenar">Facturar a / notify</ThOrden>
          <ThOrden campo="estado_factura" :orden="filtros.orden" @ordenar="ordenar">Factura</ThOrden>
          <ThOrden campo="estado_pl" :orden="filtros.orden" @ordenar="ordenar">Packing list</ThOrden>
          <ThOrden campo="avance" :orden="filtros.orden" @ordenar="ordenar">Empacado</ThOrden>
          <ThOrden campo="cajas" :orden="filtros.orden" num @ordenar="ordenar">Cajas</ThOrden>
          <ThOrden campo="peso_bruto" :orden="filtros.orden" num @ordenar="ordenar">Bruto kg</ThOrden>
          <ThOrden campo="cbm" :orden="filtros.orden" num @ordenar="ordenar">m³</ThOrden>
          <ThOrden campo="pendientes" :orden="filtros.orden" num @ordenar="ordenar">Pendientes</ThOrden>
          <ThOrden campo="etapa" :orden="filtros.orden" @ordenar="ordenar">Paso</ThOrden>
          <ThOrden campo="embarque" :orden="filtros.orden" @ordenar="ordenar">Contenedor</ThOrden>
          <ThOrden campo="dias" :orden="filtros.orden" num @ordenar="ordenar">Días</ThOrden>
        </tr>
      </thead>
      <tbody>
        <tr v-if="cargando && !datos.items.length"><td colspan="13" class="vacio">Cargando…</td></tr>
        <tr v-else-if="!datos.items.length"><td colspan="13" class="vacio">No hay documentos con esos filtros.</td></tr>
        <tr v-for="f in datos.items" :key="`${f.factura_id}-${f.pl_id}`">
          <td>
            <router-link :to="`/facturas/${f.factura_id}`" class="fuerte">{{ f.factura }}</router-link>
            <span class="sub codigo">{{ f.ocs.join(', ') }}</span>
          </td>
          <td v-if="!sesion.proveedorId">{{ f.proveedor }}</td>
          <td><span class="codigo">{{ f.sociedad }} · {{ f.centro || '—' }}</span><span class="sub">destino {{ f.centro_destino || '—' }} · {{ fmtMoneda(f.importe, f.moneda) }}</span></td>
          <td><EstadoBadge :estado="f.estado_factura" /><span v-if="f.pendientes_factura" class="sub">{{ f.pendientes_factura }} datos por completar</span></td>
          <td>
            <template v-if="f.pl_id">
              <router-link :to="`/packing-lists/${f.pl_id}`" class="cajas-rango">{{ f.pl }}</router-link> <EstadoBadge :estado="f.estado_pl" />
            </template>
            <span v-else class="ayuda">Sin packing list</span>
          </td>
          <td style="min-width: 120px"><Avance v-if="f.pl_id" :porcentaje="f.avance" /><span v-else class="ayuda">—</span></td>
          <td class="num">{{ fmtNum(f.cajas) }}<span v-if="f.pallets" class="sub">{{ f.pallets }} pallets</span></td>
          <td class="num">{{ fmtNum(f.peso_bruto, 1) }}</td>
          <td class="num">{{ fmtNum(f.cbm, 2) }}</td>
          <td class="num"><span v-if="f.pendientes" class="etiqueta aviso">{{ f.pendientes }}</span><span v-else class="ayuda">0</span></td>
          <td><span class="etiqueta" :class="TONO[f.etapa]" style="margin-left: 0">{{ nombreEtapa[f.etapa] || f.etapa }}</span></td>
          <td>
            <template v-if="f.embarque_id">
              <span class="codigo">{{ f.contenedor }}</span>
              <span class="sub">
                <router-link v-if="esInterno()" :to="`/transporte/embarques/${f.embarque_id}`">{{ f.embarque }}</router-link><template v-else>{{ f.embarque }}</template>
                · ETA {{ fmtFecha(f.eta) }}
              </span>
            </template>
            <span v-else class="ayuda">—</span>
          </td>
          <td class="num">{{ f.dias ?? '—' }}<span class="sub">{{ fmtFecha(f.fecha) }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
  <Paginacion :page="filtros.page" :size="filtros.size" :total="datos.total"
              @cambiar="(p) => { filtros.page = p; cargar() }" @tamano="(t) => (filtros.size = t)" />
</template>
