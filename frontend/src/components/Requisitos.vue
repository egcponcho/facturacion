<script setup>
import { tx } from '../i18n/index.js'
import Icono from './Icono.vue'

// Requisitos para continuar: cada condición cumplida (✓) o pendiente (✕), por
// qué y cómo resolverla. Una acción puede abrir una ruta (`to`) o avisar al
// padre (`clave` → evento «accion»). Un botón deshabilitado nunca queda sin
// explicación: la lista dice qué falta y lleva a resolverlo.
//   items: [{ clave, ok, titulo, detalle, acciones: [{ texto, to?, clave? }] }]
const props = defineProps({ items: { type: Array, required: true }, soloPendientes: { type: Boolean, default: false } })
const emit = defineEmits(['accion'])
</script>

<template>
  <ul class="checklist">
    <li v-for="r in props.items.filter((x) => !props.soloPendientes || !x.ok)" :key="r.clave" :class="r.ok ? 'ok' : 'falta'">
      <span class="marca"><Icono :nombre="r.ok ? 'check' : 'alerta'" :tam="14" /></span>
      <span>
        {{ tx(r.titulo) }}
        <span v-if="r.detalle" class="sub ayuda">{{ tx(r.detalle) }}</span>
      </span>
      <span v-if="!r.ok && r.acciones?.length" class="fila-flex requisitos-acciones">
        <template v-for="a in r.acciones" :key="a.texto">
          <router-link v-if="a.to" class="btn btn-chico" :to="a.to">{{ tx(a.texto) }}<Icono nombre="derecha" :tam="13" /></router-link>
          <button v-else type="button" class="btn btn-chico" @click="emit('accion', a.clave)">{{ tx(a.texto) }}</button>
        </template>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.requisitos-acciones { gap: 6px; justify-content: flex-end; }
</style>
