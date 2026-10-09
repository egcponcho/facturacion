<script setup>
import { t } from '@/i18n/index.js'
import { api } from '@/nucleo/api'
import { puede } from '@/stores/sesion'
import { errorApi } from '@/stores/ui'
import { fmtFechaHora } from '@/nucleo/utils'
import Icono from './Icono.vue'

// Aviso de edición exclusiva: quién edita el documento (los demás lo ven en
// solo lectura) o que la edición propia se pausó por inactividad.
const props = defineProps({
  edicion: { type: Object, default: null },
  pausado: { type: Boolean, default: false },
  entidad: { type: String, required: true },
  id: { type: Number, required: true },
})
const emit = defineEmits(['liberado', 'continuar'])

async function liberar() {
  if (!window.confirm(t('{0} will lose any changes they have not saved. Release it?', [props.edicion.usuario]))) return
  try {
    await api.del(`/edicion/${props.entidad}/${props.id}?forzar=true`)
    emit('liberado')
  } catch (e) {
    errorApi(e)
  }
}
</script>

<template>
  <div v-if="props.edicion" class="aviso-edicion" role="status">
    <Icono nombre="candado" :tam="18" />
    <span>
      <b>{{ t('{0} is editing this document', [props.edicion.usuario || t('Another user')]) }}</b>
      <span class="ayuda"> · {{ t('since {0}', [fmtFechaHora(props.edicion.desde)]) }}</span>
      <span class="sub">{{ t('You are seeing it in read-only mode. It will update by itself when they finish.') }}</span>
    </span>
    <button v-if="puede('admin')" type="button" class="btn btn-chico separar" @click="liberar">{{ t('Release editing') }}</button>
  </div>
  <div v-else-if="props.pausado" class="aviso-edicion pausado" role="status">
    <Icono nombre="reloj" :tam="18" />
    <span>
      <b>{{ t('Editing paused due to inactivity') }}</b>
      <span class="sub">{{ t('Others can edit this document now. Continue to take it back.') }}</span>
    </span>
    <button type="button" class="btn btn-chico btn-primario separar" @click="emit('continuar')">{{ t('Continue editing') }}</button>
  </div>
</template>

<style scoped>
.aviso-edicion { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px; border-radius: var(--radio-panel);
  background: var(--aviso-fondo); border: 1px solid color-mix(in srgb, var(--aviso) 35%, transparent); color: var(--tinta); }
.aviso-edicion > :deep(svg) { color: var(--aviso); flex: none; }
.aviso-edicion .sub { display: block; font-size: 0.85rem; color: var(--tinta-2); margin-top: 2px; }
.aviso-edicion.pausado { background: var(--info-fondo); border-color: color-mix(in srgb, var(--info) 35%, transparent); }
.aviso-edicion.pausado > :deep(svg) { color: var(--info); }
</style>
