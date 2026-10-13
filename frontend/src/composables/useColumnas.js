import { computed } from 'vue'
import { api } from '@/nucleo/api'
import { sesion, ve } from '@/stores/sesion'

// Columnas de una tabla: las que el rol permite (sin los grupos de datos
// ocultos) y, de esas, las que la persona eligió ver. Sin elección, la vista
// inicial corta (las columnas con `inicial: false` quedan para «Columnas»).
//   defs: [{ clave, texto, grupo, fija, inicial }]
//   grupo: grupo de datos (precios, codigos_internos, fechas_internas…)
//   fija: siempre visible (no aparece en el selector)
export function useColumnas(tabla, defs) {
  const lista = () => (typeof defs === 'function' ? defs() : defs)
  const permitidas = computed(() => lista().filter((c) => !c.grupo || ve(c.grupo)))
  const elegidas = computed(() => sesion.usuario?.preferencias?.columnas?.[tabla] || null)
  const visibles = computed(() => new Set(permitidas.value
    .filter((c) => c.fija || (elegidas.value ? elegidas.value.includes(c.clave) : c.inicial !== false))
    .map((c) => c.clave)))
  const ver = (clave) => visibles.value.has(clave)
  // Columnas que el rol permite (para mostrar u ocultar filtros y datos sueltos)
  const permitida = (clave) => permitidas.value.some((c) => c.clave === clave)

  async function guardar(claves) {
    const r = await api.put(`/perfil/columnas/${tabla}`, { columnas: claves })
    sesion.usuario.preferencias = { ...(sesion.usuario.preferencias || {}), columnas: r.columnas }
  }
  return { tabla, permitidas, visibles, ver, permitida, guardar, cuantas: computed(() => visibles.value.size) }
}
