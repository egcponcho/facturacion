<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { fmtNum } from '@/nucleo/utils'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { CANTIDADES, SUJETOS, catalogos } from '@/modulos/etiquetado/etiquetas.js'

// Primer uso (la empresa no tiene tipos de etiqueta): qué etiquetas imprime,
// cómo agrupa sus artículos y un diseño para empezar con cada tipo. Al terminar
// quedan los tipos, las familias y un diseño normal en «Toda la empresa».
const emit = defineEmits(['cerrar', 'listo'])
const paso = ref(0)
const ocupado = ref(false)
const cat = ref(null)
const tipos = ref([])
const familias = ref('grupos')
const gruposSin = ref(0)
const disenos = reactive({ crear: puede('etiquetas.disenar'), tamano: {} })

onMounted(async () => {
  try {
    cat.value = await catalogos()
    tipos.value = cat.value.sugeridos.map((s) => ({ ...s, nombre: tx(s.nombre), elegido: s.sujeto !== 'DOCUMENTO' }))
    for (const s of cat.value.sugeridos) disenos.tamano[s.codigo] = s.sujeto === 'BULTO' ? 1 : s.sujeto === 'DOCUMENTO' ? 0 : 3
  } catch (e) {
    errorApi(e)
  }
  if (puede('etiquetas.familias')) {
    api.get('/etiquetas/grupos-articulos', { familia: 'sin' }).then((r) => (gruposSin.value = r.length)).catch(() => {})
  }
})
function otro() {
  const n = tipos.value.filter((x) => x.propio).length + 1
  tipos.value.push({ codigo: `TIPO_${n}`, nombre: '', sujeto: 'ARTICULO', cantidad: 'POR_UNIDAD', obligatoria: false, elegido: true, propio: true })
}
function cambiarSujeto(x) {
  if (!cat.value.cantidades[x.sujeto].includes(x.cantidad)) x.cantidad = cat.value.cantidades[x.sujeto][0]
}
const elegidos = computed(() => tipos.value.filter((x) => x.elegido && x.nombre.trim()))
const PASOS = () => [t('What labels do you print?'), t('How do you group your items to label them?'), t('A design to start with')]

async function terminar() {
  ocupado.value = true
  try {
    const creados = []
    for (const x of elegidos.value) {
      creados.push(await api.post('/etiquetas/tipos', { codigo: x.codigo, nombre: x.nombre.trim(), sujeto: x.sujeto, cantidad: x.cantidad,
        obligatoria: x.obligatoria }))
    }
    if (familias.value === 'grupos' && gruposSin.value) await api.post('/etiquetas/familias/desde-grupos', {})
    if (disenos.crear) {
      for (const tipo of creados) {
        const original = elegidos.value.find((x) => x.codigo === tipo.codigo)
        const tam = cat.value.tamanos[disenos.tamano[original?.codigo] ?? 0] || cat.value.tamanos[0]
        const p = await api.post('/etiquetas/plantillas', { nombre: `${tipo.nombre} ${tam.nombre}`, tipo_etiqueta_id: tipo.id,
          tamano: { ancho: tam.ancho, alto: tam.alto } })
        if (puede('etiquetas.configurar')) {
          await api.post('/etiquetas/usos', { tipo_etiqueta_id: tipo.id, plantilla_id: p.id, nivel: 'GENERAL', contexto_tipo: 'NINGUNO' })
        }
      }
    }
    avisar(t('Ready. Change any cell to fine-tune which design goes on what.'))
    emit('listo')
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <!-- En la página (no en una ventana): los tres pasos se ven numerados arriba -->
  <section class="panel pu">
    <p class="pu-sup">{{ t('Set up your labels · {0} of {1}', [paso + 1, 3]) }}</p>
    <ol class="pu-pasos">
      <li v-for="(txt, i) in PASOS()" :key="i" :class="{ actual: i === paso, hecho: i < paso }"><span>{{ i + 1 }}</span>{{ txt }}</li>
    </ol>
    <h3 class="pu-titulo">{{ PASOS()[paso] }}</h3>
    <div v-if="!cat" class="vacio">{{ t('Loading…') }}</div>

    <!-- 1. Tipos -->
    <div v-else-if="paso === 0" class="pu-lista">
      <div v-for="x in tipos" :key="x.codigo" class="pu-tipo" :class="{ apagado: !x.elegido }">
        <input v-model="x.elegido" type="checkbox" :aria-label="t('Print this label')" />
        <input v-model="x.nombre" class="pu-nombre" maxlength="120" :aria-label="t('Name')" :placeholder="t('Name of the label')" />
        <template v-if="x.propio">
          <Seleccion v-model="x.sujeto" :aria-label="t('What is labeled')" @change="cambiarSujeto(x)">
            <option v-for="(txt, s) in SUJETOS()" :key="s" :value="s">{{ txt }}</option></Seleccion>
          <Seleccion v-model="x.cantidad" :aria-label="t('How many')">
            <option v-for="c in cat.cantidades[x.sujeto]" :key="c" :value="c">{{ CANTIDADES()[c] }}</option></Seleccion>
        </template>
        <template v-else>
          <span class="ayuda">{{ CANTIDADES()[x.cantidad] }}</span>
          <span class="etiqueta ms-0">{{ SUJETOS()[x.sujeto] }}</span>
        </template>
        <label class="check"><input v-model="x.obligatoria" type="checkbox" /> {{ t('Required') }}</label>
      </div>
      <button type="button" class="btn btn-chico pu-otro" @click="otro"><Icono nombre="mas" :tam="14" />{{ t('Another one (name, what is labeled, how many)') }}</button>
    </div>

    <!-- 2. Familias -->
    <div v-else-if="paso === 1" class="pu-lista">
      <template v-if="puede('etiquetas.familias')">
        <label class="pu-opcion"><input v-model="familias" type="radio" value="grupos" :disabled="!gruposSin" />
          <span><strong>{{ t('Use my item groups as families') }}</strong>
            <small class="ayuda">{{ gruposSin ? t('{0} groups → {0} families; you can join or rename them later.', [fmtNum(gruposSin)]) : t('All the item groups already have a family.') }}</small></span></label>
        <label class="pu-opcion"><input v-model="familias" type="radio" value="mano" />
          <span><strong>{{ t('Create the families by hand') }}</strong><small class="ayuda">{{ t('In Setup → Families and items, after this assistant.') }}</small></span></label>
      </template>
      <label class="pu-opcion"><input v-model="familias" type="radio" value="ninguna" />
        <span><strong>{{ t('Not yet: one label for everything') }}</strong><small class="ayuda">{{ t('Every item uses the design of the whole company until you add families.') }}</small></span></label>
    </div>

    <!-- 3. Diseños -->
    <div v-else class="pu-lista">
      <label v-if="puede('etiquetas.disenar')" class="check"><input v-model="disenos.crear" type="checkbox" />
        {{ t('Create a blank design of each type and use it for the whole company') }}</label>
      <p v-else class="nota">{{ t('You cannot create designs: someone with the design permission will add them.') }}</p>
      <template v-if="disenos.crear">
        <label v-for="x in elegidos" :key="x.codigo" class="campo pu-tamano"><span>{{ x.nombre }}</span>
          <Seleccion v-model="disenos.tamano[x.codigo]">
            <option v-for="(tm, i) in cat.tamanos" :key="i" :value="i">{{ tm.nombre }} ({{ fmtNum(tm.ancho, 1) }} × {{ fmtNum(tm.alto, 1) }} mm)</option>
          </Seleccion></label>
        <p class="ayuda">{{ t('The designs start as drafts: open them in Designs, place the fields and send them to approval. Until then they print only in test mode.') }}</p>
      </template>
      <p class="nota"><Icono nombre="info" :tam="16" />{{ t('{0} label types will be created.', [elegidos.length]) }}</p>
    </div>

    <div class="pu-pie">
      <button type="button" class="btn pu-saltar" @click="emit('cerrar')">{{ t('Skip') }}</button>
      <button v-if="paso > 0" type="button" class="btn" :disabled="ocupado" @click="paso--"><Icono nombre="atras" :tam="15" />{{ t('Back') }}</button>
      <button v-if="paso < 2" type="button" class="btn btn-primario" :disabled="!elegidos.length" @click="paso++">{{ t('Next') }}<Icono nombre="derecha" :tam="15" /></button>
      <button v-else type="button" class="btn btn-primario" :disabled="ocupado || !elegidos.length" @click="terminar">{{ t('Finish') }}</button>
    </div>
  </section>
</template>

<style scoped>
.pu { max-width: 900px; }
.pu-sup { margin: 0 0 8px; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--tinta-3); font-weight: 600; }
.pu-pasos { list-style: none; margin: 0 0 18px; padding: 0; display: flex; gap: 8px; flex-wrap: wrap; }
.pu-pasos li { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: var(--tinta-3); }
.pu-pasos li + li::before { content: ''; width: 24px; height: 1px; background: var(--linea); margin-right: 2px; }
.pu-pasos li span { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--linea); font-size: 0.75rem; }
.pu-pasos li.actual { color: var(--tinta); font-weight: 600; }
.pu-pasos li.actual span { background: var(--acento); border-color: var(--acento); color: #fff; }
.pu-pasos li.hecho span { background: var(--acento-claro); border-color: var(--acento-medio); color: var(--acento-texto); }
.pu-titulo { margin: 0 0 12px; font-size: 1.05rem; }
.pu-pie { display: flex; gap: 8px; margin-top: 20px; padding-top: 14px; border-top: 1px solid var(--linea); }
.pu-saltar { margin-inline-end: auto; }
.pu-lista { display: flex; flex-direction: column; gap: 10px; }
.pu-tipo { display: grid; grid-template-columns: auto minmax(160px, 1fr) auto auto auto; gap: 10px; align-items: center; border: 1px solid var(--linea); border-radius: 10px; padding: 8px 10px; }
.pu-tipo.apagado { opacity: 0.6; }
.pu-nombre { min-width: 0; }
.pu-otro { align-self: flex-start; }
.pu-opcion { display: flex; gap: 10px; align-items: flex-start; border: 1px solid var(--linea); border-radius: 10px; padding: 10px 12px; cursor: pointer; }
.pu-opcion span { display: flex; flex-direction: column; gap: 2px; }
.pu-opcion:has(input:checked) { border-color: var(--acento); background: var(--acento-claro); }
.pu-tamano { max-width: 420px; }
@media (max-width: 640px) { .pu-tipo { grid-template-columns: auto 1fr; } }
</style>
