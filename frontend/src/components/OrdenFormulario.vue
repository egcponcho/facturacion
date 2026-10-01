<script setup>
import { t, tx } from '../i18n/index.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { sesion } from '../stores/sesion'
import { avisar } from '../stores/ui'
import Icono from './Icono.vue'
import SelectBusqueda from './SelectBusqueda.vue'

// Orden de compra creada en la plataforma. Arma las mismas filas que el archivo
// de carga (una por línea con los datos de la cabecera) y el servidor las valida
// igual. Solo es obligatorio lo mínimo; lo que falta para facturar (empresa,
// moneda, precio) se puede completar después.
const router = useRouter()
const op = ref(null)
const articulos = ref([])
const errores = ref([])
const ocupado = ref(false)
const masDatos = ref(false)
const cab = reactive({
  proveedor: '', oc: '', sociedad: '', centro: '', centro_destino: '', moneda: '', incoterm: '', fecha_oc: '',
  puerto_despacho: '', pais_origen: '', fecha_xf: '', fecha_tienda: '', liberacion_comercial: 'C', liberacion_logistica: '',
})
const nuevaLinea = () => ({ codigo_sap: '', cantidad: '', precio: '', casepack: '', almacen: '' })
const lineas = ref([nuevaLinea()])

onMounted(async () => {
  op.value = await api.get('/ordenes/formulario')
  if (op.value.proveedores.length === 1) cab.proveedor = op.value.proveedores[0].valor
})
watch(() => cab.proveedor, async (p) => {
  articulos.value = p ? await api.get('/ordenes/formulario/articulos', { proveedor: p }) : []
})
// Solo lo coherente con el proveedor: sus sociedades y, de ellas, centros y almacenes
const socsProveedor = computed(() => op.value?.proveedores.find((p) => p.valor === cab.proveedor)?.sociedades || [])
const sociedades = computed(() => (op.value?.sociedades || []).filter((x) => socsProveedor.value.includes(x.valor)))
const permitida = (soc) => (cab.sociedad ? soc === cab.sociedad : socsProveedor.value.includes(soc))
const centros = computed(() => (op.value?.centros || []).filter((c) => permitida(c.sociedad)))
const almacenes = computed(() => (op.value?.almacenes || []).filter((a) => permitida(a.sociedad)))
watch(() => cab.proveedor, () => {
  if (cab.sociedad && !socsProveedor.value.includes(cab.sociedad)) cab.sociedad = ''
  if (sociedades.value.length === 1) cab.sociedad = sociedades.value[0].valor
})
watch(() => cab.sociedad, () => {
  for (const k of ['centro', 'centro_destino']) if (cab[k] && !centros.value.some((c) => c.valor === cab[k])) cab[k] = ''
  lineas.value.forEach((l) => { if (l.almacen && !almacenes.value.some((a) => a.valor === l.almacen)) l.almacen = '' })
})
const artDe = (sku) => articulos.value.find((a) => a.valor === sku)
const esPrepack = (l) => artDe(l.codigo_sap)?.tipo === 'PREPACK'
const unidadTxt = (l) => ({ PAR: t('pairs'), UN: t('units'), CJ: t('prepack cartons') }[artDe(l.codigo_sap)?.unidad] || '')
const valor = computed(() => {
  const conPrecio = lineas.value.filter((l) => l.cantidad && l.precio !== '')
  return conPrecio.length ? conPrecio.reduce((a, l) => a + Number(l.cantidad) * Number(l.precio), 0) : null
})
const errorDe = (i) => errores.value.filter((e) => e.campo === `lineas.${i}`).map((e) => e.mensaje)
const erroresCab = computed(() => errores.value.filter((e) => !String(e.campo || '').startsWith('lineas.')).map((e) => e.mensaje))

async function guardar() {
  errores.value = []
  ocupado.value = true
  try {
    const r = await api.post('/ordenes', {
      cabecera: { ...cab },
      lineas: lineas.value.map((l) => (esPrepack(l) ? { ...l, casepack: '' } : l)),
    })
    avisar(t('Purchase order {0} created with {1} lines.', [r.numero, r.lineas]))
    router.push({ path: '/ordenes', query: { q: r.numero } })
  } catch (e) {
    errores.value = e.detalle?.length ? e.detalle : [{ campo: 'cabecera', mensaje: e.message }]
  } finally {
    ocupado.value = false
  }
}
</script>

<template>
  <form class="orden-form" @submit.prevent="guardar">
    <section class="panel">
      <div class="panel-cabeza"><div><h2>{{ t('Header') }}</h2><p>{{ t('Required: supplier, PO number, and on each line the item and quantity. Company, currency and price can be completed later; they are needed to invoice.') }}</p></div></div>
      <div class="rejilla-campos">
        <div v-if="!sesion.proveedorId" class="campo"><span class="req">{{ t('Supplier') }}</span>
          <SelectBusqueda v-model="cab.proveedor" :opciones="op?.proveedores || []" :etiqueta="t('Supplier')" requerido /></div>
        <label class="campo"><span class="req">{{ t('PO number') }}</span><input v-model="cab.oc" class="entrada" maxlength="40" required /></label>
        <div class="campo"><span>{{ t('Company (bill to)') }}</span>
          <SelectBusqueda v-model="cab.sociedad" :opciones="sociedades" :vacio="t('Not defined')" :etiqueta="t('Company (bill to)')" /></div>
        <p v-if="cab.proveedor && !sociedades.length" class="nota aviso bloque campo-ancho">{{ t('This supplier has no companies assigned. Assign them in Master data → Suppliers.') }}</p>
        <div class="campo"><span>{{ t('Destination plant') }}</span>
          <SelectBusqueda v-model="cab.centro_destino" :opciones="centros" :vacio="t('Not defined')" :etiqueta="t('Destination plant')" /></div>
        <div class="campo"><span>{{ t('Currency') }}</span>
          <SelectBusqueda v-model="cab.moneda" :opciones="op?.monedas || []" :vacio="t('Not defined')" :etiqueta="t('Currency')" /></div>
        <label class="campo"><span>{{ t('XF date') }}</span><input v-model="cab.fecha_xf" class="entrada" type="date" /></label>
      </div>
      <button type="button" class="btn-texto mt-chico" :aria-expanded="masDatos" @click="masDatos = !masDatos">
        <Icono :nombre="masDatos ? 'abajo' : 'derecha'" :tam="14" />{{ tx(masDatos ? t('Fewer details') : t('More details (optional)')) }}
      </button>
      <div v-if="masDatos" class="rejilla-campos mt-chico">
        <div class="campo"><span>{{ t('Receiving plant') }}</span>
          <SelectBusqueda v-model="cab.centro" :opciones="centros" :vacio="t('Not defined')" :etiqueta="t('Receiving plant')" /></div>
        <div class="campo"><span>{{ t('Incoterm') }}</span>
          <SelectBusqueda v-model="cab.incoterm" :opciones="op?.incoterms || []" :vacio="t('Not defined')" :etiqueta="t('Incoterm')" /></div>
        <label class="campo"><span>{{ t('PO date') }}</span><input v-model="cab.fecha_oc" class="entrada" type="date" /></label>
        <div class="campo"><span>{{ t('Port of loading') }}</span>
          <SelectBusqueda v-model="cab.puerto_despacho" :opciones="op?.puertos || []" :vacio="t('Not defined')" :etiqueta="t('Port of loading')" /></div>
        <div class="campo"><span>{{ t('Country of origin') }}</span>
          <SelectBusqueda v-model="cab.pais_origen" :opciones="op?.paises || []" :vacio="t('Not defined')" :etiqueta="t('Country of origin')" /></div>
        <label class="campo"><span>{{ t('In-store date') }}</span><input v-model="cab.fecha_tienda" class="entrada" type="date" /></label>
        <label class="campo"><span>{{ t('Commercial release') }}</span>
          <select v-model="cab.liberacion_comercial" class="entrada"><option value="C">{{ t('Released') }}</option><option value="P">{{ t('Pending') }}</option></select></label>
        <label class="campo"><span>{{ t('Logistics release') }}</span>
          <select v-model="cab.liberacion_logistica" class="entrada"><option value="">{{ t('Automatic') }}</option><option value="300">{{ t('Released') }}</option><option value="304">{{ t('Not released') }}</option></select></label>
      </div>
      <div v-if="erroresCab.length" class="nota error bloque mt-chico"><ul class="lista-mensajes"><li v-for="(e, i) in erroresCab" :key="i">{{ tx(e) }}</li></ul></div>
    </section>

    <section class="panel">
      <div class="panel-cabeza">
        <div><h2>{{ t('Lines') }}</h2><p>{{ t('Solids may bring their casepack (exact quantity per carton); a prepack brings its size run. The inner pack is defined later, in the packing list.') }}</p></div>
        <span v-if="valor !== null" class="etiqueta">{{ t('Value') }} {{ tx(valor.toFixed(2)) }} {{ tx(cab.moneda) }}</span>
      </div>
      <p v-if="!cab.proveedor" class="ayuda">{{ t('Choose the supplier to see its items.') }}</p>
      <div v-else class="lineas-oc">
        <div v-for="(l, i) in lineas" :key="i" class="linea-oc" :class="{ invalida: errorDe(i).length }">
          <div class="campo campo-ancho"><span class="req">{{ t('Item') }}</span>
            <SelectBusqueda v-model="l.codigo_sap" :opciones="articulos" :etiqueta="t('Item')" requerido /></div>
          <label class="campo"><span class="req">{{ t('Quantity') }}</span>
            <span class="con-unidad"><input v-model="l.cantidad" class="entrada" type="number" min="1" step="1" required /><small>{{ unidadTxt(l) }}</small></span></label>
          <label class="campo"><span>{{ t('Unit price') }}</span><input v-model="l.precio" class="entrada" type="number" min="0" step="any" /></label>
          <label v-if="!esPrepack(l)" class="campo"><span>{{ t('Casepack') }}</span><input v-model="l.casepack" class="entrada" type="number" min="1" step="1" :placeholder="t('Optional')" /></label>
          <div v-else class="campo"><span>{{ t('Packing') }}</span><span class="sub">{{ t('Size run of the prepack') }}</span></div>
          <div v-if="almacenes.length" class="campo"><span>{{ t('Warehouse') }}</span>
            <SelectBusqueda v-model="l.almacen" :opciones="almacenes" :vacio="t('Not defined')" :etiqueta="t('Warehouse')" /></div>
          <button type="button" class="btn-icono quitar" :disabled="lineas.length === 1" :aria-label="t('Remove line {0}', [i + 1])" @click="lineas.splice(i, 1)"><Icono nombre="cerrar" :tam="15" /></button>
          <ul v-if="errorDe(i).length" class="lista-mensajes error-linea"><li v-for="(e, j) in errorDe(i)" :key="j">{{ tx(e) }}</li></ul>
        </div>
        <button type="button" class="btn btn-chico" @click="lineas.push(nuevaLinea())"><Icono nombre="mas" :tam="14" />{{ t('Add line') }}</button>
      </div>
    </section>

    <div class="acciones-form">
      <button class="btn btn-primario" type="submit" :disabled="ocupado || !cab.proveedor"><Icono nombre="check" />{{ tx(ocupado ? t('Saving…') : t('Create purchase order')) }}</button>
    </div>
  </form>
</template>

<style scoped>
.orden-form { display: flex; flex-direction: column; gap: 16px; }
.lineas-oc { display: flex; flex-direction: column; gap: 10px; }
.linea-oc { display: grid; grid-template-columns: minmax(220px, 2.2fr) repeat(auto-fit, minmax(120px, 1fr)) auto; gap: 10px; align-items: end;
  padding: 10px; border: 1px solid var(--linea); border-radius: 10px; background: var(--superficie); }
.linea-oc.invalida { border-color: var(--error); }
.linea-oc .quitar { align-self: center; }
.error-linea { grid-column: 1 / -1; color: var(--error); margin: 0; font-size: 0.84rem; }
.con-unidad { display: flex; align-items: center; gap: 6px; }
.con-unidad small { color: var(--tinta-2); white-space: nowrap; }
.acciones-form { display: flex; justify-content: flex-end; }
@media (max-width: 720px) {
  .linea-oc { grid-template-columns: 1fr 1fr; }
  .linea-oc .campo-ancho { grid-column: 1 / -1; }
  .linea-oc .quitar { grid-column: 2; justify-self: end; }
  .acciones-form .btn { width: 100%; justify-content: center; }
}
</style>
