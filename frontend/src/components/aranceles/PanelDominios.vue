<script setup>
import { t, tx } from '../../i18n/index.js'
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Icono from '../Icono.vue'
import SelectBusqueda from '../SelectBusqueda.vue'
import { puede } from '../../stores/sesion'
import { errorApi } from '../../stores/ui'

// Dominios de clasificación (químicos, materias primas, calzado, ropa,
// accesorios…) y los capítulos con que se relacionan. PRIMARY genera
// candidatos automáticos; SECONDARY queda disponible si los datos lo justifican.
const edita = puede('aranceles.editar')
const dominios = ref([])
const capitulos = ref([])
const nuevo = ref({})

async function cargar() {
  try {
    dominios.value = await api.get('/aranceles/oficial/dominios')
  } catch (e) {
    errorApi(e)
  }
}
onMounted(async () => {
  cargar()
  const r = await api.get('/aranceles/oficial/capitulos').catch(() => ({ items: [] }))
  capitulos.value = r.items.map((c) => ({ valor: c.capitulo, texto: `${c.capitulo} · ${c.titulo}`, sub: c.seccion ? t('Section {0}', [c.seccion]) : '' }))
})
async function guardar(d, cap, datos) {
  try {
    await api.put(`/aranceles/oficial/dominios/${d.id}/capitulos/${cap}`, datos)
    await cargar()
  } catch (e) {
    errorApi(e)
  }
}
function agregar(d) {
  const cap = nuevo.value[d.id]
  if (!cap) return
  guardar(d, cap, { relevancia: 'SECONDARY', habilitado: true })
  nuevo.value[d.id] = ''
}
</script>

<template>
  <section class="dominios">
    <p class="ayuda">{{ t('The commercial domain only helps choose questions and candidates. The legal result always comes from the tariff text, legal notes and rules; a domain never forces or excludes a chapter.') }}</p>
    <article v-for="d in dominios" :key="d.id" class="panel dominio" :class="{ apagado: !d.activo }">
      <header>
        <div><h3>{{ tx(d.nombre) }} <span class="codigo ayuda">{{ tx(d.codigo) }}</span></h3><p class="ayuda">{{ tx(d.descripcion) }}</p></div>
        <span class="etiqueta">{{ tx(d.modo === 'AUTO' ? t('Automatic') : t('Manual')) }}</span>
      </header>
      <div class="caps">
        <span v-for="c in d.capitulos" :key="c.id" class="cap" :class="[c.relevancia === 'PRIMARY' ? 'primario' : 'secundario', { off: !c.capitulo_habilitado }]"
              :title="tx(`${c.titulo}${c.capitulo_habilitado ? '' : ' · ' + t('chapter not enabled')}`)">
          <b>{{ tx(c.capitulo) }}</b>
          <button v-if="edita" type="button" class="mini" :title="tx(c.relevancia === 'PRIMARY' ? t('Make secondary') : t('Make primary'))"
                  @click="guardar(d, c.capitulo, { relevancia: c.relevancia === 'PRIMARY' ? 'SECONDARY' : 'PRIMARY' })">{{ c.relevancia === 'PRIMARY' ? 'P' : 'S' }}</button>
          <button v-if="edita" type="button" class="mini" :aria-label="t('Remove chapter {0}', [c.capitulo])" @click="guardar(d, c.capitulo, { quitar: true })">×</button>
        </span>
      </div>
      <div v-if="edita" class="agregar">
        <SelectBusqueda v-model="nuevo[d.id]" :opciones="capitulos.filter((c) => !d.capitulos.some((x) => x.capitulo === c.valor))" :placeholder="t('Add a chapter…')" :etiqueta="t('Chapter')" />
        <button class="btn btn-chico" :disabled="!nuevo[d.id]" @click="agregar(d)"><Icono nombre="mas" :tam="14" />{{ t('Add') }}</button>
      </div>
    </article>
    <p class="ayuda leyenda"><span class="cap primario"><b>P</b></span> {{ t('Primary: automatic candidates') }} · <span class="cap secundario"><b>S</b></span> {{ t('Secondary: available when the data justifies it') }} · <span class="cap off"><b>—</b></span> {{ t('chapter not enabled') }}</p>
  </section>
</template>

<style scoped>
.dominios { display: grid; gap: 12px; }
.dominio header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.dominio h3 { margin: 0; font-size: 1.05rem; }
.dominio p { margin: 2px 0 0; }
.caps { display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }
.cap { display: inline-flex; align-items: center; gap: 3px; padding: 2px 6px; border-radius: 8px; font-size: 0.82rem; border: 1px solid var(--linea); }
.cap.primario { background: var(--acento-claro); color: var(--acento-texto); border-color: transparent; }
.cap.secundario { background: var(--superficie-2); }
.cap.off { opacity: 0.5; text-decoration: line-through; }
.mini { border: 0; background: none; cursor: pointer; color: inherit; font-size: 0.72rem; padding: 0 2px; opacity: 0.7; }
.mini:hover { opacity: 1; }
.agregar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.agregar :deep(.sb) { min-width: 260px; }
.leyenda { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
</style>
