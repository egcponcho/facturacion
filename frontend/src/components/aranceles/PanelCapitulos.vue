<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../../api'
import BarraSeleccion from '../BarraSeleccion.vue'
import Icono from '../Icono.vue'
import Interruptor from '../Interruptor.vue'
import SelectBusqueda from '../SelectBusqueda.vue'
import { puede } from '../../stores/sesion'
import { avisar, errorApi } from '../../stores/ui'
import { fmtNum, useSeleccion } from '../../utils'

// Control de capítulos del SAC: qué capítulos usa el clasificador, cuáles
// generan candidatos automáticos y cuáles solo se eligen a mano. Los dominios
// son una ayuda; nunca obligan ni excluyen un capítulo por sí solos.
const edita = puede('aranceles.editar')
const datos = ref({ items: [], total: 0, habilitados: 0 })
const dominios = ref([])
const f = reactive({ q: '', estado: '', dominio: '' })
const sel = useSeleccion()
const ocupado = ref(false)
const ESTADOS = [['', t('All')], ['habilitados', t('Enabled')], ['manuales', t('Manual only')], ['inactivos', t('Inactive')]]
const CAMPOS = [['activo', t('Active')], ['clasificacion', t('Classification enabled')], ['candidato_auto', t('Automatic candidate')],
  ['solo_manual', t('Manual only')], ['archivado', t('Archived')]]

let temporizador = null
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/oficial/capitulos', { q: f.q || undefined, estado: f.estado || undefined, dominio: f.dominio || undefined })
  } catch (e) {
    errorApi(e)
  }
}
function buscar() {
  clearTimeout(temporizador)
  temporizador = setTimeout(cargar, 250)
}
onMounted(async () => {
  cargar()
  dominios.value = await api.get('/aranceles/oficial/dominios').catch(() => [])
})

async function cambiar(ids, campos, msg) {
  ocupado.value = true
  try {
    await api.patch('/aranceles/oficial/capitulos', { ids, ...campos })
    if (msg) avisar(msg)
    await cargar()
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
const ids = computed(() => datos.value.items.map((c) => c.id))
const seleccion = computed(() => sel.lista())
const bloque = (campos, msg) => cambiar(seleccion.value, campos, msg).then(() => sel.limpiar())
</script>

<template>
  <section>
    <div class="resumen-caps">
      <div><b>{{ fmtNum(datos.habilitados) }}</b><span>{{ t('of {0} chapters enabled for classification', [datos.total]) }}</span></div>
      <p class="ayuda">{{ t('Only active, enabled chapters are proposed automatically. Manual-only chapters can be chosen by a specialist. Domains are a hint for questions and candidates; they never force or exclude a chapter.') }}</p>
    </div>
    <div class="filtros" v-filtros>
      <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Chapter, title or section')" :aria-label="t('Search')" @input="buscar" /></label>
      <div class="segmentos" role="group" :aria-label="t('Status')">
        <button v-for="[v, txt] in ESTADOS" :key="v" class="segmento" :aria-pressed="f.estado === v" @click="f.estado = v; cargar()">{{ tx(txt) }}</button>
      </div>
      <SelectBusqueda v-model="f.dominio" :opciones="dominios.map((d) => ({ valor: d.codigo, texto: d.nombre }))" :vacio="t('All domains')" :etiqueta="t('Domain')" @update:model-value="cargar" />
    </div>
    <div class="tabla-marco tabla-fija">
      <table class="tabla" v-tarjetas>
        <thead>
          <tr>
            <th v-if="edita" class="chk"><input type="checkbox" :aria-label="t('Select all')" :checked="sel.todos(ids)" @change="sel.alternarTodos(ids)" /></th>
            <th>{{ t('Chapter') }}</th>
            <th>{{ t('Title') }}</th>
            <th>{{ t('Domains') }}</th>
            <th v-for="[c, txt] in CAMPOS" :key="c" class="centro">{{ tx(txt) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in datos.items" :key="c.id" :class="{ seleccionada: sel.tiene(c.id), apagado: !c.activo }">
            <td v-if="edita" class="chk"><input type="checkbox" :aria-label="t('Select chapter {0}', [c.capitulo])" :checked="sel.tiene(c.id)" @change="sel.alternar(c.id)" /></td>
            <td class="codigo fuerte">{{ tx(c.capitulo) }}<span class="sub">{{ t('Section {0}', [c.seccion || '—']) }}</span></td>
            <td class="envolver">{{ tx(c.titulo) }}<span v-if="c.nota" class="sub">{{ tx(c.nota) }}</span></td>
            <td><span v-for="d in c.dominios" :key="d.codigo" class="etiqueta" :class="d.relevancia === 'PRIMARY' ? 'acento' : ''" :title="tx(d.relevancia === 'PRIMARY' ? t('Primary') : t('Secondary'))">{{ tx(d.nombre) }}</span></td>
            <td v-for="[campo, txt] in CAMPOS" :key="campo" class="centro">
              <Interruptor :model-value="c[campo]" :etiqueta="t('{0}: chapter {1}', [txt, c.capitulo])" :deshabilitado="!edita || ocupado"
                           @update:model-value="(v) => cambiar([c.id], { [campo]: v })" />
            </td>
          </tr>
          <tr v-if="!datos.items.length"><td colspan="9" class="vacio">{{ t('No chapters match these filters.') }}</td></tr>
        </tbody>
      </table>
    </div>
    <BarraSeleccion v-if="edita" :cantidad="sel.ids.size" :singular="t('chapter selected')" :plural="t('chapters selected')" @limpiar="sel.limpiar()">
      <button class="btn btn-primario" :disabled="ocupado" @click="bloque({ clasificacion: true }, t('Chapters enabled for classification.'))">{{ t('Enable classification') }}</button>
      <button class="btn" :disabled="ocupado" @click="bloque({ candidato_auto: true }, t('Automatic candidates on.'))">{{ t('Automatic candidates') }}</button>
      <button class="btn" :disabled="ocupado" @click="bloque({ solo_manual: true }, t('Manual only.'))">{{ t('Manual only') }}</button>
      <button class="btn" :disabled="ocupado" @click="bloque({ clasificacion: false, candidato_auto: false }, t('Classification disabled.'))">{{ t('Disable') }}</button>
      <button class="btn btn-peligro" :disabled="ocupado" @click="bloque({ archivado: true }, t('Chapters archived.'))">{{ t('Archive') }}</button>
    </BarraSeleccion>
  </section>
</template>

<style scoped>
.resumen-caps { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: baseline; margin-bottom: 10px; }
.resumen-caps b { font-size: 1.4rem; margin-inline-end: 6px; }
.resumen-caps .ayuda { margin: 0; flex: 1 1 380px; }
.centro { text-align: center; }
td .etiqueta { margin: 1px 3px 1px 0; }
</style>
