<script setup>
import { opcionesLista } from '@/nucleo/listas.js'
import { t, tx, IDIOMAS } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Interruptor from '@/componentes/Interruptor.vue'
import SelectBusqueda from '@/componentes/SelectBusqueda.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { cargarSesion } from '@/stores/sesion'
import { avisar, errorApi, guardando } from '@/stores/ui'
import { reducirImagen } from '@/nucleo/utils'
import { estadoFabrica } from '@/nucleo/estados.js'
import BotonArchivo from '@/componentes/BotonArchivo.vue'
import { aplicarPaleta } from '@/nucleo/marca.js'

// Empresa de la instalación: datos generales, logo, preferencias y reglas de
// negocio. Solo la administración los cambia.
const o = ref(null)
const datos = ref(null)
const ocupado = ref(false)
// Zonas horarias: la lista ISO del navegador; países: el catálogo de países
// Monedas de la lista de la empresa (Datos maestros → Listas de valores → Currencies)
const MONEDAS = computed(() => opcionesLista('moneda').map(([valor, texto]) => ({ valor, texto: `${valor} · ${texto}` })))
const ZONAS = Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : ['UTC']
const paises = ref([])
const FORMATOS = ['MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD']
// Textos de las reglas (el servidor manda la clave; aquí, cómo se lee)
const REGLAS = {
  PROVEEDOR_PUEDE_FINALIZAR: t('Suppliers can finalize their invoices and packing lists'),
  POSICION_EN_VARIAS_FACTURAS: t('A PO line can be split across several active invoices'),
  FACTURA_EN_UNA_SOLA_UNIDAD: t('All packing lists of an invoice must travel in the same load unit'),
  REQUERIR_DATOS_ADUANA: t('Country of origin and HS code are required per line to finalize'),
  DIAS_ALERTA_BORRADOR: t('Days before warning about drafts that still reserve quantities'),
  DIAS_MARGEN_RIESGO: t('Minimum margin (days) before the required date to be on time'),
  DIAS_AVISO_TIENDA: t('Days before the in-store date at which a PO is highlighted'),
  DIAS_TOLERANCIA_ARRIBO: t('Days after the committed ETA that still count as an on-time arrival'),
  DIAS_TOLERANCIA_XF: t('Days after the original XF that still count as an on-time pickup'),
  META_LIBERACION_A_TIEMPO: t('Target (%) of logistics releases on time'),
  ETIQUETAS_CUATRO_OJOS: t('A label design version must be approved by someone other than its author'),
  PAIS_BASE_CLASIF: t('Country whose national code completes the suggested HS code'),
  COMPATIBILIDAD_BLOQUEANTE: t('PO data that cannot be mixed in one invoice'),
  COMPATIBILIDAD_ADVERTENCIA: t('PO data that only warns when mixed in one invoice'),
  APROBACION_CUATRO_OJOS: t('Whoever creates or sends a PO cannot approve it'),
  APROBAR_OC_IMPORTADAS: t('POs loaded from the ERP also go through the approval rules'),
}

// Aprobación de OCs: desde qué monto (en su moneda y, si se quiere, solo para
// una sociedad) aprueba qué rol. Las reglas que aplican se encadenan de menor a
// mayor monto; sin reglas, la OC queda aprobada al enviarla.
const roles = ref([])
const sociedades = ref([])
const nuevaRegla = () => datos.value.aprobaciones_oc.push({ nombre: '', monto_minimo: 0, moneda: datos.value.preferencias.moneda || '', sociedad: '', rol_id: '' })

// Campos propios: datos que la empresa agrega a cada entidad
const entidadCampos = ref('articulos')
const nuevoCampo = () => datos.value.campos_propios[entidadCampos.value].push({ clave: '', etiqueta: '', tipo: 'texto', opciones: '', obligatorio: false, indexado: false })

// Estados: los códigos son fijos; la empresa elige cómo se leen, su color y su
// orden en filtros y listas
const documentoEstados = ref('oc')
const TONOS = { neutro: t('Gray'), info: t('Blue'), ok: t('Green'), aviso: t('Amber'), error: t('Red') }
const moverEstado = (i, d) => {
  const lista = datos.value.estados[documentoEstados.value]
  if (i + d < 0 || i + d >= lista.length) return
  lista.splice(i + d, 0, lista.splice(i, 1)[0])
}
const estadosDe = (x) => Object.fromEntries((x.documentos_estados || []).map((d) => [d.clave, d.codigos
  .map((c, i) => { const p = x.estados?.[d.clave]?.[c] || {}; return { codigo: c, etiqueta: p.etiqueta || '', tono: p.tono || '', orden: p.orden ?? i + 1 } })
  .sort((a, b) => a.orden - b.orden)]))

// Terminología propia: una fila por texto del sistema (en inglés, como clave)
// con su reemplazo en cada idioma
const terminos = ref([])
function aFilas(textos) {
  const originales = [...new Set([...Object.keys(textos?.es || {}), ...Object.keys(textos?.en || {})])]
  return originales.map((o) => ({ original: o, es: textos?.es?.[o] || '', en: textos?.en?.[o] || '' }))
}
function aTextos(filas) {
  const res = { es: {}, en: {} }
  for (const f of filas) {
    const o = f.original.trim()
    if (!o) continue
    if (f.es.trim()) res.es[o] = f.es.trim()
    if (f.en.trim()) res.en[o] = f.en.trim()
  }
  return res
}

function copiar(x) {
  datos.value = {
    nombre: x.nombre, razon_social: x.razon_social || '', id_fiscal: x.id_fiscal || '', pais: x.pais || '', logo: x.logo,
    preferencias: { ...x.preferencias }, marca: { ...x.marca }, documentos: { ...x.documentos },
    modulos: Object.fromEntries(x.modulos.map((m) => [m.clave, m.activo])),
    campos_propios: Object.fromEntries(Object.entries(x.campos_propios).map(([e, cs]) => [e, cs.map((c) => ({ ...c, opciones: (c.opciones || []).join(', ') }))])),
    reglas: Object.fromEntries(x.reglas.map((r) => [r.clave, Array.isArray(r.valor) ? [...r.valor] : r.valor])),
    aprobaciones_oc: (x.aprobaciones_oc || []).map((r) => ({ ...r, sociedad: r.sociedad || '' })),
    obligatorios: { orden: [...(x.obligatorios?.orden || [])] },
    estados: estadosDe(x),
  }
  terminos.value = aFilas(x.textos)
}

async function cargar() {
  try {
    o.value = await api.get('/organizacion')
    copiar(o.value)
  } catch (e) {
    errorApi(e)
  }
}
onMounted(() => {
  cargar()
  api.get('/catalogos/paises/opciones').then((r) => { paises.value = r.map((p) => ({ valor: p.codigo, texto: p.texto, sub: p.codigo })) }).catch(() => {})
  api.get('/roles').then((r) => { roles.value = r.roles.filter((x) => x.activo).map((x) => ({ valor: x.id, texto: x.nombre })) }).catch(errorApi)
  api.get('/catalogos/sociedades/opciones').then((r) => { sociedades.value = r.map((x) => ({ valor: x.codigo, texto: x.texto })) }).catch(() => {})
})

async function subirLogo(archivo) {
  try {
    datos.value.logo = await reducirImagen(archivo, 320)
  } catch (e) {
    errorApi(e)
  }
}

// Paletas de la interfaz: el acento y la barra lateral (los colores de muestra son los de styles.css)
const PALETAS_UI = computed(() => [
  { codigo: '', nombre: t('Indigo'), texto: t('Light side bar, indigo accent (standard).'), lateral: '#ffffff', acento: '#4f46e5', borde: true },
  { codigo: 'esmeralda', nombre: t('Emerald'), texto: t('Graphite side bar, emerald accent.'), lateral: '#18181b', acento: '#047857' },
  { codigo: 'terracota', nombre: t('Terracotta'), texto: t('Warm light side bar, terracotta accent.'), lateral: '#fbf8f5', acento: '#c2410c', borde: true },
  { codigo: 'marino', nombre: t('Navy'), texto: t('Navy side bar, blue accent (the previous one).'), lateral: '#0f172a', acento: '#0369a1' },
])
// Elegir una paleta la muestra al momento; se guarda con el resto de la empresa
function elegirPaleta(codigo) {
  datos.value.marca.paleta = codigo
  aplicarPaleta(codigo)
}

async function guardar() {
  ocupado.value = true
  try {
    const campos = Object.fromEntries(Object.entries(datos.value.campos_propios).map(([e, cs]) => [e, cs.map((c) => ({
      ...c, opciones: c.tipo === 'opcion' ? c.opciones.split(',').map((x) => x.trim()).filter(Boolean) : [] }))]))
    const estados = Object.fromEntries(Object.entries(datos.value.estados).map(([d, es]) => [d, es.map(({ codigo, etiqueta, tono }) => ({ codigo, etiqueta, tono }))]))
    o.value = await guardando(api.put('/organizacion', { ...datos.value, textos: aTextos(terminos.value), campos_propios: campos, estados }))
    copiar(o.value)
    await cargarSesion(true) // nombre, logo y color en el menú; reglas en toda la app
    avisar(t('Company settings saved.'))
  } catch (e) {
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <header class="pagina-cabeza">
    <div>
      <p class="eyebrow">{{ t('Settings') }}</p>
      <h1>{{ t('Company') }}</h1>
      <p>{{ t('Name, logo, preferences and business rules of your company.') }}</p>
    </div>
    <div class="fila-flex">
      <button class="btn btn-primario" :disabled="ocupado || !datos" @click="guardar"><Icono nombre="check" />{{ t('Save changes') }}</button>
    </div>
  </header>

  <template v-if="datos">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('General information') }}</h2><p>{{ t('It appears in the menu and in the documents you issue.') }}</p></div></div>
      <div class="empresa-general">
        <div class="empresa-logo">
          <img v-if="datos.logo" :src="datos.logo" :alt="t('Company logo')" />
          <span v-else class="empresa-logo-vacio"><Icono nombre="caja" :tam="28" /></span>
          <BotonArchivo acepta="image/png,image/jpeg,image/webp" @elegir="subirLogo"><Icono nombre="importar" :tam="14" />{{ t('Upload logo') }}</BotonArchivo>
          <button v-if="datos.logo" type="button" class="btn btn-chico btn-fantasma" @click="datos.logo = null">{{ t('Remove') }}</button>
        </div>
        <div class="rejilla-campos">
          <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="datos.nombre" class="entrada" maxlength="200" required /></label>
          <label class="campo"><span>{{ t('Legal name') }}</span><input v-model="datos.razon_social" class="entrada" maxlength="200" /></label>
          <label class="campo"><span>{{ t('Tax ID') }}</span><input v-model="datos.id_fiscal" class="entrada" maxlength="40" /></label>
          <div class="campo"><span>{{ t('Country') }}</span><SelectBusqueda v-model="datos.pais" :opciones="paises" :vacio="t('None')" :prefijo="false" /></div>
          <div class="campo"><span>{{ t('Company code') }}</span><div class="valor-fijo">{{ tx(o.codigo) }}</div></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Preferences') }}</h2><p>{{ t('Defaults for new users and documents. Each person can still choose their own language and formats.') }}</p></div></div>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Default language') }}</span>
          <Seleccion v-model="datos.preferencias.idioma" class="entrada"><option v-for="x in IDIOMAS" :key="x.codigo" :value="x.codigo">{{ x.nombre }}</option></Seleccion></label>
        <div class="campo"><span>{{ t('Base currency') }}</span><SelectBusqueda v-model="datos.preferencias.moneda" :opciones="MONEDAS" :prefijo="false" /></div>
        <label class="campo"><span>{{ t('Date format') }}</span>
          <Seleccion v-model="datos.preferencias.formato_fecha" class="entrada"><option v-for="f in FORMATOS" :key="f" :value="f">{{ f }}</option></Seleccion></label>
        <div class="campo"><span>{{ t('Time zone') }}</span><SelectBusqueda v-model="datos.preferencias.zona_horaria" :opciones="ZONAS" :prefijo="false" /></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Brand') }}</h2><p>{{ t('Color of the screens and documents, name of the system and texts of the sign-in screen. Leave a text empty to use the standard one.') }}</p></div></div>
      <div class="rejilla-campos">
        <div class="campo ancho"><span>{{ t('Palette') }}</span>
          <div class="paletas" role="radiogroup" :aria-label="t('Palette')">
            <button v-for="x in PALETAS_UI" :key="x.codigo" type="button" class="paleta" role="radio"
                    :aria-checked="(datos.marca.paleta || '') === x.codigo" @click="elegirPaleta(x.codigo)">
              <span class="paleta-muestra" aria-hidden="true">
                <span class="paleta-lateral" :class="{ borde: x.borde }" :style="{ background: x.lateral }"><i :style="{ background: x.acento }" /><i /><i /></span>
                <span class="paleta-cuerpo"><i :style="{ background: x.acento }" /><i /><i /></span>
              </span>
              <b>{{ x.nombre }}</b><small>{{ x.texto }}</small>
            </button>
          </div>
          <small class="ayuda">{{ t('The colors of every screen, in the light and the dark theme. Each person still chooses light or dark.') }}</small></div>
        <label class="campo"><span>{{ t('Accent color (optional)') }}</span>
          <span class="fila-flex"><input type="color" :value="datos.marca.color || '#3355e0'" :aria-label="t('Color')" @input="datos.marca.color = $event.target.value" />
            <input v-model="datos.marca.color" class="entrada" maxlength="7" placeholder="#3355E0" />
            <button v-if="datos.marca.color" type="button" class="btn btn-chico btn-fantasma" @click="datos.marca.color = ''">{{ t('Standard') }}</button></span></label>
        <label class="campo"><span>{{ t('Name of the system') }}</span><input v-model="datos.marca.titulo" class="entrada" maxlength="60" :placeholder="t('Workspace')" /></label>
        <label class="campo ancho"><span>{{ t('Sign-in title') }}</span><input v-model="datos.marca.ingreso_titulo" class="entrada" maxlength="120" :placeholder="t('From purchase order to container, with no loose spreadsheets.')" /></label>
        <label class="campo ancho"><span>{{ t('Sign-in text') }}</span><textarea v-model="datos.marca.ingreso_texto" class="entrada" rows="2" maxlength="300" :placeholder="t('Invoice from your POs, pack with templates and follow every shipment to the warehouse.')" /></label>
        <label class="campo ancho"><span>{{ t('Sign-in help') }}</span><input v-model="datos.marca.ingreso_ayuda" class="entrada" maxlength="160" :placeholder="t('Use your supplier or import team email.')" /></label>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Documents') }}</h2><p>{{ t('Paper size and legal statements of the invoice and packing list PDFs. Leave a statement empty to use the standard one, in the language of each document.') }}</p></div></div>
      <div class="rejilla-campos">
        <label class="campo"><span>{{ t('Paper size') }}</span>
          <Seleccion v-model="datos.documentos.papel" class="entrada"><option value="LETTER">{{ t('Letter') }}</option><option value="A4">A4</option></Seleccion></label>
        <div class="campo"><span>{{ t('Company logo on reports') }}</span><Interruptor v-model="datos.documentos.logo_en_reportes" :etiqueta="t('Company logo on reports')" /></div>
        <label class="campo ancho"><span>{{ t('Item data on invoice and packing list lines') }}</span>
          <input v-model="datos.documentos.columnas_linea" class="entrada" maxlength="300" placeholder="atributo.MODELO,variante" />
          <small class="ayuda">{{ t('Comma-separated, in order: variante (all the variant values), codigo_barras (barcode), or one attribute alone as atributo.CODE (of the product or the variant, e.g. atributo.MODELO or atributo.TALLA).') }}</small></label>
        <label class="campo ancho"><span>{{ t('Invoice statement') }}</span><textarea v-model="datos.documentos.declaracion_factura" class="entrada" rows="3" maxlength="1000"
          :placeholder="t('We declare under oath that the information in this invoice is true and correct, that the value is the price actually paid or payable for the goods and that the declared origin is correct.')" /></label>
        <label class="campo ancho"><span>{{ t('Packing list statement') }}</span><textarea v-model="datos.documentos.declaracion_packing" class="entrada" rows="3" maxlength="1000"
          :placeholder="t('We declare that the contents, numbering, dimensions and weights of the packages correspond to the goods shipped. Every unit or pair carries its individual label; inner packs carry an inner pack label with the product and the quantity inside.')" /></label>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Modules') }}</h2><p>{{ t('Turn off what your company does not use: its screens and permissions disappear for everyone. Turning it on again restores them; no data is lost.') }}</p></div></div>
      <ul class="lista-reglas">
        <li v-for="m in o.modulos" :key="m.clave"><span>{{ tx(m.texto) }}</span><Interruptor v-model="datos.modulos[m.clave]" :etiqueta="tx(m.texto)" /></li>
      </ul>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Own fields') }}</h2><p>{{ t('Data your company adds to its records: they appear in the forms, the tables and, for invoices, in the documents. Purchase orders read them from the upload file by their name.') }}</p></div>
        <button type="button" class="btn btn-chico" @click="nuevoCampo"><Icono nombre="mas" :tam="14" />{{ t('Add field') }}</button></div>
      <div class="pestanas-pildora" role="tablist">
        <button v-for="e in o.entidades_campos" :key="e.clave" type="button" role="tab" class="pildora" :aria-selected="entidadCampos === e.clave" @click="entidadCampos = e.clave">
          {{ tx(e.texto) }}<span v-if="datos.campos_propios[e.clave]?.length" class="cuenta">{{ datos.campos_propios[e.clave].length }}</span></button>
      </div>
      <p v-if="!datos.campos_propios[entidadCampos]?.length" class="ayuda">{{ t('No own fields for this entity.') }}</p>
      <div v-else class="tabla-marco tabla-captura">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Name') }}</th><th>{{ t('Type') }}</th><th>{{ t('Options (comma-separated)') }}</th><th>{{ t('Required') }}</th><th :title="t('Speeds up filters and reports on this field')">{{ t('Indexed') }}</th><th /></tr></thead>
          <tbody>
            <tr v-for="(c, i) in datos.campos_propios[entidadCampos]" :key="i">
              <td><input v-model="c.etiqueta" class="entrada" maxlength="60" :aria-label="t('Name')" /></td>
              <td><Seleccion v-model="c.tipo" class="entrada" :aria-label="t('Type')"><option v-for="x in o.tipos_campos" :key="x.clave" :value="x.clave">{{ tx(x.texto) }}</option></Seleccion></td>
              <td><input v-if="c.tipo === 'opcion'" v-model="c.opciones" class="entrada" :aria-label="t('Options (comma-separated)')" /></td>
              <td><input v-model="c.obligatorio" type="checkbox" :aria-label="t('Required')" /></td>
              <td><input v-model="c.indexado" type="checkbox" :aria-label="t('Indexed')" :title="t('Speeds up filters and reports on this field')" /></td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="datos.campos_propios[entidadCampos].splice(i, 1)"><Icono nombre="basura" :tam="16" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Statuses') }}</h2><p>{{ t('How each status of your documents reads, its color and its place in filters. The system keeps deciding with the fixed code.') }}</p></div></div>
      <div class="pestanas-pildora" role="tablist">
        <button v-for="d in o.documentos_estados" :key="d.clave" type="button" role="tab" class="pildora" :aria-selected="documentoEstados === d.clave" @click="documentoEstados = d.clave">{{ tx(d.texto) }}</button>
      </div>
      <div class="tabla-marco tabla-captura">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Code') }}</th><th>{{ t('Standard name') }}</th><th>{{ t('Your name') }}</th><th>{{ t('Color') }}</th><th>{{ t('Preview') }}</th><th>{{ t('Order') }}</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in datos.estados[documentoEstados]" :key="e.codigo">
              <td class="codigo">{{ e.codigo }}</td>
              <td>{{ estadoFabrica(e.codigo, documentoEstados)[0] }}</td>
              <td><input v-model="e.etiqueta" class="entrada" maxlength="60" :placeholder="estadoFabrica(e.codigo, documentoEstados)[0]" :aria-label="t('Your name')" /></td>
              <td><Seleccion v-model="e.tono" class="entrada" :aria-label="t('Color')"><option value="">{{ t('Standard') }}</option><option v-for="x in o.tonos" :key="x" :value="x">{{ TONOS[x] }}</option></Seleccion></td>
              <td><span class="estado" :class="`estado-${e.tono || estadoFabrica(e.codigo, documentoEstados)[1]}`"><span class="estado-marca" aria-hidden="true"></span>{{ tx(e.etiqueta || estadoFabrica(e.codigo, documentoEstados)[0]) }}</span></td>
              <td class="fila-flex">
                <button type="button" class="btn-icono" :aria-label="t('Move up')" :disabled="i === 0" @click="moverEstado(i, -1)"><Icono nombre="arriba" :tam="16" /></button>
                <button type="button" class="btn-icono" :aria-label="t('Move down')" :disabled="i === datos.estados[documentoEstados].length - 1" @click="moverEstado(i, 1)"><Icono nombre="abajo" :tam="16" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Terminology') }}</h2><p>{{ t('Replace any text of the system with the words your company uses, in each language. Write the original text as it appears in English; it applies to screens and documents (reload to see it everywhere).') }}</p></div>
        <button type="button" class="btn btn-chico" @click="terminos.push({ original: '', es: '', en: '' })"><Icono nombre="mas" :tam="14" />{{ t('Add text') }}</button></div>
      <p v-if="!terminos.length" class="ayuda">{{ t('No own texts: the system uses its standard terminology.') }}</p>
      <div v-else class="tabla-marco tabla-captura">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Original text (English)') }}</th><th>{{ t('Spanish') }}</th><th>{{ t('English') }}</th><th /></tr></thead>
          <tbody>
            <tr v-for="(f, i) in terminos" :key="i">
              <td><input v-model="f.original" class="entrada" maxlength="600" :placeholder="t('e.g. Purchase order')" :aria-label="t('Original text (English)')" /></td>
              <td><input v-model="f.es" class="entrada" maxlength="600" :placeholder="f.original ? t(f.original) : ''" :aria-label="t('Spanish')" /></td>
              <td><input v-model="f.en" class="entrada" maxlength="600" :placeholder="f.original" :aria-label="t('English')" /></td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="terminos.splice(i, 1)"><Icono nombre="basura" :tam="16" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Purchase order approval') }}</h2><p>{{ t('Who approves a PO before it can be invoiced. Every rule whose minimum amount the PO reaches (in its currency and, if set, for its company) adds an approval step, from the lowest to the highest amount. With no rule, a PO is approved when it is sent.') }}</p></div>
        <button type="button" class="btn btn-chico" @click="nuevaRegla"><Icono nombre="mas" :tam="14" />{{ t('Add rule') }}</button></div>
      <p v-if="!datos.aprobaciones_oc.length" class="ayuda">{{ t('No approval rules: POs are approved when they are sent.') }}</p>
      <div v-else class="tabla-marco tabla-captura">
        <table class="tabla" v-tarjetas>
          <thead><tr><th>{{ t('Name') }}</th><th class="num">{{ t('From amount') }}</th><th>{{ t('Currency') }}</th><th>{{ t('Company') }}</th><th>{{ t('Approved by role') }}</th><th /></tr></thead>
          <tbody>
            <tr v-for="(r, i) in datos.aprobaciones_oc" :key="i">
              <td><input v-model="r.nombre" class="entrada" maxlength="80" :placeholder="t('e.g. Purchasing manager')" :aria-label="t('Name')" /></td>
              <td><input v-model.number="r.monto_minimo" class="entrada regla-monto" type="number" min="0" step="any" :aria-label="t('From amount')" /></td>
              <td><SelectBusqueda v-model="r.moneda" :opciones="MONEDAS" :prefijo="false" :etiqueta="t('Currency')" /></td>
              <td><SelectBusqueda v-model="r.sociedad" :opciones="sociedades" :vacio="t('All')" :prefijo="false" :etiqueta="t('Company')" /></td>
              <td><SelectBusqueda v-model="r.rol_id" :opciones="roles" :prefijo="false" :etiqueta="t('Approved by role')" /></td>
              <td><button type="button" class="btn-icono" :aria-label="t('Remove')" @click="datos.aprobaciones_oc.splice(i, 1)"><Icono nombre="basura" :tam="16" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Required PO data') }}</h2><p>{{ t('Besides supplier, number, company, items, quantities, currency, prices and ship date, which are always required, choose what else a PO needs before it can be sent.') }}</p></div></div>
      <div class="regla-lista obligatorios">
        <label v-for="c in o.campos_obligables" :key="c.clave" class="check">
          <input v-model="datos.obligatorios.orden" type="checkbox" :value="c.clave" />{{ tx(c.texto) }}
        </label>
      </div>
    </section>

    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Business rules') }}</h2><p>{{ t('How your company works. They apply to everyone in it right after saving.') }}</p></div></div>
      <ul class="lista-reglas">
        <li v-for="r in o.reglas" :key="r.clave">
          <span>{{ tx(REGLAS[r.clave] || r.texto) }}</span>
          <div v-if="Array.isArray(r.valor)" class="regla-lista">
            <label v-for="c in o.campos_compatibilidad" :key="c.clave" class="check">
              <input type="checkbox" :checked="datos.reglas[r.clave].includes(c.clave)"
                     @change="datos.reglas[r.clave] = datos.reglas[r.clave].includes(c.clave) ? datos.reglas[r.clave].filter((x) => x !== c.clave) : [...datos.reglas[r.clave], c.clave]" />{{ tx(c.texto) }}
            </label>
          </div>
          <Interruptor v-else-if="typeof r.valor === 'boolean'" v-model="datos.reglas[r.clave]" :etiqueta="tx(REGLAS[r.clave] || r.texto)" />
          <input v-else-if="typeof r.valor === 'number'" v-model.number="datos.reglas[r.clave]" type="number" min="0" max="365" class="entrada regla-numero"
                 :aria-label="tx(REGLAS[r.clave] || r.texto)" />
          <SelectBusqueda v-else v-model="datos.reglas[r.clave]" class="regla-pais" :opciones="paises" :prefijo="false" :etiqueta="tx(REGLAS[r.clave] || r.texto)" />
        </li>
      </ul>
    </section>
  </template>
</template>

<style scoped>
.paletas { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
.paleta { display: flex; flex-direction: column; gap: 4px; text-align: start; padding: 10px; border: 1px solid var(--linea); border-radius: var(--radio-panel);
  background: var(--superficie); cursor: pointer; color: inherit; transition: border-color 0.12s, box-shadow 0.12s; }
.paleta:hover { border-color: var(--borde-hover); }
.paleta[aria-checked='true'] { border-color: var(--acento); box-shadow: 0 0 0 3px var(--foco); }
.paleta small { color: var(--tinta-3); font-size: var(--t-xs); line-height: 1.35; }
.paleta-muestra { display: grid; grid-template-columns: 34% 1fr; height: 58px; border-radius: 8px; overflow: hidden; border: 1px solid var(--linea); margin-bottom: 4px; }
.paleta-lateral { display: flex; flex-direction: column; gap: 5px; padding: 8px 6px; }
.paleta-lateral.borde { border-inline-end: 1px solid #e4e7ec; }
.paleta-lateral i { display: block; height: 5px; border-radius: 3px; background: rgba(128, 128, 128, 0.35); }
.paleta-lateral i:first-child { width: 70%; }
.paleta-cuerpo { display: flex; flex-direction: column; gap: 5px; padding: 8px; background: #f6f7f9; }
.paleta-cuerpo i { display: block; height: 6px; border-radius: 3px; background: #dfe3ea; }
.paleta-cuerpo i:first-child { width: 42%; height: 10px; }
.panel + .panel { margin-top: 16px; }
.empresa-general { display: grid; grid-template-columns: 180px 1fr; gap: 24px; align-items: start; }
.empresa-logo { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.empresa-logo img, .empresa-logo-vacio { width: 120px; height: 120px; border-radius: var(--radio-panel); border: 1px solid var(--linea); object-fit: contain; background: var(--superficie-2); }
.empresa-logo-vacio { display: grid; place-items: center; color: var(--tinta-3); }
.lista-reglas { list-style: none; margin: 0; padding: 0; }
.lista-reglas li { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--linea-suave); }
.lista-reglas li:last-child { border-bottom: 0; }
.regla-numero { width: 90px; flex: none; }
@media (max-width: 720px) { .empresa-general { grid-template-columns: 1fr; } }
.regla-pais { min-width: 220px; }
.campo.ancho { grid-column: 1 / -1; }
input[type='color'] { width: 42px; height: 36px; padding: 2px; border: 1px solid var(--linea); border-radius: var(--radio, 8px); background: var(--superficie); }
.regla-lista { display: flex; flex-wrap: wrap; gap: 4px 14px; justify-content: flex-end; max-width: 520px; }
.regla-lista.obligatorios { justify-content: flex-start; max-width: none; gap: 8px 20px; }
.regla-monto { width: 120px; text-align: end; }
</style>
