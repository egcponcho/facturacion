<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { esInterno, sesion } from '../stores/sesion'
import { avisar, errorApi } from '../stores/ui'
import { fmtFechaHora } from '../utils'

const router = useRouter()
const datos = ref(null)

async function cargar() {
  try {
    datos.value = await api.get('/inicio', { proveedor_id: sesion.proveedorId })
  } catch (e) {
    errorApi(e)
  }
}

async function resolver(a) {
  try {
    await api.post(`/alertas/${a.id}/resolver`)
    avisar('Alerta marcada como resuelta.')
    cargar()
  } catch (e) {
    errorApi(e)
  }
}

onMounted(cargar)
watch(() => sesion.proveedorId, cargar)
</script>

<template>
  <div class="pagina-cabeza">
    <div>
      <h1>Pendientes</h1>
      <p>Lo que requiere atención ahora. Cada tarjeta abre la lista ya filtrada.</p>
    </div>
    <router-link class="btn btn-primario" to="/ordenes">Facturar desde órdenes de compra</router-link>
  </div>

  <div v-if="datos" class="tarjetas">
    <button
      v-for="t in datos.tarjetas"
      :key="t.clave"
      type="button"
      class="tarjeta"
      :class="`tono-${t.tono}`"
      @click="router.push({ path: t.ruta, query: t.query })"
    >
      <span class="valor">{{ t.valor }}</span>
      <span class="titulo">{{ t.titulo }}</span>
      <span v-if="t.ayuda" class="ayuda">{{ t.ayuda }}</span>
    </button>
  </div>

  <section v-if="esInterno() && datos" class="panel mt">
    <div class="panel-cabeza"><h2>Alertas de importación de OCs</h2></div>
    <p v-if="!datos.alertas.length" class="ayuda">No hay conflictos abiertos.</p>
    <ul v-else class="linea-tiempo">
      <li v-for="a in datos.alertas" :key="a.id">
        <span class="ayuda">{{ fmtFechaHora(a.creada_en) }}</span>
        <span class="fila-flex">{{ a.mensaje }}<button class="btn btn-chico separar" @click="resolver(a)">Marcar resuelta</button></span>
      </li>
    </ul>
  </section>
</template>
