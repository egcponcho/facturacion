<script setup>
import { t, tx } from '@/i18n/index.js'
import { computed, onMounted, ref } from 'vue'
import { api } from '@/nucleo/api'
import Icono from '@/componentes/Icono.vue'

// Nueva contraseña con los requisitos a la vista: cada uno se marca cumplido o
// pendiente mientras se escribe (las reglas vienen del servidor, que las
// vuelve a comprobar al guardar). Con `repetir`, pide confirmarla.
const props = defineProps({ modelValue: { type: String, default: '' }, email: { type: String, default: '' }, repetir: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue', 'valida'])
const reglas = ref([])
const otra = ref('')
const ver = ref(false)
onMounted(async () => { reglas.value = await api.get('/auth/politica').catch(() => []) })
const PRUEBAS = {
  largo: (p) => p.length >= 10, mayuscula: (p) => /[A-Z]/.test(p), minuscula: (p) => /[a-z]/.test(p), numero: (p) => /\d/.test(p),
  simbolo: (p) => /[^A-Za-z0-9]/.test(p), usuario: (p) => !(props.email && p.toLowerCase().includes(props.email.split('@')[0].toLowerCase())),
}
const estado = computed(() => reglas.value.map((r) => ({ ...r, ok: (PRUEBAS[r.clave] || (() => true))(props.modelValue || '') })))
const coinciden = computed(() => !props.repetir || (otra.value && otra.value === props.modelValue))
const cumplidas = computed(() => estado.value.filter((r) => r.ok).length)
const valida = computed(() => estado.value.length > 0 && cumplidas.value === estado.value.length && coinciden.value)
const nivel = computed(() => (estado.value.length ? cumplidas.value / estado.value.length : 0))
const emitir = () => emit('valida', valida.value)
</script>

<template>
  <div class="clave-segura">
    <label class="campo"><span class="req">{{ t('New password') }}</span>
      <span class="con-ojo">
        <input :value="modelValue" class="entrada" :type="ver ? 'text' : 'password'" autocomplete="new-password" required
               @input="emit('update:modelValue', $event.target.value); $nextTick(emitir)" />
        <button type="button" class="btn-icono" :aria-label="ver ? t('Hide password') : t('Show password')" @click="ver = !ver"><Icono nombre="ojo" :tam="15" /></button>
      </span>
    </label>
    <div class="fuerza" :data-nivel="nivel >= 1 ? 'alta' : nivel >= 0.6 ? 'media' : 'baja'"><span :style="{ width: `${Math.round(nivel * 100)}%` }"></span></div>
    <ul class="reglas" :aria-label="t('Password requirements')">
      <li v-for="r in estado" :key="r.clave" :class="{ ok: r.ok }"><Icono :nombre="r.ok ? 'check' : 'cerrar'" :tam="13" />{{ tx(r.texto) }}</li>
    </ul>
    <label v-if="repetir" class="campo"><span class="req">{{ t('Repeat the new password') }}</span>
      <input v-model="otra" class="entrada" :type="ver ? 'text' : 'password'" autocomplete="new-password" required @input="$nextTick(emitir)" />
      <small v-if="otra && !coinciden" class="nota error relleno-chico">{{ t('The new passwords do not match.') }}</small>
    </label>
  </div>
</template>

<style scoped>
.clave-segura { display: flex; flex-direction: column; gap: 10px; }
.con-ojo { position: relative; display: flex; }
.con-ojo .entrada { width: 100%; padding-inline-end: 38px; }
.con-ojo .btn-icono { position: absolute; inset-inline-end: 4px; top: 50%; transform: translateY(-50%); }
.fuerza { height: 6px; border-radius: 99px; background: var(--superficie-2); overflow: hidden; }
.fuerza span { display: block; height: 100%; border-radius: 99px; background: var(--error); transition: width 0.2s; }
.fuerza[data-nivel='media'] span { background: var(--aviso); }
.fuerza[data-nivel='alta'] span { background: var(--ok); }
.reglas { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 4px 12px; font-size: 0.84rem; }
.reglas li { display: flex; align-items: center; gap: 6px; color: var(--tinta-3); }
.reglas li.ok { color: var(--ok); }
</style>
