<script setup>
import { IDIOMAS, cambiarIdioma, idioma, t } from '../i18n/index.js'
import Icono from './Icono.vue'
import SelectBusqueda from './SelectBusqueda.vue'
import { guardarPerfil, sesion } from '../stores/sesion'
import { errorApi } from '../stores/ui'

// Idioma de la interfaz, cada uno con su nombre en su propio idioma. Usa la
// misma lista desplegable del sistema, así respeta el tema claro u oscuro.
// Con sesión, el idioma se guarda en el perfil (y se recarga la página).
const opciones = IDIOMAS.map((x) => ({ valor: x.codigo, texto: x.nombre }))
function elegir(codigo) {
  if (!codigo || codigo === idioma) return
  if (sesion.usuario) guardarPerfil({ idioma: codigo }).catch(errorApi)
  else cambiarIdioma(codigo)
}
</script>

<template>
  <div class="idioma" :title="t('Language')">
    <Icono nombre="globo" :tam="16" />
    <SelectBusqueda class="idioma-sb" :model-value="idioma" :opciones="opciones" :busqueda="false" :prefijo="false"
                    :etiqueta="t('Language')" @update:model-value="elegir" />
  </div>
</template>

<style scoped>
.idioma { display: inline-flex; align-items: center; gap: 2px; padding-inline-start: 9px; height: 36px; border: 1px solid var(--linea);
  border-radius: var(--radio); background: var(--superficie); color: var(--tinta-2); transition: border-color 0.15s, background 0.15s; }
.idioma:hover { border-color: var(--acento-medio, var(--acento)); }
.idioma:focus-within { border-color: var(--acento); box-shadow: 0 0 0 3px var(--foco); }
.idioma :deep(.sb) { width: auto; min-width: 0; }
.idioma :deep(.sb-boton), .idioma :deep(.sb.abierto .sb-boton) { border: 0 !important; background: transparent; box-shadow: none !important; min-height: 34px; padding-inline: 6px 8px; font-weight: 620; color: var(--tinta); }
.idioma :deep(.sb-boton:focus-visible) { outline: none; }
</style>
