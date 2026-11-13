<script setup>
import { datosModo } from '@/composables/useRutas'
import { t, tx } from '@/i18n/index.js'
import { useRouter } from 'vue-router'
import EstadoBadge from '@/componentes/EstadoBadge.vue'
import Icono from '@/componentes/Icono.vue'
import { esInterno } from '@/stores/sesion'
import { avanceViaje, fmtFecha, plural } from '@/nucleo/utils'

// Embarques en curso (planificados y en tránsito) con su ruta y avance del viaje.
// Lo usan el Inicio (si la persona lo agrega) y el tablero ejecutivo.
defineProps({ envios: { type: Array, required: true } })
const router = useRouter()
const viaje = avanceViaje
function diasPara(fecha) {
  if (!fecha) return ''
  const dias = Math.round((new Date(fecha).getTime() - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (dias === 0) return t('today')
  return dias > 0 ? t('in {0}', [plural(dias, t('day'), t('days'))]) : t('{0} ago', [plural(-dias, t('day'), t('days'))])
}
function abrirEnvio(e) {
  router.push(esInterno() ? `/transporte/embarques/${e.id}` : `/facturas/${e.factura_ids[0]}?tab=pl`)
}
</script>

<template>
<section class="panel">
  <div class="panel-cabeza">
    <div><h2>{{ t('Shipments') }}</h2><p>{{ tx(esInterno() ? t('Planned and in-transit shipments.') : t('Shipments carrying your goods.')) }}</p></div>
    <router-link v-if="esInterno()" class="btn btn-chico btn-fantasma" to="/transporte">{{ t('See all') }}<Icono nombre="derecha" :tam="14" /></router-link>
  </div>
  <ul v-if="envios.length" class="envios">
    <li v-for="e in envios" :key="e.id">
      <button type="button" class="envio" @click="abrirEnvio(e)">
        <span class="envio-cabeza">
          <span class="envio-modo"><Icono :nombre="datosModo(e.tipo_transporte).icono" :tam="16" /></span>
          <b class="envio-codigo">{{ tx(e.codigo) }}</b>
          <EstadoBadge :estado="e.estado" tipo="embarque" />
          <span class="ayuda separar">{{ plural(e.cajas, t('carton'), t('cartons')) }}</span>
        </span>
        <span class="ruta">
          <span><b>{{ tx(e.origen || t('Origin')) }}</b><small>{{ tx(e.etd ? fmtFecha(e.etd) : t('No ETD')) }}</small></span>
          <span class="ruta-riel" aria-hidden="true">
            <span class="ruta-avance" :style="{ width: `${viaje(e)}%` }"></span>
            <span v-if="e.estado !== 'PLANIFICADO'" class="ruta-punto" :style="{ left: `${viaje(e)}%` }"></span>
          </span>
          <span class="texto-derecha"><b>{{ tx(e.destino || t('Destination')) }}</b><small>{{ tx(e.eta ? fmtFecha(e.eta) : t('No ETA')) }}</small></span>
        </span>
        <span class="ayuda envio-pie">
          <template v-if="e.eta && e.estado !== 'ARRIBADO'">{{ t('Arrives {0}.', [diasPara(e.eta)]) }} </template>
          {{ tx(e.facturas.slice(0, 2).join(', ')) }}<template v-if="e.facturas.length > 2">&nbsp;{{ t('and {0} more', [e.facturas.length - 2]) }}</template>
        </span>
      </button>
    </li>
  </ul>
  <p v-else class="ayuda">{{ t('No shipments in progress.') }}</p>
</section>

</template>
