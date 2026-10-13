<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import NavComercial from '@/modulos/comercial/componentes/NavComercial.vue'
import { opcionesLista } from '@/nucleo/listas.js'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtFecha, fmtMoneda } from '@/nucleo/utils'
import Seleccion from '@/componentes/Seleccion.vue'

// Cobros (de clientes) y pagos (a proveedores). Un pago se reparte entre los
// documentos con saldo del tercero; lo que no se aplica queda a su favor.
const tabla = ref(null)
const filtros = reactive({ direccion: '', q: '' })
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const op = ref(null)
const modal = ref(null)
const ocupado = ref(false)

const DIRECCIONES = [['', t('All')], ['COBRO', t('Collections')], ['PAGO', t('Payments')]]
const columnas = [
  { clave: 'fecha', texto: t('Date'), fija: true, prioridad: 1, textoValor: (v) => fmtFecha(v) },
  { clave: 'direccion', texto: t('Kind'), prioridad: 2, opciones: [['COBRO', t('Collection')], ['PAGO', t('Payment')]] },
  { clave: 'tercero', texto: t('Business partner'), prioridad: 1 },
  { clave: 'sociedad', texto: t('Company'), prioridad: 3, inicial: false },
  { clave: 'importe', texto: t('Amount'), num: true, prioridad: 1, filtro: false },
  { clave: 'sin_aplicar', texto: t('Not applied'), num: true, prioridad: 2, ordenable: false, filtro: false },
  { clave: 'metodo', texto: t('Method'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'referencia', texto: t('Reference'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'estado', texto: t('Status'), prioridad: 2, opciones: [['REGISTRADO', t('Registered')], ['ANULADO', t('Voided')]] },
]
const externosApi = () => ({ direccion: filtros.direccion || undefined, q: filtros.q || undefined })
const valores = (columna, buscar, otros) => api.get('/pagos/valores', { columna, buscar, f: JSON.stringify(otros), ...externosApi() })

let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/pagos', { ...externosApi(), orden: c.orden, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}

// ---- Registrar un pago y repartirlo ----
const hoy = () => new Date().toISOString().slice(0, 10)
async function nuevo(direccion) {
  try {
    op.value = op.value || await api.get('/comercial/opciones')
  } catch (e) {
    errorApi(e)
    return
  }
  modal.value = { direccion, tercero_id: null, sociedad: op.value.sociedades[0]?.codigo || '', fecha: hoy(), moneda: op.value.sociedades[0]?.moneda || '',
    importe: '', metodo_pago: op.value.metodos_pago[0]?.codigo || '', referencia: '', abiertos: [], aplicar: {} }
}
async function buscarTerceros(texto) {
  const r = await api.get('/terceros', { q: texto || undefined, rol: modal.value.direccion === 'COBRO' ? 'CLIENTE' : undefined, size: 30 })
  return r.items.map((x) => ({ valor: x.id, texto: x.nombre, sub: [x.codigo, x.id_fiscal].filter(Boolean).join(' · ') }))
}
async function alElegirTercero() {
  if (!modal.value.tercero_id) return
  try {
    const r = await api.get(`/terceros/${modal.value.tercero_id}/estado-cuenta`, { direccion: modal.value.direccion === 'COBRO' ? 'EMITIDO' : 'RECIBIDO' })
    modal.value.abiertos = r.documentos.filter((x) => x.signo > 0)
    modal.value.aplicar = {}
  } catch (e) {
    errorApi(e)
  }
}
const abiertosMoneda = computed(() => (modal.value?.abiertos || []).filter((x) => x.moneda === modal.value.moneda && x.sociedad === modal.value.sociedad))
const aplicado = computed(() => Object.values(modal.value?.aplicar || {}).reduce((s, v) => s + (Number(v) || 0), 0))
function repartir() {
  // Llena de la más antigua a la más reciente hasta agotar el importe
  let resto = Number(modal.value.importe) || 0
  const aplicar = {}
  for (const x of abiertosMoneda.value) {
    const v = Math.min(resto, x.saldo)
    if (v > 0) aplicar[x.id] = Math.round(v * 10000) / 10000
    resto -= v
  }
  modal.value.aplicar = aplicar
}
async function registrar() {
  ocupado.value = true
  try {
    await api.post('/pagos', {
      direccion: modal.value.direccion, tercero_id: modal.value.tercero_id, sociedad: modal.value.sociedad, fecha: modal.value.fecha,
      moneda: modal.value.moneda, importe: Number(modal.value.importe), metodo_pago: modal.value.metodo_pago || null,
      referencia: modal.value.referencia || null,
      aplicaciones: Object.entries(modal.value.aplicar).filter(([, v]) => Number(v) > 0).map(([id, v]) => ({ documento_id: Number(id), importe: Number(v) })),
    })
    avisar(modal.value.direccion === 'COBRO' ? t('Collection registered.') : t('Payment registered.'))
    modal.value = null
    recargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const anulando = ref(null) // { pago, motivo }
async function anular() {
  ocupado.value = true
  try {
    await api.post(`/pagos/${anulando.value.pago.id}/anular`, { motivo: anulando.value.motivo })
    avisar(t('Payment voided.'))
    anulando.value = null
    consultar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Collections and payments') }}</h1>
      <p>{{ t('What customers paid you and what you paid suppliers, and the documents each one settles.') }}</p>
    </div>
    <div v-if="puede('comercial.pagos')" class="acciones">
      <button class="btn" @click="nuevo('PAGO')"><Icono nombre="moneda" />{{ t('Register payment') }}</button>
      <button class="btn btn-primario" @click="nuevo('COBRO')"><Icono nombre="moneda" />{{ t('Register collection') }}</button>
    </div>
  </div>
  <NavComercial />

  <TablaDatos ref="tabla" tabla="pagos" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              :etiqueta="t('Collections and payments')" :valores="valores" :externos="{ direccion: filtros.direccion, q: filtros.q }"
              :clase-fila="(p) => ({ apagado: p.estado === 'ANULADO' })" @consulta="consultar">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search reference or business partner')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <div class="segmentos" role="group" :aria-label="t('Kind')">
        <button v-for="[v, txt] in DIRECCIONES" :key="v" class="segmento" type="button" :aria-pressed="filtros.direccion === v" @click="filtros.direccion = v; recargar()">{{ tx(txt) }}</button>
      </div>
    </template>
    <template #celda-fecha="{ fila: p }">{{ fmtFecha(p.fecha) }}</template>
    <template #celda-direccion="{ fila: p }"><span class="etiqueta ms-0" :class="p.direccion === 'COBRO' ? 'ok' : 'info'">{{ tx(p.direccion === 'COBRO' ? t('Collection') : t('Payment')) }}</span></template>
    <template #celda-tercero="{ fila: p }">{{ tx(p.tercero) }}</template>
    <template #celda-importe="{ fila: p }"><span class="fuerte">{{ fmtMoneda(p.importe, p.moneda) }}</span></template>
    <template #celda-sin_aplicar="{ fila: p }">{{ p.sin_aplicar ? fmtMoneda(p.sin_aplicar, p.moneda) : '—' }}</template>
    <template #celda-metodo="{ fila: p }">{{ tx(p.metodo_pago_nombre || '—') }}</template>
    <template #celda-referencia="{ fila: p }">{{ tx(p.referencia || '—') }}</template>
    <template #celda-estado="{ fila: p }"><EstadoBadge :estado="p.estado" tipo="pago" /></template>
    <template #acciones="{ fila: p }">
      <button v-if="puede('comercial.pagos') && p.estado === 'REGISTRADO'" class="btn btn-chico" @click.stop="anulando = { pago: p, motivo: '' }">{{ t('Void') }}</button>
    </template>
    <template #vacio>{{ t('No collections or payments yet.') }}</template>
  </TablaDatos>

  <Modal v-if="modal" :titulo="modal.direccion === 'COBRO' ? t('Register collection') : t('Register payment')" ancho="760px" @cerrar="modal = null">
    <div class="rejilla-formulario">
      <label class="campo col-2"><span class="req">{{ modal.direccion === 'COBRO' ? t('Customer') : t('Supplier') }}</span>
        <SelectBusqueda v-model="modal.tercero_id" :buscar="buscarTerceros" :prefijo="false" :etiqueta="t('Business partner')" @change="alElegirTercero" />
      </label>
      <label class="campo"><span class="req">{{ t('Company') }}</span>
        <Seleccion v-model="modal.sociedad" class="entrada"><option v-for="s in op.sociedades" :key="s.codigo" :value="s.codigo">{{ s.codigo }} · {{ tx(s.nombre) }}</option></Seleccion>
      </label>
      <label class="campo"><span class="req">{{ t('Currency') }}</span>
        <Seleccion v-model="modal.moneda" class="entrada"><option v-for="[c] in opcionesLista('moneda')" :key="c" :value="c">{{ c }}</option></Seleccion>
      </label>
      <label class="campo"><span class="req">{{ t('Amount') }}</span><input v-model="modal.importe" type="number" min="0.01" step="any" class="entrada" /></label>
      <label class="campo"><span class="req">{{ t('Date') }}</span><CampoFecha v-model="modal.fecha" /></label>
      <label class="campo"><span>{{ t('Payment method') }}</span>
        <Seleccion v-model="modal.metodo_pago" class="entrada"><option v-for="m in op.metodos_pago" :key="m.codigo" :value="m.codigo">{{ tx(m.nombre) }}</option></Seleccion>
      </label>
      <label class="campo"><span>{{ t('Reference') }}</span><input v-model="modal.referencia" class="entrada" maxlength="80" /></label>
    </div>
    <div v-if="modal.tercero_id" class="mt">
      <div class="fila-flex"><b>{{ t('Documents with balance') }}</b>
        <button type="button" class="btn btn-chico" :disabled="!abiertosMoneda.length || !modal.importe" @click="repartir">{{ t('Apply oldest first') }}</button>
      </div>
      <div v-if="abiertosMoneda.length" class="tabla-marco tabla-captura mt">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Document') }}</th><th>{{ t('Due date') }}</th><th class="num">{{ t('Balance') }}</th><th class="num">{{ t('Apply') }}</th></tr></thead>
          <tbody>
            <tr v-for="x in abiertosMoneda" :key="x.id">
              <td>{{ tx(x.nombre) }} <span class="sub">{{ tx(x.tipo_nombre) }}</span></td>
              <td>{{ fmtFecha(x.fecha_vencimiento) }} <EstadoBadge v-if="x.estado_cobro === 'VENCIDO'" estado="VENCIDO" tipo="cobro" /></td>
              <td class="num">{{ fmtMoneda(x.saldo, x.moneda) }}</td>
              <td class="num"><input v-model="modal.aplicar[x.id]" type="number" min="0" :max="x.saldo" step="any" class="entrada num ancho-m" :aria-label="t('Apply')" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="ayuda">{{ t('This business partner has no documents with balance in this company and currency: the amount stays in its favor.') }}</p>
      <p class="ayuda">{{ t('Applied {0} of {1}; the rest stays in favor of the business partner.', [fmtMoneda(aplicado, modal.moneda), fmtMoneda(Number(modal.importe) || 0, modal.moneda)]) }}</p>
    </div>
    <template #pie>
      <button class="btn" @click="modal = null">{{ t('Cancel') }}</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.tercero_id || !(Number(modal.importe) > 0) || aplicado > Number(modal.importe) + 1e-9" @click="registrar">{{ t('Register') }}</button>
    </template>
  </Modal>
  <Modal v-if="anulando" :titulo="t('Void the payment')" @cerrar="anulando = null">
    <p>{{ t('The documents it settled get their balance back.') }}</p>
    <label class="campo"><span class="req">{{ t('Reason') }}</span><input v-model="anulando.motivo" class="entrada" maxlength="500" /></label>
    <template #pie>
      <button class="btn" @click="anulando = null">{{ t('Cancel') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado || !anulando.motivo.trim()" @click="anular">{{ t('Void') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.rejilla-formulario { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
</style>
