<script setup>
import { alCambiar } from '@/nucleo/cambios.js'
import { t, tx } from '@/i18n/index.js'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'
import Modal from '@/componentes/Modal.vue'
import Seleccion from '@/componentes/Seleccion.vue'
import { confirmar } from '@/stores/confirmar'
import { puede } from '@/stores/sesion'
import { avisar, errorApi } from '@/stores/ui'
import EfectoCambio from '@/modulos/etiquetado/componentes/EfectoCambio.vue'
import SelectorDiseno from '@/modulos/etiquetado/componentes/SelectorDiseno.vue'
import { textoExcepcion, textoPorque } from '@/modulos/etiquetado/etiquetas.js'

// La pestaña Etiquetas del producto: su familia de etiquetado, qué diseño
// lleva en cada tipo de etiqueta y por qué, las excepciones que pueden
// cambiarlo y las tallas con diseño propio. Desde aquí se le pone un diseño
// propio (a todo el producto o a algunas tallas) y se imprimen sus etiquetas.
const props = defineProps({ productoId: { type: Number, required: true } })
const datos = ref(null)
const cargando = ref(false)
const configurable = computed(() => puede('etiquetas.configurar'))

async function cargar() {
  cargando.value = true
  try {
    datos.value = await api.get(`/etiquetas/productos/${props.productoId}`)
  } catch (e) {
    errorApi(e)
  } finally {
    cargando.value = false
  }
}
onMounted(cargar)
alCambiar(() => cargar(), ['/etiquetas/usos', '/etiquetas/familias', '/etiquetas/productos'])
const miniatura = (e) => (e?.version_id ? `/api/etiquetas/versiones/${e.version_id}/miniatura.svg` : null)
const ORIGEN = () => ({ PRODUCTO: t('of the product'), GRUPO: t('by its item group') })

// Cambiar la familia del producto (la heredan sus tallas sin familia propia)
const familias = ref([])
const cambioFamilia = ref(null)
async function abrirFamilia() {
  if (!familias.value.length) familias.value = await api.get('/etiquetas/familias', { activas: true }).catch(() => [])
  cambioFamilia.value = { familia_id: datos.value.familia?.origen === 'PRODUCTO' ? datos.value.familia.id : '' }
}
async function guardarFamilia() {
  try {
    await api.post('/etiquetas/productos/familia', { familia_id: cambioFamilia.value.familia_id ? Number(cambioFamilia.value.familia_id) : null, ids: [props.productoId] })
    avisar(t('Labeling family of the product changed.'))
    cambioFamilia.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

// Diseño propio: para todo el producto o solo para algunas tallas
const propio = ref(null)
const formPropio = ref(null)
function abrirPropio(x) {
  propio.value = { tipo: x.tipo, plantilla_id: x.propio?.plantilla_id || '', tallas: [], cambia: !!x.propio }
  nextTick(() => formPropio.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
}
const efecto = ref(null)
const simulando = ref(false)
let espera
watch(() => propio.value && [propio.value.plantilla_id, propio.value.tallas.length], () => {
  clearTimeout(espera)
  efecto.value = null
  const x = propio.value
  if (!x?.plantilla_id || x.tallas.length) return
  simulando.value = true
  espera = setTimeout(async () => {
    efecto.value = await api.post('/etiquetas/usos/simular', { tipo_etiqueta_id: x.tipo.id, nivel: 'PRODUCTO', destino_id: props.productoId,
      normal: { plantilla_id: Number(x.plantilla_id) } }).catch(() => null)
    simulando.value = false
  }, 400)
})
async function guardarPropio() {
  const x = propio.value
  try {
    const base = { tipo_etiqueta_id: x.tipo.id, plantilla_id: Number(x.plantilla_id), contexto_tipo: 'NINGUNO', reemplazar: true }
    if (x.tallas.length) {
      for (const id of x.tallas) await api.post('/etiquetas/usos', { ...base, nivel: 'SKU', destino_id: id })
    } else await api.post('/etiquetas/usos', { ...base, nivel: 'PRODUCTO', destino_id: props.productoId })
    avisar(t('Saved. The next labels of this product use this design.'))
    propio.value = null
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
async function heredar(usoId, texto) {
  if (!(await confirmar(texto, { titulo: t('Inherit again'), boton: t('Inherit again') }))) return
  try {
    await api.post(`/etiquetas/usos/${usoId}/baja`, { motivo: t('Back to the design of its family') })
    cargar()
  } catch (e) {
    errorApi(e)
  }
}
const imprimir = computed(() => ({ path: '/etiquetas/trabajos/nuevo', query: { origen: 'ARTICULOS', articulos: (datos.value?.articulos || []).map((a) => a.id).join(',') } }))
</script>

<template>
  <div v-if="cargando && !datos" class="vacio">{{ t('Loading…') }}</div>
  <div v-else-if="datos" class="ep">
    <div class="ep-cabeza">
      <h3>{{ t('Labels of this product') }}</h3>
      <span class="ep-familia">{{ t('Labeling family') }}:
        <strong v-if="datos.familia">{{ tx(datos.familia.nombre) }}</strong><span v-else class="etiqueta aviso ms-0">{{ t('Without family') }}</span>
        <span v-if="datos.familia" class="ayuda">({{ ORIGEN()[datos.familia.origen] }})</span>
        <button v-if="puede('etiquetas.familias')" type="button" class="btn btn-chico" @click="abrirFamilia">{{ t('Change family') }}</button></span>
    </div>

    <!-- Diseño propio: en la página, encima de las tarjetas (no en una ventana) -->
    <section v-if="propio" ref="formPropio" class="panel en-linea">
      <div class="en-linea-cabeza"><h3>{{ t('Design of “{0}” for this product', [tx(propio.tipo.nombre)]) }}</h3>
        <button type="button" class="btn-icono" :aria-label="t('Close')" @click="propio = null"><Icono nombre="cerrar" :tam="16" /></button></div>
      <div class="ep-form">
        <SelectorDiseno v-model="propio.plantilla_id" :tipo-id="propio.tipo.id" />
        <fieldset v-if="datos.articulos.length > 1" class="ep-solo">
          <legend>{{ t('Only for these sizes (empty: the whole product)') }}</legend>
          <label v-for="a in datos.articulos" :key="a.id" class="check"><input v-model="propio.tallas" type="checkbox" :value="a.id" /> {{ a.talla || a.sku }}</label>
        </fieldset>
        <EfectoCambio v-if="!propio.tallas.length" :efecto="efecto" :cargando="simulando" :sin-cambios="!propio.plantilla_id" />
        <p v-else class="ayuda">{{ t('{0} sizes get this design; the rest keep the one of the product.', [propio.tallas.length]) }}</p>
      </div>
      <div class="en-linea-pie">
        <button type="button" class="btn" @click="propio = null">{{ t('Cancel') }}</button>
        <button type="button" class="btn btn-primario" :disabled="!propio.plantilla_id" @click="guardarPropio">{{ t('Save') }}</button>
      </div>
    </section>

    <div class="ep-tarjetas">
      <article v-for="x in datos.tipos" :key="x.tipo.id" class="ep-tarjeta panel" :class="{ editando: propio?.tipo.id === x.tipo.id }">
        <h4>{{ tx(x.tipo.nombre) }}</h4>
        <div class="ep-diseno">
          <div class="ep-mini"><img v-if="miniatura(x.eleccion)" :src="miniatura(x.eleccion)" :alt="t('Preview of {0}', [x.eleccion.plantilla])" /></div>
          <div>
            <strong v-if="x.eleccion?.plantilla">{{ tx(x.eleccion.plantilla) }}</strong>
            <span v-else class="etiqueta aviso ms-0">{{ x.tipo.obligatoria ? t('No design (required)') : t('No design') }}</span>
            <p class="ayuda">{{ x.propio ? t('Own design of this product') : t('By: {0}', [textoPorque(x.eleccion)]) }}</p>
            <span v-if="x.eleccion?.plantilla && !x.eleccion.aprobada" class="etiqueta aviso ms-0">{{ t('Not approved yet') }}</span>
          </div>
        </div>
        <ul v-if="x.excepciones.length" class="ep-excepciones">
          <li v-for="u in x.excepciones" :key="u.id">{{ t('Exception') }}: {{ textoExcepcion(u) }} → {{ tx(u.plantilla) }}</li>
        </ul>
        <p v-if="x.tallas.length" class="ayuda">{{ t('Sizes with their own design') }}:</p>
        <ul v-if="x.tallas.length" class="ep-tallas">
          <li v-for="s in x.tallas" :key="s.uso_id">{{ s.talla || s.sku }} → {{ tx(s.plantilla) }}
            <button v-if="configurable" type="button" class="btn btn-chico btn-texto" @click="heredar(s.uso_id, t('Size {0} goes back to the design of the product.', [s.talla || s.sku]))">{{ t('Inherit again') }}</button></li>
        </ul>
        <div v-if="configurable" class="ep-acciones">
          <button type="button" class="btn btn-chico" @click="abrirPropio(x)">{{ x.propio ? t('Change') : t('Use another design for this product') }}</button>
          <button v-if="x.propio" type="button" class="btn btn-chico btn-texto" @click="heredar(x.propio.id, t('The product goes back to the design of its family.'))">{{ t('Inherit again') }}</button>
        </div>
      </article>
    </div>
    <p v-if="!datos.tipos.length" class="ayuda">{{ t('There are no label types for items yet.') }}
      <router-link to="/etiquetas/configuracion?paso=tipos" class="enlace">{{ t('Set them up') }}</router-link></p>

    <div class="ep-pie">
      <router-link v-if="puede('etiquetas.generar') && datos.articulos.length" :to="imprimir" class="btn btn-primario"><Icono nombre="etiqueta" :tam="16" />{{ t('Print labels of this product') }}</router-link>
      <router-link :to="{ path: '/etiquetas/configuracion', query: { paso: 'revisar' } }" class="btn btn-chico btn-texto"><Icono nombre="historial" :tam="15" />{{ t('Generated labels') }}</router-link>
    </div>
  </div>

  <Modal v-if="cambioFamilia" :titulo="t('Labeling family of the product')" @cerrar="cambioFamilia = null">
    <label class="campo"><span>{{ t('Family') }}</span>
      <Seleccion v-model="cambioFamilia.familia_id">
        <option value="">{{ t('None of its own (it uses the one of its item group)') }}</option>
        <option v-for="f in familias" :key="f.id" :value="f.id">{{ tx(f.ruta || f.nombre) }}</option></Seleccion></label>
    <p class="ayuda mt">{{ t('All its sizes inherit it, except the ones with a family of their own.') }}</p>
    <template #pie>
      <button type="button" class="btn separar" @click="cambioFamilia = null">{{ t('Cancel') }}</button>
      <button type="button" class="btn btn-primario" @click="guardarFamilia">{{ t('Save') }}</button>
    </template>
  </Modal>

</template>

<style scoped>
.ep { display: flex; flex-direction: column; gap: 14px; }
.ep-cabeza { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.ep-cabeza h3 { margin: 0; }
.ep-familia { display: inline-flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.ep-tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.ep-tarjeta { display: flex; flex-direction: column; gap: 8px; }
.ep-tarjeta h4 { margin: 0; }
.ep-diseno { display: flex; gap: 12px; align-items: flex-start; }
.ep-diseno p { margin: 4px 0; }
.ep-mini { width: 96px; height: 72px; flex: none; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid var(--linea); border-radius: 8px; padding: 4px; background: var(--superficie-2); }
.ep-mini img { max-width: 100%; max-height: 100%; object-fit: contain; background: #fff; }
.ep-excepciones, .ep-tallas { margin: 0; padding-inline-start: 18px; font-size: 0.86rem; display: flex; flex-direction: column; gap: 2px; }
.ep-acciones, .ep-pie { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.ep-tarjeta.editando { border-color: var(--acento); }
.ep-form { display: flex; flex-direction: column; gap: 12px; }
.ep-solo { border: 1px solid var(--linea); border-radius: 8px; padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 6px 14px; }
</style>
