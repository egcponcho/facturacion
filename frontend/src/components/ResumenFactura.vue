<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { errorApi } from '../stores/ui'
import { ACCIONES, fmtFecha, fmtFechaHora, fmtMoneda, plural } from '../utils'
import EstadoBadge from './EstadoBadge.vue'
import PanelLateral from './PanelLateral.vue'
import Requisitos from './Requisitos.vue'

// Resumen de una factura en el panel lateral: datos clave, qué le falta,
// sus packing lists y la actividad reciente.
const props = defineProps({ id: { type: Number, required: true } })
const emit = defineEmits(['cerrar'])
const f = ref(null)
const actividad = ref([])

watch(() => props.id, async (id) => {
  f.value = null
  try {
    const [d, h] = await Promise.all([api.get(`/facturas/${id}`), api.get(`/facturas/${id}/historial`)])
    f.value = d
    actividad.value = h.slice(0, 6)
  } catch (e) {
    errorApi(e)
    emit('cerrar')
  }
}, { immediate: true })

const faltan = computed(() => (f.value?.pendientes || []).map((p, i) => ({
  clave: String(i), ok: false, titulo: p.mensaje,
  acciones: p.producto_id ? [{ texto: t('Open technical sheet'), to: `/productos/${p.producto_id}` }] : [],
})))
</script>

<template>
  <PanelLateral :titulo="f?.nombre || t('Invoice')" :detalle="`/facturas/${props.id}`" @cerrar="emit('cerrar')">
    <template #estado><EstadoBadge v-if="f" :estado="f.estado" /></template>
    <p v-if="!f" class="ayuda">{{ t('Loading…') }}</p>
    <template v-else>
      <dl class="resumen-datos">
        <dt>{{ t('Supplier') }}</dt><dd>{{ tx(f.proveedor) }}</dd>
        <dt>{{ t('Date') }}</dt><dd>{{ fmtFecha(f.fecha) || '—' }}</dd>
        <dt>{{ t('Amount') }}</dt><dd class="fuerte">{{ fmtMoneda(f.totales.importe, f.moneda) }}</dd>
        <dt>{{ t('Lines') }}</dt><dd>{{ f.lineas.length }}</dd>
        <dt>{{ t('Incoterm') }}</dt><dd>{{ tx(f.incoterm || '—') }}</dd>
        <dt>{{ t('Plant') }}</dt><dd>{{ tx(f.centro || '—') }}</dd>
      </dl>
      <section v-if="faltan.length">
        <h3 class="resumen-titulo">{{ t('Missing to finalize ({0})', [faltan.length]) }}</h3>
        <Requisitos :items="faltan.slice(0, 6)" />
        <p v-if="faltan.length > 6" class="ayuda">{{ t('And {0} more.', [faltan.length - 6]) }}</p>
      </section>
      <section>
        <h3 class="resumen-titulo">{{ t('Packing lists') }}</h3>
        <p v-if="!f.packing_lists.length" class="ayuda">{{ t('No packing list') }}</p>
        <ul v-else class="resumen-lista">
          <li v-for="pl in f.packing_lists" :key="pl.id">
            <router-link :to="`/packing-lists/${pl.id}`">{{ tx(pl.numero) }}</router-link>
            <EstadoBadge :estado="pl.estado" />
            <span class="ayuda">{{ plural(pl.totales?.cajas || 0, t('carton'), t('cartons')) }}</span>
          </li>
        </ul>
      </section>
      <section v-if="actividad.length">
        <h3 class="resumen-titulo">{{ t('Recent activity') }}</h3>
        <ul class="linea-tiempo">
          <li v-for="h in actividad" :key="h.id">
            <span class="ayuda">{{ fmtFechaHora(h.fecha) }}<template v-if="h.usuario"> · {{ tx(h.usuario) }}</template></span>
            <span>{{ tx(ACCIONES[h.accion] || h.accion) }}</span>
          </li>
        </ul>
      </section>
    </template>
  </PanelLateral>
</template>
