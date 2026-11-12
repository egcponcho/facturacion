<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import { avisar, errorApi } from '@/stores/ui'

// Una sección de la familia: lo que un módulo guarda de ella (GET/PUT
// /grupos-producto/{id}/secciones/{clave}). La familia es una sola; cada módulo
// agrega aquí lo suyo y la pantalla de configuración de ese módulo muestra lo mismo.
const props = defineProps({
  familiaId: { type: Number, required: true },
  seccion: { type: Object, required: true }, // {clave, nombre, datos, editable}
})
const emit = defineEmits(['guardada'])
const borrador = ref(null)
const guardando = ref(false)
function copiar() {
  const d = props.seccion.datos || {}
  borrador.value = { dias_extra: d.dias_extra ?? '', categoria: d.categoria || '', campos: (d.campos || []).map((c) => ({ ...c })) }
}
watch(() => props.seccion, copiar, { immediate: true })

// Etiquetado: los campos que esperan las etiquetas de sus productos (vocabulario de las etiquetas)
const camposEtiqueta = ref([])
const buscar = ref('')
onMounted(() => {
  if (props.seccion.clave === 'etiquetado') {
    api.get('/etiquetas/campos', { sujeto: 'ARTICULO' })
      .then((r) => (camposEtiqueta.value = r.campos.filter((c) => ['articulo', 'producto'].includes(c.grupo)))).catch(() => {})
  }
})
const nombreCampo = (clave) => tx(camposEtiqueta.value.find((c) => c.clave === clave)?.etiqueta || clave)
const marcado = (clave) => borrador.value.campos.find((c) => c.campo === clave)
// Sin búsqueda se ofrecen los datos que una etiqueta suele pedir; con búsqueda, cualquiera
const HABITUALES = ['articulo.codigo_barras', 'articulo.peso_unitario', 'articulo.codigo_proveedor', 'producto.marca',
  'producto.descripcion_comercial', 'producto.pais_origen']
const visibles = computed(() => {
  const q = buscar.value.trim().toLowerCase()
  return camposEtiqueta.value.filter((c) => marcado(c.clave)
    || (q ? `${c.clave} ${tx(c.etiqueta)}`.toLowerCase().includes(q) : props.seccion.editable && HABITUALES.includes(c.clave)))
})
function alternar(clave, como) {
  const lista = borrador.value.campos
  const x = marcado(clave)
  if (como === 'quitar') borrador.value.campos = lista.filter((c) => c.campo !== clave)
  else if (x) x.obligatorio = como === 'obligatorio'
  else lista.push({ campo: clave, obligatorio: como === 'obligatorio' })
}

async function guardar() {
  const b = borrador.value
  const cuerpo = props.seccion.clave === 'logistica'
    ? { dias_extra: b.dias_extra === '' || b.dias_extra === null ? null : Number(b.dias_extra) }
    : props.seccion.clave === 'comex' ? { categoria: b.categoria || null } : { campos: b.campos }
  guardando.value = true
  try {
    const r = await api.put(`/grupos-producto/${props.familiaId}/secciones/${props.seccion.clave}`, cuerpo)
    avisar(t('Saved.'))
    emit('guardada', r)
  } catch (e) {
    errorApi(e)
  } finally {
    guardando.value = false
  }
}
</script>

<template>
  <div class="seccion">
    <!-- Logística -->
    <template v-if="seccion.clave === 'logistica'">
      <label class="campo"><span>{{ t('Extra days to the store') }}</span>
        <input v-model="borrador.dias_extra" type="number" min="0" max="365" class="ancho-s" :disabled="!seccion.editable" />
        <small class="ayuda">{{ t('Days its products add after the port (inspection, labeling…) when estimating the date in store. Empty: the ones of the parent family, or none.') }}
          {{ t('Today it uses {0}.', [seccion.datos.efectivos ?? 0]) }}</small></label>
    </template>

    <!-- Comercio exterior -->
    <template v-else-if="seccion.clave === 'comex'">
      <label class="campo"><span>{{ t('Customs category') }}</span>
        <select v-model="borrador.categoria" :disabled="!seccion.editable">
          <option value="">{{ t('The one of the parent family') }}</option>
          <option v-for="c in seccion.datos.categorias" :key="c.codigo" :value="c.codigo">{{ tx(c.nombre) }}</option>
        </select>
        <small class="ayuda">{{ t('The technical sheets of its products start with this category (what the product is), and the classification engine uses it while a sheet has none.') }}
          <template v-if="seccion.datos.efectiva">{{ t('Today it uses {0}.', [tx(seccion.datos.efectiva_nombre || seccion.datos.efectiva)]) }}</template></small></label>
      <p v-if="seccion.datos.productos_sin_categoria" class="ayuda">
        {{ t('{0} products of this family have no category in their sheet yet.', [seccion.datos.productos_sin_categoria]) }}</p>
    </template>

    <!-- Etiquetado -->
    <template v-else-if="seccion.clave === 'etiquetado'">
      <p class="ayuda mt-0">{{ t('Fields the labels of its products expect. A required one that is empty stops the labels from being printed until it is filled.') }}</p>
      <p v-if="seccion.datos.heredados?.length" class="ayuda">{{ t('From the families that contain it') }}:
        {{ seccion.datos.heredados.map((c) => nombreCampo(c.campo) + (c.obligatorio ? ' *' : '')).join(' · ') }}</p>
      <input v-if="seccion.editable" v-model="buscar" type="search" :placeholder="t('Search a field (barcode, weight, brand…)')" :aria-label="t('Search a field')" />
      <ul class="campos">
        <li v-for="c in visibles" :key="c.clave">
          <span class="crece">{{ tx(c.etiqueta) }}</span>
          <template v-if="seccion.editable">
            <label class="check"><input type="checkbox" :checked="!!marcado(c.clave)"
                   @change="alternar(c.clave, $event.target.checked ? 'habitual' : 'quitar')" /> {{ t('Usual') }}</label>
            <label class="check"><input type="checkbox" :checked="!!marcado(c.clave)?.obligatorio"
                   @change="alternar(c.clave, $event.target.checked ? 'obligatorio' : 'habitual')" /> {{ t('Required') }}</label>
          </template>
          <span v-else-if="marcado(c.clave)?.obligatorio" class="etiqueta ms-0">{{ t('Required') }}</span>
        </li>
        <li v-if="!visibles.length" class="ayuda">{{ buscar ? t('No field matches the search.') : t('No fields yet.') }}</li>
      </ul>
      <router-link :to="{ path: '/etiquetas/configuracion', query: { paso: 'familias', familia: familiaId } }" class="enlace">
        <Icono nombre="etiqueta" :tam="14" /> {{ t('Its label designs ({0} rules)', [seccion.datos.reglas || 0]) }}</router-link>
    </template>

    <!-- Empaque -->
    <template v-else-if="seccion.clave === 'empaque'">
      <p class="ayuda mt-0">{{ t('Packing rules that choose the packing recipe of its products.') }}</p>
      <ul v-if="seccion.datos.reglas?.length" class="campos">
        <li v-for="r in seccion.datos.reglas" :key="r.id" :class="{ apagado: !r.activa }">
          <span class="crece"><strong>{{ tx(r.receta) }}</strong> <span class="codigo">{{ r.receta_codigo }}</span></span>
          <span v-if="r.condiciones.length" class="ayuda">{{ t('{0} conditions', [r.condiciones.length]) }}</span>
          <span v-if="!r.activa" class="etiqueta ms-0">{{ t('Inactive') }}</span>
        </li>
      </ul>
      <p v-else class="ayuda">{{ t('No packing rules for this family: the ones of the families that contain it or of the whole company apply.') }}</p>
      <router-link to="/empaque/recetas" class="enlace"><Icono nombre="caja" :tam="14" /> {{ t('Packing recipes and rules') }}</router-link>
    </template>

    <div v-if="seccion.editable && seccion.clave !== 'empaque'" class="pie">
      <button type="button" class="btn btn-primario" :disabled="guardando" @click="guardar">{{ t('Save') }}</button>
    </div>
  </div>
</template>

<style scoped>
.seccion { display: flex; flex-direction: column; gap: 10px; }
.campos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 320px; overflow: auto; }
.campos li { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 4px 0; border-bottom: 1px solid var(--linea-suave); }
.campos li.apagado { opacity: 0.6; }
.crece { flex: 1 1 160px; min-width: 0; }
.codigo { font-family: var(--mono, monospace); font-size: var(--t-sm); color: var(--tinta-3); }
.pie { display: flex; justify-content: flex-end; }
</style>
