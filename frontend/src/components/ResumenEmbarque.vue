<script setup>
import { t, tx } from '../i18n/index.js'
import { ref, watch } from 'vue'
import { api } from '../api'
import { MODOS } from '../composables/useRutas'
import { errorApi } from '../stores/ui'
import { ACCIONES, fmtFecha, fmtFechaHora, fmtNum, plural } from '../utils'
import Avance from './Avance.vue'
import EstadoBadge from './EstadoBadge.vue'
import EstadoTiempo from './EstadoTiempo.vue'
import PanelLateral from './PanelLateral.vue'

// Resumen de un embarque en el panel lateral: ruta, fechas, unidades de carga
// con su llenado y la actividad reciente.
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
</script>

<template>
  <PanelLateral :titulo="e?.codigo || t('Shipment')" :detalle="`/transporte/embarques/${props.id}`" @cerrar="emit('cerrar')">
    <template #estado>
      <span v-if="e" class="fila-flex" style="gap: 6px"><EstadoBadge :estado="e.estado" /><EstadoTiempo :estado="e.estado_tiempo" :holgura="e.holgura_dias" /></span>
    </template>
    <p v-if="!e" class="ayuda">{{ t('Loading…') }}</p>
    <template v-else>
      <dl class="resumen-datos">
        <dt>{{ t('Mode') }}</dt><dd>{{ tx(MODOS[e.tipo_transporte]?.nombre || e.tipo_transporte) }}</dd>
        <dt>{{ MODOS[e.tipo_transporte]?.doc || 'B/L' }}</dt><dd>{{ tx(e.documento_numero || '—') }}</dd>
        <dt>{{ t('Route') }}</dt><dd>{{ tx(e.puerto_origen || '—') }} → {{ tx(e.puerto_destino || '—') }}</dd>
        <dt>ETD</dt><dd>{{ fmtFecha(e.salida_real || e.etd) || '—' }}</dd>
        <dt>ETA</dt><dd>{{ fmtFecha(e.arribo_real || e.eta) || '—' }}</dd>
        <dt>{{ t('Carrier') }}</dt><dd>{{ tx(e.transportista || '—') }}</dd>
      </dl>
      <section>
        <h3 class="resumen-titulo">{{ t('Load units') }}</h3>
        <p v-if="!e.unidades.length" class="ayuda">{{ t('No load units yet.') }}</p>
        <ul v-else class="resumen-lista resumen-unidades">
          <li v-for="u in e.unidades" :key="u.id">
            <b>{{ tx(u.numero || u.nombre) }}</b><span class="etiqueta">{{ tx(u.tipo) }}</span>
            <span class="ayuda">{{ plural(u.packing_lists?.length || 0, 'PL', t('PLs')) }} · {{ plural(u.cajas, t('carton'), t('cartons')) }} · {{ fmtNum(u.cbm, 1) }} m³</span>
            <Avance v-if="u.capacidad_cbm" :porcentaje="u.pct_cbm || 0" />
          </li>
        </ul>
      </section>
      <section v-if="e.historial.length">
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

<style scoped>
.resumen-unidades li { display: grid; grid-template-columns: auto auto 1fr; gap: 4px 8px; align-items: center; padding-bottom: 8px; border-bottom: 1px solid var(--linea-suave); }
.resumen-unidades .ayuda, .resumen-unidades :deep(.avance) { grid-column: 1 / -1; }
</style>
