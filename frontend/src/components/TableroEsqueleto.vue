<script setup>
// Silueta del Home mientras llegan los datos
</script>

<template>
  <div class="tablero-esqueleto" aria-hidden="true">
    <div class="panel"><span class="esqueleto" style="width: 220px; height: 16px"></span>
      <div class="atencion-lista" style="margin-top: 16px"><span v-for="i in 3" :key="i" class="esqueleto" style="height: 64px"></span></div>
    </div>
    <div class="tablero">
      <div class="col"><div class="panel"><span v-for="i in 4" :key="i" class="esqueleto" style="height: 38px; margin-bottom: 12px"></span></div></div>
      <div class="col"><div class="panel"><span v-for="i in 2" :key="i" class="esqueleto" style="height: 90px; margin-bottom: 12px"></span></div></div>
    </div>
  </div>
</template>
