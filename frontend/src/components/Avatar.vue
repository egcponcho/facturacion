<script setup>
import { computed } from 'vue'

// Foto del usuario o, sin foto, sus iniciales
const props = defineProps({ nombre: { type: String, default: '' }, foto: { type: String, default: null }, tam: { type: Number, default: 32 } })
const iniciales = computed(() => (props.nombre || '?').trim().split(/\s+/).map((x) => x[0]).slice(0, 2).join('').toUpperCase())
</script>

<template>
  <span class="avatar" :style="{ width: `${tam}px`, height: `${tam}px`, fontSize: `${Math.round(tam * 0.38)}px` }" aria-hidden="true">
    <img v-if="foto" :src="foto" alt="" />
    <template v-else>{{ iniciales }}</template>
  </span>
</template>

<style scoped>
.avatar { overflow: hidden; flex: none; }
.avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
</style>
