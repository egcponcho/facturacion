<script setup>
// Flujo de clasificación: quién llena la ficha, qué ve el proveedor y cómo se
// aprueba. Cada interruptor se guarda al cambiarlo y aplica a todos los usuarios.
import { t, tx } from '@/i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Interruptor from '@/componentes/Interruptor.vue'
import { cargarSesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

const interruptores = ref([])
const guardando = ref('')

// Interruptores agrupados por etapa: captura de la ficha y aprobación
const GRUPOS = [
  { titulo: t('Who fills the technical sheet'), claves: ['proveedor_captura', 'interno_captura', 'proveedor_ve_sugerencia'] },
  { titulo: t('How a sheet is approved'), claves: ['revision_obligatoria', 'cuatro_ojos', 'aprobacion_lote'] },
]
const de = (k) => interruptores.value.find((x) => x.clave === k)

async function cargar() {
  try {
    interruptores.value = (await api.get('/flujo-clasificacion')).interruptores
  } catch (e) {
    errorApi(e)
  }
}

async function cambiar(x, valor) {
  guardando.value = x.clave
  try {
    interruptores.value = (await api.put('/flujo-clasificacion', { [x.clave]: valor })).interruptores
    avisar(t('Classification workflow updated.'))
    cargarSesion(true)
  } catch (e) {
    errorApi(e)
  } finally {
    guardando.value = ''
  }
}

onMounted(cargar)
</script>

<template>
  <section class="panel">
    <div class="panel-cabeza">
      <div>
        <h2>{{ t('Classification workflow') }}</h2>
        <p class="sub-panel">{{ t('Who fills the technical sheets and how they are approved. Roles say what each user can open; these switches say how the work is shared. Families, attributes and rules belong to roles with “Configure product families, attributes and rules”.') }}</p>
      </div>
    </div>
    <div class="flujo-grupos">
      <div v-for="g in GRUPOS" :key="g.titulo" class="flujo-grupo">
        <h3>{{ g.titulo }}</h3>
        <template v-for="k in g.claves" :key="k">
          <label v-if="de(k)" class="flujo-fila">
            <Interruptor :model-value="de(k).valor" :etiqueta="tx(de(k).etiqueta)" :deshabilitado="guardando === k" @update:model-value="cambiar(de(k), $event)" />
            <span><b>{{ tx(de(k).etiqueta) }}</b><small>{{ tx(de(k).ayuda) }}</small></span>
          </label>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.flujo-grupos { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.flujo-grupo h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); margin: 0 0 8px; }
.flujo-fila { display: flex; gap: 12px; align-items: flex-start; padding: 10px 0; border-top: 1px solid var(--linea); cursor: pointer; }
.flujo-fila span { display: flex; flex-direction: column; gap: 2px; }
.flujo-fila small { color: var(--tinta-3); line-height: 1.35; }
</style>
