<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref } from 'vue'
import PanelLateral from '@/componentes/PanelLateral.vue'
import Icono from '@/componentes/Icono.vue'
import { api } from '@/nucleo/api'
import { sesion } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'

// «Personalizar panel»: cada persona elige qué bloques ve en su Inicio y sus
// cuatro indicadores. Se guarda en su perfil (PUT /perfil/inicio y
// PUT /tableros/inicio/propios); «Volver a lo de fábrica» borra su elección.
const props = defineProps({
  bloques: { type: Array, required: true }, // [{ clave, titulo, texto, icono }] que su rol puede ver
  elegidos: { type: Array, required: true }, // claves de bloques puestos
  catalogo: { type: Array, default: () => [] }, // indicadores que puede ver (tableros/inicio)
  indicadores: { type: Array, default: () => [] }, // los cuatro elegidos
})
const emit = defineEmits(['cerrar', 'guardado'])
const MAX = 4

const puestos = ref(new Set(props.elegidos))
const kpis = ref([...props.indicadores])
const guardando = ref(false)
function alternar(clave) {
  const s = new Set(puestos.value)
  if (s.has(clave)) s.delete(clave)
  else s.add(clave)
  puestos.value = s
}
function alternarKpi(clave) {
  kpis.value = kpis.value.includes(clave) ? kpis.value.filter((k) => k !== clave) : [...kpis.value, clave].slice(0, MAX)
}
const lleno = computed(() => kpis.value.length >= MAX)

async function guardar(fabrica = false) {
  guardando.value = true
  try {
    const r = await api.put('/perfil/inicio', { bloques: fabrica ? null : [...puestos.value] })
    if (props.catalogo.length) await api.put('/tableros/inicio/propios', { claves: fabrica ? null : kpis.value })
    if (sesion.usuario) sesion.usuario.preferencias = { ...(sesion.usuario.preferencias || {}), inicio_bloques: fabrica ? undefined : r.bloques }
    avisar(t('Home updated.'))
    emit('guardado')
  } catch (e) {
    errorApi(e)
  } finally {
    guardando.value = false
  }
}
</script>

<template>
  <PanelLateral :titulo="t('Customize panel')" :detalle="t('Choose what you see on your Home. It only changes for you.')" @cerrar="emit('cerrar')">
    <h3 class="subtitulo">{{ t('Blocks') }}</h3>
    <ul class="bloques">
      <li v-for="b in bloques" :key="b.clave">
        <label class="bloque-op" :class="{ puesto: puestos.has(b.clave) }">
          <input type="checkbox" :checked="puestos.has(b.clave)" @change="alternar(b.clave)" />
          <span class="mini" aria-hidden="true"><Icono :nombre="b.icono" :tam="18" /></span>
          <span><b>{{ tx(b.titulo) }}</b><small>{{ tx(b.texto) }}</small></span>
        </label>
      </li>
    </ul>

    <template v-if="catalogo.length">
      <h3 class="subtitulo">{{ t('Your {0} indicators', [MAX]) }} <span class="ayuda">{{ t('{0} of {1} chosen', [kpis.length, MAX]) }}</span></h3>
      <ul class="bloques">
        <li v-for="c in catalogo" :key="c.clave">
          <label class="bloque-op compacto" :class="{ puesto: kpis.includes(c.clave) }" :title="tx(c.formula)">
            <input type="checkbox" :checked="kpis.includes(c.clave)" :disabled="lleno && !kpis.includes(c.clave)" @change="alternarKpi(c.clave)" />
            <span><b>{{ tx(c.titulo) }}</b><small>{{ tx(c.momento === 'hoy' ? t('Current state, today') : t('Last 30 days, with its trend')) }}</small></span>
          </label>
        </li>
      </ul>
    </template>

    <template #pie>
      <button type="button" class="btn btn-fantasma" :disabled="guardando" @click="guardar(true)">{{ t('Back to the standard Home') }}</button>
      <span class="separar"></span>
      <button type="button" class="btn" @click="emit('cerrar')">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" :disabled="guardando" @click="guardar()">{{ t('Save') }}</button>
    </template>
  </PanelLateral>
</template>

<style scoped>
.bloques { list-style: none; margin: 0 0 20px; padding: 0; display: grid; gap: 8px; }
.bloque-op { display: flex; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--linea); border-radius: var(--radio); background: var(--superficie); cursor: pointer; }
.bloque-op.puesto { border-color: var(--acento); background: var(--acento-claro); }
.bloque-op b { display: block; font-weight: 600; }
.bloque-op small { color: var(--tinta-3); font-size: var(--t-sm); }
.bloque-op.compacto { padding: 8px 12px; }
.mini { width: 48px; height: 34px; border-radius: 4px; background: var(--superficie-2); border: 1px solid var(--linea); flex: none; display: grid; place-items: center; color: var(--tinta-3); }
</style>
