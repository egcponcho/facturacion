<script setup>
import { t, tx } from '../../i18n/index.js'
import { ref, watch } from 'vue'
import { api } from '../../api'
import { M } from '../../clasificacion/useClasificacion'

// Busca la subpartida (6 dígitos) en todo el SAC oficial: por código o por
// palabras de su texto o del de su partida.
const props = defineProps({ modelValue: { type: String, default: '' }, descripcion: { type: String, default: '' }, disabled: Boolean, id: String })
const emit = defineEmits(['elegir'])
const texto = ref('')
const items = ref([])
const abierto = ref(false)
const buscando = ref(false)
let espera = null

watch(texto, (q) => {
  clearTimeout(espera)
  if (q.trim().length < 2) { items.value = []; return }
  espera = setTimeout(async () => {
    buscando.value = true
    try {
      items.value = await api.get('/clasificacion/sac', { q })
      abierto.value = true
    } finally {
      buscando.value = false
    }
  }, 250)
})
function elegir(x) {
  emit('elegir', x)
  abierto.value = false
  texto.value = ''
}
const propio = (d) => String(d || '').split('—').slice(-1)[0].trim()
</script>

<template>
  <div class="sac-buscador">
    <div v-if="modelValue" class="elegida">
      <span class="codigo-sac">{{ M.fmtCode(modelValue) }}</span>
      <span class="texto" :title="tx(descripcion)">{{ tx(propio(descripcion) || '—') }}</span>
    </div>
    <input v-if="!disabled" :id="id" v-model="texto" class="entrada" type="search" autocomplete="off"
           :placeholder="tx(modelValue ? t('Search another subheading…') : t('Search by words or code, e.g. laptop, 8471.30'))"
           @focus="abierto = items.length > 0" @keydown.esc="abierto = false" />
    <ul v-if="abierto && (items.length || buscando)" class="resultados" role="listbox">
      <li v-if="buscando && !items.length" class="apagado">{{ t('Searching…') }}</li>
      <li v-for="x in items" :key="x.codigo" role="option" tabindex="0" @mousedown.prevent="elegir(x)" @keydown.enter="elegir(x)">
        <span class="codigo-sac">{{ M.fmtCode(x.codigo) }}</span>
        <span><b>{{ tx(propio(x.descripcion)) }}</b><small>{{ tx(x.partida) }}</small></span>
      </li>
    </ul>
    <p v-if="abierto && !buscando && texto.trim().length >= 2 && !items.length" class="hint">{{ t('No subheading matches; try other words.') }}</p>
  </div>
</template>

<style scoped>
.sac-buscador { position: relative; display: flex; flex-direction: column; gap: 6px; }
.elegida { display: flex; gap: 8px; align-items: baseline; padding: 8px 10px; border: 1px solid var(--acento); border-radius: 8px; background: var(--acento-claro); min-width: 0; }
.elegida .texto { font-size: 0.86rem; color: var(--tinta); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.resultados { position: absolute; top: 100%; inset-inline-start: 0; inset-inline-end: 0; z-index: 30; margin: 4px 0 0; padding: 4px; list-style: none; max-height: 320px; overflow: auto;
  background: var(--superficie); border: 1px solid var(--linea); border-radius: 8px; box-shadow: 0 8px 24px rgb(0 0 0 / 0.12); }
.resultados li { display: flex; gap: 10px; align-items: baseline; padding: 7px 8px; border-radius: 6px; cursor: pointer; }
.resultados li:hover, .resultados li:focus { background: var(--superficie-2); outline: none; }
.resultados li small { display: block; font-size: 0.74rem; color: var(--tinta-3); line-height: 1.3; }
.resultados li b { font-weight: 560; font-size: 0.86rem; }
.hint { margin: 0; font-size: 0.8rem; color: var(--tinta-3); }
</style>
