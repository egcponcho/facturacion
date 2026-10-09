<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, ref, watch } from 'vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { api } from '@/nucleo/api'
import { norm } from '@/modulos/clasificacion/formato.js'
import { avisar, errorApi } from '@/stores/ui'
import { sesion } from '@/stores/sesion'
import Icono from '@/componentes/Icono.vue'
import CampoCategoria from './CampoCategoria.vue'
import CampoFicha from './CampoFicha.vue'
import ComposicionParte from './ComposicionParte.vue'

// Formulario de la ficha técnica para cualquier categoría (también las creadas
// en la configuración): los datos que aplican, en qué orden, cuáles son
// obligatorios, cuáles deciden el código, qué opciones no caben y qué se llenó
// solo los dice el motor del servidor (r = respuesta de /clasificacion/sesion).
// Aquí solo se muestra y se edita; cada cambio vuelve al motor.
const props = defineProps({
  f: { type: Object, required: true }, // {tipo, ficha, nombre, origen, ...} editable
  r: { type: Object, default: null },
  ctx: { type: Object, required: true },
  producto: { type: Object, required: true },
  paises: { type: Array, default: () => [] },
  filas: { type: Object, required: true }, // {comp.parte: [{m, pct}]} filas de composición que se editan
  tocados: { type: Object, required: true }, // Set de lo que eligió la persona
  editable: Boolean,
})
const emit = defineEmits(['cambio', 'subir-foto', 'borrar-foto', 'contexto', 'acuerdos'])
const f = props.f

// Lo que ya dice el registro del producto (nombre, destinos) no se pregunta
const campos = computed(() => (props.r?.campos || []).filter((c) => !c.del_registro))
const MOTIVO = { composicion: t('composition'), categoria: t('product type') }
const vacio = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)
const valor = (c) => (c.codigo.startsWith('comp.') ? f.ficha.comp?.[c.codigo.slice(5)] : f.ficha[c.codigo])
const elegir = (c, v) => emit('cambio', { campo: c.codigo, valor: v })

// ---- Qué se muestra y dónde ---------------------------------------------------------
const camposProducto = computed(() => campos.value.filter((c) => c.seccion === 'producto' && c.tipo_dato !== 'composition'))
const preguntar = computed(() => campos.value.filter((c) => ['caracteristicas'].includes(c.seccion) && c.estado === 'preguntar'
  && c.tipo_dato !== 'composition' && c.principal))
const nacionales = computed(() => campos.value.filter((c) => c.seccion === 'nacional' && c.estado === 'preguntar'))
const definidos = computed(() => campos.value.filter((c) => c.estado === 'definido' && !vacio(c.valor) && c.seccion !== 'producto'))
const mas = computed(() => campos.value.filter((c) => c.seccion === 'caracteristicas' && c.estado === 'preguntar' && !c.principal))
const partes = computed(() => campos.value.filter((c) => c.tipo_dato === 'composition' && c.codigo.startsWith('comp.')))
const verMas = ref(false)
const textoValor = (c) => (c.tipo_dato === 'boolean' ? (c.valor ? t('Yes') : t('No')) : c.opciones.find((o) => o.codigo === c.valor)?.etiqueta || String(c.valor))

// ---- Lo que se dedujo del nombre, el uso o la composición ------------------------------
const etiquetaCat = (k) => (props.ctx.categorias || []).find((c) => c.codigo === k)?.nombre_corto || (props.ctx.categorias || []).find((c) => c.codigo === k)?.nombre || k
const detTexto = computed(() => {
  if (!props.r) return ''
  const out = []
  if (props.r.detectado?.categoria && !props.tocados.has('tipo') && props.r.detectado.categoria === f.tipo) out.push(etiquetaCat(f.tipo))
  for (const c of campos.value) if (c.auto && !vacio(c.valor) && c.seccion !== 'derivado') out.push(textoValor(c).toLowerCase())
  if (!out.length) return ''
  const palabra = props.r.detectado?._palabra
  return t('Detected: {0}{1}. You can change it below.', [out.join(', '), palabra ? t(' (keyword “{0}”)', [palabra]) : ''])
})

function elegirTipo(k) {
  emit('cambio', { campo: 'tipo', valor: k })
}

// ---- Enseñar una palabra clave cuando la categoría no se reconoció ----------------------
const NO_FRASE = new Set('the m w u ua mn wm mens men womens women kids kid youth unisex black white grey gray blue red green brown size pack pk and with de del para'.split(' '))
const frase = ref('')
const soloMarca = ref(true)
const ensenarCerrado = ref(false)
const tipoDetectado = computed(() => props.r?.detectado?.categoria || '')
const fraseSugerida = computed(() => String(f.nombre || '').split(/[\s/,;()-]+/).filter((w) => w && !/\d/.test(w) && w.length >= 2 && !NO_FRASE.has(norm(w))).slice(0, 2).join(' '))
const mostrarEnsenar = computed(() => props.editable && !ensenarCerrado.value && f.tipo && props.tocados.has('tipo') && tipoDetectado.value !== f.tipo && !!fraseSugerida.value)
watch(fraseSugerida, (v) => (frase.value = v), { immediate: true })
async function ensenarPalabra() {
  if (frase.value.trim().length < 2) return avisar(t('Write the word or phrase.'), 'error')
  // Lo elegido de la ficha que la palabra también implica (las preguntas de la categoría ya respondidas)
  const atributos = Object.fromEntries(preguntar.value.filter((c) => c.tipo_dato === 'select' && !vacio(c.valor) && !c.auto && props.tocados.has(c.codigo)).slice(0, 2).map((c) => [c.codigo, c.valor]))
  try {
    await api.post('/clasificacion/palabras', { frase: frase.value.trim(), tipo: f.tipo, marca: soloMarca.value ? props.producto.marca_nombre || null : null, atributos })
    ensenarCerrado.value = true
    emit('contexto')
    avisar(t('Learned: “{0}” will be recognized as {1}.', [frase.value.trim(), etiquetaCat(f.tipo)]))
  } catch (e) {
    errorApi(e)
  }
}

async function ensenarMaterial(palabra, equivale) {
  try {
    await api.post('/clasificacion/sinonimos', { palabra, equivale })
    emit('contexto')
    avisar(t('Learned: “{0}”. It will be recognized in every sheet.', [palabra]))
  } catch (e) {
    errorApi(e)
  }
}

// ---- Acuerdos comerciales según el país de origen (detalle en su pestaña) ----------------
const nAcuerdos = computed(() => (props.ctx.destinos || []).filter((d) => f.origen === d.iso
  || (props.ctx.acuerdos || []).some((a) => a.origenes.includes(f.origen) && a.destinos.includes(d.iso))).length)

// ---- Avance ------------------------------------------------------------------------------
const pasos = computed(() => {
  const falt = props.r?.faltantes || []
  const enProd = new Set(['origen', ...camposProducto.value.map((c) => c.codigo)])
  const faltanProd = (f.tipo ? 0 : 1) + falt.filter((x) => enProd.has(x.campo)).length
  const pend = [...preguntar.value, ...nacionales.value].filter((c) => !c.respondida && (c.modo === 'REQUIRE' || c.discrimina)).length
  const comp = partes.value.filter((c) => c.modo === 'REQUIRE')
  const malComp = comp.filter((c) => Math.abs((c.composicion?.total || 0) - 100) >= 0.05)
  const nFotos = props.producto.fotos.length
  return [
    ['blk-producto', t('Product'), faltanProd ? 'pend' : 'ok', faltanProd ? t('{0} to fill', [faltanProd]) : ''],
    ['blk-carac', t('Features'), !f.tipo ? '' : pend ? 'pend' : 'ok', pend ? t('{0} to answer', [pend]) : ''],
    ['blk-comp', t('Composition'), !partes.value.length ? '' : malComp.length ? 'pend' : 'ok',
      malComp.length ? malComp.map((c) => (c.composicion?.total ? `${c.etiqueta} ${c.composicion.total}%` : t('{0} missing', [c.etiqueta]))).join(' · ') : ''],
    ['blk-fotos', t('Photos'), nFotos ? 'ok' : '', nFotos ? String(nFotos) : t('optional')],
  ]
})
function irA(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// Descripciones: las arma el motor; se pueden escribir a mano
function editarCom() {
  if (!f.ficha.comManual) emit('cambio', { campo: 'descCom', valor: props.r?.descripciones?.comercial || props.producto.descripcion_comercial || '', extra: { comManual: true } })
  else emit('cambio', { campo: 'comManual', valor: false })
}
function editarDesc() {
  if (!f.ficha.descManual) emit('cambio', { campo: 'desc', valor: props.r?.descripciones?.aduana || '', extra: { descManual: true } })
  else emit('cambio', { campo: 'descManual', valor: false })
}
</script>

<template>
  <div class="ficha-form">
    <nav class="pasos" :aria-label="t('Sheet progress')">
      <button v-for="([id, l, e, x], i) in pasos" :key="id" type="button" :class="e" @click="irA(id)">
        <b>{{ tx(i + 1) }}</b> {{ tx(l) }}{{ tx(e === 'ok' ? ' ✓' : '') }}{{ tx(x ? ` · ${x}` : '') }}
      </button>
      <span class="req-nota leyenda-req">{{ t('Required for a complete sheet') }}</span>
    </nav>

    <!-- Producto -->
    <section id="blk-producto" class="bloque">
      <div class="bloque-head"><h3>{{ t('Product') }}</h3><span class="sub">{{ t('What it is and who it is for. Shared by every size and prepack.') }}</span></div>
      <div class="fila2">
        <div class="campo-f">
          <label for="f_categoria" class="req">{{ t('Category') }}</label>
          <CampoCategoria id="f_categoria" :model-value="f.tipo" :categorias="props.ctx.categorias || []" :disabled="!props.editable" @update:model-value="elegirTipo" />
          <p v-if="detTexto" class="hint det" :title="tx(detTexto)">{{ tx(detTexto) }}</p>
          <p v-else-if="r?.categoria?.capitulos?.length" class="hint">{{ t('Chapter {0} · only what changes its code is asked', [r.categoria.capitulos.join(' / ')]) }}</p>
        </div>
        <div class="campo-f">
          <span class="lbl-f">{{ t('Generic') }}</span>
          <span class="generico-fijo" :title="t('Generic (style-color): all its sizes share this sheet')">{{ tx(producto.codigo_generico || '—') }}<small>{{ tx(producto.skus) }} {{ tx(producto.skus === 1 ? 'size' : 'sizes') }}<template v-if="producto.rango_tallas"> ({{ tx(producto.rango_tallas) }})</template><template v-if="producto.n_prepacks"> · {{ tx(producto.n_prepacks) }} {{ tx(producto.n_prepacks === 1 ? 'prepack' : 'prepacks') }}</template></small></span>
        </div>
      </div>
      <div v-if="camposProducto.length" class="fila3">
        <CampoFicha v-for="c in camposProducto" :key="c.codigo" :campo="c" :valor="valor(c)" :editable="props.editable" @elegir="(v) => elegir(c, v)" />
      </div>
      <div class="fila2">
        <div class="campo-f">
          <label for="f_origen" class="req">{{ t('Country of origin') }}</label>
          <Seleccion id="f_origen" :value="f.origen" class="entrada" :disabled="!props.editable" @change="emit('cambio', { campo: 'origen', valor: $event })">
            <option value="">{{ t('Choose…') }}</option>
            <option v-for="x in props.paises" :key="x.codigo" :value="x.codigo">{{ tx(x.nombre) }}</option>
          </Seleccion>
          <p class="hint"><button v-if="f.origen" type="button" class="btn-texto" @click="emit('acuerdos')">{{ t('Trade agreements: {0} of {1} destinations', [nAcuerdos, (props.ctx.destinos || []).length]) }}</button><template v-else>{{ t('Decides the trade agreements by destination') }}</template></p>
        </div>
        <div class="campo-f">
          <label for="f_uso">{{ t('What it is for') }} <span class="opcional">{{ t('(optional)') }}</span></label>
          <input id="f_uso" :value="f.ficha.uso || ''" class="entrada" type="text" maxlength="200" :disabled="!props.editable"
                 :placeholder="t('E.g. bag worn on the waist to carry climbing chalk')" @input="emit('cambio', { campo: 'uso', valor: $event.target.value })" />
        </div>
      </div>
      <div class="descripciones">
        <div class="campo-f">
          <div class="lbl-fila"><label for="f_desc">{{ t('Customs description') }} <span class="opcional">{{ tx(f.ficha.descManual ? t('(edited by hand)') : t('(built from the sheet · Spanish, as declared at customs)')) }}</span></label><button v-if="props.editable" type="button" class="btn-texto" @click="editarDesc">{{ tx(f.ficha.descManual ? t('Use automatic') : t('Edit')) }}</button></div>
          <div class="desc-fila">
            <textarea id="f_desc" :value="f.ficha.descManual ? f.ficha.desc : (props.editable ? r?.descripciones?.aduana : producto.descripcion_aduana) || ''" class="entrada" rows="2" maxlength="400"
                      :readonly="!f.ficha.descManual || !props.editable" :placeholder="t('Appears when you choose the category and the composition')" @input="emit('cambio', { campo: 'desc', valor: $event.target.value })"></textarea>
          </div>
        </div>
        <div class="campo-f">
          <div class="lbl-fila"><label for="f_desc_com">{{ t('Commercial description') }} <span class="opcional">{{ tx(f.ficha.comManual ? t('(edited by hand)') : t('(type and brand, as on invoices and packing lists)')) }}</span></label><button v-if="props.editable" type="button" class="btn-texto" @click="editarCom">{{ tx(f.ficha.comManual ? t('Use automatic') : t('Edit')) }}</button></div>
          <div class="desc-fila">
            <textarea id="f_desc_com" :value="f.ficha.comManual ? f.ficha.descCom : (props.editable ? r?.descripciones?.comercial : producto.descripcion_comercial) || ''" class="entrada comercial" rows="2" maxlength="300"
                      :readonly="!f.ficha.comManual || !props.editable" :placeholder="t('Appears when you choose the category')" @input="emit('cambio', { campo: 'descCom', valor: $event.target.value })"></textarea>
          </div>
        </div>
      </div>
      <div v-if="mostrarEnsenar" class="ensenar">
        <b>{{ t('Teach the system.') }}</b>
        {{ t('{0} and you chose “{1}”. Save a keyword so it is recognized next time.', [tipoDetectado ? t('From the name it looked like “{0}”', [etiquetaCat(tipoDetectado)]) : t('The category was not recognized from the name'), etiquetaCat(f.tipo)]) }}
        <div class="fila-flex mt-chico">
          <input v-model="frase" class="entrada" type="text" :aria-label="t('Keyword')" style="max-width: 240px" />
          <label v-if="producto.marca_nombre" class="check"><input v-model="soloMarca" type="checkbox" /><span>{{ t('Only for {0}', [producto.marca_nombre]) }}</span></label>
          <button type="button" class="btn btn-chico" @click="ensenarPalabra">{{ t('Save keyword') }}</button>
          <button type="button" class="btn btn-chico btn-fantasma" @click="ensenarCerrado = true">{{ t('Not now') }}</button>
        </div>
      </div>
    </section>

    <!-- Ficha técnica: características y composición -->
    <section class="bloque">
      <div class="bloque-head">
        <h3>{{ t('Technical sheet') }}</h3><span class="vbadge">{{ t('Version {0}', [producto.version_ficha]) }}</span>
        <span class="sub">{{ tx(r?.categoria?.nombre || t('Choose the category first')) }}</span>
      </div>

      <fieldset v-if="f.tipo" id="blk-carac" class="fs" :disabled="!props.editable">
        <legend>{{ t('Features') }}</legend>
        <p v-if="!preguntar.length" class="hint">{{ t('This category needs no more data to be classified.') }}</p>
        <div class="rejilla-attrs">
          <CampoFicha v-for="c in preguntar" :key="c.codigo" :campo="c" :valor="valor(c)" :editable="props.editable" @elegir="(v) => elegir(c, v)" />
        </div>
        <p v-if="definidos.length" class="hint ya">
          {{ t('Already defined:') }}
          <template v-for="(c, i) in definidos" :key="c.codigo">{{ tx(i ? ' · ' : '') }}{{ tx(c.etiqueta) }}: <b>{{ tx(textoValor(c).toLowerCase()) }}</b> <span v-if="c.motivo_derivado" class="apagado"> {{ t('(by {0})', [MOTIVO[c.motivo_derivado] || c.motivo_derivado]) }}</span></template>
        </p>
        <template v-if="mas.length">
          <button type="button" class="btn-texto" :aria-expanded="verMas" @click="verMas = !verMas">{{ tx(verMas ? t('Hide more details') : t('More details (optional, {0})', [mas.length])) }}</button>
          <div v-if="verMas" class="rejilla-attrs mt-chico">
            <CampoFicha v-for="c in mas" :key="c.codigo" :campo="c" :valor="valor(c)" :editable="props.editable" @elegir="(v) => elegir(c, v)" />
          </div>
        </template>
      </fieldset>

      <fieldset v-if="partes.length" id="blk-comp" class="fs">
        <legend>{{ t('Composition') }}</legend>
        <p class="hint mb-2">{{ t('Materials of the product and their percentage.') }}</p>
        <div class="rejilla-partes">
          <ComposicionParte v-for="c in partes" :key="`${f.tipo}-${c.codigo}`" :campo="c" :filas="props.filas[c.codigo] || []" :editable="props.editable"
                            @cambio="(k, txt, reiniciar) => emit('cambio', { campo: k, valor: txt, reiniciar })" @ensenar="ensenarMaterial" />
        </div>
      </fieldset>

      <fieldset v-if="nacionales.length && props.editable" class="fs">
        <legend>{{ t('For national codes') }}</legend>
        <p class="hint mb-2">{{ t('Some destination countries split this subheading further.') }}</p>
        <div class="rejilla-attrs">
          <CampoFicha v-for="c in nacionales" :key="c.codigo" :campo="c" :valor="valor(c)" :editable="props.editable" @elegir="(v) => elegir(c, v)" />
        </div>
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
        <p class="hint" style="margin-top: 8px">{{ t('Front, side and sole or label: they help to confirm the materials. JPG, PNG or WebP up to {0} MB.', [sesion.usuario?.max_subida_mb]) }}</p>
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
