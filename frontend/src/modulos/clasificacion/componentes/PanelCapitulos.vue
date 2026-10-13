<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import BarraSeleccion from '@/componentes/BarraSeleccion.vue'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtNum } from '@/nucleo/utils'

// Control de capítulos del SAC: qué capítulos usa el clasificador, cuáles
// generan candidatos automáticos y cuáles solo se eligen a mano. Los dominios
// son una ayuda; nunca obligan ni excluyen un capítulo por sí solos.
const edita = puede('aranceles.editar')
const datos = ref({ items: [], total: 0, habilitados: 0 })
const dominios = ref([])
const f = reactive({ q: '', estado: '', dominio: '' })
const sel = ref([])
const cargando = ref(true)
const ocupado = ref(false)
const ESTADOS = [['', t('All')], ['habilitados', t('Enabled')], ['manuales', t('Manual only')], ['inactivos', t('Inactive')]]
const CAMPOS = [['activo', t('Active')], ['clasificacion', t('Classification enabled')], ['candidato_auto', t('Automatic candidate')],
  ['solo_manual', t('Manual only')], ['archivado', t('Archived')]]

let temporizador = null
async function cargar() {
  try {
    datos.value = await api.get('/aranceles/oficial/capitulos', { q: f.q || undefined, estado: f.estado || undefined, dominio: f.dominio || undefined })
    const hay = new Set(datos.value.items.map((c) => c.id))
    sel.value = sel.value.filter((id) => hay.has(id))
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
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
const SI_NO = [[true, t('Yes')], [false, t('No')]]
const columnas = computed(() => [
  { clave: 'capitulo', texto: t('Chapter'), fija: true, prioridad: 1 },
  { clave: 'seccion', texto: t('Section'), prioridad: 3, textoValor: (v) => v || '—' },
  { clave: 'titulo', texto: t('Title'), prioridad: 1, filtro: false },
  { clave: 'dominios', texto: t('Domains'), prioridad: 2, valor: (c) => c.dominios.map((d) => d.nombre), ordenable: false },
  ...CAMPOS.map(([clave, texto]) => ({ clave, texto, prioridad: 3, opciones: SI_NO })),
])
const bloque = (campos, msg) => cambiar(sel.value, campos, msg).then(() => (sel.value = []))
</script>

<template>
  <section>
    <div class="resumen-caps">
      <div><b>{{ fmtNum(datos.habilitados) }}</b><span>{{ t('of {0} chapters enabled for classification', [datos.total]) }}</span></div>
      <p class="ayuda">{{ t('Only active, enabled chapters are proposed automatically. Manual-only chapters can be chosen by a specialist. Domains are a hint for questions and candidates; they never force or exclude a chapter.') }}</p>
    </div>
    <TablaDatos tabla="aranceles_capitulos" :columnas="columnas" :filas="datos.items" :cargando="cargando" :por-pagina="50"
                :seleccionable="edita" v-model:seleccion="sel" :clase-fila="(c) => ({ apagada: !c.activo })" :etiqueta="t('Chapters')"
                :externos="{ q: f.q, estado: f.estado, dominio: f.dominio }"
                @vista="(x) => { Object.assign(f, { q: x.q || '', estado: x.estado || '', dominio: x.dominio || '' }); cargar() }"
                @limpiar-externos="Object.assign(f, { q: '', estado: '', dominio: '' }); cargar()">
      <template #barra>
        <label class="buscador"><Icono nombre="buscar" :tam="16" /><input v-model="f.q" type="search" :placeholder="t('Chapter, title or section')" :aria-label="t('Search')" @input="buscar" /></label>
      </template>
      <template #filtros>
        <div class="segmentos" role="group" :aria-label="t('Status')">
          <button v-for="[v, txt] in ESTADOS" :key="v" type="button" class="segmento" :aria-pressed="f.estado === v" @click="f.estado = v; cargar()">{{ tx(txt) }}</button>
        </div>
        <SelectBusqueda v-model="f.dominio" :opciones="dominios.map((d) => ({ valor: d.codigo, texto: d.nombre }))" :vacio="t('All domains')" :etiqueta="t('Domain')" @update:model-value="cargar" />
      </template>
      <template #celda-capitulo="{ fila: c }"><span class="codigo fuerte">{{ tx(c.capitulo) }}</span></template>
      <template #celda-seccion="{ fila: c }">{{ t('Section {0}', [c.seccion || '—']) }}</template>
      <template #celda-titulo="{ fila: c }"><div class="titulo-cap">{{ tx(c.titulo) }}<span v-if="c.nota" class="sub">{{ tx(c.nota) }}</span></div></template>
      <template #celda-dominios="{ fila: c }"><span v-for="d in c.dominios" :key="d.codigo" class="etiqueta" :class="d.relevancia === 'PRIMARY' ? 'acento' : ''" :title="tx(d.relevancia === 'PRIMARY' ? t('Primary') : t('Secondary'))">{{ tx(d.nombre) }}</span></template>
      <template v-for="[campo, txt] in CAMPOS" :key="campo" #[`celda-${campo}`]="{ fila: c }">
        <Interruptor :model-value="c[campo]" :etiqueta="t('{0}: chapter {1}', [txt, c.capitulo])" :deshabilitado="!edita || ocupado"
                     @update:model-value="(v) => cambiar([c.id], { [campo]: v })" />
      </template>
      <template #vacio>{{ t('No chapters match these filters.') }}</template>
    </TablaDatos>
    <BarraSeleccion v-if="edita" :cantidad="sel.length" :singular="t('chapter selected')" :plural="t('chapters selected')" @limpiar="sel = []">
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
.titulo-cap { min-width: 260px; max-width: 480px; white-space: normal; }
.etiqueta { margin: 1px 3px 1px 0; }
:deep(tr.apagada > td) { opacity: 0.6; }
</style>
