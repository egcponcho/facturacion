<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import Avance from '../components/Avance.vue'
import BarraSeleccion from '../components/BarraSeleccion.vue'
import CeldaEditable from '../components/CeldaEditable.vue'
import EstadoBadge from '../components/EstadoBadge.vue'
import Modal from '../components/Modal.vue'
import { sesion } from '../stores/sesion'
import { avisar, errorApi, guardando } from '../stores/ui'
import { fmtNum, plural, porUnidadTxt, useSeleccion } from '../utils'

const props = defineProps({ id: String })
const router = useRouter()
const u = ref(null)
const disponibles = ref([])
const filtros = reactive({ q: '', solo_listos: false })
const selA = useSeleccion()
const selD = useSeleccion()
const abiertas = reactive(new Set())
const modal = ref(null)
const ocupado = ref(false)

const todosDisponibles = computed(() => disponibles.value.flatMap((g) => g.packing_lists))
const suma = (pls) => pls.reduce((a, p) => ({ cajas: a.cajas + p.cajas, cbm: a.cbm + p.cbm, kg: a.kg + p.peso_bruto }), { cajas: 0, cbm: 0, kg: 0 })
const selAsignados = computed(() => (u.value?.asignados || []).filter((p) => selA.tiene(p.id)))
const selDisponibles = computed(() => todosDisponibles.value.filter((p) => selD.tiene(p.id)))
const totSelA = computed(() => suma(selAsignados.value))
const totSelD = computed(() => suma(selDisponibles.value))
const proyeccion = computed(() => {
  if (!u.value?.capacidad_cbm) return null
  const cbm = u.value.cbm + totSelD.value.cbm
  return { cbm, pct: (cbm * 100) / u.value.capacidad_cbm }
})

async function cargarDisponibles() {
  try {
    disponibles.value = await api.get(`/unidades/${props.id}/disponibles`, { proveedor_id: sesion.proveedorId, ...filtros })
    selD.podar(todosDisponibles.value.map((p) => p.id))
  } catch (e) {
    errorApi(e)
  }
}

async function cargar() {
  try {
    u.value = await api.get(`/unidades/${props.id}`)
    selA.podar(u.value.asignados.map((p) => p.id))
    await cargarDisponibles()
  } catch (e) {
    errorApi(e)
    if (e.status === 404) router.push('/transporte')
  }
}

const guardar = (campo) => async (valor) => {
  try {
    await guardando(api.patch(`/unidades/${props.id}`, { [campo]: valor || null }))
    await cargar()
  } catch (e) {
    errorApi(e)
    throw e
  }
}

async function ejecutar(fn, exito) {
  ocupado.value = true
  try {
    await guardando(fn())
    avisar(exito)
    modal.value = null
    selA.limpiar()
    selD.limpiar()
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}

function asignar(modo) {
  if (u.value.embarque.salio) {
    modal.value = { tipo: 'asignar', modo, motivo: '' }
    return
  }
  const n = selD.ids.size
  ejecutar(() => api.post(`/unidades/${props.id}/asignar`, { pl_ids: selD.lista(), modo }),
    `${plural(n, 'packing list asignado', 'packing lists asignados')} como ${modo === 'CONFIRMADA' ? 'confirmado' : 'tentativo'}${n === 1 ? '' : 's'}.`)
}

function asignarConMotivo() {
  const { modo, motivo } = modal.value
  ejecutar(() => api.post(`/unidades/${props.id}/asignar`, { pl_ids: selD.lista(), modo, motivo }), 'Packing lists asignados.')
}

function confirmar() {
  ejecutar(() => api.post(`/unidades/${props.id}/confirmar`, { pl_ids: selA.lista() }), `${plural(selA.ids.size, 'packing list confirmado', 'packing lists confirmados')}.`)
}

function quitar() {
  ejecutar(() => api.post(`/unidades/${props.id}/desasignar`, { pl_ids: selA.lista(), motivo: modal.value.motivo || null }),
    'Packing lists quitados de la unidad.')
}

function mover() {
  const { destino, modo, motivo } = modal.value
  ejecutar(() => api.post(`/unidades/${destino}/asignar`, { pl_ids: selA.lista(), modo, motivo: motivo || null }),
    'Packing lists movidos a la otra unidad.')
}

const requiereMotivo = computed(() => u.value?.embarque.salio || selAsignados.value.some((p) => p.asignacion === 'CONFIRMADA'))

function alternarAbierta(id) {
  if (abiertas.has(id)) abiertas.delete(id)
  else abiertas.add(id)
}

let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(cargarDisponibles, 300)
}

onMounted(cargar)
watch(() => sesion.proveedorId, cargarDisponibles)
</script>

<template>
  <template v-if="u">
    <router-link :to="`/transporte/embarques/${u.embarque.id}`" class="volver">Embarque {{ u.embarque.codigo }}</router-link>
    <section class="doc-cabeza">
      <div class="doc-fila">
        <span class="doc-numero">{{ u.nombre }}</span>
        <span class="etiqueta">{{ u.tipo }}</span>
        <EstadoBadge :estado="u.embarque.estado" />
        <span class="ayuda">{{ u.embarque.puerto_origen || '—' }} a {{ u.embarque.puerto_destino || '—' }}</span>
      </div>
      <div class="rejilla-campos mt">
        <label class="campo"><span>Número de contenedor o guía</span>
          <CeldaEditable class="entrada" :valor="u.numero" :guardar="guardar('numero')" etiqueta="Número" :vacia-texto="u.etiqueta" />
        </label>
        <label class="campo"><span>Sello</span>
          <CeldaEditable class="entrada" :valor="u.sello" :guardar="guardar('sello')" etiqueta="Sello" />
        </label>
      </div>
      <div class="progresos">
        <div class="progreso">
          <h3>Volumen</h3>
          <template v-if="u.capacidad_cbm">
            <Avance :porcentaje="u.pct_cbm || 0" />
            <p class="ayuda">{{ fmtNum(u.cbm, 2) }} de {{ fmtNum(u.capacidad_cbm, 0) }} m³</p>
            <p v-if="proyeccion && selD.ids.size" class="ayuda">Con la selección: {{ fmtNum(proyeccion.cbm, 2) }} m³ ({{ Math.round(proyeccion.pct) }}%)</p>
          </template>
          <p v-else>{{ fmtNum(u.cbm, 2) }} m³</p>
        </div>
        <div class="progreso">
          <h3>Peso bruto</h3>
          <template v-if="u.capacidad_kg">
            <Avance :porcentaje="u.pct_kg || 0" />
            <p class="ayuda">{{ fmtNum(u.peso_bruto, 0) }} de {{ fmtNum(u.capacidad_kg, 0) }} kg</p>
          </template>
          <p v-else>{{ fmtNum(u.peso_bruto, 0) }} kg</p>
        </div>
        <div class="progreso">
          <h3>Carga</h3>
          <p>{{ plural(u.facturas, 'factura', 'facturas') }}, {{ u.packing_lists }} PL, {{ plural(u.cajas, 'caja', 'cajas') }}</p>
          <p v-if="u.tentativas" class="ayuda">{{ u.tentativas }} asignaciones tentativas por confirmar.</p>
        </div>
      </div>
      <p v-for="a in u.alertas" :key="a" class="nota error mt">{{ a }}</p>
      <p v-if="u.embarque.salio" class="nota aviso mt">El embarque ya salió: cualquier cambio de carga pide un motivo y queda en el historial.</p>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><h2>En esta unidad</h2></div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todos los asignados" :checked="selA.todos(u.asignados.map((p) => p.id))" @change="selA.alternarTodos(u.asignados.map((p) => p.id))" /></th>
              <th>Factura</th>
              <th>Proveedor</th>
              <th>Packing list</th>
              <th>Estado</th>
              <th>Asignación</th>
              <th>Contenido</th>
              <th class="num">Cajas</th>
              <th class="num">Bruto kg</th>
              <th class="num">CBM</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in u.asignados" :key="p.id" :class="{ seleccionada: selA.tiene(p.id) }">
              <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${p.factura} ${p.numero}`" :checked="selA.tiene(p.id)" @change="selA.alternar(p.id)" /></td>
              <td><router-link :to="`/facturas/${p.factura_id}`">{{ p.factura }}</router-link></td>
              <td>{{ p.proveedor }}</td>
              <td><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango">{{ p.numero }}</router-link></td>
              <td><EstadoBadge :estado="p.estado" /></td>
              <td>
                <EstadoBadge :estado="p.asignacion" />
                <div v-if="p.asignacion === 'TENTATIVA' && !p.puede_confirmar" class="ayuda">{{ p.motivo_no_confirmable }}</div>
              </td>
              <td>{{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
              <td class="num">{{ fmtNum(p.cajas) }}</td>
              <td class="num">{{ fmtNum(p.peso_bruto, 2) }}</td>
              <td class="num">{{ fmtNum(p.cbm, 3) }}</td>
            </tr>
            <tr v-if="!u.asignados.length"><td colspan="10" class="vacio">La unidad está vacía. Asigna packing lists desde la lista de abajo.</td></tr>
          </tbody>
        </table>
      </div>
      <BarraSeleccion :cantidad="selA.ids.size" singular="PL seleccionado" plural="PL seleccionados" @limpiar="selA.limpiar()">
        <template #resumen>{{ fmtNum(totSelA.cajas) }} cajas, {{ fmtNum(totSelA.cbm, 2) }} m³</template>
        <button class="btn btn-primario" :disabled="ocupado || !selAsignados.some((p) => p.asignacion === 'TENTATIVA')" @click="confirmar">Confirmar</button>
        <button class="btn" :disabled="!u.otras_unidades.length" @click="modal = { tipo: 'mover', destino: u.otras_unidades[0]?.id, modo: 'TENTATIVA', motivo: '' }">Mover a otra unidad</button>
        <button class="btn btn-peligro" @click="modal = { tipo: 'quitar', motivo: '' }">Quitar de la unidad</button>
      </BarraSeleccion>
    </section>

    <section class="panel">
      <div class="panel-cabeza">
        <h2>Por asignar</h2>
        <span class="ayuda">Asigna facturas completas (todos sus PL) o solo algunos PL.</span>
      </div>
      <div class="filtros">
        <input v-model="filtros.q" type="search" placeholder="Buscar número de factura" aria-label="Buscar factura" @input="buscar" />
        <label class="check"><input v-model="filtros.solo_listos" type="checkbox" @change="cargarDisponibles" /> Solo listos para confirmar</label>
      </div>
      <div class="tabla-marco">
        <table class="tabla">
          <thead>
            <tr>
              <th class="chk"><input type="checkbox" aria-label="Seleccionar todo lo disponible" :checked="selD.todos(todosDisponibles.map((p) => p.id))" @change="selD.alternarTodos(todosDisponibles.map((p) => p.id))" /></th>
              <th><span class="oculto-visual">Ver PL</span></th>
              <th>Factura</th>
              <th>Proveedor</th>
              <th>Estado</th>
              <th>Packing lists</th>
              <th class="num">Cajas</th>
              <th class="num">Bruto kg</th>
              <th class="num">CBM</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in disponibles" :key="g.factura_id">
              <tr :class="{ seleccionada: selD.todos(g.packing_lists.map((p) => p.id)) }">
                <td class="chk">
                  <input type="checkbox" :aria-label="`Seleccionar la factura ${g.factura} completa`" :checked="selD.todos(g.packing_lists.map((p) => p.id))" @change="selD.alternarTodos(g.packing_lists.map((p) => p.id))" />
                </td>
                <td><button class="btn-icono" :aria-expanded="abiertas.has(g.factura_id)" :aria-label="`Ver PL de ${g.factura}`" @click="alternarAbierta(g.factura_id)">{{ abiertas.has(g.factura_id) ? '▾' : '▸' }}</button></td>
                <td><router-link :to="`/facturas/${g.factura_id}`"><strong>{{ g.factura }}</strong></router-link></td>
                <td>{{ g.proveedor }}</td>
                <td><EstadoBadge :estado="g.factura_estado" /></td>
                <td>
                  {{ g.packing_lists.length }} sin unidad
                  <span v-if="g.todos_confirmables" class="etiqueta ok">Listos</span>
                </td>
                <td class="num">{{ fmtNum(g.cajas) }}</td>
                <td class="num">{{ fmtNum(g.peso_bruto, 2) }}</td>
                <td class="num">{{ fmtNum(g.cbm, 3) }}</td>
              </tr>
              <template v-if="abiertas.has(g.factura_id)">
                <tr v-for="p in g.packing_lists" :key="p.id" :class="{ seleccionada: selD.tiene(p.id) }">
                  <td></td>
                  <td class="chk"><input type="checkbox" :aria-label="`Seleccionar ${p.numero}`" :checked="selD.tiene(p.id)" @change="selD.alternar(p.id)" /></td>
                  <td colspan="2"><router-link :to="`/packing-lists/${p.id}`" class="cajas-rango">{{ p.numero }}</router-link> {{ porUnidadTxt(p.por_unidad, 'cantidad') }}</td>
                  <td><EstadoBadge :estado="p.estado" /></td>
                  <td><span v-if="!p.puede_confirmar" class="ayuda">{{ p.motivo_no_confirmable }} Solo tentativo.</span></td>
                  <td class="num">{{ fmtNum(p.cajas) }}</td>
                  <td class="num">{{ fmtNum(p.peso_bruto, 2) }}</td>
                  <td class="num">{{ fmtNum(p.cbm, 3) }}</td>
                </tr>
              </template>
            </template>
            <tr v-if="!disponibles.length"><td colspan="9" class="vacio">No hay packing lists sin unidad con estos filtros.</td></tr>
          </tbody>
        </table>
      </div>
      <BarraSeleccion :cantidad="selD.ids.size" singular="PL seleccionado" plural="PL seleccionados" @limpiar="selD.limpiar()">
        <template #resumen>{{ fmtNum(totSelD.cajas) }} cajas, {{ fmtNum(totSelD.cbm, 2) }} m³, {{ fmtNum(totSelD.kg, 0) }} kg</template>
        <button class="btn" :disabled="ocupado" @click="asignar('TENTATIVA')">Asignar como tentativo</button>
        <button class="btn btn-primario" :disabled="ocupado || !selDisponibles.every((p) => p.puede_confirmar)" @click="asignar('CONFIRMADA')">Asignar y confirmar</button>
      </BarraSeleccion>
    </section>
  </template>

  <Modal v-if="modal?.tipo === 'quitar'" titulo="Quitar de la unidad de carga" @cerrar="modal = null">
    <p>Los {{ selA.ids.size }} packing lists quedan sin unidad y vuelven a “Por asignar”.</p>
    <label class="campo"><span>Motivo{{ requiereMotivo ? '' : ' (opcional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-peligro" :disabled="ocupado || (requiereMotivo && !modal.motivo.trim())" @click="quitar">Quitar</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'mover'" titulo="Mover a otra unidad" @cerrar="modal = null">
    <label class="campo"><span>Unidad destino</span>
      <select v-model="modal.destino"><option v-for="o in u.otras_unidades" :key="o.id" :value="o.id">{{ o.nombre }}</option></select>
    </label>
    <label class="campo"><span>Asignación en el destino</span>
      <select v-model="modal.modo"><option value="TENTATIVA">Tentativa</option><option value="CONFIRMADA">Confirmada</option></select>
    </label>
    <label class="campo"><span>Motivo{{ requiereMotivo ? '' : ' (opcional)' }}</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.destino || (requiereMotivo && !modal.motivo.trim())" @click="mover">Mover</button>
    </template>
  </Modal>

  <Modal v-if="modal?.tipo === 'asignar'" titulo="El embarque ya salió" @cerrar="modal = null">
    <p>Agregar carga a un embarque que ya salió es una corrección logística. Indica el motivo.</p>
    <label class="campo"><span>Motivo</span><textarea v-model="modal.motivo"></textarea></label>
    <template #pie>
      <button class="btn" @click="modal = null">Volver</button>
      <button class="btn btn-primario" :disabled="ocupado || !modal.motivo.trim()" @click="asignarConMotivo">Asignar</button>
    </template>
  </Modal>
</template>
