<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { errorApi } from '@/stores/ui'
import { AJUSTABLES, AJUSTES_CAJA, LISTAS, maquetar, seguidores, textoElemento, NUMERICOS, OPERADORES, PATRONES_FECHA, SIN_VALOR, TRANSFORMACIONES, catalogos, fechaConPatron } from '@/modulos/etiquetado/etiquetas.js'
import { usarEditor } from './estado.js'
import CampoColor from './CampoColor.vue'
import Medida from './Medida.vue'

// Propiedades de lo elegido. Con un elemento: posición y medidas, contenido
// según el tipo, estilo del texto, formato del valor, qué hacer si el campo
// está vacío y la condición para mostrarlo. Con varios: alinear, distribuir e
// igualar medidas.
const props = defineProps({ grupos: { type: Object, default: () => ({}) } })
const ed = usarEditor()
const est = ed.estado
const e = computed(() => ed.unico.value)
const u = computed(() => est.diseno?.unidad || 'mm')
const bloqueado = computed(() => !est.editable || !!e.value?.bloqueado)
const TIPOS = computed(() => ({ texto: t('Text'), campo: t('Field'), codigo: t('Code'), imagen: t('Image'), rect: t('Rectangle'), elipse: t('Ellipse'), linea: t('Line'), tabla: t('Table') }))

// Los campos que la empresa oculta no se ofrecen, salvo el que el elemento ya usa
const ofrecido = (c) => !c.oculto || [e.value?.campo, e.value?.condicion?.campo].includes(c.clave)
const camposTexto = computed(() => ed.camposTodos.value.filter((c) => c.tipo !== 'imagen' && ofrecido(c)))
const camposImagen = computed(() => ed.camposTodos.value.filter((c) => c.tipo === 'imagen' && ofrecido(c)))
const textoCampo = (c) => `${tx(props.grupos[c.grupo] || c.grupo)} · ${tx(c.etiqueta)}`
const campoActual = computed(() => ed.camposTodos.value.find((c) => c.clave === e.value?.campo))
const insertar = ref('')
function insertarCampo(prop, clave) {
  if (!clave || bloqueado.value) return
  e.value[prop] = `${e.value[prop] || ''}{{${clave}}}`
  insertar.value = ''
}

// Estilo y formato: se crean al primer cambio
const estilo = computed(() => e.value?.estilo || {})
// Recuadro que se ajusta al contenido: qué medidas son automáticas y qué opciones tiene cada tipo
const anchoAuto = computed(() => {
  const x = e.value
  if (!x || !AJUSTABLES.includes(x.tipo)) return false
  return x.tipo === 'imagen' ? x.ajustar === 'ancho' : ['texto', 'campo'].includes(x.tipo) && ['ancho', 'ambos'].includes(x.ajustar)
})
const altoAuto = computed(() => !!e.value && AJUSTABLES.includes(e.value.tipo) && ['alto', 'ambos'].includes(e.value.ajustar))
// «Debajo de»: cualquier otro elemento que no lo siga ya (evita ciclos)
const posiblesArriba = computed(() => {
  if (!e.value) return []
  const fuera = seguidores(ed.elementos.value, e.value.id)
  return ed.elementos.value.filter((x) => x.id !== e.value.id && !fuera.has(x.id))
})
const nombreElemento = (x) => x.nombre || (x.tipo === 'campo' ? `{{${x.campo}}}` : x.tipo === 'texto' ? (x.contenido || '').slice(0, 30) : x.tipo)
// Con el recuadro fijo, la letra que de verdad se dibuja (si se reduce para caber)
const letraReducida = computed(() => {
  const x = e.value
  if (!x || !['texto', 'campo'].includes(x.tipo) || (x.ajustar && x.ajustar !== 'no')) return null
  const est = { fuente: 'sans', tam: 10, interlineado: 1.15, espaciado: 0, relleno: 0, ajuste: 'reducir', tam_min: 6, ...(x.estilo || {}) }
  if (est.ajuste !== 'reducir') return null
  let txt = textoElemento(x, ed.ejemplosTodos.value, ed.estado.tipos) || (x.tipo === 'campo' ? `{{${x.campo}}}` : x.contenido || '')
  if (est.mayusculas) txt = txt.toUpperCase()
  const m = maquetar(txt, est, x.w, x.h)
  return m.tam < est.tam - 0.01 ? Math.round(m.tam * 4) / 4 : null
})
const opcionesAjuste = computed(() => {
  const tipo = e.value?.tipo
  if (tipo === 'tabla') return [['no', t('Fixed size')], ['alto', t('Grow with its rows')]]
  if (tipo === 'imagen') return [['no', t('Fixed size')], ['alto', t('Height from the image proportion')], ['ancho', t('Width from the image proportion')]]
  return AJUSTES_CAJA()
})
const ayudaAjuste = computed(() => ({
  no: t('The box keeps its size; if the text does not fit, the option «If it does not fit» applies.'),
  ambos: t('The box grows or shrinks with the text and its letter size, from its alignment, up to the safe area.'),
  ancho: t('The width follows the text (one line); the height stays.'),
  alto: e.value?.tipo === 'tabla' ? t('The height follows the number of rows of each label.')
    : e.value?.tipo === 'imagen' ? t('The height follows the proportion of the image.') : t('The text is split into lines inside the width and the height follows them.'),
})[e.value?.ajustar || 'no'])
function poner(obj, prop, v) {
  if (bloqueado.value) return
  e.value[obj] = { ...(e.value[obj] || {}), [prop]: v }
}
const alternarEstilo = (prop) => poner('estilo', prop, !estilo.value[prop])
const formato = computed(() => e.value?.formato || { tipo: 'auto', decimales: 0, miles: true, fecha: 'dd/mm/aaaa' })
function condicion(activa) {
  if (bloqueado.value) return
  e.value.condicion = activa ? { campo: e.value.campo || ed.camposTodos.value[0]?.clave || '', op: 'existe', valor: null } : null
}

// Código compuesto: partes (campo o texto fijo) con transformaciones y un separador
const conPartes = computed(() => !!e.value?.partes?.length)
function modoPartes(si) {
  if (bloqueado.value) return
  if (si) e.value.partes = [{ tipo: 'campo', campo: camposTexto.value[0]?.clave || '', transformar: [] }]
  else e.value.partes = []
  if (si) e.value.separador = e.value.separador || ''
  else e.value.valor = e.value.valor || '{{articulo.sku}}'
}
const agregarParte = () => e.value.partes.push({ tipo: 'campo', campo: camposTexto.value[0]?.clave || '', transformar: [] })
function alternarTransformacion(parte, x) {
  const l = parte.transformar || []
  parte.transformar = l.includes(x) ? l.filter((y) => y !== x) : [...l, x]
}

// Tabla: la lista (colección) y sus columnas
const coleccion = computed(() => est.colecciones.find((c) => c.clave === e.value?.coleccion))
function cambiarColeccion(clave) {
  const c = est.colecciones.find((x) => x.clave === clave)
  e.value.coleccion = clave
  e.value.columnas = (c?.columnas || []).slice(0, 3).map((x) => ({ campo: x.clave, titulo: x.etiqueta, ancho: 1, alin: x.tipo === 'numero' ? 'der' : 'izq' }))
  e.value.totales = []
}
const agregarColumna = () => {
  const libre = coleccion.value?.columnas.find((x) => !e.value.columnas.some((c) => c.campo === x.clave)) || coleccion.value?.columnas[0]
  if (libre) e.value.columnas.push({ campo: libre.clave, titulo: libre.etiqueta, ancho: 1, alin: libre.tipo === 'numero' ? 'der' : 'izq' })
}
function alternarTotal(campo) {
  const l = e.value.totales || []
  e.value.totales = l.includes(campo) ? l.filter((x) => x !== campo) : [...l, campo]
}
function condicionValor(v) {
  const c = e.value.condicion
  c.valor = LISTAS.includes(c.op) ? v.split(',').map((x) => x.trim()).filter(Boolean) : NUMERICOS.includes(c.op) && v !== '' ? Number(v) : v
}

// Ejemplo de campo dentro de un texto (en el script: en la plantilla cerraría la interpolación)
const EJEMPLO = '{{articulo.sku}}'
// Simbologías del servidor (con su uso: GS1, matriciales…)
const simbologias = ref([])
onMounted(() => catalogos().then((c) => (simbologias.value = c.simbologias)).catch(() => {}))
const simbologia = computed(() => simbologias.value.find((s) => s.codigo === e.value?.simbologia))

// Imagen propia: se sube al servidor (PNG, JPEG o WebP) y el diseño guarda su número
const subiendo = ref(false)
const archivo = ref(null)
async function subir(ev) {
  const f = ev.target.files?.[0]
  ev.target.value = ''
  if (!f) return
  subiendo.value = true
  try {
    const fd = new FormData()
    fd.append('archivo', f)
    const r = await api.post('/etiquetas/imagenes', fd)
    e.value.fuente_imagen = 'adjunto'
    e.value.adjunto_id = r.id
    e.value.campo = null
    if (r.ancho_px && r.alto_px) e.value.h = Math.round(((e.value.w * r.alto_px) / r.ancho_px) * 10) / 10
  } catch (err) {
    errorApi(err)
  } finally {
    subiendo.value = false
  }
}
function fuenteImagen(v) {
  if (bloqueado.value) return
  e.value.fuente_imagen = v
  if (v === 'campo' && !e.value.campo) e.value.campo = camposImagen.value[0]?.clave || null
}
</script>

<template>
  <!-- Varios elementos -->
  <div v-if="ed.seleccionados.value.length > 1" class="panel-prop">
    <p class="prop-titulo">{{ t('{0} elements selected', [ed.seleccionados.value.length]) }}</p>
    <h4>{{ t('Align') }}</h4>
    <div class="botonera">
      <button v-for="[m, i, txt] in [['izq', 'alin-izq', t('Left')], ['centro', 'alin-centro', t('Center')], ['der', 'alin-der', t('Right')], ['arriba', 'alin-arriba', t('Top')], ['medio', 'alin-medio', t('Middle')], ['abajo', 'alin-abajo', t('Bottom')]]"
              :key="m" type="button" class="btn btn-icono" :disabled="!est.editable" :title="txt" :aria-label="txt" @click="ed.alinear(m)"><Icono :nombre="i" :tam="17" /></button>
    </div>
    <h4>{{ t('Distribute and match') }}</h4>
    <div class="botonera">
      <button type="button" class="btn btn-icono" :disabled="!est.editable || ed.seleccionados.value.length < 3" :title="t('Same horizontal space')" :aria-label="t('Same horizontal space')" @click="ed.distribuir('h')"><Icono nombre="dist-h" :tam="17" /></button>
      <button type="button" class="btn btn-icono" :disabled="!est.editable || ed.seleccionados.value.length < 3" :title="t('Same vertical space')" :aria-label="t('Same vertical space')" @click="ed.distribuir('v')"><Icono nombre="dist-v" :tam="17" /></button>
      <button type="button" class="btn btn-chico" :disabled="!est.editable" @click="ed.igualar('w')">{{ t('Same width') }}</button>
      <button type="button" class="btn btn-chico" :disabled="!est.editable" @click="ed.igualar('h')">{{ t('Same height') }}</button>
    </div>
    <p class="ayuda">{{ t('They align with each other; with a single element, it aligns to the label.') }}</p>
    <div class="botonera mt">
      <button type="button" class="btn btn-chico" :disabled="!est.editable" @click="ed.agrupar()"><Icono nombre="agrupar" :tam="15" />{{ t('Group') }}</button>
      <button type="button" class="btn btn-chico" :disabled="!est.editable" @click="ed.duplicar()"><Icono nombre="copiar" :tam="15" />{{ t('Duplicate') }}</button>
      <button type="button" class="btn btn-chico btn-peligro" :disabled="!est.editable" @click="ed.eliminar()"><Icono nombre="basura" :tam="15" />{{ t('Delete') }}</button>
    </div>
  </div>

  <!-- Un elemento -->
  <div v-else-if="e" class="panel-prop">
    <div class="prop-cabeza">
      <span class="etiqueta ms-0">{{ TIPOS[e.tipo] }}</span>
      <input v-model.trim="e.nombre" class="prop-nombre" :placeholder="t('Name in layers (optional)')" maxlength="60" :disabled="!est.editable" :aria-label="t('Name')" />
    </div>
    <div class="botonera">
      <button type="button" class="btn btn-icono btn-chico" :disabled="!est.editable" :title="t('Duplicate (Ctrl+D)')" :aria-label="t('Duplicate')" @click="ed.duplicar()"><Icono nombre="copiar" :tam="15" /></button>
      <button type="button" class="btn btn-icono btn-chico" :class="{ activo: e.bloqueado }" :disabled="!est.editable" :title="e.bloqueado ? t('Unlock') : t('Lock')" :aria-label="t('Lock')" @click="e.bloqueado = !e.bloqueado"><Icono nombre="candado" :tam="15" /></button>
      <button type="button" class="btn btn-icono btn-chico" :class="{ activo: e.visible === false }" :disabled="!est.editable" :title="e.visible === false ? t('Show') : t('Hide')" :aria-label="t('Hide')" @click="e.visible = e.visible === false"><Icono nombre="ojo" :tam="15" /></button>
      <span class="crece" />
      <button type="button" class="btn btn-icono btn-chico btn-peligro" :disabled="bloqueado" :title="t('Delete (Del)')" :aria-label="t('Delete')" @click="ed.eliminar()"><Icono nombre="basura" :tam="15" /></button>
    </div>

    <h4>{{ t('Position and size') }}</h4>
    <div class="rejilla-2">
      <Medida v-model="e.x" etiqueta="X" :unidad="u" :disabled="bloqueado" />
      <Medida v-model="e.y" etiqueta="Y" :unidad="u" :disabled="bloqueado || !!e.debajo_de" />
      <Medida v-model="e.w" :etiqueta="t('Width')" :unidad="u" :min="0" :disabled="bloqueado || anchoAuto" :title="anchoAuto ? t('Automatic: it follows the content') : null" />
      <Medida v-model="e.h" :etiqueta="t('Height')" :unidad="u" :min="0" :disabled="bloqueado || altoAuto" :title="altoAuto ? t('Automatic: it follows the content') : null" />
      <Medida v-model="e.rot" :etiqueta="t('Rotation')" unidad="°" :min="-360" :max="360" :disabled="bloqueado" />
    </div>
    <div class="rejilla-2 mt-chico">
      <label class="campo-mini"><span>{{ t('Below') }}</span>
        <Seleccion :model-value="e.debajo_de || ''" :disabled="bloqueado" :aria-label="t('Below')" @change="(v) => (e.debajo_de = v || null)">
          <option value="">{{ t('Free position') }}</option>
          <option v-for="x in posiblesArriba" :key="x.id" :value="x.id">{{ nombreElemento(x) }}</option>
        </Seleccion>
      </label>
      <Medida v-if="e.debajo_de" :model-value="e.separacion ?? 1" :etiqueta="t('Gap')" :unidad="u" :min="0" :max="100" :disabled="bloqueado"
              @update:model-value="(v) => (e.separacion = v)" />
    </div>
    <small v-if="e.debajo_de" class="ayuda">{{ t('It moves with the element above when it grows, shrinks or is not printed.') }}</small>
    <label v-if="AJUSTABLES.includes(e.tipo)" class="campo-mini mt-chico"><span>{{ t('Box size') }}</span>
      <Seleccion :model-value="e.ajustar || 'no'" :disabled="bloqueado" :aria-label="t('Box size')" @change="(v) => (e.ajustar = v)">
        <option v-for="[v, txt] in opcionesAjuste" :key="v" :value="v">{{ txt }}</option>
      </Seleccion>
      <small class="ayuda">{{ ayudaAjuste }}</small>
    </label>
    <div class="botonera mt-chico">
      <button v-for="[m, i, txt] in [['izq', 'alin-izq', t('Left')], ['centro', 'alin-centro', t('Center')], ['der', 'alin-der', t('Right')], ['arriba', 'alin-arriba', t('Top')], ['medio', 'alin-medio', t('Middle')], ['abajo', 'alin-abajo', t('Bottom')]]"
              :key="m" type="button" class="btn btn-icono btn-chico" :disabled="bloqueado" :title="t('Align to the label: {0}', [txt])" :aria-label="txt" @click="ed.alinear(m)"><Icono :nombre="i" :tam="15" /></button>
    </div>

    <!-- Contenido -->
    <template v-if="e.tipo === 'texto'">
      <h4>{{ t('Text') }}</h4>
      <textarea v-model="e.contenido" rows="3" class="prop-area" :disabled="bloqueado" :aria-label="t('Text')" />
      <Seleccion v-model="insertar" :disabled="bloqueado" :aria-label="t('Insert field')" @change="(v) => insertarCampo('contenido', v)">
        <option value="">{{ t('Insert field…') }}</option>
        <option v-for="c in camposTexto" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option>
      </Seleccion>
      <p class="ayuda">{{ t('Fixed text and fields like {0}. Double click on the label to edit it there.', [EJEMPLO]) }}</p>
    </template>

    <template v-if="e.tipo === 'campo'">
      <h4>{{ t('Field') }}</h4>
      <Seleccion v-model="e.campo" :disabled="bloqueado" :aria-label="t('Field')">
        <option v-for="c in camposTexto" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option>
      </Seleccion>
      <p v-if="campoActual" class="ayuda">{{ t('Comes from {0}. Example: {1}', [campoActual.origen, campoActual.ejemplo ?? '—']) }}</p>
      <div class="rejilla-2">
        <label class="campo-mini"><span>{{ t('Prefix') }}</span><input v-model="e.prefijo" maxlength="100" :disabled="bloqueado" /></label>
        <label class="campo-mini"><span>{{ t('Suffix') }}</span><input v-model="e.sufijo" maxlength="100" :disabled="bloqueado" /></label>
      </div>
      <h4>{{ t('Format') }}</h4>
      <div class="rejilla-2">
        <label class="campo-mini col-2"><span>{{ t('Show as') }}</span>
          <Seleccion :model-value="formato.tipo" :disabled="bloqueado" :aria-label="t('Show as')" @change="(v) => poner('formato', 'tipo', v)">
            <option value="auto">{{ t('As it comes') }}</option>
            <option value="numero">{{ t('Number') }}</option>
            <option value="fecha">{{ t('Date') }}</option>
            <option value="mayus">{{ t('UPPERCASE') }}</option>
            <option value="minus">{{ t('lowercase') }}</option>
          </Seleccion>
        </label>
        <template v-if="formato.tipo === 'numero'">
          <Medida :model-value="formato.decimales" :etiqueta="t('Decimals')" unidad="" :min="0" :max="6" :disabled="bloqueado" @update:model-value="(v) => poner('formato', 'decimales', Math.round(v))" />
          <label class="check-linea"><input type="checkbox" :checked="formato.miles !== false" :disabled="bloqueado" @change="poner('formato', 'miles', $event.target.checked)" />{{ t('Thousands separator') }}</label>
        </template>
        <label v-if="formato.tipo === 'fecha'" class="campo-mini col-2"><span>{{ t('Date pattern') }}</span>
          <input :value="formato.fecha || 'dd/mm/aaaa'" :disabled="bloqueado" maxlength="30" list="patrones-fecha" :aria-label="t('Date pattern')"
                 @change="poner('formato', 'fecha', $event.target.value.trim() || 'dd/mm/aaaa')" />
          <datalist id="patrones-fecha"><option v-for="x in PATRONES_FECHA" :key="x" :value="x">{{ fechaConPatron(2026, 12, 31, x) }}</option></datalist>
          <small class="ayuda">{{ t('dd, d, mm, mmm, mmmm, aa, aaaa. E.g. {0}', [fechaConPatron(2026, 12, 31, formato.fecha || 'dd/mm/aaaa')]) }}</small>
        </label>
      </div>
    </template>

    <template v-if="e.tipo === 'campo' || e.tipo === 'imagen'">
      <h4>{{ t('If the data is empty') }}</h4>
      <Seleccion v-model="e.si_vacio" :disabled="bloqueado" :aria-label="t('If the data is empty')">
        <option value="advertir">{{ t('Leave it blank and warn') }}</option>
        <option value="ocultar">{{ t('Hide the element') }}</option>
        <option v-if="e.tipo === 'campo'" value="alternativo">{{ t('Use an alternative text') }}</option>
        <option value="error">{{ t('Do not allow generating (required)') }}</option>
      </Seleccion>
      <input v-if="e.si_vacio === 'alternativo'" v-model="e.alternativo" class="mt-chico" maxlength="200" :placeholder="t('Alternative text')" :disabled="bloqueado" :aria-label="t('Alternative text')" />
    </template>

    <template v-if="e.tipo === 'codigo'">
      <h4>{{ t('Code') }}</h4>
      <Seleccion v-model="e.simbologia" :disabled="bloqueado" :aria-label="t('Symbology')">
        <option v-for="x in simbologias" :key="x.codigo" :value="x.codigo">{{ x.nombre }} — {{ tx(x.descripcion) }}</option>
      </Seleccion>
      <p v-if="simbologia" class="ayuda">{{ tx(simbologia.descripcion) }}</p>
      <label class="check-linea"><input type="checkbox" :checked="conPartes" :disabled="bloqueado" @change="modoPartes($event.target.checked)" />{{ t('Compose the value from parts') }}</label>
      <template v-if="!conPartes">
        <label class="campo-mini"><span>{{ t('Value to encode') }}</span><input v-model="e.valor" maxlength="1000" :disabled="bloqueado" class="mono" /></label>
        <Seleccion v-model="insertar" :disabled="bloqueado" :aria-label="t('Insert field')" @change="(v) => insertarCampo('valor', v)">
          <option value="">{{ t('Insert field…') }}</option>
          <option v-for="c in camposTexto" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option>
        </Seleccion>
      </template>
      <template v-else>
        <div v-for="(parte, i) in e.partes" :key="i" class="parte-codigo">
          <div class="rejilla-2">
            <Seleccion v-model="parte.tipo" :disabled="bloqueado" :aria-label="t('Part')"><option value="campo">{{ t('Field') }}</option><option value="fijo">{{ t('Fixed text') }}</option></Seleccion>
            <Seleccion v-if="parte.tipo === 'campo'" v-model="parte.campo" :disabled="bloqueado" :aria-label="t('Field')">
              <option v-for="c in camposTexto" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option></Seleccion>
            <input v-else v-model="parte.texto" maxlength="80" class="mono" :disabled="bloqueado" :aria-label="t('Fixed text')" />
          </div>
          <div class="transformaciones">
            <label v-for="(txt, x) in TRANSFORMACIONES()" :key="x" class="check-linea"><input type="checkbox" :checked="(parte.transformar || []).includes(x)" :disabled="bloqueado"
                   @change="alternarTransformacion(parte, x)" />{{ tx(txt) }}</label>
          </div>
          <div class="rejilla-2">
            <label class="campo-mini"><span>{{ t('Pad to length') }}</span><input v-model.number="parte.rellenar" type="number" min="1" max="40" :disabled="bloqueado" /></label>
            <label class="campo-mini"><span>{{ t('Keep the first') }}</span><input v-model.number="parte.recortar" type="number" min="1" max="80" :disabled="bloqueado" /></label>
          </div>
          <button type="button" class="btn btn-chico btn-texto" :disabled="bloqueado" @click="e.partes.splice(i, 1)">{{ t('Remove part') }}</button>
        </div>
        <div class="rejilla-2">
          <button type="button" class="btn btn-chico" :disabled="bloqueado || e.partes.length >= 10" @click="agregarParte"><Icono nombre="mas" :tam="14" />{{ t('Add a part') }}</button>
          <label class="campo-mini"><span>{{ t('Separator') }}</span><input v-model="e.separador" maxlength="5" class="mono" :disabled="bloqueado" /></label>
        </div>
      </template>
      <div class="rejilla-2 mt-chico">
        <Medida v-model="e.margen" :etiqueta="t('Quiet zone')" :unidad="u" :min="0" :max="30" :disabled="bloqueado" />
        <label v-if="e.simbologia === 'qr'" class="campo-mini"><span>{{ t('Error correction') }}</span>
          <Seleccion v-model="e.correccion" :disabled="bloqueado" :aria-label="t('Error correction')">
            <option value="L">L · 7 %</option><option value="M">M · 15 %</option><option value="Q">Q · 25 %</option><option value="H">H · 30 %</option>
          </Seleccion>
        </label>
        <label v-else class="check-linea"><input v-model="e.legible" type="checkbox" :disabled="bloqueado" />{{ t('Human-readable text') }}</label>
        <CampoColor v-model="e.color" :etiqueta="t('Bars')" :disabled="bloqueado" />
        <CampoColor v-model="e.relleno" :etiqueta="t('Background')" ninguno :disabled="bloqueado" />
      </div>
      <p class="ayuda">{{ t('The server checks the value (length, check digit) and that the bars are wide enough to be read; problems appear in the preview.') }}</p>
    </template>

    <template v-if="e.tipo === 'tabla'">
      <h4>{{ t('Table') }}</h4>
      <label class="campo-mini"><span>{{ t('List') }}</span>
        <Seleccion :model-value="e.coleccion" :disabled="bloqueado" :aria-label="t('List')" @update:model-value="cambiarColeccion">
          <option v-for="c in est.colecciones" :key="c.clave" :value="c.clave">{{ tx(c.etiqueta) }}</option></Seleccion></label>
      <div v-for="(c, i) in e.columnas" :key="i" class="columna-tabla">
        <Seleccion v-model="c.campo" :disabled="bloqueado" :aria-label="t('Column')">
          <option v-for="x in coleccion?.columnas || []" :key="x.clave" :value="x.clave">{{ tx(x.etiqueta) }}</option></Seleccion>
        <input v-model="c.titulo" maxlength="60" :disabled="bloqueado" :aria-label="t('Header')" :placeholder="t('Header')" />
        <input v-model.number="c.ancho" type="number" min="0.1" max="100" step="0.5" :disabled="bloqueado" :aria-label="t('Width (relative)')" :title="t('Width (relative)')" />
        <Seleccion v-model="c.alin" :disabled="bloqueado" :aria-label="t('Alignment')"><option value="izq">⟵</option><option value="centro">↔</option><option value="der">⟶</option></Seleccion>
        <label class="check-linea" :title="t('Total at the bottom')"><input type="checkbox" :checked="(e.totales || []).includes(c.campo)" :disabled="bloqueado" @change="alternarTotal(c.campo)" />Σ</label>
        <button type="button" class="btn-icono" :disabled="bloqueado" :aria-label="t('Remove')" @click="e.columnas.splice(i, 1)"><Icono nombre="cerrar" :tam="13" /></button>
      </div>
      <button type="button" class="btn btn-chico" :disabled="bloqueado || e.columnas.length >= 12" @click="agregarColumna"><Icono nombre="mas" :tam="14" />{{ t('Add a column') }}</button>
      <div class="rejilla-2 mt-chico">
        <Medida v-model="e.alto_fila" :etiqueta="t('Row height')" :unidad="u" :min="2" :max="50" :disabled="bloqueado" />
        <label class="check-linea"><input v-model="e.encabezado" type="checkbox" :disabled="bloqueado" />{{ t('Header row') }}</label>
        <label class="check-linea"><input v-model="e.cuadricula" type="checkbox" :disabled="bloqueado" />{{ t('Grid lines') }}</label>
        <CampoColor v-model="e.color" :etiqueta="t('Lines')" :disabled="bloqueado" />
      </div>
      <label class="campo-mini"><span>{{ t('If the rows do not fit') }}</span>
        <Seleccion v-model="e.desborde" :disabled="bloqueado" :aria-label="t('If the rows do not fit')">
          <option value="error">{{ t('Do not generate (error)') }}</option>
          <option value="reducir">{{ t('Smaller text (error if still too many)') }}</option>
          <option value="resumir">{{ t('Show the ones that fit and “+N more” (warning)') }}</option>
        </Seleccion></label>
      <label class="campo-mini"><span>{{ t('If the list is empty') }}</span>
        <Seleccion v-model="e.si_vacio" :disabled="bloqueado" :aria-label="t('If the list is empty')">
          <option value="advertir">{{ t('Warn') }}</option><option value="ocultar">{{ t('Hide the table') }}</option>
          <option value="error">{{ t('Do not allow generating (required)') }}</option></Seleccion></label>
      <p class="ayuda">{{ t('Totals add up every row, even the ones not shown. Rows are never cut silently.') }}</p>
    </template>

    <template v-if="e.tipo === 'imagen'">
      <h4>{{ t('Image') }}</h4>
      <div class="segmentos" role="group" :aria-label="t('Image source')">
        <button type="button" class="segmento" :aria-pressed="e.fuente_imagen === 'adjunto' || e.fuente_imagen === 'datos'" :disabled="bloqueado" @click="archivo.click()">{{ t('Upload image') }}</button>
        <button type="button" class="segmento" :aria-pressed="e.fuente_imagen === 'campo'" :disabled="bloqueado || !camposImagen.length" @click="fuenteImagen('campo')">{{ t('From a field') }}</button>
      </div>
      <input ref="archivo" type="file" accept="image/png,image/jpeg,image/webp" class="oculto-visual" @change="subir" />
      <p v-if="subiendo" class="ayuda">{{ t('Uploading…') }}</p>
      <Seleccion v-if="e.fuente_imagen === 'campo'" v-model="e.campo" class="mt-chico" :disabled="bloqueado" :aria-label="t('Field')">
        <option v-for="c in camposImagen" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option>
      </Seleccion>
      <p v-else-if="e.adjunto_id" class="ayuda">{{ t('Uploaded image #{0}. PNG, JPEG or WebP up to 2 MB.', [e.adjunto_id]) }}</p>
      <label class="campo-mini mt-chico"><span>{{ t('Fit') }}</span>
        <Seleccion v-model="e.encaje" :disabled="bloqueado" :aria-label="t('Fit')">
          <option value="contener">{{ t('Fit inside (keep proportions)') }}</option>
          <option value="cubrir">{{ t('Fill (crop the excess)') }}</option>
          <option value="estirar">{{ t('Stretch') }}</option>
        </Seleccion>
      </label>
    </template>

    <template v-if="e.tipo === 'rect' || e.tipo === 'elipse'">
      <h4>{{ t('Fill and border') }}</h4>
      <div class="rejilla-2">
        <CampoColor v-model="e.relleno" :etiqueta="t('Fill')" ninguno :disabled="bloqueado" />
        <CampoColor v-model="e.borde" :etiqueta="t('Border')" ninguno :disabled="bloqueado" />
        <Medida v-model="e.grosor" :etiqueta="t('Thickness')" :unidad="u" :min="0" :max="20" :disabled="bloqueado" />
        <Medida v-if="e.tipo === 'rect'" v-model="e.radio" :etiqueta="t('Corner radius')" :unidad="u" :min="0" :max="100" :disabled="bloqueado" />
      </div>
    </template>
    <template v-if="e.tipo === 'linea'">
      <h4>{{ t('Line') }}</h4>
      <div class="rejilla-2">
        <CampoColor v-model="e.color" :etiqueta="t('Color')" :disabled="bloqueado" />
        <Medida v-model="e.grosor" :etiqueta="t('Thickness')" :unidad="u" :min="0" :max="20" :disabled="bloqueado" />
      </div>
    </template>
    <template v-if="['rect', 'elipse', 'linea'].includes(e.tipo)">
      <div class="segmentos mt-chico" role="group" :aria-label="t('Stroke')">
        <button v-for="[v, txt] in [['solido', t('Solid')], ['discontinuo', t('Dashed')], ['punteado', t('Dotted')]]" :key="v" type="button" class="segmento"
                :aria-pressed="(e.trazo || 'solido') === v" :disabled="bloqueado" @click="e.trazo = v">{{ txt }}</button>
      </div>
    </template>

    <!-- Estilo del texto -->
    <template v-if="e.tipo === 'texto' || e.tipo === 'campo'">
      <h4>{{ t('Text style') }}</h4>
      <div class="rejilla-2">
        <label class="campo-mini"><span>{{ t('Font') }}</span>
          <Seleccion :model-value="estilo.fuente || 'sans'" :disabled="bloqueado" :aria-label="t('Font')" @change="(v) => poner('estilo', 'fuente', v)">
            <option value="sans">Sans (Liberation Sans)</option>
            <option value="serif">Serif (Liberation Serif)</option>
            <option value="mono">Mono (Liberation Mono)</option>
          </Seleccion>
        </label>
        <Medida :model-value="estilo.tam ?? 10" :etiqueta="t('Letter height')" unidad="pt" :min="3" :max="400" :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'tam', v)" />
      </div>
      <p v-if="letraReducida" class="nota mt-chico">{{ t('The box is fixed: the letter is reduced to {0} pt to fit.', [letraReducida]) }}
        <button v-if="!bloqueado" type="button" class="enlace" @click="e.ajustar = 'ambos'">{{ t('Fit the box to the content') }}</button></p>
      <div class="botonera mt-chico">
        <button v-for="[p, txt, cls] in [['negrita', 'B', 'fw'], ['cursiva', 'I', 'it'], ['subrayado', 'U', 'ul'], ['tachado', 'S', 'st'], ['mayusculas', 'AA', '']]" :key="p" type="button"
                class="btn btn-icono btn-chico btn-estilo" :class="[cls, { activo: estilo[p] }]" :aria-pressed="!!estilo[p]" :disabled="bloqueado"
                :title="{ negrita: t('Bold'), cursiva: t('Italic'), subrayado: t('Underline'), tachado: t('Strikethrough'), mayusculas: t('Uppercase') }[p]" @click="alternarEstilo(p)">{{ txt }}</button>
        <span class="separador" />
        <button v-for="[v, i] in [['izq', 'alin-izq'], ['centro', 'alin-centro'], ['der', 'alin-der']]" :key="v" type="button" class="btn btn-icono btn-chico"
                :class="{ activo: (estilo.alin || 'izq') === v }" :aria-pressed="(estilo.alin || 'izq') === v" :disabled="bloqueado" :aria-label="v" @click="poner('estilo', 'alin', v)"><Icono :nombre="i" :tam="15" /></button>
        <button v-for="[v, i] in [['arriba', 'alin-arriba'], ['medio', 'alin-medio'], ['abajo', 'alin-abajo']]" :key="v" type="button" class="btn btn-icono btn-chico"
                :class="{ activo: (estilo.valign || 'arriba') === v }" :aria-pressed="(estilo.valign || 'arriba') === v" :disabled="bloqueado" :aria-label="v" @click="poner('estilo', 'valign', v)"><Icono :nombre="i" :tam="15" /></button>
      </div>
      <div class="rejilla-2 mt-chico">
        <CampoColor :model-value="estilo.color || '#000000'" :etiqueta="t('Color')" :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'color', v)" />
        <CampoColor :model-value="estilo.fondo || null" :etiqueta="t('Background')" ninguno :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'fondo', v)" />
        <Medida :model-value="estilo.interlineado ?? 1.15" :etiqueta="t('Line spacing')" unidad="" :min="0.7" :max="4" :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'interlineado', v)" />
        <Medida :model-value="estilo.espaciado ?? 0" :etiqueta="t('Letter spacing')" unidad="pt" :min="-2" :max="40" :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'espaciado', v)" />
        <Medida :model-value="estilo.relleno ?? 0" :etiqueta="t('Inner margin')" :unidad="u" :min="0" :max="50" :disabled="bloqueado" @update:model-value="(v) => poner('estilo', 'relleno', v)" />
        <label class="check-linea"><input type="checkbox" :checked="!!estilo.multilinea" :disabled="bloqueado" @change="poner('estilo', 'multilinea', $event.target.checked)" />{{ t('Several lines') }}</label>
      </div>
      <label class="campo-mini mt-chico"><span>{{ t('If it does not fit') }}</span>
        <Seleccion :model-value="estilo.ajuste || 'reducir'" :disabled="bloqueado" :aria-label="t('If it does not fit')" @change="(v) => poner('estilo', 'ajuste', v)">
          <option value="reducir">{{ t('Reduce the size down to the minimum') }}</option>
          <option value="cortar">{{ t('Cut it with «…»') }}</option>
          <option value="ninguno">{{ t('Leave it (warn)') }}</option>
        </Seleccion>
      </label>
      <Medida v-if="(estilo.ajuste || 'reducir') === 'reducir'" class="mt-chico" :model-value="estilo.tam_min ?? 6" :etiqueta="t('Smallest letter')" unidad="pt" :min="3" :max="400" :disabled="bloqueado"
              @update:model-value="(v) => poner('estilo', 'tam_min', v)" />
    </template>

    <!-- Condición -->
    <h4>{{ t('Show only if') }}</h4>
    <label class="check-linea"><input type="checkbox" :checked="!!e.condicion" :disabled="bloqueado" @change="condicion($event.target.checked)" />{{ t('Depends on a data value') }}</label>
    <div v-if="e.condicion" class="rejilla-2 mt-chico">
      <label class="campo-mini col-2"><span>{{ t('Field') }}</span>
        <Seleccion v-model="e.condicion.campo" :disabled="bloqueado" :aria-label="t('Field')">
          <option v-for="c in camposTexto" :key="c.clave" :value="c.clave">{{ textoCampo(c) }}</option>
        </Seleccion>
      </label>
      <label class="campo-mini"><span>{{ t('Condition') }}</span>
        <Seleccion v-model="e.condicion.op" :disabled="bloqueado" :aria-label="t('Condition')">
          <option v-for="(txt, op) in OPERADORES()" :key="op" :value="op">{{ tx(txt) }}</option>
        </Seleccion>
      </label>
      <template v-if="e.condicion.op === 'entre'">
        <label class="campo-mini"><span>{{ t('From') }}</span><input type="number" :value="e.condicion.valor?.[0]" :disabled="bloqueado"
               @input="e.condicion.valor = [Number($event.target.value), e.condicion.valor?.[1] ?? 0]" /></label>
        <label class="campo-mini"><span>{{ t('To') }}</span><input type="number" :value="e.condicion.valor?.[1]" :disabled="bloqueado"
               @input="e.condicion.valor = [e.condicion.valor?.[0] ?? 0, Number($event.target.value)]" /></label>
      </template>
      <label v-else-if="!SIN_VALOR.includes(e.condicion.op)" class="campo-mini"><span>{{ t('Value') }}</span>
        <input :value="Array.isArray(e.condicion.valor) ? e.condicion.valor.join(', ') : e.condicion.valor" maxlength="200" :disabled="bloqueado"
               :placeholder="LISTAS.includes(e.condicion.op) ? t('values separated by commas') : ''" @change="condicionValor($event.target.value)" /></label>
    </div>
  </div>
</template>

<style scoped>
.panel-prop { display: flex; flex-direction: column; gap: 6px; }
.panel-prop h4 { margin: 12px 0 2px; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.prop-titulo { margin: 0; font-weight: 600; }
.parte-codigo { border: 1px solid var(--linea); border-radius: 6px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
.transformaciones { display: flex; flex-wrap: wrap; gap: 2px 10px; font-size: 0.8rem; }
.columna-tabla { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.4fr) 52px 52px auto auto; gap: 4px; align-items: center; }
.prop-cabeza { display: flex; gap: 8px; align-items: center; }
.prop-nombre { flex: 1; min-width: 0; font-size: 0.84rem; }
.botonera { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.botonera .activo, .btn.activo { background: var(--acento-claro); border-color: var(--acento-medio); color: var(--acento-texto); }
.separador { width: 1px; height: 20px; background: var(--linea); margin: 0 2px; }
.rejilla-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: end; }
.col-2 { grid-column: 1 / -1; }
.campo-mini { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.campo-mini > span { font-size: 0.72rem; color: var(--tinta-3); }
.campo-mini input { width: 100%; min-width: 0; }
.check-linea { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--tinta-2); min-height: 32px; }
.prop-area { width: 100%; resize: vertical; font-size: 0.84rem; box-sizing: border-box; }
.ayuda { font-size: 0.74rem; margin: 2px 0 0; }
.btn-estilo { font-family: Georgia, serif; font-size: 0.86rem; width: 30px; }
.btn-estilo.fw { font-weight: 700; }
.btn-estilo.it { font-style: italic; }
.btn-estilo.ul { text-decoration: underline; }
.btn-estilo.st { text-decoration: line-through; }
.segmentos { display: flex; }
.mono { font-family: ui-monospace, monospace; }
</style>
