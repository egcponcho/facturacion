<script setup>
import { t, tx } from '../../i18n/index.js'
import { computed, reactive, ref, watch } from 'vue'
import Seleccion from '../Seleccion.vue'
import { api } from '../../api'
import { plural } from '../../utils'
import { M } from '../../clasificacion/useClasificacion'
import { avisar, errorApi } from '../../stores/ui'
import Icono from '../Icono.vue'
import CampoCategoria from './CampoCategoria.vue'
import SacBuscador from './SacBuscador.vue'
import ComposicionParte from './ComposicionParte.vue'

// Formulario de la ficha técnica, con la misma lógica del clasificador:
// empieza por qué es el producto y va pidiendo solo lo que hace falta para su
// capítulo y partida. Lo que se deduce del nombre, el uso o la composición se
// llena solo (sin pisar lo que la persona eligió) y se explica.
const props = defineProps({
  f: { type: Object, required: true }, // ficha editable (reactiva)
  r: { type: Object, default: null }, // resultado del motor
  ctx: { type: Object, required: true },
  producto: { type: Object, required: true },
  paises: { type: Array, default: () => [] },
  editable: Boolean,
})
const emit = defineEmits(['subir-foto', 'borrar-foto', 'contexto', 'acuerdos', 'sac'])
const f = props.f

// ---- Lo que eligió la persona y lo que se llenó solo ----------------------
// Al abrir una ficha guardada, lo que ya tiene valor cuenta como elegido.
const tocados = reactive(new Set([...Object.entries(f).filter(([k, v]) => !['comp', 'partidas'].includes(k) && v !== '' && v != null && v !== false).map(([k]) => k)]))
const autos = reactive(new Set())
const detectado = ref(null)
const ensenarCerrado = ref(false)

function tocar(...ks) {
  ks.forEach((k) => { tocados.add(k); autos.delete(k) })
}

function deteccion() {
  if (!props.editable) return
  const d = M.detectarFicha({ ...f }, props.ctx.palabras)
  for (const k of ['tipo', ...M.ATTR_IDS]) {
    if (tocados.has(k)) continue
    if (d[k] !== undefined && d[k] !== '') {
      if (f[k] !== d[k]) f[k] = d[k]
      autos.add(k)
    } else if (autos.has(k)) {
      f[k] = M.ATTR_BY[k]?.tipo === 'check' ? false : ''
      autos.delete(k)
    }
  }
  const libres = M.NAC_IDS.filter((k) => !tocados.has(k))
  const tmp = M.detectarNac({ ...f, ...Object.fromEntries(libres.map((k) => [k, undefined])) }, true)
  libres.forEach((k) => { if (tmp[k] !== undefined) f[k] = tmp[k] })
  detectado.value = d
}
let espera
function detectarLuego() {
  clearTimeout(espera)
  espera = setTimeout(deteccion, 250)
}

const detTexto = computed(() => {
  const d = detectado.value
  if (!d) return ''
  const out = []
  if (d.tipo && autos.has('tipo')) out.push(M.TIPO_CORTO[d.tipo])
  if (d.estiloCalz && f.tipo === 'calzado') out.push(M.opcionLbl('estiloCalz', d.estiloCalz).toLowerCase())
  if (d.genero && pideGenero.value && autos.has('genero')) out.push({ M: t('men'), F: t('women'), U: t('unisex') }[d.genero])
  if (d.tejido && M.grupoTipo(f.tipo) === 'prenda') out.push(d.tejido === 'punto' ? t('knitted') : t('woven'))
  if (d.hechura && f.tipo === 'chaqueta') out.push(M.opcionLbl('hechura', d.hechura).toLowerCase())
  if (d.recubierta && M.ATTR_BY.recubierta.aplica(f)) out.push(t('coated fabric'))
  if (d.puntera === 'metalica' && f.tipo === 'calzado') out.push(t('metal toe cap'))
  if (!out.length) return ''
  return t('Detected: {0}{1}. You can change it below.', [out.join(', '), d._palabra ? t(' (keyword “{0}”)', [d._palabra]) : ''])
})

// ---- Producto: categoría, género, edad, tallas ------------------------------
const pideGenero = computed(() => ['prenda', 'calzado', 'gorra'].includes(M.grupoTipo(f.tipo)))
const generoFijo = computed(() => (M.ATTR_BY.genero.fijo ? M.ATTR_BY.genero.fijo(f) : null))
const soloAdulto = computed(() => f.tipo === 'calzado' && ['seguridad', 'tacon', 'tacos', 'esqui'].includes(f.estiloCalz))
const sinBebe = computed(() => soloAdulto.value || f.tipo === 'brasier' || (f.tipo === 'chaqueta' && ['blazer', 'reflectivo'].includes(f.hechura)))
const GENEROS = [['M', t('Men'), t('Men or boys')], ['F', t('Women'), t('Women or girls')], ['U', t('Unisex'), '']]
const EDADES = [['adulto', t('Adult'), ''], ['nino', t('Child'), t('Child, girl or youth')], ['bebe', t('Baby'), t('Up to 86 cm tall')]]

watch(generoFijo, (g) => { if (g && f.genero !== g) f.genero = g }, { immediate: true })

function elegirTipo(t) {
  f.tipo = t
  tocar('tipo')
  M.normalizar(f)
  deteccion()
}
function elegirGenero(v) {
  f.genero = v
  tocar('genero')
}
function ponerEdad(v, manual = true) {
  f.edadNac = v
  if (M.ATTR_BY.edad.aplica({ ...f, edad: '' })) f.edad = v === 'bebe' ? 'bebe' : 'general'
  if (manual) tocar('edadNac', 'edad')
}

// ---- Características según el capítulo ---------------------------------------
const s = computed(() => props.r?.s || f)
const preguntar = computed(() => (f.tipo ? M.ATTRS.filter((a) => M.estadoAttr(a, s.value) === 'preguntar') : []))
const definidos = computed(() => (f.tipo ? M.ATTRS.filter((a) => M.estadoAttr(a, s.value) === 'definido' && s.value[a.id]) : []))
const ops = (a) => M.opcionesValidas(a, s.value)
function elegirAttr(a, v) {
  f[a.id] = v
  tocar(a.id)
  if (v && a.implica) M.aplicarImplica(f, a.id, v).forEach((k) => tocar(k))
  M.normalizar(f)
}
const CAPITULO = { calzado: '64', prenda: '61 / 62', bolso: '42', gorra: '65' }
const MOTIVO = { composition: 'composition', 'product type': t('product type'), 'your choices': t('your choices') }

// ---- Composición por partes ---------------------------------------------------
const partes = computed(() => (f.tipo ? M.partesDe(f.tipo, s.value) : []))
const principales = computed(() => M.partesPrincipales(f.tipo))
const filas = reactive({})
function filasDe(p) {
  if (!filas[p]) filas[p] = M.filasDesdeTexto(f.comp?.[p])
  return filas[p]
}
function cambioParte(p, txt) {
  f.comp = { ...f.comp, [p]: txt }
  detectarLuego()
}
const COMP_HINT = {
  prenda: t('The fiber that weighs most in the outer fabric governs.'),
  calzado: t('Upper: by external surface, without reinforcements or trims. Sole: by the surface that touches the ground.'),
  bolso: t('The material of the outer surface governs.'),
}
// Composiciones ya usadas: del mismo estilo y las más frecuentes en la categoría
function usadasDe(p) {
  const out = []
  const meter = (txt, de) => { if (txt && !out.some((x) => M.norm(x.txt) === M.norm(txt))) out.push({ txt, de }) }
  const recs = props.ctx.recs.filter((x) => x.id !== f.id && x.comp?.[p])
  recs.filter((x) => M.norm(x.estilo) === M.norm(f.estilo)).forEach((x) => meter(String(x.comp[p]).trim(), t('style {0}{1}', [x.estilo, x.color ? `, ${x.color}` : ''])))
  const cuenta = {}
  recs.filter((x) => x.tipo === f.tipo).forEach((x) => {
    const t = String(x.comp[p]).trim()
    cuenta[t] = cuenta[t] || { n: 0, marca: 0 }
    cuenta[t].n++
    if (f.marca && M.norm(x.marca) === M.norm(f.marca)) cuenta[t].marca++
  })
  Object.entries(cuenta).sort((a, b) => b[1].marca - a[1].marca || b[1].n - a[1].n).slice(0, 3)
    .forEach(([txt, c]) => meter(txt, `${plural(c.n, t('product'), t('products'))}${c.marca ? t(' of {0}', [f.marca]) : ''}`))
  return out.slice(0, 3)
}

async function ensenarMaterial(palabra, equivale) {
  try {
    await api.post('/clasificacion/sinonimos', { palabra, equivale })
    emit('contexto')
    avisar(t('Learned: “{0}” = {1}. It will be recognized in every sheet.', [palabra, (M.MAT_EQUIV.find((x) => x[0] === equivale) || ['', equivale])[1]]))
  } catch (e) {
    errorApi(e)
  }
}

// ---- Enseñar una palabra clave cuando la categoría no se reconoció ---------------
const NO_FRASE = new Set('tnf the north face vans m w u ua mn wm mens men womens women kids kid youth unisex black white grey gray blue red green brown size pack pk and with de del para'.split(' '))
const frase = ref('')
const soloMarca = ref(true)
const tipoDetectado = computed(() => M.detectarCon([f.estilo, f.descArchivo].filter(Boolean).join(' '), {}, '', props.ctx.palabras, f.marca).tipo || '')
const fraseSugerida = computed(() => String(f.descArchivo || '').split(/[\s/,;()-]+/).filter((w) => w && !/\d/.test(w) && w.length >= 2 && !NO_FRASE.has(M.norm(w))).slice(0, 2).join(' '))
const mostrarEnsenar = computed(() => props.editable && !ensenarCerrado.value && f.tipo && tocados.has('tipo') && tipoDetectado.value !== f.tipo && !!fraseSugerida.value && !autos.has('tipo'))
watch(fraseSugerida, (v) => (frase.value = v), { immediate: true })
async function ensenarPalabra() {
  if (frase.value.trim().length < 2) return avisar(t('Write the word or phrase.'), 'error')
  const atributos = f.tipo === 'calzado' && f.estiloCalz ? { estiloCalz: f.estiloCalz } : {}
  try {
    await api.post('/clasificacion/palabras', { frase: frase.value.trim(), tipo: f.tipo, marca: soloMarca.value ? f.marca || null : null, atributos })
    ensenarCerrado.value = true
    emit('contexto')
    avisar(t('Learned: “{0}” will be recognized as {1}.', [frase.value.trim(), M.TIPO_CORTO[f.tipo]]))
  } catch (e) {
    errorApi(e)
  }
}

// ---- Preguntas de los códigos nacionales --------------------------------------
const preguntasNac = computed(() => {
  if (!props.r) return []
  const ids = new Set(Object.values(props.r.partidas).flatMap((x) => x.pedir || []))
  return M.NAC_PREG.filter((q) => ids.has(q.id) && q.id !== 'edadNac' && q.id !== 'genero')
})
function respNac(k, v) {
  f[k] = v
  tocar(k)
}

// ---- Acuerdos comerciales según el país de origen (detalle en su pestaña) ------
const nAcuerdos = computed(() => (props.ctx.destinos || []).filter((d) => f.origen === d.iso
  || (props.ctx.acuerdos || []).some((a) => a.origenes.includes(f.origen) && a.destinos.includes(d.iso))).length)

// ---- Cualquier producto: subpartida elegida en el SAC --------------------------
function elegirSac(x) {
  f.sacElegido = x.codigo
  f.sacDesc = x.descripcion
  M.setSac([{ codigo: x.codigo, descripcion: x.descripcion }])
  tocar('sacElegido')
  emit('sac', x.codigo)
}

// ---- Avance ----------------------------------------------------------------------
const pasos = computed(() => {
  const faltanProd = [!f.tipo, pideGenero.value && !f.genero, !M.edadDe(f), !f.origen].filter(Boolean).length
  const pend = preguntar.value.filter((a) => a.tipo !== 'check' && !a.info && M.vacio(s.value[a.id])).length
  const tots = principales.value.map((p) => (f.comp?.[p] ? M.totalTexto(f.comp[p]) : 0))
  const compOk = tots.every((t) => Math.abs(t - 100) < 0.05)
  const nFotos = props.producto.fotos.length
  return [
    ['blk-producto', t('Product'), faltanProd ? 'pend' : 'ok', faltanProd ? t('{0} to fill', [faltanProd]) : ''],
    ['blk-carac', t('Features'), !f.tipo ? '' : pend ? 'pend' : 'ok', pend ? t('{0} to answer', [pend]) : ''],
    ['blk-comp', t('Composition'), !f.tipo ? '' : compOk ? 'ok' : 'pend', !f.tipo || compOk ? '' : tots.some((n) => n > 0) ? t('adds up to {0}%', [tots.filter((n) => Math.abs(n - 100) >= 0.05).join(' · ')]) : t('missing')],
    ['blk-fotos', t('Photos'), nFotos ? 'ok' : '', nFotos ? String(nFotos) : 'optional'],
  ]
})
function irA(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function editarCom() {
  if (!f.comManual) {
    f.descCom = props.r?.descCom || props.producto.descripcion_comercial || ''
    f.comManual = true
  } else f.comManual = false
}
// Descripción aduanera: se arma sola; se puede escribir a mano
function editarDesc() {
  if (!f.descManual) {
    f.desc = props.r?.desc || ''
    f.descManual = true
  } else f.descManual = false
}

if (props.editable) deteccion()
</script>

<template>
  <div class="ficha-form">
    <nav class="pasos" :aria-label="t('Sheet progress')">
      <button v-for="([id, l, e, x], i) in pasos" :key="id" type="button" :class="e" @click="irA(id)">
        <b>{{ tx(i + 1) }}</b> {{ tx(l) }}{{ tx(e === 'ok' ? ' ✓' : '') }}{{ tx(x ? ` · ${x}` : '') }}
      </button>
      <span class="req-nota"><span class="req-ast">*</span> {{ t('Required for a complete sheet') }}</span>
    </nav>

    <!-- Producto -->
    <section id="blk-producto" class="bloque">
      <div class="bloque-head"><h3>{{ t('Product') }}</h3><span class="sub">{{ t('What it is and who it is for. Shared by every size and prepack.') }}</span></div>
      <div class="fila2">
        <div class="campo-f">
          <label for="f_categoria">{{ t('Category') }}<span class="req-ast">*</span></label>
          <CampoCategoria id="f_categoria" :model-value="f.tipo" :disabled="!props.editable" @update:model-value="elegirTipo" />
          <p v-if="detTexto" class="hint det" :title="tx(detTexto)">{{ tx(detTexto) }}</p>
          <p v-else-if="f.tipo" class="hint">{{ t('{0}only what changes its code is asked', [CAPITULO[M.grupoTipo(f.tipo)] ? t('Chapter {0} · ', [CAPITULO[M.grupoTipo(f.tipo)]]) : '']) }}</p>
        </div>
        <div class="campo-f">
          <span class="lbl-f">{{ t('Generic') }}</span>
          <span class="generico-fijo" :title="t('First 8 digits of the item code: all its sizes share this sheet')">{{ tx(producto.codigo_generico || '—') }}<small>{{ tx(producto.skus) }} {{ tx(producto.skus === 1 ? 'size' : 'sizes') }}<template v-if="producto.rango_tallas"> ({{ tx(producto.rango_tallas) }})</template><template v-if="producto.n_prepacks"> · {{ tx(producto.n_prepacks) }} {{ tx(producto.n_prepacks === 1 ? 'prepack' : 'prepacks') }}</template></small></span>
        </div>
      </div>
      <div v-if="f.tipo === 'otro_sac'" class="fila2 otro-sac">
        <div class="campo-f">
          <label for="f_sac">{{ t('SAC subheading') }}<span class="req-ast">*</span></label>
          <SacBuscador id="f_sac" :model-value="f.sacElegido || ''" :descripcion="f.sacDesc || ''" :disabled="!props.editable" @elegir="elegirSac" />
          <p class="hint">{{ t('Any product of the tariff: its section, chapter and explanatory notes and the national codes of each country apply.') }}</p>
        </div>
        <div class="campo-f">
          <label for="f_quees">{{ t('Name in Spanish for customs') }} <span class="opcional">{{ t('(optional)') }}</span></label>
          <input id="f_quees" v-model="f.queEs" class="entrada" type="text" maxlength="80" :disabled="!props.editable" :placeholder="t('E.g. audífonos inalámbricos')" />
          <p class="hint">{{ t('Without it, the customs description uses the text of the subheading.') }}</p>
        </div>
      </div>
      <div class="fila3">
        <div v-if="pideGenero || generoFijo" class="campo-f">
          <span class="lbl-f">{{ t('Gender') }}<span class="req-ast">*</span></span>
          <div class="segs" role="radiogroup" :aria-label="t('Gender')">
            <button v-for="[v, txt, tt] in GENEROS" :key="v" type="button" role="radio" :aria-checked="f.genero === v" :title="tx(generoFijo && v !== generoFijo ? t('This garment is always classified as women’s') : tt)"
                    :disabled="!props.editable || (!!generoFijo && v !== generoFijo)" @click="elegirGenero(v)">{{ tx(txt) }}</button>
          </div>
        </div>
        <div class="campo-f">
          <span class="lbl-f">{{ t('Who it is for') }}<span class="req-ast">*</span></span>
          <div class="segs" role="radiogroup" :aria-label="t('Who it is for')">
            <button v-for="[v, txt, tt] in EDADES" :key="v" type="button" role="radio" :aria-checked="M.edadDe(f) === v"
                    :disabled="!props.editable || (v === 'bebe' && sinBebe) || (v === 'nino' && soloAdulto)"
                    :title="tx((v === 'bebe' && sinBebe) || (v === 'nino' && soloAdulto) ? t('Does not apply to this product') : tt)" @click="ponerEdad(v)">{{ tx(txt) }}</button>
          </div>
        </div>
      </div>
      <div class="fila2">
        <div class="campo-f">
          <label for="f_origen">{{ t('Country of origin') }}<span class="req-ast">*</span></label>
          <Seleccion id="f_origen" v-model="f.origen" class="entrada" :disabled="!props.editable">
            <option value="">{{ t('Choose…') }}</option>
            <option v-for="x in props.paises" :key="x.codigo" :value="x.codigo">{{ tx(x.nombre) }}</option>
          </Seleccion>
          <p class="hint"><button v-if="f.origen" type="button" class="btn-texto" @click="emit('acuerdos')">{{ t('Trade agreements: {0} of {1} destinations', [nAcuerdos, (props.ctx.destinos || []).length]) }}</button><template v-else>{{ t('Decides the trade agreements by destination') }}</template></p>
        </div>
        <div class="campo-f">
          <label for="f_uso">{{ t('What it is for') }} <span class="opcional">{{ t('(optional)') }}</span></label>
          <input id="f_uso" v-model="f.uso" class="entrada" type="text" maxlength="200" :disabled="!props.editable"
                 :placeholder="t('E.g. bag worn on the waist to carry climbing chalk')" @input="detectarLuego" />
        </div>
      </div>
      <div class="descripciones">
        <div class="campo-f">
          <div class="lbl-fila"><label for="f_desc">{{ t('Customs description') }} <span class="opcional">{{ tx(f.descManual ? t('(edited by hand)') : t('(built from the sheet · Spanish, as declared at customs)')) }}</span></label><button v-if="props.editable" type="button" class="btn-texto" @click="editarDesc">{{ tx(f.descManual ? t('Use automatic') : t('Edit')) }}</button></div>
          <div class="desc-fila">
            <textarea id="f_desc" :value="f.descManual ? f.desc : (props.editable ? props.r?.desc : producto.descripcion_aduana) || ''" class="entrada" rows="2" maxlength="400"
                      :readonly="!f.descManual || !props.editable" :placeholder="t('Appears when you choose the category and the composition')" @input="f.desc = $event.target.value"></textarea>
          </div>
        </div>
        <div class="campo-f">
          <div class="lbl-fila"><label for="f_desc_com">{{ t('Commercial description') }} <span class="opcional">{{ tx(f.comManual ? t('(edited by hand)') : t('(type and brand, as on invoices and packing lists)')) }}</span></label><button v-if="props.editable" type="button" class="btn-texto" @click="editarCom">{{ tx(f.comManual ? t('Use automatic') : t('Edit')) }}</button></div>
          <div class="desc-fila">
            <textarea id="f_desc_com" :value="f.comManual ? f.descCom : (props.editable ? props.r?.descCom : producto.descripcion_comercial) || ''" class="entrada comercial" rows="2" maxlength="300"
                      :readonly="!f.comManual || !props.editable" :placeholder="t('Appears when you choose the category')" @input="f.descCom = $event.target.value"></textarea>
          </div>
        </div>
      </div>
      <div v-if="mostrarEnsenar" class="ensenar">
        <b>{{ t('Teach the system.') }}</b>
        {{ t('{0} and you chose “{1}”. Save a keyword so it is recognized next time.', [tipoDetectado ? t('From the name it looked like “{0}”', [M.TIPO_CORTO[tipoDetectado]]) : t('The category was not recognized from the name'), M.TIPO_CORTO[f.tipo]]) }}
        <div class="fila-flex mt-chico">
          <input v-model="frase" class="entrada" type="text" :aria-label="t('Keyword')" style="max-width: 240px" />
          <label v-if="f.marca" class="check"><input v-model="soloMarca" type="checkbox" /><span>{{ t('Only for {0}', [f.marca]) }}</span></label>
          <button type="button" class="btn btn-chico" @click="ensenarPalabra">{{ t('Save keyword') }}</button>
          <button type="button" class="btn btn-chico btn-fantasma" @click="ensenarCerrado = true">{{ t('Not now') }}</button>
        </div>
      </div>
    </section>

    <!-- Ficha técnica: características y composición -->
    <section class="bloque">
      <div class="bloque-head">
        <h3>{{ t('Technical sheet') }}</h3><span class="vbadge">{{ t('Version {0}', [producto.version_ficha]) }}</span>
        <span class="sub">{{ tx(f.tipo ? M.TIPO_LBL[f.tipo] : t('Choose the category first')) }}</span>
      </div>

      <fieldset v-if="f.tipo" id="blk-carac" class="fs" :disabled="!props.editable">
        <legend>{{ t('Features') }}</legend>
        <p v-if="!preguntar.length" class="hint">{{ t('This category needs no more data to be classified.') }}</p>
        <div class="rejilla-attrs">
        <template v-for="a in preguntar" :key="a.id">
          <label v-if="a.tipo === 'check'" class="check-f"><input type="checkbox" :checked="!!f[a.id]" @change="elegirAttr(a, $event.target.checked)" /><span>{{ tx(a.label) }}</span></label>
          <div v-else-if="a.tipo === 'select'" class="campo-f select-f">
            <label :for="`a_${a.id}`">{{ tx(a.label) }}<span v-if="!a.info" class="req-ast">*</span><span v-if="a.ayuda" class="opcional"> ({{ tx(a.ayuda) }})</span></label>
            <Seleccion :id="`a_${a.id}`" class="entrada" :value="f[a.id] || ''" @change="elegirAttr(a, $event)">
              <option value="">{{ t('Choose…') }}</option>
              <option v-for="o in ops(a)" :key="o.v" :value="o.v">{{ tx(o.l) }}</option>
            </Seleccion>
          </div>
          <div v-else class="opts">
            <span class="lbl-f">{{ tx(a.label) }}<span v-if="!a.info" class="req-ast">*</span><span v-if="a.ayuda" class="opcional"> ({{ tx(a.ayuda) }})</span><span v-if="a.info" class="opcional"> {{ t('(detail)') }}</span>
              <span v-if="autos.has(a.id) && f[a.id]" class="auto-tag">auto</span></span>
            <div class="segs" role="radiogroup" :aria-label="tx(a.label)">
              <button v-for="o in ops(a)" :key="o.v" type="button" role="radio" :aria-checked="s[a.id] === o.v" @click="elegirAttr(a, o.v)">{{ tx(o.l) }}</button>
            </div>
          </div>
        </template>
        </div>
        <p v-if="definidos.length" class="hint ya">
          {{ t('Already defined:') }}
          <template v-for="(a, i) in definidos" :key="a.id">{{ tx(i ? ' · ' : '') }}{{ tx(a.label) }}: <b>{{ tx(M.opcionLbl(a.id, s[a.id]).toLowerCase()) }}</b> <span class="apagado">{{ t('(by {0})', [MOTIVO[M.motivoDefinido(a, s)]]) }}</span></template>
        </p>
      </fieldset>

      <fieldset v-if="partes.length" id="blk-comp" class="fs">
        <legend>{{ t('Composition') }}</legend>
        <p class="hint" style="margin-bottom: 8px">{{ tx(COMP_HINT[M.grupoTipo(f.tipo)] || t('Materials of the product and their percentage.')) }}</p>
        <div class="rejilla-partes">
        <ComposicionParte v-for="p in partes" :key="`${f.tipo}-${p}`" :parte="p" :filas="filasDe(p)" :s="s" :recs="props.ctx.recs"
                          :usadas="props.editable ? usadasDe(p) : []" :principal="principales.includes(p)" :editable="props.editable"
                          @cambio="cambioParte" @ensenar="ensenarMaterial" />
        </div>
      </fieldset>

      <fieldset v-if="preguntasNac.length && props.editable" class="fs">
        <legend>{{ t('For national codes') }}</legend>
        <p class="hint" style="margin-bottom: 8px">{{ t('Some destination countries split this subheading further.') }}</p>
        <template v-for="q in preguntasNac" :key="q.id">
          <div v-if="q.tipo === 'num'" class="campo-f" style="max-width: 280px">
            <label :for="`n_${q.id}`">{{ tx(q.label) }}</label>
            <input :id="`n_${q.id}`" :value="f[q.id]" class="entrada" type="number" min="0" step="0.01" @input="respNac(q.id, $event.target.value)" />
          </div>
          <div v-else class="opts">
            <span class="lbl-f">{{ tx(q.label) }}</span>
            <div class="segs">
              <template v-if="q.tipo === 'sino'">
                <button type="button" role="radio" :aria-checked="f[q.id] === true" @click="respNac(q.id, true)">{{ t('Yes') }}</button>
                <button type="button" role="radio" :aria-checked="f[q.id] === false" @click="respNac(q.id, false)">{{ t('No') }}</button>
              </template>
              <template v-else-if="q.ops">
                <button v-for="[v, txt] in q.ops" :key="v" type="button" role="radio" :aria-checked="f[q.id] === v" @click="respNac(q.id, v)">{{ tx(txt) }}</button>
              </template>
              <template v-else-if="M.ATTR_BY[q.id]">
                <button v-for="o in M.ATTR_BY[q.id].ops" :key="o.v" type="button" role="radio" :aria-checked="f[q.id] === o.v" @click="respNac(q.id, o.v)">{{ tx(o.l) }}</button>
              </template>
            </div>
          </div>
        </template>
      </fieldset>

      <fieldset id="blk-fotos" class="fs">
        <legend>{{ t('Photos') }}</legend>
        <div class="fotos">
          <figure v-for="x in producto.fotos" :key="x.id" class="foto">
            <a :href="`/api/productos/fotos/${x.id}`" target="_blank" rel="noopener"><img :src="`/api/productos/fotos/${x.id}`" :alt="tx(x.nombre)" loading="lazy" /></a>
            <button v-if="props.editable" type="button" :aria-label="t('Remove {0}', [x.nombre])" @click="emit('borrar-foto', x)">{{ t('Remove') }}</button>
          </figure>
          <label v-if="props.editable && producto.fotos.length < 8" class="foto-add"><Icono nombre="mas" :tam="16" /> {{ t('Add photos') }}
            <input type="file" accept="image/jpeg,image/png,image/webp" class="oculto-visual" @change="emit('subir-foto', $event)" /></label>
        </div>
        <p class="hint" style="margin-top: 8px">{{ t('Front, side and sole or label: they help to confirm the materials. JPG, PNG or WebP up to 8 MB.') }}</p>
      </fieldset>
    </section>
  </div>
</template>

<style scoped>
.pasos { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 14px; }
.pasos button { border: 1px solid var(--linea); background: var(--superficie-2); border-radius: 999px; padding: 4px 11px; font-size: 0.8rem; cursor: pointer; color: var(--tinta); font-family: inherit; }
.pasos button:hover { border-color: var(--acento); }
.pasos button.ok { border-color: var(--ok-borde); color: var(--ok); background: var(--ok-fondo); }
.pasos button.pend { border-color: var(--aviso-borde); color: var(--aviso); background: var(--aviso-fondo); }
.pasos button b { font-weight: 650; }
.req-nota { margin-inline-start: auto; font-size: 0.78rem; color: var(--tinta-3); }
.req-ast { color: var(--error); font-weight: 700; margin-inline-start: 2px; }
.opcional { font-weight: 400; color: var(--tinta-3); }
.bloque { background: var(--superficie); border: 1px solid var(--linea); border-radius: var(--radio-panel); padding: 14px 18px 6px; margin-bottom: 14px; box-shadow: var(--sombra); scroll-margin-top: 130px; }
.bloque-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: -2px 0 12px; padding-bottom: 10px; border-bottom: 1px solid var(--linea-suave); }
.bloque-head h3 { font-size: 1.02rem; font-weight: 720; margin: 0; }
.bloque-head .sub { font-size: 0.8rem; color: var(--tinta-3); }
.vbadge { font-size: 0.74rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: var(--acento-claro); color: var(--acento-texto); }
.fila1 { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.fila3 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.hint .btn-texto { font-size: inherit; padding: 0; }
.fila2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 900px) { .fila3, .fila2 { grid-template-columns: minmax(0, 1fr); } }
.campo-f { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; min-width: 0; }
.campo-f label, .lbl-f { font-size: 0.84rem; font-weight: 620; color: var(--tinta); }
.rejilla-attrs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 20px; align-items: start; }
.rejilla-attrs .check-f { grid-column: 1 / -1; }
.rejilla-partes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
.rejilla-partes > * { margin-bottom: 0; }
@media (max-width: 1100px) { .rejilla-attrs, .rejilla-partes { grid-template-columns: minmax(0, 1fr); } }
.lbl-fila { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.lbl-fila .btn-texto { font-size: 0.8rem; flex: none; }
.hint { margin: 0; font-size: 0.8rem; color: var(--tinta-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hint.det { color: var(--acento-texto); }
.hint.auto { color: var(--ok); }
.hint.ya { white-space: normal; margin: 2px 0 10px; }
.fs { border: 0; border-top: 1px solid var(--linea-suave); margin: 4px 0 0; padding: 12px 0 6px; min-width: 0; scroll-margin-top: 130px; }
.fs:first-of-type { border-top: 0; padding-top: 0; }
legend { font-size: 0.84rem; font-weight: 650; color: var(--tinta-3); padding: 0 8px 0 0; text-transform: uppercase; letter-spacing: 0.04em; }
.opts { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.segs { display: flex; flex-wrap: wrap; gap: 6px; }
.segs button { padding: 6px 12px; font-size: 0.88rem; border: 1px solid var(--linea); border-radius: 7px; background: var(--superficie-2); color: var(--tinta); cursor: pointer; font-family: inherit; }
.segs button:hover:not(:disabled) { border-color: var(--acento); }
.segs button[aria-checked='true'] { background: var(--acento-claro); border-color: var(--acento); color: var(--acento-texto); font-weight: 620; }
.segs button:disabled { opacity: 0.42; border-style: dashed; background: transparent; cursor: not-allowed; }
.segs button[aria-checked='true']:disabled { opacity: 1; border-style: solid; }
.check-f { display: flex; gap: 8px; align-items: flex-start; font-size: 0.9rem; margin-bottom: 12px; cursor: pointer; }
.check-f input { margin-top: 3px; accent-color: var(--acento); }
.auto-tag { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ok); margin-inline-start: 6px; }
.desc-fila { display: flex; gap: 8px; align-items: flex-start; }
.desc-fila textarea { flex: 1; resize: vertical; min-height: 52px; font-size: 0.86rem; font-weight: 600; letter-spacing: 0.01em; }
.desc-fila textarea.comercial { font-weight: 500; letter-spacing: 0; }
.generico-fijo { font-stretch: 112%; font-weight: 700; font-size: 1.02rem; padding: 7px 12px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; background: var(--superficie-2); border: 1px solid var(--linea); border-radius: var(--radio); min-height: 38px; }
.generico-fijo small { font-stretch: 100%; font-weight: 450; font-size: 0.8rem; color: var(--tinta-3); }
.descripciones textarea { field-sizing: content; min-height: 64px; resize: vertical; }
.descripciones { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 900px) { .generico-fijo { font-stretch: 112%; font-weight: 700; font-size: 1.02rem; padding: 6px 0; display: flex; gap: 8px; align-items: baseline; }
.generico-fijo small { font-stretch: 100%; font-weight: 450; font-size: 0.8rem; color: var(--tinta-3); }
.descripciones { grid-template-columns: minmax(0, 1fr); } }
.desc-fila textarea[readonly] { background: var(--superficie); border-style: dashed; }
.ensenar { border: 1px solid var(--acento); border-radius: 8px; padding: 10px 12px; margin: 0 0 12px; background: var(--acento-claro); font-size: 0.86rem; }
.fotos { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }
.foto { position: relative; margin: 0; width: 96px; height: 96px; border-radius: 8px; overflow: hidden; border: 1px solid var(--linea); background: var(--superficie-2); }
.foto img { width: 100%; height: 100%; object-fit: cover; display: block; }
.foto button { position: absolute; inset-inline-end: 4px; top: 4px; border: 0; border-radius: 6px; background: var(--superficie); color: var(--tinta); font-size: 0.74rem; padding: 2px 7px; cursor: pointer; opacity: 0.92; }
.foto-add { width: 96px; height: 96px; border: 1.5px dashed var(--borde-hover); border-radius: 8px; display: flex; flex-direction: column; gap: 4px; align-items: center; justify-content: center; text-align: center; font-size: 0.8rem; color: var(--tinta-3); cursor: pointer; padding: 6px; }
.foto-add:hover { border-color: var(--acento); color: var(--acento-texto); }
</style>
