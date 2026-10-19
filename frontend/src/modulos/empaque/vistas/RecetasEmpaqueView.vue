<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Segmentos from '@/componentes/Segmentos.vue'
import { alCambiar } from '@/nucleo/cambios.js'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import ConstructorReceta from '@/modulos/empaque/componentes/ConstructorReceta.vue'
import ProbarEmpaque from '@/modulos/empaque/componentes/ProbarEmpaque.vue'
import ReglasEmpaque from '@/modulos/empaque/componentes/ReglasEmpaque.vue'

// Empaque: recetas (cómo se empaca un artículo, en N niveles del catálogo de
// tipos de empaque), reglas (qué receta lleva cada posición de OC) y probar
// (qué receta toma cada posición de una OC y por qué).
const route = useRoute()
const router = useRouter()
const VISTAS = computed(() => [['recetas', t('Recipes')], ['reglas', t('Rules')], ['probar', t('Test')]])
const vista = ref(['reglas', 'probar'].includes(route.query.vista) ? route.query.vista : 'recetas')
watch(vista, (v) => router.replace({ query: { ...route.query, vista: v === 'recetas' ? undefined : v } }))
const editable = computed(() => puede('catalogos.editar'))

const recetas = ref([])
const tipos = ref([])
const inactivas = ref(false)
const elegida = ref(null) // receta abierta en el constructor; 'nueva' para una receta nueva
async function cargar() {
  try {
    const [r, x] = await Promise.all([api.get('/recetas-empaque', { incluir_inactivas: inactivas.value }), api.get('/tipos-empaque')])
    recetas.value = r
    tipos.value = x
    if (elegida.value && elegida.value !== 'nueva') elegida.value = r.find((y) => y.id === elegida.value.id) || null
  } catch (e) {
    errorApi(e)
  }
}
onMounted(cargar)
watch(inactivas, cargar)
alCambiar(cargar, ['/recetas-empaque', '/tipos-empaque'])
function guardada(r) {
  cargar().then(() => (elegida.value = recetas.value.find((y) => y.id === r.id) || r))
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Packing recipes') }}</h1>
      <p>{{ t('How each item is packed, level by level (inner pack, carton, pallet…), and which recipe each PO line takes. The packaging types come from Master data.') }}</p>
    </div>
  </div>
  <Segmentos v-model="vista" :opciones="VISTAS" :etiqueta="t('View')" class="mb" />

  <div v-if="vista === 'recetas'" class="dos-columnas">
    <section class="panel lista-recetas">
      <div class="fila-flex">
        <button v-if="editable" type="button" class="btn btn-primario" @click="elegida = 'nueva'"><Icono nombre="mas" />{{ t('New recipe') }}</button>
        <label class="check separar"><input v-model="inactivas" type="checkbox" /> {{ t('Show inactive') }}</label>
      </div>
      <p v-if="!recetas.length" class="nota">{{ t('No recipes yet. Create one, or they are created by themselves from the casepack of the POs.') }}</p>
      <ul class="recetas">
        <li v-for="r in recetas" :key="r.id">
          <button type="button" class="receta" :class="{ activa: elegida && elegida !== 'nueva' && elegida.id === r.id, apagada: !r.activa }"
                  :aria-pressed="elegida && elegida !== 'nueva' && elegida.id === r.id" @click="elegida = r">
            <span class="nombre">{{ tx(r.nombre) }} <span v-if="r.automatica" class="etiqueta ms-0" :title="t('Created from the casepack of the POs')">{{ t('Automatic') }}</span>
              <span v-if="!r.activa" class="etiqueta ms-0">{{ t('Inactive') }}</span></span>
            <span class="ayuda">{{ tx(r.resumen) }}</span>
            <span class="ayuda">{{ t('{0} rules · {1} open PO lines', [r.usos?.reglas || 0, r.usos?.posiciones_abiertas || 0]) }}</span>
          </button>
        </li>
      </ul>
    </section>
    <section class="panel">
      <template v-if="elegida">
        <h2 class="mt-0">{{ elegida === 'nueva' ? t('New recipe') : tx(elegida.nombre) }}</h2>
        <ConstructorReceta :receta="elegida === 'nueva' ? null : elegida" :tipos="tipos" :editable="editable"
                           @guardada="guardada" @eliminada="elegida = null; cargar()" />
      </template>
      <p v-else class="ayuda">{{ t('Choose a recipe on the left to see and edit its levels.') }}</p>
    </section>
  </div>
  <ReglasEmpaque v-else-if="vista === 'reglas'" :editable="editable" />
  <ProbarEmpaque v-else :editable="editable" />
</template>

<style scoped>
.dos-columnas { display: grid; grid-template-columns: minmax(0, 340px) minmax(0, 1fr); gap: 16px; align-items: start; }
@media (max-width: 1000px) { .dos-columnas { grid-template-columns: 1fr; } }
.lista-recetas { display: flex; flex-direction: column; gap: 10px; }
.recetas { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
.receta { width: 100%; text-align: start; display: flex; flex-direction: column; gap: 2px; border: 1px solid var(--linea); border-radius: 8px;
  padding: 8px 10px; background: var(--superficie); cursor: pointer; color: inherit; font: inherit; }
.receta:hover { border-color: var(--borde-hover); }
.receta.activa { border-color: var(--acento); box-shadow: inset 3px 0 0 var(--acento); }
.receta.apagada { opacity: 0.6; }
.nombre { font-weight: 600; overflow-wrap: anywhere; }
.mb { margin-bottom: 12px; }
</style>
