<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'

// «Mi bandeja»: lo que la persona tiene que hacer hoy, en una sola lista. Junta
// lo que bloquea el siguiente paso (atención), las tareas de sus documentos y
// las alertas de recepción. Lo urgente va primero y lleva un punto rojo; cada
// fila dice de qué módulo es y tiene su botón.
// items: [{ clave, titulo, detalle, modulo, a (ruta), accion, urgente, cifra }]
const props = defineProps({ items: { type: Array, required: true } })
const filtro = ref('todo')
const urgentes = computed(() => props.items.filter((x) => x.urgente))
const visibles = computed(() => (filtro.value === 'urgente' ? urgentes.value : props.items))
</script>

<template>
  <section class="panel bandeja" :aria-label="t('My inbox')">
    <div class="panel-cabeza">
      <div><h2>{{ t('My inbox') }}</h2></div>
      <div v-if="items.length" class="segmentos" role="group" :aria-label="t('Show')">
        <button type="button" class="segmento" :aria-pressed="filtro === 'todo'" @click="filtro = 'todo'">{{ t('All · {0}', [items.length]) }}</button>
        <button type="button" class="segmento" :aria-pressed="filtro === 'urgente'" :disabled="!urgentes.length" @click="filtro = 'urgente'">
          {{ t('Urgent · {0}', [urgentes.length]) }}</button>
      </div>
    </div>
    <ul v-if="visibles.length" class="bandeja-lista">
      <li v-for="x in visibles" :key="x.clave">
        <!-- El punto acompaña al texto «Urgente»: el color nunca va solo -->
        <span class="bandeja-punto" :class="{ urgente: x.urgente }" aria-hidden="true"></span>
        <div class="bandeja-texto">
          <b>{{ tx(x.titulo) }}</b>
          <small>{{ [tx(x.modulo), tx(x.detalle)].filter(Boolean).join(' · ') }}</small>
        </div>
        <div class="bandeja-derecha">
          <span v-if="x.urgente" class="etiqueta error">{{ t('Urgent') }}</span>
          <router-link class="btn btn-chico" :to="x.a">{{ tx(x.accion || t('Open')) }}</router-link>
        </div>
      </li>
    </ul>
    <div v-else class="todo-listo">
      <span class="icono-ok"><Icono nombre="check" :tam="20" /></span>
      <div><b>{{ t('Nothing pending') }}</b><p class="ayuda">{{ t('When something needs you (a document to correct, goods to receive, a late PO), it shows up here.') }}</p></div>
    </div>
  </section>
</template>

<style scoped>
.bandeja-lista { list-style: none; margin: 0 -22px -20px; padding: 0; }
.bandeja-lista li { display: flex; align-items: center; gap: 12px; padding: 11px 22px; border-top: 1px solid var(--linea-suave); }
.bandeja-punto { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--tinta-3); }
.bandeja-punto.urgente { background: var(--error); }
.bandeja-texto { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.bandeja-texto b { font-weight: 600; }
.bandeja-texto small { color: var(--tinta-3); font-size: var(--t-sm); }
.bandeja-derecha { display: flex; align-items: center; gap: 8px; flex: none; }
@media (max-width: 720px) {
  .bandeja-lista li { flex-wrap: wrap; align-items: flex-start; }
  .bandeja-punto { margin-top: 6px; }
  .bandeja-derecha { width: 100%; margin-inline-start: 20px; justify-content: space-between; }
}
</style>
