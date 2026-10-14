<script setup>
import { t } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import Icono from '@/componentes/Icono.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { IDIOMAS_ETIQUETA, catalogos } from '@/modulos/etiquetado/etiquetas.js'
import { usarEditor } from './estado.js'
import CampoColor from './CampoColor.vue'
import Medida from './Medida.vue'

// La etiqueta sin nada elegido: medidas reales y unidad, orientación, área
// segura, fondo y borde, resolución de la imagen PNG, cuadrícula y cómo se
// imprime (una por página o varias en una hoja).
const ed = usarEditor()
const est = ed.estado
const d = computed(() => est.diseno)
const u = computed(() => d.value.unidad || 'mm')
const no = computed(() => !est.editable)

// Tamaños de la empresa (Configuración → Tipos de etiqueta) o los de fábrica
const tamanos = ref([])
onMounted(() => catalogos().then((c) => (tamanos.value = c.tamanos)).catch(() => {}))
const tamano = computed(() => tamanos.value.findIndex(({ ancho: w, alto: h }) => (Math.abs(w - d.value.ancho) < 0.05 && Math.abs(h - d.value.alto) < 0.05)
  || (Math.abs(h - d.value.ancho) < 0.05 && Math.abs(w - d.value.alto) < 0.05)))
function elegirTamano(i) {
  if (no.value || i === '' || i < 0) return
  const { ancho: w, alto: h } = tamanos.value[i]
  const horizontal = d.value.ancho >= d.value.alto
  d.value.ancho = horizontal ? Math.max(w, h) : Math.min(w, h)
  d.value.alto = horizontal ? Math.min(w, h) : Math.max(w, h)
}
function girarEtiqueta() {
  if (no.value) return
  ;[d.value.ancho, d.value.alto] = [d.value.alto, d.value.ancho]
}
function borde(activo) {
  if (no.value) return
  d.value.borde = activo ? { color: '#000000', grosor: 0.3, radio: 0 } : null
}

// Impresión en hoja: papeles habituales y cuántas caben
// En el script: en la plantilla cerraría la interpolación
const EJEMPLO = '{{manual.lote}}'
const PAPELES = [['Letter', 215.9, 279.4], ['A4', 210, 297], ['Legal', 215.9, 355.6]]
const hoja = computed(() => d.value.hoja)
const papel = computed(() => PAPELES.findIndex(([, w, h]) => Math.abs(w - hoja.value.papel_ancho) < 0.05 && Math.abs(h - hoja.value.papel_alto) < 0.05))
function elegirPapel(i) {
  if (no.value || i === '' || i < 0) return
  hoja.value.papel_ancho = PAPELES[i][1]
  hoja.value.papel_alto = PAPELES[i][2]
}
function caben() {
  if (no.value) return
  const h = hoja.value
  h.columnas = Math.max(1, Math.floor((h.papel_ancho - h.margen_izq + h.espacio_h) / (d.value.ancho + h.espacio_h)))
  h.filas = Math.max(1, Math.floor((h.papel_alto - h.margen_sup + h.espacio_v) / (d.value.alto + h.espacio_v)))
}
// Campos que se escriben al generar: lote, temporada, destino… ({{manual.clave}})
const variables = computed(() => d.value.variables || [])
const claveDe = (txt) => (txt || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 'c$1').slice(0, 30) || 'campo'
function agregarVariable() {
  if (no.value) return
  if (!d.value.variables) d.value.variables = []
  let n = d.value.variables.length + 1
  while (d.value.variables.some((v) => v.clave === `campo_${n}`)) n++
  d.value.variables.push({ clave: `campo_${n}`, etiqueta: t('Field {0}', [n]), defecto: null, obligatorio: false })
}
function renombrar(v, etiqueta) {
  const anterior = v.clave
  v.etiqueta = etiqueta
  if (usada(anterior)) return // si ya está en la etiqueta, la clave no cambia
  let clave = claveDe(etiqueta)
  let i = 2
  while (variables.value.some((x) => x !== v && x.clave === clave)) clave = `${claveDe(etiqueta).slice(0, 27)}_${i++}`
  v.clave = clave
}
const usada = (clave) => d.value.elementos.some((e) => [e.contenido, e.valor, e.campo, e.condicion?.campo].some((x) => (x || '').includes(`manual.${clave}`)))
function quitarVariable(i) {
  if (no.value) return
  d.value.variables.splice(i, 1)
}
const noCabe = computed(() => {
  const h = hoja.value
  if (h.modo !== 'hoja') return false
  return h.margen_izq + h.columnas * d.value.ancho + (h.columnas - 1) * h.espacio_h > h.papel_ancho + 0.01
    || h.margen_sup + h.filas * d.value.alto + (h.filas - 1) * h.espacio_v > h.papel_alto + 0.01
})
</script>

<template>
  <div class="panel-prop">
    <h4>{{ t('Label dimensions') }}</h4>
    <div class="segmentos" role="group" :aria-label="t('Unit')">
      <button v-for="x in ['mm', 'cm', 'in']" :key="x" type="button" class="segmento" :aria-pressed="u === x" :disabled="no" @click="d.unidad = x">{{ x }}</button>
    </div>
    <Seleccion :model-value="tamano" :disabled="no" :aria-label="t('Common dimensions')" @change="elegirTamano">
      <option :value="-1">{{ t('Custom dimensions') }}</option>
      <option v-for="(x, i) in tamanos" :key="i" :value="i">{{ x.nombre }}</option>
    </Seleccion>
    <div class="rejilla-2">
      <Medida v-model="d.ancho" :etiqueta="t('Width')" :unidad="u" :min="5" :max="1000" :disabled="no" />
      <Medida v-model="d.alto" :etiqueta="t('Height')" :unidad="u" :min="5" :max="1000" :disabled="no" />
    </div>
    <button type="button" class="btn btn-chico" :disabled="no" @click="girarEtiqueta"><Icono nombre="girar" :tam="15" />
      {{ d.ancho >= d.alto ? t('Switch to portrait') : t('Switch to landscape') }}</button>

    <h4>{{ t('Language and numbers') }}</h4>
    <div class="rejilla-2">
      <label class="campo-mini"><span>{{ t('Language of months and yes/no') }}</span>
        <Seleccion :model-value="d.idioma || 'en'" :disabled="no" :aria-label="t('Language')" @change="(v) => (d.idioma = v)">
          <option v-for="[c, n] in IDIOMAS_ETIQUETA()" :key="c" :value="c">{{ n }}</option>
        </Seleccion></label>
      <label class="campo-mini"><span>{{ t('Thousands separator') }}</span>
        <Seleccion :model-value="d.separador_miles ?? ','" :disabled="no" :aria-label="t('Thousands separator')" @change="(v) => (d.separador_miles = v)">
          <option value=",">1,000</option><option value=".">1.000</option><option value=" ">1 000</option><option value="'">1'000</option><option value="">1000</option>
        </Seleccion></label>
      <label class="campo-mini"><span>{{ t('Decimal separator') }}</span>
        <Seleccion :model-value="d.separador_decimal || '.'" :disabled="no" :aria-label="t('Decimal separator')" @change="(v) => (d.separador_decimal = v)">
          <option value=".">0.50</option><option value=",">0,50</option>
        </Seleccion></label>
    </div>

    <h4>{{ t('Print area') }}</h4>
    <div class="rejilla-2">
      <Medida v-model="d.margen" :etiqueta="t('Safe margin')" :unidad="u" :min="0" :max="100" :disabled="no" />
      <label class="campo-mini"><span>{{ t('PNG resolution') }}</span>
        <Seleccion :model-value="d.dpi" :disabled="no" :aria-label="t('PNG resolution')" @change="(v) => (d.dpi = Number(v))">
          <option v-for="x in [203, 300, 600]" :key="x" :value="x">{{ x }} dpi</option>
        </Seleccion>
      </label>
    </div>
    <p class="ayuda">{{ t('The dashed line is the safe margin: the printer may cut what is outside. 203 and 300 dpi are the usual label printers.') }}</p>

    <h4>{{ t('Background and border') }}</h4>
    <div class="rejilla-2">
      <CampoColor v-model="d.fondo" :etiqueta="t('Background')" :disabled="no" />
      <label class="check-linea"><input type="checkbox" :checked="!!d.borde" :disabled="no" @change="borde($event.target.checked)" />{{ t('Border') }}</label>
      <template v-if="d.borde">
        <CampoColor v-model="d.borde.color" :etiqueta="t('Border color')" :disabled="no" />
        <Medida v-model="d.borde.grosor" :etiqueta="t('Thickness')" :unidad="u" :min="0.05" :max="10" :disabled="no" />
        <Medida v-model="d.borde.radio" :etiqueta="t('Corner radius')" :unidad="u" :min="0" :max="50" :disabled="no" />
      </template>
    </div>

    <h4>{{ t('Grid') }}</h4>
    <div class="rejilla-2">
      <Medida v-model="d.cuadricula.paso" :etiqueta="t('Step')" :unidad="u" :min="0.1" :max="50" :disabled="no" />
      <div>
        <label class="check-linea"><input v-model="d.cuadricula.visible" type="checkbox" />{{ t('Show') }}</label>
        <label class="check-linea"><input v-model="d.cuadricula.ajustar" type="checkbox" />{{ t('Snap to grid') }}</label>
      </div>
    </div>

    <h4>{{ t('Fields written when generating') }}</h4>
    <p class="ayuda">{{ t('Information that is not in the system (lot, season, destination…): it is asked when generating. Use it like any field or as {0} in a text.', [EJEMPLO]) }}</p>
    <div v-for="(v, i) in variables" :key="i" class="variable">
      <div class="rejilla-2">
        <label class="campo-mini"><span>{{ t('Name') }}</span><input :value="v.etiqueta" maxlength="60" :disabled="no" @change="renombrar(v, $event.target.value)" /></label>
        <label class="campo-mini"><span>{{ t('Default value') }}</span><input v-model="v.defecto" maxlength="200" :disabled="no" /></label>
      </div>
      <div class="variable-pie">
        <code>{{ `manual.${v.clave}` }}</code>
        <label class="check-linea"><input v-model="v.obligatorio" type="checkbox" :disabled="no" />{{ t('Required') }}</label>
        <span v-if="usada(v.clave)" class="etiqueta ms-0">{{ t('In use') }}</span>
        <button v-else type="button" class="btn btn-icono btn-chico" :disabled="no" :aria-label="t('Remove')" @click="quitarVariable(i)"><Icono nombre="basura" :tam="14" /></button>
      </div>
    </div>
    <button type="button" class="btn btn-chico" :disabled="no || variables.length >= 30" @click="agregarVariable"><Icono nombre="mas" :tam="14" />{{ t('Add field to fill in') }}</button>

    <h4>{{ t('How it prints') }}</h4>
    <div class="segmentos" role="group" :aria-label="t('How it prints')">
      <button type="button" class="segmento" :aria-pressed="hoja.modo === 'individual'" :disabled="no" @click="hoja.modo = 'individual'">{{ t('One per page (label printer)') }}</button>
      <button type="button" class="segmento" :aria-pressed="hoja.modo === 'hoja'" :disabled="no" @click="hoja.modo = 'hoja'">{{ t('Several per sheet') }}</button>
    </div>
    <template v-if="hoja.modo === 'hoja'">
      <Seleccion :model-value="papel" :disabled="no" :aria-label="t('Paper')" @change="elegirPapel">
        <option :value="-1">{{ t('Custom paper') }}</option>
        <option v-for="([n, w, h], i) in PAPELES" :key="n" :value="i">{{ n }} ({{ w }} × {{ h }} mm)</option>
      </Seleccion>
      <div class="rejilla-2">
        <Medida v-model="hoja.papel_ancho" :etiqueta="t('Paper width')" :unidad="u" :min="10" :max="2000" :disabled="no" />
        <Medida v-model="hoja.papel_alto" :etiqueta="t('Paper height')" :unidad="u" :min="10" :max="2000" :disabled="no" />
        <Medida :model-value="hoja.columnas" :etiqueta="t('Columns')" unidad="" :min="1" :max="50" :disabled="no" @update:model-value="(v) => (hoja.columnas = Math.round(v))" />
        <Medida :model-value="hoja.filas" :etiqueta="t('Rows')" unidad="" :min="1" :max="100" :disabled="no" @update:model-value="(v) => (hoja.filas = Math.round(v))" />
        <Medida v-model="hoja.margen_izq" :etiqueta="t('Left margin')" :unidad="u" :min="0" :max="500" :disabled="no" />
        <Medida v-model="hoja.margen_sup" :etiqueta="t('Top margin')" :unidad="u" :min="0" :max="500" :disabled="no" />
        <Medida v-model="hoja.espacio_h" :etiqueta="t('Space between columns')" :unidad="u" :min="0" :max="200" :disabled="no" />
        <Medida v-model="hoja.espacio_v" :etiqueta="t('Space between rows')" :unidad="u" :min="0" :max="200" :disabled="no" />
      </div>
      <button type="button" class="btn btn-chico" :disabled="no" @click="caben">{{ t('As many as fit') }}</button>
      <p v-if="noCabe" class="texto-error">{{ t('The labels do not fit on the sheet with these columns, rows and margins.') }}</p>
      <p v-else class="ayuda">{{ t('{0} labels per sheet.', [hoja.columnas * hoja.filas]) }}</p>
    </template>
  </div>
</template>

<style scoped>
.panel-prop { display: flex; flex-direction: column; gap: 8px; }
.panel-prop h4 { margin: 12px 0 0; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--tinta-3); font-weight: 600; }
.panel-prop h4:first-child { margin-top: 0; }
.rejilla-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: end; }
.campo-mini { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.campo-mini > span { font-size: 0.72rem; color: var(--tinta-3); }
.check-linea { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--tinta-2); min-height: 30px; }
.ayuda { font-size: 0.74rem; margin: 0; }
.segmentos { display: flex; flex-wrap: wrap; }
.btn-chico { align-self: flex-start; }
.variable { border: 1px solid var(--linea); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.variable-pie { display: flex; align-items: center; gap: 8px; }
.variable-pie code { font-size: 0.72rem; color: var(--tinta-3); flex: 1; overflow: hidden; text-overflow: ellipsis; }
</style>
