<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icono from './Icono.vue'

// Lista desplegable con búsqueda. Busca sin importar acentos ni mayúsculas,
// por código, nombre o detalle, y con varias palabras (todas deben estar).
// opciones: ['SVAQJ', ...] o [{ valor, texto, sub }]
// Con `multiple`, el valor es una lista y la lista queda abierta al elegir.
const props = defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  multiple: Boolean,
  opciones: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Choose…' },
  vacio: { type: String, default: '' }, // texto de la opción "sin valor" (p. ej. "Todos")
  etiqueta: { type: String, default: '' },
  deshabilitado: Boolean,
  requerido: Boolean,
  busqueda: { type: Boolean, default: null },
  prefijo: { type: Boolean, default: true }, // en filtros: "Marca: valor" // null: solo con más de 7 opciones
})
const emit = defineEmits(['update:modelValue', 'change'])

const abierto = ref(false)
const texto = ref('')
const activo = ref(0)
const raiz = ref(null)
const campo = ref(null)
const lista = ref(null)
const pos = ref({})
const MAX = 150

const normal = (v) => String(v ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
const items = computed(() => props.opciones.map((o) => (typeof o === 'object' && o !== null
  ? { valor: o.valor ?? o.id ?? o.codigo, texto: o.texto ?? o.nombre ?? String(o.valor ?? o.codigo), sub: o.sub }
  : { valor: o, texto: String(o) })))
const elegidos = computed(() => (props.multiple ? (props.modelValue || []).map(String) : []))
const esElegido = (o) => (props.multiple ? elegidos.value.includes(String(o.valor)) : String(o.valor) === String(props.modelValue))
const elegido = computed(() => (props.multiple ? null : items.value.find((o) => String(o.valor) === String(props.modelValue))))
const resumen = computed(() => {
  if (!props.multiple) return ''
  const textos = items.value.filter((o) => elegidos.value.includes(String(o.valor))).map((o) => o.texto.split(' · ')[0])
  return textos.length > 3 ? `${textos.slice(0, 3).join(', ')} and ${textos.length - 3} more` : textos.join(', ')
})

const filtrados = computed(() => {
  const palabras = normal(texto.value).split(/\s+/).filter(Boolean)
  let res = items.value
  if (palabras.length) {
    res = res
      .map((o) => {
        const heno = normal(`${o.valor} ${o.texto} ${o.sub || ''}`)
        if (!palabras.every((p) => heno.includes(p))) return null
        // Primero lo que empieza con lo escrito (código o nombre)
        const inicio = normal(o.valor).startsWith(palabras[0]) || normal(o.texto).startsWith(palabras[0])
        return { o, peso: inicio ? 0 : 1 }
      })
      .filter(Boolean)
      .sort((a, b) => a.peso - b.peso)
      .map((x) => x.o)
  }
  const conVacio = props.vacio && !props.multiple && !palabras.length ? [{ valor: '', texto: props.vacio, vacio: true }, ...res] : res
  return conVacio
})
const visibles = computed(() => filtrados.value.slice(0, MAX))
const conBusqueda = computed(() => (props.busqueda === null ? items.value.length > 7 : props.busqueda))

function colocar() {
  const r = raiz.value?.getBoundingClientRect()
  if (!r) return
  const abajo = window.innerHeight - r.bottom
  const alto = Math.min(320, Math.max(abajo - 12, r.top - 12))
  const arriba = abajo < 220 && r.top > abajo
  pos.value = {
    left: `${r.left}px`, width: `${Math.max(r.width, 220)}px`, maxHeight: `${alto}px`,
    ...(arriba ? { bottom: `${window.innerHeight - r.top + 4}px` } : { top: `${r.bottom + 4}px` }),
  }
}

async function abrir() {
  if (props.deshabilitado || abierto.value) return
  abierto.value = true
  texto.value = ''
  activo.value = props.multiple ? 0 : Math.max(0, visibles.value.findIndex((o) => String(o.valor) === String(props.modelValue)))
  colocar()
  await nextTick()
  if (conBusqueda.value) campo.value?.focus()
  else lista.value?.querySelector('.sb-lista')?.focus()
  desplazar()
}
function cerrar() {
  abierto.value = false
}
function elegir(o) {
  if (props.multiple) {
    const actual = (props.modelValue || []).map(String)
    const v = String(o.valor)
    const nuevo = actual.includes(v) ? actual.filter((x) => x !== v) : [...actual, v]
    // Conserva el tipo original de los valores (números o códigos)
    const valores = items.value.filter((x) => nuevo.includes(String(x.valor))).map((x) => x.valor)
    emit('update:modelValue', valores)
    emit('change', valores)
    return
  }
  emit('update:modelValue', o.valor)
  emit('change', o.valor)
  cerrar()
}
function desplazar() {
  nextTick(() => lista.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }))
}
function tecla(e) {
  if (e.key === 'ArrowDown') { activo.value = Math.min(activo.value + 1, visibles.value.length - 1); desplazar(); e.preventDefault() }
  else if (e.key === 'ArrowUp') { activo.value = Math.max(activo.value - 1, 0); desplazar(); e.preventDefault() }
  else if (e.key === 'Enter') { if (visibles.value[activo.value]) elegir(visibles.value[activo.value]); e.preventDefault() }
  else if (e.key === 'Escape') { cerrar(); e.stopPropagation() } // cierra solo la lista, no la ventana que la contiene
  else if (e.key === 'Tab') cerrar()
}
watch(texto, () => (activo.value = 0))

function fuera(e) {
  if (!raiz.value?.contains(e.target) && !lista.value?.contains(e.target)) cerrar()
}
watch(abierto, (v) => {
  const m = v ? 'addEventListener' : 'removeEventListener'
  document[m]('mousedown', fuera)
  window[m]('resize', colocar)
  window[m]('scroll', colocar, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', fuera)
  window.removeEventListener('resize', colocar)
  window.removeEventListener('scroll', colocar, true)
})
</script>

<template>
  <div ref="raiz" class="sb" :class="{ abierto, deshabilitado }">
    <button type="button" class="sb-boton" :disabled="deshabilitado" :aria-label="etiqueta || placeholder"
            aria-haspopup="listbox" :aria-expanded="abierto" @click="abrir" @keydown.down.prevent="abrir">
      <span v-if="multiple && resumen" class="sb-valor" :title="`${etiqueta}: ${resumen}`"><span v-if="prefijo && vacio && etiqueta" class="sb-etq">{{ etiqueta }}:</span> {{ resumen }}</span>
      <span v-else-if="multiple" :class="vacio ? 'sb-valor' : 'sb-placeholder'">{{ vacio || placeholder }}</span>
      <span v-else-if="elegido && (elegido.valor !== '' || !vacio)" class="sb-valor" :title="elegido.texto"><span v-if="prefijo && vacio && etiqueta" class="sb-etq">{{ etiqueta }}:</span> {{ elegido.texto }}</span>
      <span v-else-if="vacio && !modelValue" class="sb-valor">{{ vacio }}</span>
      <span v-else class="sb-placeholder">{{ placeholder }}</span>
      <Icono nombre="abajo" :tam="14" />
    </button>
    <input v-if="requerido" class="sb-requerido" :value="multiple ? elegidos.join(',') : modelValue" required tabindex="-1" aria-hidden="true" />
    <Teleport to="body">
      <div v-if="abierto" ref="lista" class="sb-panel" :style="pos">
        <label v-if="conBusqueda" class="sb-buscar">
          <Icono nombre="buscar" :tam="15" />
          <input ref="campo" v-model="texto" type="search" placeholder="Search…" :aria-label="`Search ${etiqueta}`"
                 role="combobox" aria-autocomplete="list" :aria-expanded="true" @keydown="tecla" />
        </label>
        <ul class="sb-lista" role="listbox" :aria-multiselectable="multiple || undefined" :aria-label="etiqueta || placeholder" tabindex="-1" @keydown="tecla">
          <li v-for="(o, i) in visibles" :key="`${o.valor}-${i}`" role="option" :aria-selected="i === activo"
              :class="{ elegido: esElegido(o), vacio: o.vacio }" :aria-checked="multiple ? esElegido(o) : undefined"
              @mousedown.prevent="elegir(o)" @mousemove="activo = i">
            <span><Icono v-if="multiple" :nombre="esElegido(o) ? 'check' : 'mas'" :tam="13" class="sb-marca" /> {{ o.texto }}</span>
            <small v-if="o.sub">{{ o.sub }}</small>
          </li>
          <li v-if="!visibles.length" class="sb-nada">No results for “{{ texto }}”</li>
          <li v-if="filtrados.length > MAX" class="sb-nada">Showing {{ MAX }} of {{ filtrados.length }}; type to narrow it down.</li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
