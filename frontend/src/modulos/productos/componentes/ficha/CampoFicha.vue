<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed } from 'vue'
import FiltroMulti from '@/componentes/FiltroMulti.vue'
import Seleccion from '@/componentes/Seleccion.vue'

// Un dato de la ficha tal como lo describe el motor del servidor (tipo, opciones,
// bloqueos, si es obligatorio, si decide el código, si se llenó solo). Sirve para
// cualquier atributo de cualquier categoría, también los creados en la configuración.
const props = defineProps({
  campo: { type: Object, required: true },
  valor: { default: null },
  editable: Boolean,
})
const emit = defineEmits(['elegir'])

const c = computed(() => props.campo)
const ops = computed(() => (c.value.opciones || []))
const botones = computed(() => c.value.tipo_dato === 'select' && c.value.control !== 'lista' && ops.value.length <= 6)
const largo = computed(() => ['text', 'composition'].includes(c.value.tipo_dato) && /description|descripcion|function|use/.test(c.value.codigo))
const id = computed(() => `c_${c.value.codigo.replace(/\W/g, '_')}`)
const vacio = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)

function numero(e) {
  const v = e.target.value
  emit('elegir', v === '' ? '' : Number(v))
}
</script>

<template>
  <label v-if="c.tipo_dato === 'boolean'" class="check-f" :title="tx(c.bloqueo_casilla || '')">
    <input type="checkbox" :checked="valor === true" :disabled="!editable || (!!c.bloqueo_casilla && valor !== true)" @change="emit('elegir', $event.target.checked)" />
    <span>{{ tx(c.etiqueta) }}<span v-if="c.auto && valor === true" class="auto-tag">auto</span>
      <span v-if="c.discrimina && !c.respondida" class="etiqueta acento disc">{{ t('decides the code') }}</span></span>
  </label>
  <div v-else class="campo-f" :class="{ ancho: largo }">
    <label :for="id" class="lbl-f"><span :class="{ req: c.modo === 'REQUIRE' }">{{ tx(c.etiqueta) }}</span>
      <span v-if="c.ayuda && !largo" class="opcional"> ({{ tx(c.ayuda) }})</span><span v-if="c.unidad" class="opcional"> ({{ tx(c.unidad) }})</span>
      <span v-if="c.auto && !vacio(valor)" class="auto-tag">auto</span>
      <span v-if="c.discrimina && !c.respondida" class="etiqueta acento disc">{{ t('decides the code') }}</span></label>
    <div v-if="botones" class="segs" role="radiogroup" :aria-label="tx(c.etiqueta)">
      <button v-for="o in ops" :key="o.codigo" type="button" role="radio" :aria-checked="valor === o.codigo"
              :disabled="!editable || (o.bloqueada && valor !== o.codigo)" :title="tx(o.motivo || '')" @click="emit('elegir', o.codigo)">{{ tx(o.etiqueta) }}</button>
    </div>
    <Seleccion v-else-if="c.tipo_dato === 'select'" :id="id" class="entrada" :value="valor || ''" :disabled="!editable" @change="emit('elegir', $event)">
      <option value="">{{ t('Choose…') }}</option>
      <option v-for="o in ops" :key="o.codigo" :value="o.codigo" :disabled="o.bloqueada && valor !== o.codigo">{{ tx(o.etiqueta) }}</option>
    </Seleccion>
    <FiltroMulti v-else-if="c.tipo_dato === 'multi_select'" :model-value="valor || []" :etiqueta="tx(c.etiqueta)" vacio="—"
                 :opciones="ops.filter((o) => !o.bloqueada).map((o) => ({ valor: o.codigo, texto: o.etiqueta }))" @update:model-value="(v) => emit('elegir', v)" />
    <span v-else-if="c.tipo_dato === 'country'" class="chips-f">
      <span v-for="x in (valor || [])" :key="x" class="etiqueta">{{ tx(x) }}</span>
      <small class="opcional">{{ t('From the product destinations') }}</small>
    </span>
    <input v-else-if="c.tipo_dato === 'number'" :id="id" class="entrada" type="number" step="any" :value="valor ?? ''" :disabled="!editable" @input="numero" />
    <textarea v-else-if="largo" :id="id" class="entrada" rows="2" maxlength="600" :value="valor || ''" :disabled="!editable" :placeholder="tx(c.ayuda || '')"
              @input="emit('elegir', $event.target.value)"></textarea>
    <input v-else :id="id" class="entrada" type="text" maxlength="300" :value="valor ?? ''" :disabled="!editable" @input="emit('elegir', $event.target.value)" />
    <small v-if="c.nota_ambito" class="hint">{{ tx(c.nota_ambito) }}</small>
  </div>
</template>

<style scoped>
.campo-f { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; min-width: 0; }
.campo-f.ancho { grid-column: 1 / -1; }
.lbl-f { font-size: 0.84rem; font-weight: 620; color: var(--tinta); }
.opcional { font-weight: 400; color: var(--tinta-3); }
.hint { font-size: 0.78rem; color: var(--tinta-3); }
.segs { display: flex; flex-wrap: wrap; gap: 6px; }
.segs button { padding: 6px 12px; font-size: 0.88rem; border: 1px solid var(--linea); border-radius: 7px; background: var(--superficie-2); color: var(--tinta); cursor: pointer; font-family: inherit; }
.segs button:hover:not(:disabled) { border-color: var(--acento); }
.segs button[aria-checked='true'] { background: var(--acento-claro); border-color: var(--acento); color: var(--acento-texto); font-weight: 620; }
.segs button:disabled { opacity: 0.42; border-style: dashed; background: transparent; cursor: not-allowed; }
.segs button[aria-checked='true']:disabled { opacity: 1; border-style: solid; }
.check-f { display: flex; gap: 8px; align-items: flex-start; font-size: 0.9rem; margin-bottom: 12px; cursor: pointer; grid-column: 1 / -1; }
.check-f input { margin-top: 3px; accent-color: var(--acento); }
.auto-tag { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ok); margin-inline-start: 6px; }
.disc { margin-inline-start: 6px; font-size: 0.7rem; }
.chips-f { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
textarea.entrada { resize: vertical; }
</style>
