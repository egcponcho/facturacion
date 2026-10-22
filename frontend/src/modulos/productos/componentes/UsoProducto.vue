<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'
import { fmtFecha, fmtNum } from '@/nucleo/utils'
import EstadoBadge from '@/componentes/EstadoBadge.vue'

// Dónde se usa el producto: sus OCs, facturas y embarques (solo las secciones
// que el rol puede ver; el servidor aplica el alcance del usuario)
const props = defineProps({ productoId: { type: Number, required: true } })
const d = ref(null)
onMounted(async () => {
  try {
    d.value = await api.get(`/productos/${props.productoId}/uso`)
  } catch (e) {
    errorApi(e)
  }
})
const cantidad = (c) => Object.entries(c || {}).map(([u, n]) => `${fmtNum(n)} ${u}`).join(' · ')
const SECCIONES = [
  ['ordenes', t('Purchase orders'), (x) => `/ordenes/${x.id}`, 'oc'],
  ['facturas', t('Invoices'), (x) => `/facturas/${x.id}`, 'factura'],
  ['embarques', t('Shipments'), (x) => `/transporte/embarques/${x.id}`, 'embarque'],
]
</script>

<template>
  <div v-if="!d" class="esqueleto" style="height: 120px" />
  <div v-else class="uso-secciones">
    <template v-for="[clave, titulo, enlace, tipo] in SECCIONES" :key="clave">
      <section v-if="d[clave]" class="panel" :aria-label="titulo">
        <h3>{{ titulo }} <span class="cuenta">{{ d[clave].total }}</span></h3>
        <p v-if="!d[clave].total" class="ayuda">{{ t('None yet.') }}</p>
        <ul v-else class="uso-lista">
          <li v-for="x in d[clave].items" :key="x.id">
            <router-link :to="enlace(x)" class="enlace-doc"><b>{{ tx(x.numero || x.codigo) }}</b></router-link>
            <EstadoBadge :tipo="tipo" :estado="x.estado" />
            <span class="apagado">{{ cantidad(x.cantidad) }}</span>
            <span v-if="x.fecha_tienda || x.fecha || x.eta" class="apagado">{{ fmtFecha(x.fecha_tienda || x.fecha || x.eta) }}</span>
          </li>
        </ul>
        <p v-if="d[clave].total > d[clave].items.length" class="ayuda">{{ t('Showing {0} of {1}.', [d[clave].items.length, d[clave].total]) }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.uso-secciones { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.uso-secciones h3 { margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
.uso-lista { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.uso-lista li { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; padding: 8px 0; border-top: 1px solid var(--linea); }
.uso-lista li:first-child { border-top: 0; }
</style>
