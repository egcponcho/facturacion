<script setup>
import { t, tx } from '@/i18n/index.js'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import TablaDatos from '@/componentes/TablaDatos.vue'
import NavComercial from '@/modulos/comercial/componentes/NavComercial.vue'
import { opcionesLista } from '@/nucleo/listas.js'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import { fmtMoneda } from '@/nucleo/utils'
import Seleccion from '@/componentes/Seleccion.vue'
import Segmentos from '@/componentes/Segmentos.vue'

// Terceros: una identidad fiscal por persona o empresa con sus roles (cliente,
// proveedor, transportista, agente), direcciones y medios de contacto. Los
// proveedores y transportistas de los datos maestros ya son terceros.
const router = useRouter()
const tabla = ref(null)
const filtros = reactive({ rol: '', q: '' })
const datos = ref({ items: [], total: 0 })
const cargando = ref(false)
const form = ref(null)
const ocupado = ref(false)
const errores = ref([])
const cuenta = ref(null)

const ROLES = [['CLIENTE', t('Customer')], ['PROVEEDOR', t('Supplier')], ['TRANSPORTISTA', t('Carrier')], ['AGENTE', t('Agent')]]
const nombreRol = (r) => ROLES.find((x) => x[0] === r)?.[1] || r
const TIPOS_DIRECCION = [['FISCAL', t('Tax address')], ['ENTREGA', t('Delivery')], ['RECOGIDA', t('Pickup')], ['OTRA', t('Other')]]
const TIPOS_MEDIO = [['CORREO', t('Email')], ['TELEFONO', t('Phone')], ['MOVIL', t('Mobile')], ['WEB', t('Website')], ['OTRO', t('Other')]]
const columnas = [
  { clave: 'nombre', texto: t('Name'), fija: true, prioridad: 1 },
  { clave: 'codigo', texto: t('Code'), prioridad: 2 },
  { clave: 'roles', texto: t('Roles'), prioridad: 1, ordenable: false, opciones: ROLES },
  { clave: 'id_fiscal', texto: t('Tax ID'), prioridad: 2 },
  { clave: 'pais', texto: t('Country'), prioridad: 3 },
  { clave: 'moneda', texto: t('Currency'), prioridad: 3, inicial: false },
  { clave: 'correo', texto: t('Email'), prioridad: 3, ordenable: false, filtro: false },
  { clave: 'activo', texto: t('Active'), prioridad: 3, inicial: false, opciones: [[true, t('Yes')], [false, t('No')]] },
]
const externosApi = () => ({ rol: filtros.rol || undefined, q: filtros.q || undefined })
const valores = (columna, buscar, otros) => api.get('/terceros/valores', { columna, buscar, f: JSON.stringify(otros), ...externosApi() })

let ultima = null
async function consultar(c = ultima) {
  if (!c) return
  ultima = c
  cargando.value = true
  try {
    datos.value = await api.get('/terceros', { ...externosApi(), orden: c.orden, page: c.page, size: c.size,
      f: Object.keys(c.filtros).length ? JSON.stringify(c.filtros) : undefined })
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
function recargar() {
  if (tabla.value?.pagina !== 1) tabla.value.pagina = 1
  else consultar()
}
let espera
function buscar() {
  clearTimeout(espera)
  espera = setTimeout(recargar, 300)
}

const vacio = () => ({ id: null, codigo: '', tipo_persona: 'JURIDICA', nombre: '', razon_social: '', tipo_identificacion: '', id_fiscal: '',
  pais: '', moneda: '', condicion_pago: '', roles: ['CLIENTE'], direcciones: [], medios: [], activo: true })
async function abrir(fila) {
  errores.value = []
  if (!fila) {
    form.value = vacio()
    return
  }
  try {
    const x = await api.get(`/terceros/${fila.id}`)
    form.value = { ...vacio(), ...x, razon_social: x.razon_social || '', tipo_identificacion: x.tipo_identificacion || '',
      id_fiscal: x.id_fiscal || '', pais: x.pais || '', moneda: x.moneda || '', condicion_pago: x.condicion_pago || '' }
  } catch (e) {
    errorApi(e)
  }
}
async function guardar() {
  ocupado.value = true
  errores.value = []
  const f = form.value
  const cuerpo = { codigo: f.codigo || null, tipo_persona: f.tipo_persona, nombre: f.nombre, razon_social: f.razon_social || null,
    tipo_identificacion: f.tipo_identificacion || null, id_fiscal: f.id_fiscal || null, pais: f.pais || null, moneda: f.moneda || null,
    condicion_pago: f.condicion_pago || null, roles: f.roles, activo: f.activo,
    direcciones: f.direcciones.map(({ id: _id, ...d }) => ({ ...d, pais: d.pais || null })), medios: f.medios.map(({ id: _id, ...m }) => m) }
  try {
    if (f.id) await api.patch(`/terceros/${f.id}`, cuerpo)
    else await api.post('/terceros', cuerpo)
    avisar(t('Business partner saved.'))
    form.value = null
    consultar()
  } catch (e) {
    errores.value = e.detalle || []
    errorApi(e)
  } finally {
    ocupado.value = false
  }
}
async function verCuenta(fila) {
  try {
    const dir = fila.roles.includes('CLIENTE') ? 'EMITIDO' : 'RECIBIDO'
    cuenta.value = { ...(await api.get(`/terceros/${fila.id}/estado-cuenta`, { direccion: dir })), direccion: dir }
  } catch (e) {
    errorApi(e)
  }
}
const alternarRol = (r) => {
  const roles = form.value.roles
  form.value.roles = roles.includes(r) ? roles.filter((x) => x !== r) : [...roles, r]
}
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>{{ t('Business partners') }}</h1>
      <p>{{ t('Customers, suppliers, carriers and agents with a single tax identity, their addresses and contact channels.') }}</p>
    </div>
    <div v-if="puede('comercial.editar')" class="acciones">
      <button class="btn btn-primario" @click="abrir(null)"><Icono nombre="mas" />{{ t('New business partner') }}</button>
    </div>
  </div>
  <NavComercial />

  <TablaDatos ref="tabla" tabla="terceros" modo="servidor" :columnas="columnas" :filas="datos.items" :total="datos.total" :cargando="cargando"
              fila-clicable :etiqueta="t('Business partners')" :valores="valores" :externos="{ rol: filtros.rol, q: filtros.q }"
              @consulta="consultar" @fila="abrir">
    <template #barra>
      <label class="buscador">
        <Icono nombre="buscar" :tam="16" />
        <input v-model="filtros.q" type="search" :placeholder="t('Search name, code or tax ID')" :aria-label="t('Search')" @input="buscar" />
      </label>
    </template>
    <template #filtros>
      <Segmentos v-model="filtros.rol" :opciones="[['', t('All')], ...ROLES]" :etiqueta="t('Role')" @change="recargar()" />
    </template>
    <template #celda-nombre="{ fila: x }"><strong>{{ tx(x.nombre) }}</strong><span v-if="x.direccion" class="sub">{{ tx(x.direccion) }}</span></template>
    <template #celda-codigo="{ fila: x }"><span class="codigo">{{ tx(x.codigo) }}</span></template>
    <template #celda-roles="{ fila: x }"><span v-for="r in x.roles" :key="r" class="etiqueta ms-0">{{ tx(nombreRol(r)) }}</span></template>
    <template #celda-id_fiscal="{ fila: x }">{{ tx(x.id_fiscal || '—') }}</template>
    <template #celda-correo="{ fila: x }">{{ tx(x.correo || '—') }}</template>
    <template #celda-activo="{ fila: x }">{{ tx(x.activo ? t('Yes') : t('No')) }}</template>
    <template #acciones="{ fila: x }"><button class="btn btn-chico" @click.stop="verCuenta(x)">{{ t('Statement') }}</button></template>
    <template #vacio>{{ t('No business partners match these filters.') }}</template>
  </TablaDatos>

  <Modal v-if="form" :titulo="form.id ? form.nombre : t('New business partner')" ancho="820px" @cerrar="form = null">
    <div class="rejilla-formulario">
      <label class="campo"><span class="req">{{ t('Name') }}</span><input v-model="form.nombre" class="entrada" maxlength="200" /></label>
      <label class="campo"><span>{{ t('Code') }}</span><input v-model="form.codigo" class="entrada" maxlength="30" :placeholder="t('Automatic')" /></label>
      <label class="campo"><span>{{ t('Legal name') }}</span><input v-model="form.razon_social" class="entrada" maxlength="200" /></label>
      <label class="campo"><span>{{ t('Person type') }}</span>
        <Seleccion v-model="form.tipo_persona" class="entrada"><option value="JURIDICA">{{ t('Legal entity') }}</option><option value="NATURAL">{{ t('Natural person') }}</option></Seleccion>
      </label>
      <label class="campo"><span>{{ t('ID type') }}</span><input v-model="form.tipo_identificacion" class="entrada" maxlength="20" :placeholder="t('e.g. NIT, RUC, VAT')" /></label>
      <label class="campo"><span>{{ t('Tax ID') }}</span><input v-model="form.id_fiscal" class="entrada" maxlength="40" /></label>
      <label class="campo"><span>{{ t('Country') }}</span><input v-model="form.pais" class="entrada" maxlength="2" :placeholder="t('ISO, e.g. SV')" @input="form.pais = form.pais.toUpperCase()" /></label>
      <label class="campo"><span>{{ t('Default currency') }}</span>
        <Seleccion v-model="form.moneda" class="entrada"><option value="">—</option><option v-for="[c] in opcionesLista('moneda')" :key="c" :value="c">{{ c }}</option></Seleccion>
      </label>
      <label class="campo"><span>{{ t('Payment terms') }}</span>
        <Seleccion v-model="form.condicion_pago" class="entrada"><option value="">—</option><option v-for="[c, n] in opcionesLista('condicion_pago')" :key="c" :value="c">{{ tx(n) }}</option></Seleccion>
      </label>
    </div>
    <fieldset class="mt"><legend>{{ t('Roles') }}</legend>
      <label v-for="[v, txt] in ROLES" :key="v" class="casilla"><input type="checkbox" :checked="form.roles.includes(v)" @change="alternarRol(v)" />{{ tx(txt) }}</label>
    </fieldset>
    <fieldset class="mt"><legend>{{ t('Addresses') }}</legend>
      <div v-for="(d, i) in form.direcciones" :key="i" class="fila-flex mt">
        <Seleccion v-model="d.tipo" class="entrada" :aria-label="t('Type')"><option v-for="[v, txt] in TIPOS_DIRECCION" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
        <input v-model="d.linea1" class="entrada" maxlength="300" :placeholder="t('Address')" :aria-label="t('Address')" />
        <input v-model="d.ciudad" class="entrada" maxlength="100" :placeholder="t('City')" :aria-label="t('City')" />
        <input v-model="d.pais" class="entrada ancho-xs" maxlength="2" :placeholder="t('Country')" :aria-label="t('Country')" @input="d.pais = (d.pais || '').toUpperCase()" />
        <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="form.direcciones.splice(i, 1)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <button type="button" class="btn btn-chico mt" @click="form.direcciones.push({ tipo: 'FISCAL', linea1: '', ciudad: '', pais: form.pais, principal: !form.direcciones.length })"><Icono nombre="mas" :tam="14" />{{ t('Add address') }}</button>
    </fieldset>
    <fieldset class="mt"><legend>{{ t('Contact channels') }}</legend>
      <div v-for="(m, i) in form.medios" :key="i" class="fila-flex mt">
        <Seleccion v-model="m.tipo" class="entrada" :aria-label="t('Type')"><option v-for="[v, txt] in TIPOS_MEDIO" :key="v" :value="v">{{ tx(txt) }}</option></Seleccion>
        <input v-model="m.valor" class="entrada" maxlength="200" :aria-label="t('Value')" />
        <Seleccion v-model="m.uso" class="entrada" :aria-label="t('Use')"><option :value="null">{{ t('General') }}</option><option v-for="[c, n] in opcionesLista('tipo_contacto')" :key="c" :value="c">{{ tx(n) }}</option></Seleccion>
        <label class="casilla"><input v-model="m.principal" type="checkbox" />{{ t('Main') }}</label>
        <button type="button" class="btn-icono" :aria-label="t('Remove')" @click="form.medios.splice(i, 1)"><Icono nombre="basura" :tam="15" /></button>
      </div>
      <button type="button" class="btn btn-chico mt" @click="form.medios.push({ tipo: 'CORREO', valor: '', uso: null, principal: !form.medios.length })"><Icono nombre="mas" :tam="14" />{{ t('Add channel') }}</button>
    </fieldset>
    <p v-for="e in errores" :key="e.campo + e.mensaje" class="texto-error">{{ tx(e.mensaje) }}</p>
    <template #pie>
      <button class="btn" @click="form = null">{{ t('Cancel') }}</button>
      <button v-if="puede('comercial.editar')" class="btn btn-primario" :disabled="ocupado || !form.nombre.trim()" @click="guardar">{{ t('Save') }}</button>
    </template>
  </Modal>

  <Modal v-if="cuenta" :titulo="t('Statement of {0}', [cuenta.tercero.nombre])" ancho="760px" @cerrar="cuenta = null">
    <p>
      <b>{{ t('Balance') }}:</b>
      <template v-for="(v, m) in cuenta.saldo" :key="m"> {{ fmtMoneda(v, m) }}</template>
      <template v-if="!Object.keys(cuenta.saldo).length"> {{ t('nothing pending') }}</template>
    </p>
    <div v-if="cuenta.documentos.length" class="tabla-marco tabla-captura">
      <table class="tabla" v-tarjetas>
        <thead><tr><th>{{ t('Document') }}</th><th>{{ t('Due date') }}</th><th class="num">{{ t('Balance') }}</th></tr></thead>
        <tbody>
          <tr v-for="x in cuenta.documentos" :key="x.id" class="clicable" @click="router.push(`/comercial/documentos/${x.id}`)">
            <td>{{ tx(x.nombre) }} <span class="sub">{{ tx(x.tipo_nombre) }}</span></td><td>{{ x.fecha_vencimiento }}</td>
            <td class="num">{{ fmtMoneda(x.signo < 0 ? -x.saldo : x.saldo, x.moneda) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="cuenta.pagos_sin_aplicar.length" class="ayuda">{{ t('{0} payments with an amount not applied.', [cuenta.pagos_sin_aplicar.length]) }}</p>
  </Modal>
</template>

<style scoped>
.rejilla-formulario { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
fieldset { border: 1px solid var(--linea); border-radius: 10px; padding: 10px 14px; }
legend { font-weight: 600; padding: 0 6px; }
.casilla { display: inline-flex; align-items: center; gap: 6px; margin-inline-end: 16px; }
.clicable { cursor: pointer; }
</style>
