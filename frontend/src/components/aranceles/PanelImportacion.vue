<script setup>
import { t, tx } from '../../i18n/index.js'
import { ref } from 'vue'
import { api } from '../../api'
import CargaMasiva from '../CargaMasiva.vue'
import Icono from '../Icono.vue'
import { puede } from '../../stores/sesion'
import { errorApi } from '../../stores/ui'

// Paquetes de carga oficiales. El sistema trae la versión incluida; se puede
// descargar, completar y volver a cargar. La carga actualiza por clave natural
// y nunca borra lo publicado.
const emit = defineEmits(['cargado'])
const edita = puede('aranceles.editar')
const carga = ref(null)
const PAQUETES = [
  { n: 1, titulo: t('Official catalogs'), detalle: t('Sources, versions, countries (code schema), chapter control and domain-chapter map.'), hojas: 'Sources · Versions · Countries · Chapter_Control · Domain_Chapter_Map', carga: true },
  { n: 2, titulo: t('Dynamic engine'), detalle: t('Classification domains, attributes, options, scopes and rules.'), hojas: 'Domains · Attributes · Attribute_Options · Attribute_Scope · Classification_Rules', carga: true },
  { n: 3, titulo: t('National codes, regulations and taxes'), detalle: t('Official national codes per country and version, permits and tax rules with their legal basis.'), hojas: 'National_Codes · Regulations · Taxes', carga: false },
]
async function bajar(p) {
  try {
    await api.descargar(`/aranceles/oficial/paquete/${p.n}`, `package_${p.n}.xlsx`)
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <section class="paquetes">
    <p class="ayuda">{{ t('Official data is loaded by package. Each load updates by natural key (source, version, country, chapter, domain) and never deletes what is published; rows with errors are reported and not loaded.') }}</p>
    <article v-for="p in PAQUETES" :key="p.n" class="panel paquete">
      <span class="num">{{ String(p.n).padStart(2, '0') }}</span>
      <div class="cuerpo">
        <h3>{{ tx(p.titulo) }}</h3>
        <p>{{ tx(p.detalle) }}</p>
        <p class="ayuda codigo">{{ tx(p.hojas) }}</p>
        <p v-if="!p.carga" class="ayuda">{{ t('Its loader arrives with the national codes phase.') }}</p>
      </div>
      <div class="acciones">
        <button class="btn" @click="bajar(p)"><Icono nombre="descargar" :tam="15" />{{ t('Download package') }}</button>
        <button v-if="edita && p.carga" class="btn btn-primario" @click="carga = p"><Icono nombre="importar" :tam="15" />{{ t('Upload') }}</button>
      </div>
    </article>
    <CargaMasiva v-if="carga" :titulo="t('Upload {0}', [carga.titulo])" ruta="/aranceles/oficial/importar" :plantilla="`/aranceles/oficial/paquete/${carga.n}`"
                 :ayuda="t('Use the package Excel: the sheets it contains are loaded; the others are ignored.')"
                 @cerrar="carga = null" @cargado="emit('cargado')" />
  </section>
</template>

<style scoped>
.paquetes { display: grid; gap: 10px; }
.paquete { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: center; }
.num { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; background: var(--acento-claro); color: var(--acento-texto); font-weight: 800; }
.cuerpo h3 { margin: 0; font-size: 1rem; }
.cuerpo p { margin: 2px 0 0; }
.acciones { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
@media (max-width: 640px) { .paquete { grid-template-columns: auto 1fr; } .acciones { grid-column: 1 / -1; justify-content: flex-start; } }
</style>
