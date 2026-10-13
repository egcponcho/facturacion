<script setup>
// Silueta del Home mientras llegan los datos (misma estructura que el tablero)
</script>

<template>
  <div class="tablero-esqueleto" aria-hidden="true">
    <div class="kpis"><div v-for="i in 6" :key="i" class="kpi"><span class="esqueleto" style="width: 60%; height: 11px"></span>
      <span class="esqueleto" style="width: 45%; height: 24px; margin-top: 10px"></span></div></div>
    <div class="tablero">
      <div class="col"><div class="panel"><span v-for="i in 4" :key="i" class="esqueleto mb-3" style="height: 36px"></span></div></div>
      <div class="col"><div class="panel"><span v-for="i in 2" :key="i" class="esqueleto mb-3" style="height: 92px"></span></div></div>
    </div>
  </div>
</template>
