<script setup>
import { computed } from 'vue'
import Icono from './Icono.vue'

// Datos de una parte del documento: a quién se factura (sociedad) o a quién
// se notifica (centro), con sus correos y contactos de Mantenimiento.
const props = defineProps({ titulo: String, icono: { type: String, default: 'base' }, parte: Object })
const correos = (texto) => (texto || '').split(',').map((x) => x.trim()).filter(Boolean)
const ROLES = { FACTURACION: 'Billing', NOTIFY: 'Notify', LOGISTICA: 'Logistics' }
const nombre = computed(() => props.parte?.razon_social || props.parte?.nombre)
</script>

<template>
  <section class="panel tarjeta-parte">
    <div class="tp-cabeza">
      <span class="tp-icono"><Icono :nombre="icono" :tam="16" /></span>
      <div>
        <span class="eyebrow">{{ titulo }}</span>
        <b>{{ parte?.codigo || '—' }}<template v-if="nombre"> · {{ nombre }}</template></b>
      </div>
    </div>
    <template v-if="parte?.nombre || parte?.razon_social">
      <p class="tp-linea">
        <template v-if="parte.id_fiscal">Tax ID {{ parte.id_fiscal }} · </template>{{ parte.direccion || 'No address' }}<template v-if="parte.pais"> · {{ parte.pais }}</template>
      </p>
      <p v-if="parte.puerto" class="tp-linea">Port of arrival: <b>{{ parte.puerto }}</b><template v-if="parte.puerto_nombre"> · {{ parte.puerto_nombre }}</template></p>
      <p v-if="correos(parte.correos).length" class="tp-linea">
        <Icono nombre="archivo" :tam="13" />
        <a v-for="c in correos(parte.correos)" :key="c" :href="`mailto:${c}`" class="tp-correo">{{ c }}</a>
      </p>
      <ul v-if="parte.contactos?.length" class="tp-contactos">
        <li v-for="(c, i) in parte.contactos" :key="i">
          <b>{{ c.nombre }}</b><span v-if="c.cargo" class="ayuda"> · {{ c.cargo }}</span>
          <span class="etiqueta">{{ ROLES[c.rol] || c.rol }}</span>
          <span class="sub">
            <a v-for="m in correos(c.correos)" :key="m" :href="`mailto:${m}`" class="tp-correo">{{ m }}</a>
            <template v-if="c.telefono"> · {{ c.telefono }}</template>
          </span>
        </li>
      </ul>
      <p v-else class="ayuda">No contacts registered. Add them in Master data → Contacts.</p>
    </template>
    <p v-else class="ayuda">Not registered in Master data.</p>
  </section>
</template>
