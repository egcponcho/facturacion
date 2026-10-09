<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import { datosModo } from '@/composables/useRutas'
import { errorApi } from '@/stores/ui'
import { ACCIONES, avanceViaje, eventosEmbarque, diasTxt, fmtFecha, fmtFechaHora, fmtNum, plural } from '@/nucleo/utils'
import Avance from '@/componentes/Avance.vue'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import EstadoTiempo from '@/componentes/EstadoTiempo.vue'
import Icono from '@/componentes/Icono.vue'
import PanelLateral from '@/componentes/PanelLateral.vue'

// Resumen de un embarque en el panel lateral: la ruta con su avance y la
// holgura contra el límite en puerto, las cifras de carga, cada unidad con su
// llenado, los eventos y la actividad reciente.
const props = defineProps({ id: { type: Number, required: true } })
const emit = defineEmits(['cerrar'])
const e = ref(null)

watch(() => props.id, async (id) => {
  e.value = null
  try {
    e.value = await api.get(`/embarques/${id}`)
  } catch (err) {
    errorApi(err)
    emit('cerrar')
  }
}, { immediate: true })

const total = (campo) => (e.value?.unidades || []).reduce((a, u) => a + (u[campo] || 0), 0)
const dias = (fecha) => (fecha ? Math.round((new Date(fecha).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000) : null)
const limite = computed(() => (e.value?.unidades || []).map((u) => u.limite_puerto).filter(Boolean).sort()[0] || null)
const proveedores = computed(() => [...new Set((e.value?.unidades || []).flatMap((u) => u.proveedores || []))])
const nombreEvento = (k) => eventosEmbarque().find((x) => x[0] === k)?.[1] || k
const icono = computed(() => datosModo(e.value?.tipo_transporte).icono)
const llegada = computed(() => {
  const d = e.value
  if (!d) return ''
  if (d.arribo_real) return t('Arrived on {0}.', [fmtFecha(d.arribo_real)])
  if (!d.eta) return t('No ETA yet.')
  return t('Arrives {0}.', [diasTxt(dias(d.eta))])
})
</script>

<template>
  <PanelLateral :titulo="e?.codigo || t('Shipment')" :detalle="`/transporte/embarques/${props.id}`" ancho="560px" @cerrar="emit('cerrar')">
    <template #estado>
      <span v-if="e" class="fila-flex pl-subtitulo"><EstadoBadge :estado="e.estado" /><EstadoTiempo :estado="e.estado_tiempo" :holgura="e.holgura_dias" />
        <span class="ayuda">{{ datosModo(e.tipo_transporte).nombre }}<template v-if="e.modalidad"> · {{ tx(e.modalidad) }}</template></span></span>
    </template>
    <p v-if="!e" class="ayuda">{{ t('Loading…') }}</p>
    <template v-else>
      <div class="pl-tarjeta">
        <div class="fila-flex" style="gap: 8px">
          <span class="envio-modo"><Icono :nombre="icono" :tam="16" /></span>
          <b>{{ tx(e.documento_numero || t('No transport document')) }}</b>
          <span class="ayuda separar">{{ tx(e.transportista || t('No carrier')) }}</span>
        </div>
        <div class="ruta">
          <span><b>{{ tx(e.puerto_origen || t('Origin')) }}</b><small>{{ e.salida_real ? t('Departed {0}', [fmtFecha(e.salida_real)]) : t('ETD {0}', [fmtFecha(e.etd) || '—']) }}</small></span>
          <span class="ruta-riel" aria-hidden="true">
            <span class="ruta-avance" :style="{ width: `${avanceViaje(e)}%` }"></span>
            <span v-if="e.estado !== 'PLANIFICADO'" class="ruta-punto" :style="{ left: `${avanceViaje(e)}%` }"></span>
          </span>
          <span class="texto-derecha"><b>{{ tx(e.puerto_destino || t('Destination')) }}</b><small>{{ e.arribo_real ? t('Arrived {0}', [fmtFecha(e.arribo_real)]) : t('ETA {0}', [fmtFecha(e.eta) || '—']) }}</small></span>
        </div>
        <dl class="pl-hitos">
          <div><dt>{{ t('Arrival') }}</dt><dd>{{ llegada }}</dd></div>
          <div><dt>{{ t('Port deadline') }}</dt><dd>{{ limite ? fmtFecha(limite) : '—' }}<template v-if="e.holgura_dias !== null && e.holgura_dias !== undefined"> · {{ e.holgura_dias < 0 ? t('{0} d late', [-e.holgura_dias]) : t('{0} d margin', [e.holgura_dias]) }}</template></dd></div>
          <div><dt>{{ t('In store') }}</dt><dd>{{ e.fecha_tienda ? fmtFecha(e.fecha_tienda) : '—' }}</dd></div>
        </dl>
      </div>

      <div class="pl-cifras">
        <div class="pl-cifra"><span>{{ t('Load units') }}</span><b>{{ fmtNum(e.unidades.length) }}</b></div>
        <div class="pl-cifra"><span>{{ t('Invoices') }}</span><b>{{ fmtNum(total('facturas')) }}</b></div>
        <div class="pl-cifra"><span>{{ t('Packing lists') }}</span><b>{{ fmtNum(total('packing_lists')) }}</b></div>
        <div class="pl-cifra"><span>{{ t('Cartons') }}</span><b>{{ fmtNum(total('cajas')) }}</b></div>
        <div class="pl-cifra"><span>{{ t('Gross weight') }}</span><b>{{ fmtNum(total('peso_bruto'), 1) }} kg</b></div>
        <div class="pl-cifra"><span>{{ t('Volume') }}</span><b>{{ fmtNum(total('cbm'), 2) }} m³</b></div>
      </div>

      <section class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Load units') }}</h3>
        <p v-if="!e.unidades.length" class="ayuda">{{ t('No load units yet.') }}</p>
        <div v-for="u in e.unidades" :key="u.id" class="pl-tarjeta">
          <div class="fila-flex" style="gap: 8px">
            <b>{{ tx(u.numero || u.etiqueta) }}</b><span class="etiqueta">{{ tx(u.tipo) }}</span>
            <span v-if="u.sello" class="ayuda">{{ t('Seal {0}', [u.sello]) }}</span>
            <span class="separar"><EstadoTiempo :estado="u.estado_tiempo" :holgura="u.holgura_dias" /></span>
          </div>
          <div class="ayuda">
            {{ plural(u.packing_lists || 0, 'PL', t('PLs')) }} · {{ plural(u.cajas || 0, t('carton'), t('cartons')) }} · {{ fmtNum(u.peso_bruto, 1) }} kg · {{ fmtNum(u.cbm, 2) }} m³
            <template v-if="u.tentativas"> · {{ plural(u.tentativas, t('tentative PL'), t('tentative PLs')) }}</template>
          </div>
          <div v-if="u.proveedores?.length" class="ayuda">{{ tx(u.proveedores.join(', ')) }}</div>
          <div v-if="u.capacidad_cbm || u.capacidad_kg" class="pl-avances">
            <template v-if="u.capacidad_cbm"><span>{{ t('Volume') }}</span><Avance :porcentaje="u.pct_cbm || 0" /></template>
            <template v-if="u.capacidad_kg"><span>{{ t('Weight') }}</span><Avance :porcentaje="u.pct_kg || 0" /></template>
          </div>
          <ul v-if="u.alertas?.length" class="pl-alertas">
            <li v-for="(a, i) in u.alertas" :key="i"><Icono nombre="alerta" :tam="14" />{{ tx(a) }}</li>
          </ul>
        </div>
      </section>

      <section class="pl-seccion pl-partes">
        <div><h3 class="resumen-titulo">{{ t('Suppliers') }}</h3>
          <span v-if="!proveedores.length" class="ayuda">—</span>
          <div v-for="p in proveedores" :key="p">{{ tx(p) }}</div></div>
        <div v-if="e.notify"><h3 class="resumen-titulo">{{ t('Notify') }}</h3><b>{{ tx(e.notify.nombre) }}</b>
          <div class="ayuda">{{ tx(e.notify.puerto_nombre || e.notify.puerto || '') }}</div>
          <div v-for="c in e.notify.contactos || []" :key="c.nombre" class="ayuda">{{ tx(c.nombre) }}<template v-if="c.telefono"> · {{ tx(c.telefono) }}</template></div></div>
      </section>

      <section class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Events') }}</h3>
        <p v-if="!e.eventos.length" class="ayuda">{{ t('No events yet.') }}</p>
        <ol v-else class="pl-eventos">
          <li v-for="ev in [...e.eventos].reverse()" :key="ev.id">
            <b>{{ tx(nombreEvento(ev.tipo)) }}</b>
            <span class="ayuda">{{ fmtFechaHora(ev.fecha) }}<template v-if="ev.ubicacion"> · {{ tx(ev.ubicacion) }}</template></span>
            <span v-if="ev.observacion" class="ayuda">{{ tx(ev.observacion) }}</span>
          </li>
        </ol>
      </section>

      <section v-if="e.historial.length" class="pl-seccion">
        <h3 class="resumen-titulo">{{ t('Recent activity') }}</h3>
        <ul class="linea-tiempo">
          <li v-for="(h, i) in e.historial.slice(0, 6)" :key="i">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<template v-if="h.usuario"> · {{ tx(h.usuario) }}</template></span>
            <span>{{ tx(ACCIONES[h.accion] || h.accion) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </PanelLateral>
</template>
