<script setup>
import { t, tx } from '@/i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import { errorApi } from '@/stores/ui'

// Cómo se empaca el producto: las reglas que pueden aplicarle, en el orden en
// que compiten (la más específica primero), y las recetas con que se pidió.
// Qué regla gana en cada OC depende de sus datos (destino, origen…).
const props = defineProps({ productoId: { type: Number, required: true } })
const d = ref(null)
onMounted(async () => {
  try {
    d.value = await api.get(`/productos/${props.productoId}/empaque`)
  } catch (e) {
    errorApi(e)
  }
})
const ORIGEN = { MANUAL: t('chosen by hand'), REGLA: t('by rule'), DATOS: t('from the PO data') }
</script>

<template>
  <div v-if="!d" class="esqueleto" style="height: 120px" />
  <div v-else class="emp-secciones">
    <section class="panel">
      <h3>{{ t('Packing rules that can apply') }}</h3>
      <p class="ayuda">{{ t('The most specific rule wins (item, product, family, company); with conditions before without. Which one applies to each PO depends on its data.') }}</p>
      <p v-if="!d.reglas.length" class="ayuda">{{ t('No packing rule applies to this product.') }}</p>
      <ol v-else class="emp-lista">
        <li v-for="r in d.reglas" :key="r.regla_id">
          <b>{{ tx(r.receta) }}</b> <span v-if="r.resumen" class="apagado">({{ tx(r.resumen) }})</span>
          <span class="sub">{{ t('For {0}', [tx(r.destino)]) }}<template v-if="r.condiciones"> · {{ t('if {0}', [tx(r.condiciones)]) }}</template></span>
        </li>
      </ol>
      <router-link to="/empaque/recetas" class="enlace">{{ t('Manage packing recipes and rules') }}</router-link>
    </section>
    <section class="panel">
      <h3>{{ t('Recipes used in its PO lines') }}</h3>
      <p v-if="!d.en_uso.length" class="ayuda">{{ t('No PO line of this product has a packing recipe yet.') }}</p>
      <ul v-else class="emp-lista">
        <li v-for="u in d.en_uso" :key="u.receta_id">
          <b>{{ tx(u.receta) }}</b> <span v-if="u.resumen" class="apagado">({{ tx(u.resumen) }})</span>
          <span class="sub">{{ t('{0} PO lines', [u.posiciones]) }}<template v-if="u.origenes.length"> · {{ u.origenes.map((o) => ORIGEN[o] || o).join(', ') }}</template></span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.emp-secciones { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.emp-secciones h3 { margin: 0 0 6px; }
.emp-lista { margin: 8px 0; padding-inline-start: 18px; display: flex; flex-direction: column; gap: 8px; }
.emp-lista .sub { display: block; color: var(--tinta-3); font-size: 0.86rem; }
</style>
