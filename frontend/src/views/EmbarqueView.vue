<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import { avisar, errorApi, guardando } from '../stores/ui'
import { ACCIONES, fmtFecha, fmtFechaHora, fmtFechaHoraLocal, fmtNum, plural } from '../utils'

const props = defineProps({ id: String })
const router = useRouter()
const e = ref(null)
const nuevaUnidad = reactive({ tipo: '40HC', numero: '' })
const evento = reactive({ tipo: 'SALIDA', fecha: '', ubicacion: '', observacion: '' })

const EVENTOS = [
  ['RECOLECCION', 'Recolección'],
  ['SALIDA', 'Salida'],
  ['TRANSITO', 'En tránsito'],
  ['ARRIBO', 'Arribo'],
  ['LIBERACION', 'Liberación'],
  ['ENTREGA', 'Entrega'],
  ['RECEPCION', 'Recepción en bodega'],
  ['OTRO', 'Otro'],
]
const nombreEvento = (t) => EVENTOS.find((x) => x[0] === t)?.[1] || t

const CAMPOS = [
  ['documento_numero', 'BL / AWB', 'text'],
  ['transportista', 'Naviera o transportista', 'text'],
  ['puerto_origen', 'Origen', 'text'],
  ['puerto_destino', 'Destino', 'text'],
  ['etd', 'ETD', 'date'],
  ['eta', 'ETA', 'date'],
]

async function cargar() {
  try {
    e.value = await api.get(`/embarques/${props.id}`)
  } catch (err) {
    errorApi(err)
    if (err.status === 404) router.push('/transporte')
  }
}

const guardar = (campo) => async (valor) => {
  try {
    await guardando(api.patch(`/embarques/${props.id}`, { [campo]: valor || null }))
    await cargar()
  } catch (err) {
    errorApi(err)
    throw err
  }
}

async function agregarUnidad() {
  try {
    const r = await api.post(`/embarques/${props.id}/unidades`, { tipo: nuevaUnidad.tipo, numero: nuevaUnidad.numero || null })
    avisar(`Unidad ${r.etiqueta} agregada.`)
    nuevaUnidad.numero = ''
    cargar()
  } catch (err) {
    errorApi(err)
  }
}

async function eliminarUnidad(u) {
  try {
    await api.del(`/unidades/${u.id}`)
    avisar(`Unidad ${u.nombre} eliminada.`)
    cargar()
  } catch (err) {
    errorApi(err)
  }
}

async function registrarEvento() {
  if (!evento.fecha) return avisar('Indica la fecha del evento.', 'error')
  try {
    const r = await api.post(`/embarques/${props.id}/eventos`, { ...evento, ubicacion: evento.ubicacion || null, observacion: evento.observacion || null })
    avisar(r.estado === e.value.estado ? 'Evento registrado.' : 'Evento registrado; el estado del embarque cambió.')
    Object.assign(evento, { fecha: '', ubicacion: '', observacion: '' })
    cargar()
  } catch (err) {
    errorApi(err)
  }
}

onMounted(cargar)
</script>

<template>
  <template v-if="e">
    <router-link to="/transporte" class="volver">Transporte</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ e.codigo }}</span>
        <EstadoBadge :estado="e.estado" />
        <span class="ayuda">{{ e.tipo_transporte.toLowerCase() }}{{ e.modalidad ? ` ${e.modalidad}` : '' }}</span>
      </div>
      <div class="rejilla-campos mt">
        <label v-for="[campo, texto, tipo] in CAMPOS" :key="campo" class="campo">
          <span>{{ texto }}</span>
          <CeldaEditable class="entrada" :tipo="tipo" :valor="e[campo]" :guardar="guardar(campo)" :etiqueta="texto" :vacia-texto="campo === 'documento_numero' ? 'Pendiente' : ''" />
        </label>
      </div>
      <div class="doc-meta">
        <span>Salida real <b>{{ fmtFecha(e.salida_real) }}</b></span>
        <span>Arribo real <b>{{ fmtFecha(e.arribo_real) }}</b></span>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza">
        <h2>Unidades de carga</h2>
        <form class="fila-flex" @submit.prevent="agregarUnidad">
          <select v-model="nuevaUnidad.tipo" class="entrada" aria-label="Tipo de unidad">
            <option v-for="t in e.tipos_unidad" :key="t" :value="t">{{ t }}</option>
          </select>
          <input v-model="nuevaUnidad.numero" class="entrada" placeholder="Número (opcional)" aria-label="Número de contenedor" />
          <button class="btn btn-primario" type="submit">Agregar unidad</button>
        </form>
      </div>
      <div class="unidades">
        <article v-for="u in e.unidades" :key="u.id" class="unidad">
          <div class="fila-flex">
            <span class="unidad-nombre">{{ u.nombre }}</span>
            <span class="etiqueta">{{ u.tipo }}</span>
            <span v-if="u.numero && u.numero !== u.etiqueta" class="ayuda">{{ u.etiqueta }}</span>
          </div>
          <div v-if="u.capacidad_cbm">
            <span class="ayuda">Volumen {{ fmtNum(u.cbm, 1) }} de {{ fmtNum(u.capacidad_cbm, 0) }} m³</span>
            <Avance :porcentaje="u.pct_cbm || 0" />
          </div>
          <div v-if="u.capacidad_kg">
            <span class="ayuda">Peso {{ fmtNum(u.peso_bruto, 0) }} de {{ fmtNum(u.capacidad_kg, 0) }} kg</span>
            <Avance :porcentaje="u.pct_kg || 0" />
          </div>
          <p v-if="!u.capacidad_cbm" class="ayuda">{{ fmtNum(u.cbm, 2) }} m³, {{ fmtNum(u.peso_bruto, 0) }} kg</p>
          <p>{{ plural(u.facturas, 'factura', 'facturas') }}, {{ u.packing_lists }} PL, {{ plural(u.cajas, 'caja', 'cajas') }}
            <span v-if="u.tentativas" class="etiqueta aviso">{{ u.tentativas }} tentativos</span>
          </p>
          <p v-if="u.proveedores.length" class="ayuda">{{ u.proveedores.join(', ') }}</p>
          <p v-for="a in u.alertas" :key="a" class="nota error">{{ a }}</p>
          <div class="fila-flex">
            <router-link class="btn btn-primario btn-chico" :to="`/transporte/unidades/${u.id}`">Asignar y ver carga</router-link>
            <button v-if="!u.packing_lists" class="btn btn-chico btn-peligro" @click="eliminarUnidad(u)">Eliminar</button>
          </div>
        </article>
        <p v-if="!e.unidades.length" class="ayuda">Aún no hay unidades. Agrega un contenedor, una guía aérea o un camión.</p>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><h2>Seguimiento</h2></div>
      <form class="rejilla-campos" @submit.prevent="registrarEvento">
        <label class="campo"><span>Evento</span>
          <select v-model="evento.tipo"><option v-for="[v, t] in EVENTOS" :key="v" :value="v">{{ t }}</option></select>
        </label>
        <label class="campo"><span>Fecha y hora</span><input v-model="evento.fecha" type="datetime-local" required /></label>
        <label class="campo"><span>Ubicación</span><input v-model="evento.ubicacion" /></label>
        <label class="campo"><span>Observación</span><input v-model="evento.observacion" /></label>
        <div class="campo" style="justify-content: flex-end"><button class="btn btn-primario" type="submit">Registrar evento</button></div>
      </form>
      <p class="ayuda mt">Para registrar la salida, todos los packing lists del embarque deben estar confirmados.</p>
      <ul class="linea-tiempo mt">
        <li v-for="ev in [...e.eventos].reverse()" :key="ev.id">
          <span class="ayuda">{{ fmtFechaHoraLocal(ev.fecha) }}</span>
          <span><b>{{ nombreEvento(ev.tipo) }}</b>{{ ev.ubicacion ? `, ${ev.ubicacion}` : '' }}<span v-if="ev.observacion" class="ayuda"> {{ ev.observacion }}</span></span>
        </li>
        <li v-if="!e.eventos.length"><span></span><span class="ayuda">Sin eventos todavía.</span></li>
      </ul>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><h2>Historial de cambios</h2></div>
      <ul class="linea-tiempo">
        <li v-for="(h, i) in e.historial" :key="i">
          <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<br />{{ h.usuario }}</span>
          <span>
            <b>{{ ACCIONES[h.accion] || h.accion }}</b>
            <span class="ayuda" style="margin-left: 6px">{{ h.detalle ? Object.entries(h.detalle).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? `${v[0] ?? '—'} a ${v[1] ?? '—'}` : v}`).join(', ') : '' }}</span>
            <div v-if="h.motivo">Motivo: {{ h.motivo }}</div>
          </span>
        </li>
      </ul>
    </section>
  </template>
</template>
